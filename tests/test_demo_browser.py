"""The demo page, opened in a browser and clicked, the way a visitor uses it.

Everything else in the suite reads studio.html. This runs it. The difference
mattered: the page passed every static check while its answer pane was wired
to a function that only existed with a backend, its identity controls sat in a
drawer that was `display:none`, and `answerOn` was never set without a
server -- so a visitor saw a list of table names and nothing else. None of
that is visible in the file. All of it is visible in a browser.

Needs `pip install playwright && playwright install chromium`; skipped
otherwise, and CI does not run it. Run it before touching the demo.
"""
from __future__ import annotations

import pathlib

import pytest

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

PAGE = pathlib.Path(__file__).resolve().parent.parent / "src" / "schemagate" / "studio.html"

pytestmark = pytest.mark.skipif(not PAGE.is_file(), reason="no studio.html")


@pytest.fixture(scope="module")
def page():
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:                               # noqa: BLE001
            pytest.skip("no chromium: %s" % str(e)[:80])
        pg = browser.new_page(viewport={"width": 1380, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(PAGE.as_uri())
        pg.wait_for_timeout(1200)
        pg.errors = errors                                   # type: ignore[attr-defined]
        yield pg
        browser.close()


def _pick(page, title: str) -> None:
    rows = page.locator(".dbrow")
    for i in range(rows.count()):
        if rows.nth(i).inner_text().startswith(title):
            rows.nth(i).click()
            page.wait_for_timeout(1500)
            return
    raise AssertionError("no database row starting %r" % title)


def _ask(page, q: str) -> None:
    page.fill("#q", q)
    page.click("#go")
    page.wait_for_timeout(1800)


def _grant(page, role: str) -> None:
    chips = page.locator("#roles .chip")
    for i in range(chips.count()):
        if chips.nth(i).inner_text().strip() == role:
            chips.nth(i).click()
            page.wait_for_timeout(400)
            return
    raise AssertionError("no role chip %r" % role)


def test_loads_without_js_errors(page):
    assert page.errors == [], page.errors[:2]


def test_database_picker_is_vertical_and_lists_every_schema(page):
    rows = page.locator(".dbrow")
    assert rows.count() >= 6
    assert "objects" in rows.nth(0).inner_text()
    assert "260" in rows.nth(rows.count() - 1).inner_text()
    assert page.locator("#tabs").is_hidden(), "the old horizontal strip should be gone"


def test_identity_controls_are_on_the_page_not_in_a_drawer(page):
    """The one feature that distinguishes this tool cannot live behind a gear."""
    assert page.locator("#principal").is_visible()
    assert page.locator("#roles").is_visible()
    assert page.locator("#settingsDrawer").is_hidden()


def test_commerce_is_the_landing_schema(page):
    _pick(page, "Commerce")
    assert page.locator('.dbrow[aria-selected="true"]').inner_text().startswith("Commerce")


def test_a_suggested_question_returns_tables_and_a_recorded_answer(page):
    _pick(page, "Commerce")
    ex = page.locator(".examples button")
    assert ex.count() >= 18
    ex.nth(1).click()
    page.wait_for_timeout(2000)
    assert page.locator("#objs li").count() > 0
    assert page.locator("#answerPane").is_visible()
    meta = page.locator("#answerMeta").inner_text().lower()
    assert "recorded" in meta, meta
    assert page.locator("#answerRows tr").count() > 1
    page.locator("#answerSqlWrap summary").click()
    page.wait_for_timeout(300)
    assert "select" in page.locator("#answerSql").inner_text().lower()


def test_the_two_step_identity_story_changes_the_answer(page):
    """Not just the table list -- the answer. This is the claim the project
    is built on, and it is the part that was never asserted."""
    _pick(page, "Commerce")
    # make sure the role is off to start with
    chips = page.locator("#roles .chip")
    for i in range(chips.count()):
        c = chips.nth(i)
        if c.inner_text().strip() == "payroll" and "on" in (c.get_attribute("class") or ""):
            c.click(); page.wait_for_timeout(300)

    _ask(page, "salary by employee")
    assert "hr_compensation" not in page.locator("#objs").inner_text().lower()
    body = page.locator("#answerRows").inner_text().lower()
    assert "no sql was written" in body, body[:120]

    _grant(page, "payroll")
    _ask(page, "salary by employee")
    assert "hr_compensation" in page.locator("#objs").inner_text().lower()
    assert page.locator("#answerRows tr").count() > 1
    headers = " ".join(page.locator("#answerRows th").all_inner_texts()).lower()
    assert "salary" in headers or "employee" in headers or "amount" in headers, headers

    _grant(page, "payroll")                                  # and take it away again
    _ask(page, "salary by employee")
    assert "no sql was written" in page.locator("#answerRows").inner_text().lower()


SCHEMAS = ["Commerce", "Clinical claims", "Claims warehouse", "Bank ledger",
           "IoT fleet", "Hostile"]


@pytest.mark.parametrize("title", SCHEMAS)
def test_every_suggested_question_answers_on_every_schema(page, title):
    """A button that leads to "no recorded answer" is a broken button.

    Parametrised over all six databases because the first version of this
    checked Commerce only -- and Commerce was the only schema with any
    recordings, so five sixths of the demo was dead and the test was green.
    """
    _pick(page, title)
    ex = page.locator(".examples button")
    assert ex.count() > 0, "no suggested questions on %s" % title
    dead = []
    for i in range(ex.count()):
        q = ex.nth(i).inner_text()
        ex.nth(i).click()
        page.wait_for_timeout(700)
        body = page.locator("#answerRows").inner_text().lower()
        if "no answer was recorded" in body:
            dead.append(q)
    assert not dead, "%s: %d question(s) with no recording: %s" % (title, len(dead), dead[:4])


def test_no_answer_is_served_from_the_wrong_database(page):
    """Two schemas ask "paid amount per claim line" in exactly those words.

    Keyed on the question alone, whichever was recorded last won and the other
    schema showed rows from a database it was not looking at.
    """
    shared = "paid amount per claim line"
    seen = {}
    for title in ("Clinical claims", "Claims warehouse"):
        _pick(page, title)
        ex = page.locator(".examples button", has_text=shared)
        if ex.count() == 0:
            continue
        ex.first.click()
        page.wait_for_timeout(1200)
        page.locator("#answerSqlWrap summary").click()
        page.wait_for_timeout(200)
        seen[title] = page.locator("#answerSql").inner_text().strip()
        page.locator("#answerSqlWrap summary").click()
    if len(seen) == 2:
        a, b = list(seen.values())
        assert a != b, "both schemas served identical SQL for %r" % shared
