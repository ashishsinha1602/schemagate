"""The image is built on a Linux runner from a checkout made on Windows, and
nothing else in the suite runs it, so a mode that is wrong only there ships.

0.1.51's published image could not start -- `exec:
"/usr/local/bin/docker-entrypoint.sh": permission denied` -- while the image
built locally from the same commit was fine. git recorded the script 100644
because a Windows checkout cannot carry an exec bit; Docker Desktop hands a
Windows build context 0777 and hid it; the runner did not.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "Dockerfile"
ENTRYPOINT = ROOT / "docker-entrypoint.sh"

pytestmark = pytest.mark.skipif(not DOCKERFILE.is_file(), reason="no Dockerfile in this tree")


def _index_mode(path: Path) -> str:
    """The mode git has, which is the mode the builder copies -- not the mode
    the working tree reports, which on Windows is invented."""
    out = subprocess.run(["git", "ls-files", "-s", "--", path.name],
                         cwd=ROOT, capture_output=True, text=True)
    if out.returncode or not out.stdout.strip():
        pytest.skip("not a git checkout")
    return out.stdout.split()[0]


def test_entrypoint_is_executable_in_the_index():
    assert _index_mode(ENTRYPOINT) == "100755", (
        "docker-entrypoint.sh is not executable in git, so the image built on "
        "a Linux runner cannot start it: git update-index --chmod=+x")


def test_dockerfile_sets_the_mode_itself():
    """Belt as well as braces: a future checkout or a `COPY` added elsewhere
    should not be able to reintroduce this."""
    assert "--chmod=0755 docker-entrypoint.sh" in DOCKERFILE.read_text(), (
        "COPY should set the mode rather than trust the checkout's")


def test_entrypoint_is_a_script_the_kernel_can_start():
    """An exec bit on a file with no shebang fails the same way."""
    assert ENTRYPOINT.read_bytes().startswith(b"#!"), "no shebang"
