# OAuth: identity from your identity provider, not from the client

Over stdio, the only caller is the desktop app on your machine. Over HTTP, anyone who can reach the
port could send `roles=["payroll"]`. Without OAuth, the HTTP transport is therefore safe only behind
something that authenticates people: a gateway, a proxy, your own service.

With OAuth on, schemagate is an OAuth 2.1 resource server, as the MCP authorization specification
describes. That means:

- it publishes Protected Resource Metadata (RFC 9728) at
  `/.well-known/oauth-protected-resource/mcp`, naming your provider. An MCP client that implements the
  specification finds out from it where to sign the user in;
- every request must carry `Authorization: Bearer <token>`, a JWT signed by that provider. schemagate
  checks the signature against the provider's published keys, and also `iss`, `aud`, `exp` and the
  scopes you require. Only asymmetric algorithms are accepted: `none` and HMAC are refused, which
  rules out the key-confusion forgery. Anything else gets `401` with a `WWW-Authenticate` header
  pointing to the metadata;
- on every tool call, `principal` and `roles` are replaced with the token's subject and role claim.
  What the client sent is discarded, so nobody can claim a role or another user's identity.
  Restrictions then apply exactly as before, down to single columns. With a `groups` resolver
  configured, the roles come from the directory, keyed by the token's subject.

No gateway is needed. It needs nothing beyond the `mcp` extra.

```
SCHEMAGATE_MCP_TRANSPORT=streamable-http
SCHEMAGATE_MCP_HOST=0.0.0.0
SCHEMAGATE_MCP_OAUTH_ISSUER=https://login.example.com/oauth2/default
SCHEMAGATE_MCP_OAUTH_AUDIENCE=api://schemagate
SCHEMAGATE_MCP_OAUTH_RESOURCE=https://schemagate.example.com/mcp   # this server's public URL
```

| Setting | Default | |
|---|---|---|
| `SCHEMAGATE_MCP_OAUTH_ISSUER` | off | turns OAuth on; the provider's issuer URL (https) |
| `SCHEMAGATE_MCP_OAUTH_AUDIENCE` | required | the `aud` your tokens carry; without it a token for any other app would pass |
| `SCHEMAGATE_MCP_OAUTH_RESOURCE` | the audience | the public URL of `/mcp`, used in the metadata and the 401 header |
| `SCHEMAGATE_MCP_OAUTH_JWKS_URL` | discovered | the signing keys; otherwise read from the issuer's OpenID or OAuth metadata |
| `SCHEMAGATE_MCP_OAUTH_ROLES_CLAIM` | `roles groups` | claims holding the roles, first found wins; exact names, then dotted paths |
| `SCHEMAGATE_MCP_OAUTH_SUBJECT_CLAIM` | `sub` | `email` when a `groups` resolver is keyed by mail |
| `SCHEMAGATE_MCP_OAUTH_NAMESPACE` | `oauth` | the principal is `<namespace>:<subject>`, e.g. `okta` for `okta:00u1…` |
| `SCHEMAGATE_MCP_OAUTH_SCOPES` | none | scopes every token must carry; a token without them gets `403 insufficient_scope` |

A wrong setting stops the server at start, before the database is read. `health` reports
`"auth": "oauth"`. Without OAuth, HTTP on a non-loopback host logs a warning that identity is
whatever the client sends.

## Providers

| Provider | Issuer | Audience | Roles claim |
|---|---|---|---|
| Microsoft Entra ID | `https://login.microsoftonline.com/<tenant>/v2.0` | the app ID URI or client ID | `roles` (app roles) |
| Okta | `https://<org>.okta.com/oauth2/<server>` | the authorization server's audience | `groups` (add a groups claim) |
| Auth0 | `https://<tenant>.auth0.com/` | the API identifier | a namespaced claim, e.g. `https://example.com/roles` |
| Keycloak | `https://<host>/realms/<realm>` | add an audience mapper | `realm_access.roles` |
The provider must issue JWT access tokens. Some do not (Google's are opaque), and those cannot be
verified here.

### Keycloak, step by step

This is what `tests/keycloak_e2e.py` sets up. CI runs it against Keycloak 26.4.

1. Create realm roles (`sales`, `payroll`) and assign them to users.
2. Create a client scope `schemagate` with *Include in token scope* on. Give it three mappers:
   - **Audience**: included custom audience `schemagate`;
   - **User Attribute**: `username` → `preferred_username`;
   - **User Realm Role**: claim `realm_access.roles`, multivalued.

   Under its *Scope* tab, add the realm roles schemagate cares about. Make it a realm default client
   scope.
3. For MCP clients that register themselves, go to *Clients → Client registration → Anonymous access
   policies*. Allow the `schemagate` scope under *Allowed Client Scopes*, and set *Trusted Hosts* to
   the hosts your clients redirect to.
4. Start schemagate with:

   ```
   SCHEMAGATE_MCP_OAUTH_ISSUER=https://<host>/realms/<realm>
   SCHEMAGATE_MCP_OAUTH_AUDIENCE=schemagate
   SCHEMAGATE_MCP_OAUTH_SCOPES=schemagate
   SCHEMAGATE_MCP_OAUTH_ROLES_CLAIM=realm_access.roles
   SCHEMAGATE_MCP_OAUTH_SUBJECT_CLAIM=preferred_username
   SCHEMAGATE_MCP_OAUTH_NAMESPACE=keycloak
   ```

Why the mappers live on the `schemagate` scope: a client that registers itself and asks only for
`schemagate` gets only that scope. Without them, its tokens carry neither the username nor the roles,
and schemagate refuses them. Keycloak applies a scope with role mappings only to users who hold one of
those roles. So removing a user's last such role also removes the audience from their next token, and
schemagate refuses it at the door.

Issuers must match the token's `iss` character for character, trailing slash included.

## Clients

A client that implements the MCP authorization specification reads the metadata, sends the user to
your provider and comes back with a token. If the client relies on Dynamic Client Registration, your
provider must offer it (Keycloak and Auth0 can). Otherwise, register the client in your provider and
give it the client ID. A service calling schemagate itself gets a token from your provider the usual
way (client credentials) and sends it as a bearer token.

## What is tested

`tests/test_oauth.py` starts the real server over streamable HTTP with the demo database, against a
local provider with OpenID metadata and keys on loopback. It checks that:

- requests with no token, an expired token, another audience, another issuer, another key, no
  signature, or HMAC signed with the public key get 401 and the metadata URL;
- a token saying `sales` cannot read the payroll table by sending `roles=["payroll"]` or another
  principal in the tool arguments;
- a token saying `payroll` can.

Removing the identity rewrite makes these tests fail.

`tests/keycloak_e2e.py` runs the same server against a real Keycloak 26.4, using the MCP SDK's own
OAuth client (17 checks, in CI). The client starts from the server URL alone and goes through the
whole flow: the 401, the metadata, Dynamic Client Registration, and authorization code with PKCE (the
login is Keycloak's own form). Then two users with different roles see different data. Real tokens
for another application or from another realm are refused, an edited token is refused, and removing
a role in Keycloak takes effect on the next token.

Not run against a hosted Entra ID, Okta or Auth0 tenant, or through Claude.ai.
