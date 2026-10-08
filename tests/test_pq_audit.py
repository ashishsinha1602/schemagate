"""Signed audit log: every way of altering the evidence must be caught, and the honest log must pass.

The attacker here has write access to the log file but not the private key. Each test makes one change an
attacker (or an accident) could make and checks that `verify` names it. The last tests pin what the feature does
not claim, so the docs cannot drift from the code.
"""
import json
import subprocess
import sys

import pytest

pytest.importorskip("cryptography.hazmat.primitives.asymmetric.mldsa")

from schemagate import pq  # noqa: E402
from schemagate.audit import AuditLog, summarize  # noqa: E402


@pytest.fixture()
def keys(tmp_path):
    priv, pub = pq.generate_keypair(tmp_path / "keys")
    return pq.load_signer(priv), pq.load_verifier(pub), priv, pub


def _write(tmp_path, signer, n=5, name="audit.jsonl"):
    log = AuditLog(tmp_path / name, signer=signer)
    for i in range(n):
        log.record(summarize("select_schema", {"question": f"q{i}", "principal": "okta:a", "roles": ["sales"]},
                             {"selected": 2, "total_objects": 10, "objects": ["t1", "t2"], "_visible_objects": 8}))
    return tmp_path / name


def _lines(path):
    return path.read_text(encoding="utf-8").splitlines()


def _save(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_an_honest_log_verifies(tmp_path, keys):
    signer, verifier, *_ = keys
    path = _write(tmp_path, signer)
    rep = pq.verify_files([path], verifier)
    assert rep.ok, rep.problems
    assert (rep.records, rep.first_seq, rep.last_seq) == (5, 0, 4)
    first = json.loads(_lines(path)[0])
    assert first["alg"] == "ML-DSA-65" and first["prev"] == pq.GENESIS and len(first["hash"]) == 64


def test_editing_any_field_is_caught(tmp_path, keys):
    signer, verifier, *_ = keys
    path = _write(tmp_path, signer)
    lines = _lines(path)
    rec = json.loads(lines[2])
    rec["objects"] = ["t1", "t2", "hr_compensation"]        # claim the caller was shown more than they were
    lines[2] = json.dumps(rec, separators=(",", ":"))
    _save(path, lines)
    rep = pq.verify_files([path], verifier)
    assert not rep.ok and rep.problems[0]["line"] == 3 and "edited" in rep.problems[0]["reason"]
    assert len(rep.problems) == 1, "one edited record is one problem, not a cascade over the records after it"


def test_rehashing_an_edit_does_not_help_without_the_key(tmp_path, keys):
    """The attacker recomputes the hash after editing; the signature then no longer verifies."""
    signer, verifier, *_ = keys
    path = _write(tmp_path, signer)
    lines = _lines(path)
    rec = json.loads(lines[1])
    rec["principal"] = "okta:someone-else"
    import hashlib
    rec["hash"] = hashlib.sha256(pq.canonical(rec)).hexdigest()
    lines[1] = json.dumps(rec, separators=(",", ":"))
    _save(path, lines)
    rep = pq.verify_files([path], verifier)
    assert not rep.ok and "signature does not verify" in rep.problems[0]["reason"]


def test_deleting_a_record_in_the_middle_is_caught(tmp_path, keys):
    signer, verifier, *_ = keys
    path = _write(tmp_path, signer)
    lines = _lines(path)
    del lines[2]
    _save(path, lines)
    rep = pq.verify_files([path], verifier)
    assert not rep.ok and "removed, inserted or reordered" in rep.problems[0]["reason"]


def test_reordering_is_caught(tmp_path, keys):
    signer, verifier, *_ = keys
    path = _write(tmp_path, signer)
    lines = _lines(path)
    lines[1], lines[3] = lines[3], lines[1]
    _save(path, lines)
    assert not pq.verify_files([path], verifier).ok


def test_a_record_signed_with_another_key_is_caught(tmp_path, keys):
    signer, verifier, *_ = keys
    path = _write(tmp_path, signer)
    other_priv, _ = pq.generate_keypair(tmp_path / "other")
    forged = AuditLog(None, signer=pq.load_signer(other_priv)).record(
        summarize("run_query", {"principal": "okta:a"}, {"sql": "select 1", "row_count": 1}))
    _save(path, _lines(path) + [json.dumps(forged, separators=(",", ":"))])
    rep = pq.verify_files([path], verifier)
    assert not rep.ok and "different key" in rep.problems[0]["reason"]


def test_the_wrong_public_key_fails_everything(tmp_path, keys):
    signer, _, *_ = keys
    path = _write(tmp_path, signer)
    _, other_pub = pq.generate_keypair(tmp_path / "other")
    assert not pq.verify_files([path], pq.load_verifier(other_pub)).ok


def test_an_unsigned_line_after_signing_began_is_caught(tmp_path, keys):
    signer, verifier, *_ = keys
    path = _write(tmp_path, signer)
    _save(path, _lines(path) + ['{"ts":"2026-10-07T00:00:00Z","tool":"run_query","principal":"okta:a","ok":true}'])
    rep = pq.verify_files([path], verifier)
    assert not rep.ok and "unsigned record after signing began" in rep.problems[0]["reason"]


def test_a_restart_continues_the_chain(tmp_path, keys):
    signer, verifier, priv, _ = keys
    path = _write(tmp_path, signer, n=3)
    _write(tmp_path, pq.load_signer(priv), n=2)              # a new AuditLog on the same file = a restart
    rep = pq.verify_files([path], verifier)
    assert rep.ok, rep.problems
    assert (rep.first_seq, rep.last_seq) == (0, 4)


def test_the_chain_continues_across_rotation(tmp_path, keys):
    signer, verifier, *_ = keys
    log = AuditLog(tmp_path / "audit.jsonl", signer=signer, max_bytes=9000)   # each record ~4.6 KB
    for i in range(6):
        log.record(summarize("run_query", {"principal": "okta:a"}, {"sql": f"select {i}", "row_count": i}))
    rotated, current = tmp_path / "audit.jsonl.1", tmp_path / "audit.jsonl"
    assert rotated.exists() and current.exists()
    rep = pq.verify_files([rotated, current], verifier)
    assert rep.ok, rep.problems
    alone = pq.verify_files([current], verifier)              # the newer file alone starts mid-chain, still valid
    assert alone.ok and alone.first_seq > 0


def test_removing_the_newest_records_is_caught_only_against_a_kept_head(tmp_path, keys):
    """The documented limit: a shorter chain is still a valid chain. Keeping the head elsewhere closes it."""
    signer, verifier, *_ = keys
    path = _write(tmp_path, signer)
    head = pq.head_of([path])
    _save(path, _lines(path)[:3])
    assert pq.verify_files([path], verifier).ok, "truncation alone is not detectable; the docs say so"
    rep = pq.verify_files([path], verifier, head=head)
    assert not rep.ok and "no longer contains record 4" in rep.problems[0]["reason"]


def test_without_a_key_the_log_is_byte_for_byte_what_it_was(tmp_path):
    """Signing is opt-in: an unsigned log gains no fields."""
    log = AuditLog(tmp_path / "a.jsonl")
    rec = log.record(summarize("run_query", {"principal": "okta:a"}, {"sql": "select 1", "row_count": 1}))
    assert not {"seq", "prev", "hash", "sig", "alg", "key"} & set(rec)


def test_signing_records_no_row_data(tmp_path, keys):
    signer, *_ = keys
    rec = AuditLog(tmp_path / "a.jsonl", signer=signer).record(
        summarize("run_query", {"principal": "okta:a"}, {"sql": "select salary from t", "row_count": 2,
                                                          "rows": [[100000], [120000]]}))
    assert "rows" not in rec and "100000" not in json.dumps(rec)


def test_a_configured_key_that_cannot_load_fails_at_start(tmp_path):
    bad = tmp_path / "missing.pem"
    with pytest.raises(FileNotFoundError):
        AuditLog.from_env({"SCHEMAGATE_AUDIT_LOG": str(tmp_path / "a.jsonl"), pq.ENV_KEY: str(bad)})


def test_keygen_refuses_to_overwrite_a_key(tmp_path):
    pq.generate_keypair(tmp_path)
    with pytest.raises(FileExistsError):
        pq.generate_keypair(tmp_path)


def test_the_cli_round_trip(tmp_path):
    run = lambda *a: subprocess.run([sys.executable, "-m", "schemagate", "audit", *a],  # noqa: E731
                                    capture_output=True, text=True, cwd=tmp_path)
    r = run("keygen", "--out", str(tmp_path / "k"))
    assert r.returncode == 0, r.stderr
    signer = pq.load_signer(tmp_path / "k" / "audit-signing-key.pem")
    path = _write(tmp_path, signer, n=3)
    pub = str(tmp_path / "k" / "audit-signing-key.pub.pem")
    ok = run("verify", str(path), "--public-key", pub)
    assert ok.returncode == 0 and "OK  3 signed records" in ok.stdout, ok.stdout + ok.stderr
    head = run("head", str(path)).stdout.strip()
    assert head.startswith("2:")
    lines = _lines(path)
    rec = json.loads(lines[1]); rec["row_count"] = 999  # noqa: E702
    lines[1] = json.dumps(rec, separators=(",", ":"))
    _save(path, lines)
    bad = run("verify", str(path), "--public-key", pub)
    assert bad.returncode == 1 and "FAILED" in bad.stdout and ":2 " in bad.stdout
