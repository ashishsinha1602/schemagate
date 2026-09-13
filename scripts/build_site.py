"""Assemble the GitHub Pages site into ./site.

    pip install markdown && python scripts/build_site.py

Pages:
  /                      the Studio, with real <head> metadata (title, description,
                         Open Graph, Twitter card, canonical, JSON-LD)
  /install/              pip, Docker and the OCI stack, with the version read
                         out of pyproject.toml so it cannot go stale
  /benchmarks/           BENCHMARKS.md rendered as a page
  /local-models/         docs/local-models.md rendered as a page
  /vanna-alternative/    docs/migrating-from-vanna.md rendered as a page
  /cost/                 the token-cost table and a small calculator
  /robots.txt, /sitemap.xml, /llms.txt, /social-preview.png

The three rendered pages read the repository's own markdown instead of
restating it. A number that lives in two places is a number that will
eventually disagree with itself, and the Spider 2.0 figure here was published
wrong twice before it was published right.

Nothing here is a tracker, a font CDN or a third-party script.
"""
from __future__ import annotations

import datetime as dt
import html
import pathlib
import re
import shutil

import markdown

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
BASE = "https://ashishsinha1602.github.io/schemagate"
REPO = "https://github.com/ashishsinha1602/schemagate"
TITLE = "schemagate — identity-scoped schema selection for text-to-SQL"
DESC = ("Shows the model only the tables this caller may read, before any SQL exists, "
        "and cuts prompt tokens 65–97%. Any SQLAlchemy database. pip install schemagate.")

CSS = """
:root{--ink:#161A22;--muted:#5E6779;--line:#DCE1E9;--accent:#0F7B6C;--bg:#F5F7FA;--panel:#fff}
@media(prefers-color-scheme:dark){:root{--ink:#E6E9EF;--muted:#9AA3B5;--line:#2A303C;--accent:#3FBFA9;--bg:#0F1218;--panel:#171B23}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:760px;margin:0 auto;padding:32px 20px 64px}nav{font-size:14px;color:var(--muted);display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px}
a{color:var(--accent)}h1{font-size:30px;line-height:1.2;margin:0 0 12px}h2{font-size:22px;margin:32px 0 8px}
pre{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:12px 14px;overflow:auto;font-size:13px}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.92em}table{border-collapse:collapse;width:100%;font-size:14px}
td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left}th{color:var(--muted);font-weight:500}
.cta{display:inline-block;background:var(--accent);color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none;font-weight:500;margin:8px 8px 8px 0}
input{font:inherit;padding:4px 8px;width:7em;border:1px solid var(--line);border-radius:4px;background:var(--panel);color:var(--ink)}
.muted{color:var(--muted)}
"""

NAV = ('<nav><a href="/schemagate/">Demo</a><a href="/schemagate/install/">Install</a>'
       '<a href="/schemagate/benchmarks/">Benchmarks</a>'
       '<a href="/schemagate/local-models/">Local models</a>'
       '<a href="/schemagate/cost/">Cost</a>'
       '<a href="/schemagate/vanna-alternative/">Coming from Vanna</a>'
       f'<a href="{REPO}">GitHub</a><a href="https://pypi.org/project/schemagate/">PyPI</a></nav>')


def version() -> str:
    """Read it from pyproject rather than writing it down twice."""
    m = re.search(r'^version = "([^"]+)"',
                  (ROOT / "pyproject.toml").read_text("utf-8"), re.M)
    return m.group(1)


def render(md_path: pathlib.Path) -> str:
    """Repository markdown as page HTML, with its relative links repointed.

    `](benchmarks/)` means the directory on GitHub, not a path on this site,
    and a reader who follows it to a 404 has been told something false about
    how carefully the rest was made."""
    md = md_path.read_text("utf-8")
    here = md_path.parent.relative_to(ROOT).as_posix()
    def fix(m: "re.Match[str]") -> str:
        href = m.group(1)
        if href.startswith(("http://", "https://", "#", "mailto:", "/")):
            return m.group(0)
        target = href if here == "." else f"{here}/{href}"
        kind = "tree" if href.endswith("/") else "blob"
        return f"]({REPO}/{kind}/main/{target.rstrip('/')})"
    md = re.sub(r"\]\(([^)]+)\)", fix, md)
    return markdown.markdown(md, extensions=["fenced_code", "tables", "toc"])


def head(title: str, desc: str, path: str, extra: str = "") -> str:
    url = f"{BASE}{path}"
    ld = {
        "@context": "https://schema.org", "@type": "SoftwareApplication",
        "name": "schemagate", "applicationCategory": "DeveloperApplication",
        "operatingSystem": "Any", "url": BASE, "downloadUrl": "https://pypi.org/project/schemagate/",
        "codeRepository": REPO, "license": "https://www.apache.org/licenses/LICENSE-2.0",
        "author": {"@type": "Person", "name": "Ashish Sinha"}, "description": DESC,
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
    }
    import json
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title>"
        f'<meta name="description" content="{html.escape(desc)}">'
        f'<link rel="canonical" href="{url}">'
        '<meta property="og:type" content="website">'
        f'<meta property="og:title" content="{html.escape(title)}">'
        f'<meta property="og:description" content="{html.escape(desc)}">'
        f'<meta property="og:url" content="{url}">'
        f'<meta property="og:image" content="{BASE}/social-preview.png">'
        '<meta property="og:image:width" content="1280"><meta property="og:image:height" content="640">'
        '<meta name="twitter:card" content="summary_large_image">'
        f'<meta name="twitter:title" content="{html.escape(title)}">'
        f'<meta name="twitter:description" content="{html.escape(desc)}">'
        f'<meta name="twitter:image" content="{BASE}/social-preview.png">'
        f'<script type="application/ld+json">{json.dumps(ld)}</script>'
        f"{extra}</head>"
    )


def page(title: str, desc: str, path: str, body: str) -> str:
    return (head(title, desc, path, f"<style>{CSS}</style>")
            + f"<body><main>{NAV}{body}</main></body></html>")


def build_index() -> None:
    studio = (ROOT / "src" / "schemagate" / "studio.html").read_text("utf-8")
    studio = re.sub(r"<title>.*?</title>\s*", "", studio, count=1)   # head() sets it
    # a crawlable summary above the app, invisible in the app's own layout
    intro = ('<div style="position:absolute;left:-9999px;top:auto;width:1px;height:1px;overflow:hidden">'
             '<h1>schemagate: identity-scoped schema selection for text-to-SQL</h1>'
             f'<p>{html.escape(DESC)}</p></div>')
    html_ = (head(TITLE, DESC, "/", "<style>body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>")
             + "<body>" + intro + studio + "</body></html>")
    (SITE / "index.html").write_text(html_, "utf-8")


def build_vanna() -> None:
    md = (ROOT / "docs" / "migrating-from-vanna.md").read_text("utf-8")
    body = markdown.markdown(md, extensions=["fenced_code", "tables"])
    body = body.replace("<h1>", "<h1>", 1)
    body += (f'<p><a class="cta" href="{REPO}">GitHub</a>'
             '<a class="cta" href="/schemagate/">Try the demo</a></p>')
    (SITE / "vanna-alternative").mkdir(parents=True, exist_ok=True)
    (SITE / "vanna-alternative" / "index.html").write_text(page(
        "Vanna alternative for schema selection with access control — schemagate",
        "Vanna was archived in March 2026 and applied identity at execution, after the model saw "
        "the whole schema. schemagate applies it at schema selection. Migration notes.",
        "/vanna-alternative/", body), "utf-8")


def build_benchmarks() -> None:
    body = render(ROOT / "BENCHMARKS.md")
    body += (f'<p><a class="cta" href="{REPO}/tree/main/benchmarks">The scripts</a>'
             '<a class="cta" href="/schemagate/">Try the demo</a></p>')
    (SITE / "benchmarks").mkdir(parents=True, exist_ok=True)
    (SITE / "benchmarks" / "index.html").write_text(page(
        "schemagate on Spider, BIRD and Spider 2.0 — table recall and execution accuracy",
        "Measured table recall on Spider (1,034 questions), BIRD (1,534) and Spider 2.0-lite, "
        "end-to-end execution accuracy, and the two corrections to a published figure.",
        "/benchmarks/", body), "utf-8")


def build_local_models() -> None:
    body = render(ROOT / "docs" / "local-models.md")
    body += (f'<p><a class="cta" href="/schemagate/install/">Install</a>'
             f'<a class="cta" href="{REPO}/blob/main/docs/local-models.md">On GitHub</a></p>')
    (SITE / "local-models").mkdir(parents=True, exist_ok=True)
    (SITE / "local-models" / "index.html").write_text(page(
        "Text-to-SQL with a local model, no API key — schemagate",
        "What schemagate does offline already, what a local model downloads, how to point it at "
        "Ollama or LM Studio instead, and what each option actually sends off the machine.",
        "/local-models/", body), "utf-8")


def build_install() -> None:
    """pip, Docker and the OCI stack.

    Docker first: it is the shortest path from reading this to looking at your
    own schema, because it skips the question of which extra a given database
    driver needs.
    """
    v = version()
    body = f"""
<h1>Install schemagate</h1>
<p class="muted">Apache-2.0. One required dependency (SQLAlchemy). No API key for the part
that selects tables &mdash; that is BM25 plus a hashed embedder, and it runs offline.</p>

<h2>Docker &mdash; nothing to install but Docker</h2>
<pre><code>docker run -p 8770:8770 ghcr.io/ashishsinha1602/schemagate</code></pre>
<p>Opens the Studio on <code>http://localhost:8770</code> with a demo schema &mdash; 42 objects,
3,817 rows &mdash; so there is something to click before you have connected anything. Point it at
your own database with a URL:</p>
<pre><code>docker run -p 8770:8770 \\
  -e SCHEMAGATE_DATABASE_URL=postgresql+psycopg://user:pass@host/db \\
  ghcr.io/ashishsinha1602/schemagate</code></pre>
<p class="muted">The image runs as a non-root user, carries a healthcheck, and is built for
linux/amd64 and linux/arm64. Tags are <code>:latest</code> and the release tag with its
<code>v</code> &mdash; <code>:v{v}</code>. There is no <code>:{v}</code>.</p>

<h2>pip</h2>
<pre><code>pip install schemagate                 # the library, the CLI and the Studio
pip install "schemagate[postgres]"     # or [oracle], [mysql], [mssql]
pip install "schemagate[databases]"    # all four drivers
</code></pre>
<p class="muted">The Studio needs no extra &mdash; it is a single page served by the standard
library. The driver extras are only the database driver.</p>
<pre><code>schemagate demo                                    # a schema to look at, no database
schemagate studio --url "postgresql://localhost/app"
schemagate select "revenue by month" --url "postgresql://localhost/app" --prompt
</code></pre>
<p>In Python, the whole of it:</p>
<pre><code>from schemagate import Catalog, Principal

cat = Catalog().bootstrap("postgresql://localhost/app")
cat.restrict("hr_compensation", ["payroll"])       # who may even see it

sel = cat.select("revenue by month", top_k=6,
                 principal=Principal("okta:jdoe", roles={"finance"}))

sel.prompt_fragment()   # compact DDL for just those tables, for the system prompt
sel.explain()           # why each object was picked
</code></pre>

<h2>Oracle Cloud, as a stack</h2>
<p>A Resource Manager stack that builds an Always Free VM with the Studio behind TLS:</p>
<p><a class="cta" href="{REPO}/releases/latest/download/schemagate-oci-stack.zip">Download the stack .zip</a>
<a class="cta" href="https://registry.terraform.io/modules/ashishsinha1602/schemagate/oci/latest">Terraform Registry</a></p>

<h2>Without an API key at all</h2>
<p>Selecting tables never calls a model. Writing the SQL does, and that can be a model on your own
machine, a server you already run, or a chat window you have open anyway &mdash;
<a href="/schemagate/local-models/">the local-model page</a> is the detail.</p>

<h2>Also</h2>
<ul>
<li><b>MCP server</b> &mdash; <code>SCHEMAGATE_DATABASE_URL=... python -m schemagate.mcp_server</code> over stdio, or <code>docker run -e SCHEMAGATE_DATABASE_URL=demo -p 8765:8765 ghcr.io/ashishsinha1602/schemagate mcp</code>, which serves streamable-http on 8765 because stdio has no meaning across a container boundary. Needs <code>[mcp]</code>; the image has it.</li>
<li><b>LangChain</b> &mdash; <code>SchemagateRetriever</code>, from <code>schemagate.integrations.langchain</code>. Needs <code>[langchain]</code>.</li>
<li><b>Oracle 23ai</b> &mdash; a native VECTOR store, so the index lives in the database.</li>
</ul>

<p><a class="cta" href="/schemagate/">Try it in the browser first</a>
<a class="cta" href="{REPO}">GitHub</a></p>
"""
    (SITE / "install").mkdir(parents=True, exist_ok=True)
    (SITE / "install" / "index.html").write_text(page(
        "Install schemagate — Docker, pip, or an OCI stack",
        f"docker run -p 8770:8770 ghcr.io/ashishsinha1602/schemagate, or pip install schemagate. "
        f"Version {v}, Apache-2.0, one dependency, no API key needed to select tables.",
        "/install/", body), "utf-8")


def build_cost() -> None:
    rows = [("Commerce", 42, 2483, 604), ("Clinical claims", 27, 1568, 543),
            ("Claims warehouse (star)", 51, 3312, 880), ("Bank ledger and trading", 39, 2255, 637),
            ("IoT telemetry", 40, 2125, 448), ("Hostile (4 schemas, copies of everything)", 260, 16095, 444)]
    table = "".join(f"<tr><td>{n}</td><td>{o}</td><td>{f:,}</td><td>{s:,}</td><td><b>{(1-s/f)*100:.0f}%</b></td></tr>"
                    for n, o, f, s in rows)
    body = f"""
<h1>What text-to-SQL prompts cost, and what schema selection saves</h1>
<p class="muted">Measured on schemagate's six test schemas with its built-in token estimator,
averaged over each schema's golden questions. Reproduce with <code>python tests/bench.py</code>.</p>
<table><tr><th>schema</th><th>objects</th><th>full schema, every call</th><th>schemagate, average</th><th>reduction</th></tr>{table}</table>
<p>The selection stays at about six tables however large the schema is, so the saving grows with the
database. Real databases look like the last row.</p>
<h2>Your numbers</h2>
<p>Tokens per question: full schema <input id="tf" type="number" value="16095"> → selected <input id="ts" type="number" value="444">.
Questions per day <input id="q" type="number" value="5000">. Input price $<input id="p" type="number" step="0.05" value="3.00"> per million tokens.</p>
<p id="out" style="font-size:20px"></p>
<p class="muted">This multiplies four numbers you typed; it knows nothing about your provider's actual pricing. The
<a href="/schemagate/">demo</a> fills the token counts from a live question.</p>
<h2>Two things that cost nothing</h2>
<p>The selector never calls a model — BM25 plus a hashed embedder, offline, milliseconds. And the optional
one-sentence table descriptions can be written by any chat window you already have instead of an API key:
<code>schemagate describe</code> prints the prompt and takes the JSON reply.</p>
<p><a class="cta" href="https://pypi.org/project/schemagate/">pip install schemagate</a><a class="cta" href="{REPO}">GitHub</a></p>
<script>
function m(x){{return x>=1000?"$"+Math.round(x).toLocaleString():"$"+x.toFixed(2)}}
function r(){{const g=i=>Math.max(0,+document.getElementById(i).value||0);const per=t=>t*g("q")*30/1e6*g("p");
const f=per(g("tf")),s=per(g("ts"));document.getElementById("out").innerHTML=
"<s style='color:var(--muted)'>"+m(f)+"</s> → <b style='color:var(--accent)'>"+m(s)+"</b> per month on schema tokens; <b>"+m(Math.max(0,f-s))+"</b> saved"}}
for(const i of ["tf","ts","q","p"])document.getElementById(i).oninput=r;r();
</script>"""
    (SITE / "cost").mkdir(parents=True, exist_ok=True)
    (SITE / "cost" / "index.html").write_text(page(
        "Text-to-SQL prompt token cost calculator — schemagate",
        "Full-schema prompts vs per-question table selection: measured token counts on six schemas "
        "(65–97% fewer tokens) and a calculator for your own volume and price.",
        "/cost/", body), "utf-8")


def build_misc() -> None:
    """Explicit "utf-8" on every write: the default is the platform's, which on
    Windows is cp1252, and llms.txt has an en dash in it. The CI runner is Linux,
    so the deployed file was right while the builder was wrong."""
    shutil.copy(ROOT / "docs" / "media" / "social-preview.png", SITE / "social-preview.png")
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n", "utf-8")
    (SITE / "google7c61fe50e3637040.html").write_text(
        "google-site-verification: google7c61fe50e3637040.html\n", "utf-8")
    today = dt.date.today().isoformat()
    urls = "".join(f"<url><loc>{BASE}{p}</loc><lastmod>{today}</lastmod></url>"
                   for p in ["/", "/install/", "/benchmarks/", "/local-models/",
                             "/cost/", "/vanna-alternative/"])
    (SITE / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>', "utf-8")
    (SITE / "llms.txt").write_text(f"""# schemagate

> {DESC}

schemagate is an open-source Python library (Apache-2.0, by Ashish Sinha) for text-to-SQL and NL2SQL
systems. Given a question and a caller identity, it returns the handful of tables and views the model
needs, with every object the caller may not read removed before ranking, plus the DDL fragment for the
prompt. It reflects any SQLAlchemy database (Oracle, PostgreSQL, SQL Server, MySQL, SQLite), needs no
API key, ships an MCP server, a LangChain retriever, a CLI and a browser Studio, and has a native
Oracle 23ai VECTOR store.

- Install: pip install schemagate  --  or  docker run -p 8770:8770 ghcr.io/ashishsinha1602/schemagate
- Repository: {REPO}
- PyPI: https://pypi.org/project/schemagate/
- Demo (runs in the browser, no database): {BASE}/
- Install, Docker and the OCI stack: {BASE}/install/
- Benchmarks (Spider, BIRD, Spider 2.0): {BASE}/benchmarks/
- Running it with a local model, no API key: {BASE}/local-models/
- Token cost table and calculator: {BASE}/cost/
- Migrating from Vanna: {BASE}/vanna-alternative/
- What was tested and what broke: {REPO}/blob/main/TESTING.md
""", "utf-8")


def main() -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    build_index(); build_install(); build_benchmarks(); build_local_models()
    build_vanna(); build_cost(); build_misc()
    for p in sorted(SITE.rglob("*")):
        if p.is_file():
            print(f"{p.stat().st_size:9,d}  {p.relative_to(SITE)}")


if __name__ == "__main__":
    main()
