"""Business rules: parsed from Markdown, sent only when relevant, never to a caller without the role."""
import json

from schemagate import config as C
from schemagate.identity import Principal
from schemagate.rules import parse_markdown, relevant, to_markdown

MD = """# Our rules
anything before the first rule is ignored

## Fiscal year
Our fiscal year starts 1 July.

## Test customers
tables: crm_customer
Always exclude customers whose email ends in @example.com.

## Pay bands
roles: payroll
Pay grade G7 and above is senior.
"""


def test_parse_markdown():
    rules = parse_markdown(MD)
    assert [r.title for r in rules] == ["Fiscal year", "Test customers", "Pay bands"]
    assert rules[1].tables == ("crm_customer",) and rules[2].roles == ("payroll",)
    assert rules[0].text == "Our fiscal year starts 1 July."
    assert [r.title for r in parse_markdown(to_markdown(rules))] == [r.title for r in rules]


def test_untitled_and_empty_rules_are_skipped():
    assert parse_markdown("just text\n\n## Empty\n\n") == []


def test_relevant_by_word_by_table_and_by_role():
    rules = parse_markdown(MD)
    assert [r.title for r in relevant(rules, "revenue this fiscal year", [])] == ["Fiscal year"]
    assert [r.title for r in relevant(rules, "list them", ["main.crm_customer"])] == ["Test customers"]
    assert relevant(rules, "list them", ["main.billing_invoice"]) == []
    assert relevant(rules, "pay grade of senior staff", []) == []                 # no role
    assert [r.title for r in relevant(rules, "pay grade of senior staff", [], roles=["payroll"])] == ["Pay bands"]


def test_no_rules_leaves_the_prompt_byte_for_byte(cat):
    before = cat.select("revenue by month", top_k=4).prompt_fragment()
    cat.rules = []
    assert cat.select("revenue by month", top_k=4).prompt_fragment() == before
    cat.rules = parse_markdown("## Unrelated\nWarehouses close on Sundays.")
    assert cat.select("revenue by month", top_k=4).prompt_fragment() == before


def test_a_relevant_rule_goes_above_the_schema(cat):
    cat.rules = parse_markdown("## Fiscal year\nOur fiscal year starts 1 July; revenue by month follows it.")
    frag = cat.select("revenue by month", top_k=4).prompt_fragment()
    assert frag.startswith("-- Business rules to follow:\n-- - Fiscal year: Our fiscal year starts 1 July")


def test_a_role_rule_never_reaches_a_caller_without_the_role(cat):
    cat.rules = parse_markdown("## Secret bonus\nroles: payroll\nRevenue bonus is 3% of revenue by month.")
    anon = cat.select("revenue by month", top_k=4).prompt_fragment()
    assert "Secret bonus" not in anon
    who = Principal("okta:p", roles=frozenset({"payroll"}))
    assert "Secret bonus" in cat.select("revenue by month", top_k=4, principal=who).prompt_fragment()


def test_config_rules_path_is_relative_to_the_config(tmp_path, cat):
    (tmp_path / "rules.md").write_text("## Fiscal year\nStarts 1 July.", "utf-8")
    cfg = tmp_path / "catalog.json"
    cfg.write_text(json.dumps({"rules": "rules.md"}), "utf-8")
    C.apply(cat, C.load(str(cfg)))
    assert [r.title for r in cat.rules] == ["Fiscal year"]


def test_studio_save_get_and_test(tmp_path, monkeypatch, cat):
    from schemagate import remember
    from schemagate.studio import StudioState
    monkeypatch.setattr(remember, "path", lambda: tmp_path / "connection.json")
    st = StudioState(cat, "t", "b")
    assert st.rules({"action": "get"})["rules"] == []
    out = st.rules({"action": "save", "markdown": "## Fiscal year\nOur fiscal year starts 1 July."})
    assert [r["title"] for r in out["rules"]] == ["Fiscal year"]
    assert "Fiscal year" in st.rules({"action": "test", "question": "revenue this fiscal year"})["applied"][0]
    # a fresh Studio on the same database picks the saved file up
    st2 = StudioState(cat.__class__(name="x"), "t", "b")
    st2._load_rules()
    assert [r.title for r in st2.catalog.rules] == ["Fiscal year"]
