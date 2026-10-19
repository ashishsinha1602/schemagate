# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""OAuth 2.1 for the MCP server's HTTP transports: identity from a signed token, not from the client.

Without this, ``principal`` and ``roles`` are whatever the client sends, so the HTTP transport is only
safe behind something that authenticates people. With it, schemagate is an OAuth resource server in the
sense of the MCP authorization specification:

- it publishes Protected Resource Metadata (RFC 9728) naming your identity provider, so an MCP client
  can discover where to sign the user in;
- every request needs ``Authorization: Bearer <access token>``, a JWT signed by that provider. The
  signature is checked against the provider's published keys (JWKS), and so are ``iss``, ``aud``,
  ``exp`` and, when configured, the scopes. Anything else is answered 401 with the
  ``WWW-Authenticate`` header that tells the client how to get a token;
- on every tool call, ``principal`` and ``roles`` are replaced with the token's subject and role
  claim. What the client put there is discarded, so nobody can claim a role their provider did not
  give them. With a ``groups`` resolver configured, the roles come from the directory instead, as
  before.

Turned on by ``SCHEMAGATE_MCP_OAUTH_ISSUER`` (see `OAuthConfig.from_env`). PyJWT, its crypto backend
and uvicorn come with the ``mcp`` extra, so it needs nothing more.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

log = logging.getLogger("schemagate.oauth")

#: asymmetric algorithms only: "none" and the HMAC family are never accepted, so a token cannot be
#: forged with the public key as an HMAC secret (the classic key-confusion attack)
ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA"]
MAX_BODY = 4 * 1024 * 1024            # the SDK's own default request body limit
WELL_KNOWN = "/.well-known/oauth-protected-resource"


class TokenError(Exception):
    """The request's token is missing, malformed, unverifiable or lacks a required scope."""

    def __init__(self, message: str, *, status: int = 401, error: str = "invalid_token"):
        super().__init__(message)
        self.status, self.error = status, error


def _split(value: Optional[str]) -> List[str]:
    return [p for p in (value or "").replace(",", " ").split() if p]


@dataclass
class OAuthConfig:
    issuer: str
    audience: str
    resource: str
    jwks_url: Optional[str] = None
    roles_claims: List[str] = field(default_factory=lambda: ["roles", "groups"])
    subject_claim: str = "sub"
    scopes: List[str] = field(default_factory=list)
    leeway: int = 60
    #: principals are namespaced ('<source>:<id>'); a token's subject becomes '<namespace>:<sub>'
    namespace: str = "oauth"

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> Optional["OAuthConfig"]:
        """None unless ``SCHEMAGATE_MCP_OAUTH_ISSUER`` is set. Then:

        ``SCHEMAGATE_MCP_OAUTH_AUDIENCE``      required: the ``aud`` this server's tokens carry
        ``SCHEMAGATE_MCP_OAUTH_RESOURCE``      this server's public URL, e.g. https://sg.example.com/mcp
                                               (default: the audience)
        ``SCHEMAGATE_MCP_OAUTH_JWKS_URL``      default: discovered from the issuer's metadata
        ``SCHEMAGATE_MCP_OAUTH_ROLES_CLAIM``   claims holding roles, dotted paths allowed, first found
                                               wins (default ``roles groups``; Keycloak:
                                               ``realm_access.roles``)
        ``SCHEMAGATE_MCP_OAUTH_SUBJECT_CLAIM`` default ``sub``
        ``SCHEMAGATE_MCP_OAUTH_SCOPES``        scopes every token must carry (default none)
        ``SCHEMAGATE_MCP_OAUTH_NAMESPACE``     the principal is ``<namespace>:<subject>``
                                               (default ``oauth``; e.g. ``okta`` to match okta:jdoe)
        """
        env = os.environ if env is None else env
        issuer = (env.get("SCHEMAGATE_MCP_OAUTH_ISSUER") or "").strip()
        if not issuer:
            return None
        audience = (env.get("SCHEMAGATE_MCP_OAUTH_AUDIENCE") or "").strip()
        if not audience:
            raise ValueError("SCHEMAGATE_MCP_OAUTH_AUDIENCE is required with SCHEMAGATE_MCP_OAUTH_ISSUER: "
                             "without an audience check, a token your provider issued for any other "
                             "application would be accepted here")
        resource = (env.get("SCHEMAGATE_MCP_OAUTH_RESOURCE") or audience).strip()
        for name, url in (("ISSUER", issuer), ("RESOURCE", resource)):
            if not url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
                raise ValueError(f"SCHEMAGATE_MCP_OAUTH_{name} must be an https URL (got {url!r})")
        return cls(issuer=issuer, audience=audience, resource=resource,
                   jwks_url=(env.get("SCHEMAGATE_MCP_OAUTH_JWKS_URL") or "").strip() or None,
                   roles_claims=_split(env.get("SCHEMAGATE_MCP_OAUTH_ROLES_CLAIM")) or ["roles", "groups"],
                   subject_claim=(env.get("SCHEMAGATE_MCP_OAUTH_SUBJECT_CLAIM") or "sub").strip(),
                   scopes=_split(env.get("SCHEMAGATE_MCP_OAUTH_SCOPES")),
                   namespace=(env.get("SCHEMAGATE_MCP_OAUTH_NAMESPACE") or "oauth").strip().rstrip(":"))

    def metadata(self) -> Dict[str, Any]:
        """RFC 9728 Protected Resource Metadata."""
        out: Dict[str, Any] = {"resource": self.resource, "authorization_servers": [self.issuer],
                               "bearer_methods_supported": ["header"],
                               "resource_name": "schemagate"}
        if self.scopes:
            out["scopes_supported"] = list(self.scopes)
        return out

    def metadata_url(self) -> str:
        """Where `metadata` is served: the well-known path inserted before the resource's path."""
        u = urllib.parse.urlsplit(self.resource)
        return f"{u.scheme}://{u.netloc}{WELL_KNOWN}{u.path.rstrip('/')}"


def discover_jwks(issuer: str, timeout: float = 10.0) -> str:
    """The provider's ``jwks_uri``, from its OpenID or OAuth server metadata."""
    base = issuer.rstrip("/")
    errors = []
    for path in ("/.well-known/openid-configuration", "/.well-known/oauth-authorization-server"):
        try:
            with urllib.request.urlopen(base + path, timeout=timeout) as r:   # noqa: S310 (https only, checked)
                meta = json.loads(r.read().decode("utf-8"))
        except Exception as e:                                               # try the next document
            errors.append(f"{path}: {e}")
            continue
        if meta.get("issuer", "").rstrip("/") != base:
            raise ValueError(f"{base + path} names issuer {meta.get('issuer')!r}, not {issuer!r}")
        if meta.get("jwks_uri"):
            return meta["jwks_uri"]
        errors.append(f"{path}: no jwks_uri")
    raise ValueError(f"could not discover the signing keys of {issuer}: " + "; ".join(errors))


def _claim(claims: Dict[str, Any], path: str) -> Any:
    if path in claims:                                # exact first: Auth0's 'https://example.com/roles'
        return claims[path]
    cur: Any = claims
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


class Verifier:
    """Checks one bearer token and returns (subject, roles)."""

    def __init__(self, config: OAuthConfig, jwk_client: Any = None):
        import jwt                                    # PyJWT, installed with the mcp extra
        self.config, self._jwt = config, jwt
        if jwk_client is None:
            jwk_client = jwt.PyJWKClient(config.jwks_url or discover_jwks(config.issuer),
                                         cache_keys=True, lifespan=300, timeout=10)
        self._keys = jwk_client

    def verify(self, token: str) -> Tuple[str, List[str]]:
        jwt, cfg = self._jwt, self.config
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in ALGORITHMS:
                raise TokenError(f"token algorithm {header.get('alg')!r} is not accepted")
            key = self._keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=ALGORITHMS, audience=cfg.audience, issuer=cfg.issuer,
                                leeway=cfg.leeway, options={"require": ["exp", "iss", "aud"]})
        except TokenError:
            raise
        except Exception as e:                        # expired, wrong audience, bad signature, unknown key...
            raise TokenError(f"token rejected: {type(e).__name__}") from None
        subject = claims.get(cfg.subject_claim)
        if not isinstance(subject, str) or not subject.strip():
            raise TokenError(f"token has no {cfg.subject_claim!r} claim")
        if cfg.scopes:
            raw = claims.get("scope", claims.get("scp", ""))
            have = set(raw.split() if isinstance(raw, str) else [str(s) for s in raw or []])
            missing = [s for s in cfg.scopes if s not in have]
            if missing:
                raise TokenError(f"token lacks scope {' '.join(missing)}", status=403, error="insufficient_scope")
        roles: List[str] = []
        for path in cfg.roles_claims:
            value = _claim(claims, path)
            if value is None:
                continue
            roles = [value] if isinstance(value, str) else [str(v) for v in value if isinstance(v, (str, int))]
            break
        # one issuer per server, so '<namespace>:<sub>' is unique here; SUBJECT_CLAIM=email gives
        # 'oauth:jdoe@example.com' for a `groups` resolver keyed by mail
        return f"{cfg.namespace}:{subject.strip()}", roles


def _rewrite(body: bytes, subject: str, roles: List[str], identity_tools: Iterable[str]) -> bytes:
    """The request body with every tools/call's principal and roles set from the token."""
    try:
        msg = json.loads(body)
    except ValueError:
        return body                                   # not JSON: the SDK answers it with a parse error
    tools = set(identity_tools)
    changed = False
    for m in msg if isinstance(msg, list) else [msg]:
        if not isinstance(m, dict) or m.get("method") != "tools/call":
            continue
        params = m.get("params")
        if not isinstance(params, dict):
            continue
        if params.get("name") not in tools:
            continue
        args = params.get("arguments")
        args = dict(args) if isinstance(args, dict) else {}
        args["principal"], args["roles"] = subject, list(roles)
        params["arguments"] = args
        changed = True
    return json.dumps(msg).encode("utf-8") if changed else body


class OAuthMiddleware:
    """ASGI middleware in front of the MCP app: metadata, token check, identity from the token."""

    def __init__(self, app: Callable, verifier: Verifier, identity_tools: Iterable[str],
                 on_verified: Optional[Callable[[str], None]] = None):
        self.app, self.verifier = app, verifier
        self.config = verifier.config
        self.identity_tools = list(identity_tools)
        self.on_verified = on_verified

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        method, path = scope.get("method", "GET"), scope.get("path", "")
        if path == WELL_KNOWN or path.startswith(WELL_KNOWN + "/"):
            if method in ("GET", "HEAD"):
                return await self._json(send, 200, self.config.metadata())
            return await self._json(send, 405, {"error": "method not allowed"})
        if method == "OPTIONS":                        # CORS preflight carries no credentials
            return await self.app(scope, receive, send)
        token = self._bearer(scope)
        try:
            if token is None:
                raise TokenError("no bearer token", error="")
            import anyio
            subject, roles = await anyio.to_thread.run_sync(self.verifier.verify, token)
        except TokenError as e:
            log.info("refused %s %s: %s", method, path, e)
            return await self._challenge(send, e)
        if self.on_verified is not None:
            self.on_verified(subject)
        if method != "POST":
            return await self.app(scope, receive, send)
        body, more = b"", True
        while more:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            body += event.get("body", b"")
            more = event.get("more_body", False)
            if len(body) > MAX_BODY:
                return await self._json(send, 413, {"error": "request body too large"})
        body = _rewrite(body, subject, roles, self.identity_tools)
        headers = [(k, v) for k, v in scope.get("headers", []) if k.lower() != b"content-length"]
        headers.append((b"content-length", str(len(body)).encode()))
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(dict(scope, headers=headers), replay, send)

    @staticmethod
    def _bearer(scope) -> Optional[str]:
        for k, v in scope.get("headers", []):
            if k.lower() == b"authorization":
                kind, _, value = v.decode("latin-1").partition(" ")
                if kind.lower() != "bearer":
                    return None
                return value.strip() or None
        return None

    async def _challenge(self, send, e: TokenError):
        parts = [f'resource_metadata="{self.config.metadata_url()}"']
        if self.config.scopes:
            parts.append(f'scope="{" ".join(self.config.scopes)}"')
        if e.error:
            parts.append(f'error="{e.error}"')
        await self._json(send, e.status, {"error": e.error or "unauthorized"},
                         [(b"www-authenticate", ("Bearer " + ", ".join(parts)).encode())])

    @staticmethod
    async def _json(send, status: int, payload: Dict[str, Any], extra=()):
        body = json.dumps(payload).encode("utf-8")
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                   (b"cache-control", b"no-store"), *extra]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})
