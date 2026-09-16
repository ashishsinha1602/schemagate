"""Assemble studio.html from the template, the JS port, blake2b and the schemas.

Produces two copies: ``studio/studio.html`` (published as the demo link) and
``schemagate/src/schemagate/studio.html`` (served by ``schemagate studio`` against a real
database, where the Python backend replaces the in-browser selector).
"""
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
PKG = HERE.parent / "src" / "schemagate"

subprocess.run([sys.executable, str(HERE / "export_schemas.py")], check=True)
schemas = json.loads((HERE / "schemas.json").read_text("utf-8"))

# sample descriptions: what a competent model writes for these objects, in
# business language. Bundled so the "AI descriptions" toggle works offline.
sys.path.insert(0, str(HERE.parent / "tests"))
from test_ai_cataloging import _CANNED           # noqa: E402
from test_warehouse import _GRAIN_AWARE          # noqa: E402
from test_complex_schema import _TRANSLATIONS    # noqa: E402
from test_domains import DESCRIPTIONS as _DOMAIN_DESC  # noqa: E402

descriptions = {
    "commerce": _CANNED,
    "warehouse": _GRAIN_AWARE,
    "hostile": _TRANSLATIONS,
    "finance": _DOMAIN_DESC["finance"],
    "telemetry": _DOMAIN_DESC["telemetry"],
    "clinical": {
        "v_claim_denial_rate": "How often each payer denies claims: denied versus total per payer.",
        "v_readmission": "Inpatient stays with length of stay, for readmission analysis.",
        "v_chronic_cohort": "Members who have a chronic diagnosis on record.",
        "v_generic_dispensing": "Pharmacy fills and cost by generic drug name.",
        "clm_remittance": "Payment checks issued against adjudicated claims.",
    },
}

# --------------------------------------------------------------------------
# Refuse to run when the template is behind the file this would overwrite.
#
# This script has not been run since 0.1.33. Everything since -- the
# answer-first layout, the vertical database picker, the identity controls in
# the rail, the recorded answers -- went straight into
# src/schemagate/studio.html, which is what scripts/build_site.py publishes and
# what `schemagate studio` serves. The template is around 1,300 lines behind
# it, so running this would silently revert all of it: a build that destroys
# the thing it claims to produce.
#
# Rather than delete the pipeline, refuse while the output is far larger than
# what would replace it, and say what to do instead. --force is for whoever
# eventually reconciles the two.
existing = PKG / "studio.html"
if existing.is_file() and "--force" not in sys.argv:
    have = len(existing.read_text("utf-8").splitlines())
    tmpl = len((HERE / "studio.template.html").read_text("utf-8").splitlines())
    if have > tmpl + 200:
        sys.exit(
            "refusing to build: %s is %d lines, the template is %d.\n"
            "The template stopped tracking that file at 0.1.33, so this build\n"
            "would revert every change since. Edit src/schemagate/studio.html\n"
            "directly (its JSON islands are read and written by\n"
            "studio/islands.py), or re-run with --force once the template has\n"
            "been brought back into line." % (existing, have, tmpl))


template = (HERE / "studio.template.html").read_text("utf-8")
html = (template
        .replace("__BLAKE__", (HERE / "blake2b.browser.js").read_text("utf-8"))
        .replace("__SCHEMAGATE_JS__", (HERE / "schemagate.js").read_text("utf-8"))
        .replace("__SCHEMAS_JSON__", json.dumps(schemas, ensure_ascii=False).replace("</", "<\\/"))
        .replace("__DESCRIPTIONS_JSON__", json.dumps(descriptions, ensure_ascii=False).replace("</", "<\\/")))

(HERE / "studio.html").write_text(html, "utf-8")
(PKG / "studio.html").write_text(html, "utf-8")
print(f"studio.html: {len(html):,} bytes  ->  {HERE / 'studio.html'}  and  {PKG / 'studio.html'}")
