"""The Pages site tells people how to install and run this. Nothing checked it.

Written after the install page was drafted from memory and five of its claims
were wrong: an extra named `[postgresql]` (it is `[postgres]`), a `[studio]`
extra (there is none -- the Studio is built in), `schemagate connect` and
`schemagate mcp` (neither is a subcommand), and `Catalog.from_url(...,
identity=)` (it is `Catalog().bootstrap(url)` with `principal=`). Every one
would have shipped to a stranger's terminal.

So these read the published HTML back and check each claim against the thing
itself: extras against pyproject, subcommands against argparse, symbols
against the package, links against the pages actually built.
"""
from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
BUILD = ROOT / "scripts" / "build_site.py"

PAGES = ["/", "/install/", "/benchmarks/", "/local-models/",
         "/row-level-security/", "/cost/", "/vanna-alternative/"]

pytestmark = pytest.mark.skipif(not BUILD.is_file(), reason="no site builder in this tree")


@pytest.fixture(scope="module")
def site() -> Path:
    pytest.importorskip("markdown", reason="site builder needs markdown")
    out = subprocess.run([sys.executable, str(BUILD)], cwd=ROOT,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-2000:]
    return SITE


def _text(site: Path, path: str) -> str:
    """A page's rendered body as plain text, entities resolved."""
    f = site / (path.strip("/") or ".") / "index.html"
    if path == "/":
        f = site / "index.html"
    body = f.read_text("utf-8").split("</nav>", 1)[-1]
    return html.unescape(re.sub(r"<[^>]+>", " ", body))


def test_every_page_is_built(site: Path):
    for p in PAGES:
        f = site / "index.html" if p == "/" else site / p.strip("/") / "index.html"
        assert f.is_file() and f.stat().st_size > 500, f"{p} missing or near-empty"


def test_no_internal_link_points_at_a_page_that_does_not_exist(site: Path):
    known = {p for p in PAGES}
    for f in site.rglob("*.html"):
        for href in set(re.findall(r'href="(/schemagate[^"#]*)"', f.read_text("utf-8"))):
            target = href.replace("/schemagate", "") or "/"
            assert target in known, f"{f.name} links to {href}, which is not a page"


def test_every_extra_the_install_page_names_exists(site: Path):
    """`pip install "schemagate[postgresql]"` is a paste that fails."""
    try:
        import tomllib
    except ModuleNotFoundError:                      # 3.9/3.10
        pytest.skip("tomllib is 3.11+")
    have = set(tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
               ["project"]["optional-dependencies"])
    named = set(re.findall(r"schemagate\[(\w+)\]", _text(site, "/install/")))
    named |= set(re.findall(r"\[(\w+)\]", _text(site, "/install/").split("# or", 1)[-1][:60]))
    assert named, "the install page names no extras at all -- did it change shape?"
    assert not (named - have), f"install page names extras that do not exist: {sorted(named - have)}"


def test_every_subcommand_the_install_page_names_is_real(site: Path):
    from schemagate.cli import build_parser              # noqa: PLC0415
    real = set()
    for action in build_parser()._subparsers._group_actions:   # noqa: SLF001
        real |= set(action.choices)
    # Only `schemagate <word>` used as a command: not `from schemagate import`,
    # and not `ghcr.io/ashishsinha1602/schemagate mcp`, which is the image's own
    # shorthand and deliberately not a CLI subcommand.
    named = set(re.findall(r"(?<![\w/])schemagate (\w+)", _text(site, "/install/")))
    named -= {"import"}
    assert named, "the install page shows no commands at all -- did it change shape?"
    bogus = named - real
    assert not bogus, f"install page names subcommands that do not exist: {sorted(bogus)}"


def test_the_python_snippet_on_the_install_page_is_the_real_api(site: Path):
    """Names, not behaviour -- behaviour is the rest of the suite's job."""
    import schemagate                                       # noqa: PLC0415
    body = _text(site, "/install/")
    for symbol in re.findall(r"\bCatalog\(\)\.(\w+)", body):
        assert hasattr(schemagate.Catalog, symbol), f"Catalog has no {symbol}()"
    for symbol in re.findall(r"\bsel\.(\w+)", body):
        assert hasattr(schemagate.Selection, symbol), f"Selection has no {symbol}"
    assert "principal=" in body, "the snippet must show the identity argument by its real name"
    assert "identity=" not in body, "select() takes principal=, not identity="


def test_the_version_on_the_page_is_this_version(site: Path):
    v = re.search(r'^version = "([^"]+)"',
                  (ROOT / "pyproject.toml").read_text("utf-8"), re.M).group(1)
    body = _text(site, "/install/")
    assert f":v{v}" in body, f"install page does not name the current tag v{v}"


def test_the_image_tag_is_the_one_the_workflow_pushes(site: Path):
    """The release workflow tags with `github.event.release.tag_name`, so the
    tag carries a `v`. A page that says `:0.1.52` sends people to a 404."""
    wf = (ROOT / ".github" / "workflows" / "publish.yml").read_text("utf-8")
    assert "schemagate:${{ github.event.release.tag_name }}" in wf, (
        "the tag scheme changed -- this test and the install page both need rereading")
    body = _text(site, "/install/")
    assert re.search(r":v\d+\.\d+\.\d+", body), "install page names no v-prefixed tag"


def test_sitemap_and_llms_txt_list_every_page(site: Path):
    sitemap = (site / "sitemap.xml").read_text("utf-8")
    for p in PAGES:
        assert f"/schemagate{p}" in sitemap or sitemap.count(p) , f"{p} missing from sitemap.xml"
    llms = (site / "llms.txt").read_text("utf-8")
    for p in ["/install/", "/benchmarks/", "/local-models/",
              "/row-level-security/", "/cost/"]:
        assert p in llms, f"{p} missing from llms.txt"


def test_rendered_docs_carry_their_own_content(site: Path):
    """They render repository markdown; if a file moves, the page should fail
    the build rather than publish an empty shell."""
    bench = _text(site, "/benchmarks/")
    assert "Spider" in bench and "BIRD" in bench and len(bench) > 4000
    local = _text(site, "/local-models/")
    assert "Ollama" in local and len(local) > 3000


def test_no_relative_markdown_link_survived_into_the_html(site: Path):
    """`](benchmarks/)` means GitHub, not this site, and a reader who follows
    it to a 404 has been told something false about the rest."""
    for path in ("/benchmarks/", "/local-models/", "/vanna-alternative/"):
        f = SITE / path.strip("/") / "index.html"
        for href in re.findall(r'href="([^"]+)"', f.read_text("utf-8")):
            assert href.startswith(("http://", "https://", "/", "#", "mailto:")), (
                f"{path} has an unresolved relative link: {href}")


# --- honest <lastmod>, and IndexNow ------------------------------------------

def _build_site_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_site", BUILD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git_date(paths) -> str:
    dates = []
    for rel in paths:
        out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", rel],
                             cwd=ROOT, capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            dates.append(out.stdout.strip())
    return max(dates) if dates else ""


def test_sitemap_lastmod_is_the_last_commit_touching_each_page(site: Path):
    """A dependency bump used to announce that all seven pages changed today.
    Google discounts a lastmod it can see is unreliable, so each date is the
    newest commit that touched the page's sources, and nothing else."""
    inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT,
                            capture_output=True, text=True)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        pytest.skip("not a git work tree; lastmod falls back to today by design")
    mod = _build_site_module()
    sitemap = (site / "sitemap.xml").read_text("utf-8")
    for path, sources in mod.PAGES.items():
        want = _git_date(sources)
        if not want:
            pytest.skip(f"git has no history for {sources} (shallow clone?)")
        m = re.search(rf"<loc>{re.escape(mod.BASE + path)}</loc><lastmod>([0-9-]+)</lastmod>", sitemap)
        assert m, f"{path} missing from sitemap.xml"
        assert m.group(1) == want, f"{path}: sitemap says {m.group(1)}, git says {want} for {sources}"


def test_pages_map_matches_what_is_built_and_names_real_sources(site: Path):
    mod = _build_site_module()
    assert sorted(mod.PAGES) == sorted(PAGES), "build_site.PAGES and the pages built disagree"
    for path, sources in mod.PAGES.items():
        assert sources, f"{path} names no source"
        for rel in sources:
            assert (ROOT / rel).is_file(), f"{path}: source {rel} does not exist"


def test_indexnow_key_file_and_payload_agree(site: Path):
    """IndexNow verifies a submission by fetching {keyLocation}, whose body
    must equal the key, and rejects any URL that is not under the key file's
    directory. Get either wrong and every submission is silently dropped."""
    import json
    mod = _build_site_module()
    key_file = site / f"{mod.INDEXNOW_KEY}.txt"
    assert key_file.is_file(), "IndexNow key file not built"
    assert key_file.read_text("utf-8").strip() == key_file.stem
    payload = json.loads((site / "indexnow.json").read_text("utf-8"))
    assert payload["key"] == mod.INDEXNOW_KEY
    assert payload["keyLocation"] == f"{mod.BASE}/{mod.INDEXNOW_KEY}.txt"
    assert payload["host"] == mod.BASE.split("//", 1)[1].split("/", 1)[0]
    prefix = payload["keyLocation"].rsplit("/", 1)[0] + "/"
    for url in payload["urlList"]:
        assert url.startswith(prefix), f"{url} is outside {prefix}; IndexNow would reject it"
        assert url[len(mod.BASE):] in mod.PAGES


def test_indexnow_lists_the_pages_whose_newest_commit_is_head(site: Path, monkeypatch):
    """Without SITE_SINCE the rule is "changed in HEAD": the pages whose
    newest source commit is HEAD, and only those. A calendar-date rule was
    wrong near midnight, because a squash-merge carries the merging user's
    timezone and the runner's clock is UTC."""
    import json
    inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT,
                            capture_output=True, text=True)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        pytest.skip("not a git work tree")
    monkeypatch.delenv("SITE_SINCE", raising=False)
    mod = _build_site_module()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    want = {f"{mod.BASE}{p}" for p, src in mod.PAGES.items() if mod.newest_commit(src) == head}
    got = set(json.loads((site / "indexnow.json").read_text("utf-8"))["urlList"])
    assert got == want
