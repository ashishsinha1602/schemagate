# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""The fuzz harness runs in ordinary CI too, without atheris, so it cannot rot.

It feeds generated SQL through run_query's gate and executes whatever passes;
a withheld value in the result is a failure. It has found two real bypasses:
on 1.4.1, a hidden column read through a scalar subquery inside a CTE; on
1.4.2, a table named with a single-quoted string on SQLite (fixed in 1.4.3,
GHSA-qhcw-c944-fhq9) -- the second within two minutes of coverage-guided fuzzing.
"""
import importlib.util
import pathlib

HARNESS = pathlib.Path(__file__).resolve().parent.parent / "fuzz" / "fuzz_run_query_scope.py"


def _load():
    spec = importlib.util.spec_from_file_location("fuzz_run_query_scope", HARNESS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_generated_sql_never_returns_a_withheld_value():
    _load().smoke(3000, seed=7)


def test_the_oracle_would_see_a_leak():
    f = _load()
    import pytest
    with pytest.raises(AssertionError, match="withheld value"):
        # bypass the gate on purpose: the check must notice the sentinel
        real = f._check_scope
        f._check_scope = lambda *a: None
        try:
            f.check("SELECT note FROM secret")
        finally:
            f._check_scope = real


def test_the_gate_refuses_the_variant_the_fuzzer_found_on_1_4_1():
    f = _load()
    sql = "WITH x AS (SELECT (select salary from staff) FROM offers) SELECT * FROM x"
    assert f._check_scope(f.CAT, sql, f.WHO) is not None
