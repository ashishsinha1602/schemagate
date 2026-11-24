# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Mutation checks: proof that a test can fail, kept as reproducible as the test itself.

A test that passes is only evidence if it would fail on the bug it guards against. For each entry below this
script runs the test as written, then a copy with one deliberate mutation, and passes only when BOTH hold:

  * the unmodified test passes, and
  * the mutated copy fails on the specific assertion named here -- not on a crash, an import error or any
    other assertion, which would "fail" without showing the test's sensitivity.

It is not collected by pytest (no test_ prefix) and runs as its own CI job, so the normal test run stays fast.

    python tests/mutations/check_mutations.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: (test file, test name, the code to replace, its mutation, text the failure must contain, why)
MUTATIONS = [
    (
        "tests/test_caller_visibility_timing.py",
        "test_role_list_revoke_on_a_reused_catalog_takes_effect_on_the_next_call",
        '    def sees(principal):\n'
        '        return "vt_salaries" in _names(cat.select(q, top_k=3, principal=principal))\n',
        # Rebuild the catalogue for carol, with the same tables and the same restriction state, on every read.
        # Everything she sees stays correct, so only the shared-object (identity) assertion can catch it.
        '    def sees(principal):\n'
        '        target = cat\n'
        '        if principal is carol:\n'
        '            target = Catalog(name="vt-reuse")\n'
        '            target.add_all(_docs())\n'
        '            for d in cat.objects():\n'
        '                if d.roles:\n'
        '                    target.restrict(d.qname, list(d.roles))\n'
        '        return "vt_salaries" in _names(target.select(q, top_k=3, principal=principal))\n',
        "alice and carol must share one catalog object across all six reads; got 4 objects in 6 reads",
        "rebuilding the catalogue between callers keeps every visible result while no longer testing shared state",
    ),
]


def run(test_file: pathlib.Path, name: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x",
                           f"{test_file}::{name}"], cwd=ROOT, capture_output=True, text=True, timeout=600)


def main() -> int:
    failures = 0
    for rel, name, original, mutated, must_say, why in MUTATIONS:
        src = (ROOT / rel).read_text("utf-8")
        if src.count(original) != 1:
            print(f"FAIL {name}: the code to mutate is not in {rel} exactly once; update this check with the test")
            failures += 1
            continue
        plain = run(ROOT / rel, name)
        if plain.returncode != 0:
            print(f"FAIL {name}: the unmodified test does not pass\n{plain.stdout[-2000:]}")
            failures += 1
            continue
        with tempfile.TemporaryDirectory() as d:
            mutant = pathlib.Path(d) / pathlib.Path(rel).name
            mutant.write_text(src.replace(original, mutated), "utf-8")
            out = run(mutant, name)
        text = out.stdout + out.stderr
        if out.returncode == 0:
            print(f"FAIL {name}: the mutated test still passes ({why}); the test no longer catches it")
            failures += 1
        elif must_say not in text or "AssertionError" not in text:
            print(f"FAIL {name}: the mutant failed, but not on the expected assertion ({must_say!r});"
                  f" a crash or another check does not show the test's sensitivity\n{text[-2000:]}")
            failures += 1
        else:
            print(f"ok   {name}: passes as written; the mutant fails with: {must_say}")
    print(f"{len(MUTATIONS) - failures} of {len(MUTATIONS)} mutation checks hold")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
