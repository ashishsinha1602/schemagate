"""The command line, driven through its entry point."""
import subprocess
import sys

import pytest

from schemagate.cli import main


def run(*argv):
    """Invoke main() in-process and capture stdout."""
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(list(argv))
    return code, buf.getvalue()


def test_demo_runs_with_no_arguments():
    code, out = run("demo")
    assert code == 0
    assert "42 objects" in out
    assert "v_monthly_revenue" in out


def test_demo_accepts_a_question():
    code, out = run("demo", "which customers owe us money")
    assert code == 0 and "v_customer_balance" in out


def test_demo_scoping_without_role():
    _, out = run("demo", "salary and pay grade by employee")
    body = out.split("\n\n", 1)[1]           # drop the header that names it
    assert "hr_compensation" not in body


def test_demo_scoping_with_role():
    _, out = run("demo", "salary and pay grade by employee",
                 "--principal", "okta:hr", "--role", "payroll")
    assert "main.hr_compensation" in out


def test_prompt_flag_prints_ddl():
    _, out = run("demo", "late shipments by carrier", "--prompt", "--top-k", "2")
    assert "TABLE main.ship_carrier (" in out


def test_explain_flag_prints_reasons():
    _, out = run("demo", "late shipments by carrier", "--explain", "--top-k", "2")
    assert "hybrid" in out or "vector" in out or "lexical" in out


def test_malformed_principal_exits_nonzero():
    with pytest.raises(SystemExit) as exc:
        run("demo", "x", "--principal", "nocolon")
    assert "namespaced" in str(exc.value)


def test_select_against_a_url(db_url):
    code, out = run("select", "stock per warehouse", "--url", db_url,
                    "--top-k", "3")
    assert code == 0 and "inv_stock_level" in out


def test_select_exclude_pattern(db_url):
    _, out = run("select", "invoices", "--url", db_url,
                 "--exclude", "sales_invoice_draft", "--no-fk")
    assert "sales_invoice_draft" not in out


def test_version_flag():
    with pytest.raises(SystemExit) as exc:
        run("--version")
    assert exc.value.code == 0


def _config_file(tmp_path, obj):
    import json
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


def test_misspelled_config_block_is_one_line_not_a_traceback(tmp_path):
    """The loader refuses a block it does not know; the command line must say why
    in one line, naming the file, rather than die with the loader's traceback."""
    from schemagate.demo_schema import create_demo_db
    path = _config_file(tmp_path, {"restrict_columns": {"hr_compensation": {"annual_amount": ["hr"]}}})
    with pytest.raises(SystemExit) as exc:
        run("select", "salary by employee", "--url", create_demo_db(), "--config", path)
    msg = str(exc.value)
    assert msg.startswith("schemagate: --config ") and "unknown block" in msg and "restrict_columns" in msg
    assert msg.count(path) == 1 and "Traceback" not in msg


def test_misspelled_config_column_is_one_line(tmp_path):
    from schemagate.demo_schema import create_demo_db
    path = _config_file(tmp_path, {"restrict_column": {"hr_compensation": {"anual_amount": ["hr"]}}})
    with pytest.raises(SystemExit) as exc:
        run("select", "salary by employee", "--url", create_demo_db(), "--config", path)
    assert "anual_amount" in str(exc.value) and str(exc.value).startswith(f"schemagate: --config {path}: ")


def test_console_script_is_installed():
    """`schemagate` on PATH, as pip would install it."""
    out = subprocess.run([sys.executable, "-m", "schemagate.cli", "demo",
                          "headcount per department"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "v_employee_headcount" in out.stdout
