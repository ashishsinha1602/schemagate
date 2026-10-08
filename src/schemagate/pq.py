# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Quantum-safe, tamper-evident audit records: ML-DSA signatures over a hash chain.

The audit log (`audit.py`) is schemagate's evidence: which caller was shown which
objects, when, and what was held back. Evidence is only worth something if it
cannot be quietly edited afterwards, and an audit log is kept for years -- long
enough that a signature made today should still hold when large quantum
computers can forge the classical ones (RSA, ECDSA). So each record is:

* **chained** -- it carries its sequence number and the hash of the record
  before it, so removing, inserting or reordering a record breaks the chain;
* **hashed** -- SHA-256 over its canonical JSON, so editing any field changes it;
* **signed** -- with ML-DSA-65, the NIST post-quantum signature standard
  (FIPS 204), over that hash.

`verify` re-checks all three and names the first record that fails and why.

What this does not do, said plainly: it cannot stop someone with write access
from deleting the *newest* records (a shorter chain is still a valid chain).
`head` prints the latest ``seq:hash``; keep that somewhere else (a ticket, a
second system, an email) and `verify --head` will tell you if the log no longer
reaches it. It also does not encrypt anything: records are readable by anyone
who can read the file, exactly as before. And it signs what schemagate decided,
which is only as true as the catalog and the roles it was given.

The signing library is PyCA `cryptography` (>= 48, OpenSSL-backed), installed
with ``pip install "schemagate[pq]"``. Nothing here is imported unless signing
is configured, so the base install is unchanged.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

__all__ = ["ALGORITHM", "CONTEXT", "GENESIS", "Signer", "Verifier", "VerifyReport",
           "generate_keypair", "load_signer", "load_verifier", "seal", "verify_files", "head_of"]

ALGORITHM = "ML-DSA-65"
#: FIPS 204 context string: a signature made for this purpose cannot be replayed as a signature for another.
CONTEXT = b"schemagate-audit-v1"
#: `prev` of the very first record.
GENESIS = "0" * 64
#: Fields that are outputs of sealing, so they are not part of what is hashed.
_SEAL_OUTPUTS = ("hash", "sig")
ENV_KEY = "SCHEMAGATE_AUDIT_SIGNING_KEY"
ENV_PASSPHRASE = "SCHEMAGATE_AUDIT_SIGNING_KEY_PASSPHRASE"


def _require():
    try:
        from cryptography.hazmat.primitives.asymmetric import mldsa  # noqa: F401
        from cryptography.hazmat.primitives import serialization  # noqa: F401
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise RuntimeError('signed audit records need ML-DSA: pip install "schemagate[pq]" '
                           "(cryptography >= 48)") from e
    from cryptography.hazmat.primitives.asymmetric import mldsa
    from cryptography.hazmat.primitives import serialization
    return mldsa, serialization


def canonical(rec: Mapping[str, Any]) -> bytes:
    """The bytes that are hashed: the record without its hash and signature, keys sorted, no whitespace."""
    body = {k: v for k, v in rec.items() if k not in _SEAL_OUTPUTS}
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _key_id(public_der: bytes) -> str:
    return hashlib.sha256(public_der).hexdigest()[:16]


class Signer:
    def __init__(self, private_key) -> None:
        _, serialization = _require()
        self._key = private_key
        der = private_key.public_key().public_bytes(serialization.Encoding.DER,
                                                    serialization.PublicFormat.SubjectPublicKeyInfo)
        self.key_id = _key_id(der)

    def sign(self, digest: bytes) -> bytes:
        return self._key.sign(digest, CONTEXT)


class Verifier:
    def __init__(self, public_key) -> None:
        _, serialization = _require()
        self._key = public_key
        der = public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        self.key_id = _key_id(der)

    def check(self, signature: bytes, digest: bytes) -> bool:
        from cryptography.exceptions import InvalidSignature
        try:
            self._key.verify(signature, digest, CONTEXT)
            return True
        except InvalidSignature:
            return False


def generate_keypair(directory: os.PathLike, passphrase: Optional[bytes] = None,
                     name: str = "audit-signing-key") -> Tuple[Path, Path]:
    """Write ``<name>.pem`` (private, mode 0600 where the OS has modes) and ``<name>.pub.pem``. Refuses to
    overwrite an existing key: replacing a signing key silently orphans every record it signed."""
    mldsa, serialization = _require()
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    priv_path, pub_path = d / f"{name}.pem", d / f"{name}.pub.pem"
    for p in (priv_path, pub_path):
        if p.exists():
            raise FileExistsError(f"{p} already exists; a new key would orphan the records the old one signed")
    key = mldsa.MLDSA65PrivateKey.generate()
    enc = (serialization.BestAvailableEncryption(passphrase) if passphrase else serialization.NoEncryption())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, enc)
    fd = os.open(priv_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem)
    pub_path.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                        serialization.PublicFormat.SubjectPublicKeyInfo))
    return priv_path, pub_path


def load_signer(path: os.PathLike, passphrase: Optional[bytes] = None) -> Signer:
    mldsa, serialization = _require()
    key = serialization.load_pem_private_key(Path(path).read_bytes(), passphrase)
    if not isinstance(key, mldsa.MLDSA65PrivateKey):
        raise ValueError(f"{path} is not an {ALGORITHM} private key")
    return Signer(key)


def load_verifier(path: os.PathLike) -> Verifier:
    mldsa, serialization = _require()
    key = serialization.load_pem_public_key(Path(path).read_bytes())
    if not isinstance(key, mldsa.MLDSA65PublicKey):
        raise ValueError(f"{path} is not an {ALGORITHM} public key")
    return Verifier(key)


def signer_from_env(env: Optional[Mapping[str, str]] = None) -> Optional[Signer]:
    """``SCHEMAGATE_AUDIT_SIGNING_KEY`` unset -> no signing. Set -> the key is loaded now, and a key that cannot
    be loaded is an error now: an operator who asked for signed evidence must not get unsigned evidence quietly."""
    src = os.environ if env is None else env
    path = (src.get(ENV_KEY) or "").strip()
    if not path:
        return None
    pw = src.get(ENV_PASSPHRASE)
    return load_signer(path, pw.encode("utf-8") if pw else None)


def seal(rec: Dict[str, Any], signer: Signer, seq: int, prev: str) -> Dict[str, Any]:
    """Add the chain fields, the hash and the signature to ``rec`` (in place) and return it."""
    rec["seq"] = seq
    rec["prev"] = prev
    rec["alg"] = ALGORITHM
    rec["key"] = signer.key_id
    digest = hashlib.sha256(canonical(rec)).digest()
    rec["hash"] = digest.hex()
    rec["sig"] = base64.b64encode(signer.sign(digest)).decode("ascii")
    return rec


def last_sealed(paths: Iterable[os.PathLike]) -> Optional[Tuple[int, str]]:
    """(seq, hash) of the newest sealed record in the first of ``paths`` that has one -- how a restarted
    server continues the chain instead of starting a second one."""
    for p in paths:
        p = Path(p)
        if not p.exists() or p.stat().st_size == 0:
            continue
        last = None
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if "hash" in r and "seq" in r:
                    last = (int(r["seq"]), str(r["hash"]))
        if last:
            return last
    return None


@dataclass
class VerifyReport:
    ok: bool = True
    records: int = 0
    first_seq: Optional[int] = None
    last_seq: Optional[int] = None
    last_hash: Optional[str] = None
    unsigned_before: int = 0
    problems: List[Dict[str, Any]] = field(default_factory=list)

    def fail(self, file: str, line: int, reason: str, **extra: Any) -> None:
        self.ok = False
        if len(self.problems) < 50:
            self.problems.append({"file": file, "line": line, "reason": reason, **extra})

    @property
    def head(self) -> Optional[str]:
        return f"{self.last_seq}:{self.last_hash}" if self.last_hash is not None else None

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "records": self.records, "first_seq": self.first_seq, "last_seq": self.last_seq,
                "head": self.head, "unsigned_before_signing_began": self.unsigned_before,
                "problems": self.problems}


def verify_files(paths: List[os.PathLike], verifier: Verifier, head: Optional[str] = None) -> VerifyReport:
    """Check every record in ``paths`` (oldest file first, e.g. ``audit.jsonl.1 audit.jsonl``).

    Records written before signing was switched on are counted, not failed; an unsigned record *after* a
    signed one is a failure, because nothing legitimate produces it. The first file may start mid-chain (its
    predecessor rotated away); every record after that must follow on exactly.
    """
    rep = VerifyReport()
    prev_seq: Optional[int] = None
    prev_hash: Optional[str] = None
    seen: Dict[int, str] = {}
    for p in paths:
        name = str(p)
        with Path(p).open("r", encoding="utf-8") as fh:
            for n, raw in enumerate(fh, 1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except ValueError:
                    rep.fail(name, n, "not valid JSON (the line was altered or truncated)")
                    continue
                if "sig" not in rec:
                    if prev_hash is None:
                        rep.unsigned_before += 1
                    else:
                        rep.fail(name, n, "unsigned record after signing began")
                    continue
                rep.records += 1
                seq = rec.get("seq")
                if rec.get("alg") != ALGORITHM:
                    rep.fail(name, n, f"algorithm is {rec.get('alg')!r}, expected {ALGORITHM}", seq=seq)
                    continue
                if rec.get("key") != verifier.key_id:
                    rep.fail(name, n, "signed with a different key than the one given", seq=seq,
                             key=rec.get("key"), expected=verifier.key_id)
                    continue
                digest = hashlib.sha256(canonical(rec)).digest()
                if digest.hex() != rec.get("hash"):
                    rep.fail(name, n, "content does not match its hash (a field was edited)", seq=seq)
                    prev_seq, prev_hash = seq, rec.get("hash")   # judge the next record on its own link
                    continue
                try:
                    sig = base64.b64decode(rec["sig"], validate=True)
                except (ValueError, TypeError):
                    rep.fail(name, n, "signature is not valid base64", seq=seq)
                    continue
                if not verifier.check(sig, digest):
                    rep.fail(name, n, "signature does not verify (record forged or re-hashed)", seq=seq)
                    prev_seq, prev_hash = seq, rec.get("hash")
                    continue
                if prev_seq is None:
                    rep.first_seq = seq
                    if seq == 0 and rec.get("prev") != GENESIS:
                        rep.fail(name, n, "first record does not start the chain", seq=seq)
                else:
                    if seq != prev_seq + 1:
                        rep.fail(name, n, f"sequence jumps from {prev_seq} to {seq} "
                                          "(records removed, inserted or reordered)", seq=seq)
                    if rec.get("prev") != prev_hash:
                        rep.fail(name, n, "does not follow the record before it "
                                          "(records removed, inserted or reordered)", seq=seq)
                prev_seq, prev_hash = seq, rec["hash"]
                seen[int(seq)] = rec["hash"]
    rep.last_seq, rep.last_hash = prev_seq, prev_hash
    if rep.records == 0 and rep.ok:
        rep.fail(", ".join(str(p) for p in paths), 0, "no signed records found")
    if head:
        try:
            hseq, hhash = head.split(":", 1)
            hseq_i = int(hseq)
        except ValueError:
            rep.fail("--head", 0, "expected SEQ:HASH as printed by `schemagate audit head`")
        else:
            if seen.get(hseq_i) != hhash:
                rep.fail("--head", 0, f"the log no longer contains record {hseq_i} as recorded "
                                      "(newest records removed, or the log was rewritten)")
    return rep


def head_of(paths: List[os.PathLike]) -> Optional[str]:
    last = last_sealed(list(reversed([Path(p) for p in paths])))
    return f"{last[0]}:{last[1]}" if last else None
