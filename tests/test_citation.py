"""CITATION.cff has to follow the package, like server.json and the stack do.

It said 0.1.0 while PyPI was on 0.1.57. Nothing checked it, and a citation
file is the one place where being fifty-seven releases stale is worst: a
paper citing this work would name a version whose numbers, retrieval and
licence text are all different from the one they ran.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CITATION = ROOT / "CITATION.cff"

pytestmark = pytest.mark.skipif(not CITATION.is_file(), reason="no CITATION.cff")


def _cff() -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(CITATION.read_text("utf-8"))


def _package_version() -> str:
    m = re.search(r'^version = "([^"]+)"',
                  (ROOT / "pyproject.toml").read_text("utf-8"), re.M)
    assert m, "no version in pyproject.toml"
    return m.group(1)


def test_it_is_valid_yaml_with_the_required_keys():
    d = _cff()
    for key in ("cff-version", "message", "title", "authors", "version",
                "date-released", "license"):
        assert key in d, f"CITATION.cff has no {key!r}"


def test_the_version_matches_the_package():
    got, want = str(_cff()["version"]), _package_version()
    assert got == want, f"CITATION.cff says {got}, the package is {want}"


def test_the_release_date_is_a_real_date_and_not_in_the_future():
    raw = _cff()["date-released"]
    day = raw if isinstance(raw, datetime.date) else datetime.date.fromisoformat(str(raw))
    assert day <= datetime.date.today(), f"date-released {day} is in the future"
    assert day.year >= 2026, day


def test_the_licence_agrees_with_pyproject():
    d = _cff()
    text = (ROOT / "pyproject.toml").read_text("utf-8")
    assert d["license"] in text, f"CITATION.cff licence {d['license']!r} not in pyproject"
