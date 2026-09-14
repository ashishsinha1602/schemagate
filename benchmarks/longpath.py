r"""Read a file whose path is too long for the Windows API.

Spider 2.0 nests a table's JSON under
`databases/<engine>/<db>/<project.dataset>/<table>.json`. Windows refuses to
open a path over 260 characters unless it is prefixed `\\?\`, so `open()`
raises FileNotFoundError, and a `except Exception: continue` in a loader turns
that into "this database has fewer tables" rather than an error. Retrieval
scored against a schema missing part of itself is easier than the benchmark
intends, so this is not cosmetic: it inflates the result.

How many files it hits is a property of your directory, not of Spider 2.0
------------------------------------------------------------------------
The limit applies to the whole absolute path, so the count moves with where
the repository is cloned. Measured on this data (n=7,892 files):

    longest path relative to databases/    154 chars   (median 72)
    any checkout rooted deeper than 105 chars loses at least one file
    databases/ root at 182 chars           2,868 of 7,892 unreadable  (36%)
    databases/ root at 183 chars           3,056 of 7,892 unreadable  (39%)

One character of directory depth moves it by 188 files. BENCHMARKS.md's
earlier "3,056 files, 39% of the benchmark" was measured in a checkout one
character deeper than the one that now reports 2,868 -- both are correct
about their own directory, and neither is a fact about the benchmark. The
durable numbers are the relative ones: 154 characters at the deepest, and a
105-character budget for everything to the left of it.

`read_text` prefixes at len > 250 rather than 260. That margin is deliberate
-- a relative path handed in, or a caller who has already `resolve()`d
somewhere deeper, should not sit one character from failing -- so the number
of paths it *prefixes* (4,809 in this checkout) is larger than the number
that would actually have failed (2,868). Those are different quantities and
the docstring used to run them together.
"""
import json
import pathlib

#: Below the 260 limit by a margin, so a path that grows slightly -- a
#: relative path resolved from a deeper cwd -- does not silently start failing.
_PREFIX_OVER = 250


def read_text(path) -> str:
    p = pathlib.Path(path).resolve()
    s = str(p)
    if len(s) > _PREFIX_OVER and not s.startswith("\\\\"):
        s = "\\\\?\\" + s
    with open(s, encoding="utf-8") as fh:
        return fh.read()


def read_json(path):
    return json.loads(read_text(path))


def survey(root) -> dict:
    """What this checkout's layout costs, in the form that travels.

    Reported relative to `root` as well as absolutely, because the absolute
    count is true only of the machine that produced it.
    """
    root = pathlib.Path(root).resolve()
    files = list(root.rglob("*.json"))
    rel = [len(str(p.relative_to(root))) for p in files]
    return {
        "files": len(files),
        "root_len": len(str(root)),
        "rel_max": max(rel) if rel else 0,
        "rel_median": sorted(rel)[len(rel) // 2] if rel else 0,
        "over_260": sum(1 for r in rel if len(str(root)) + 1 + r > 260),
        "prefixed": sum(1 for r in rel if len(str(root)) + 1 + r > _PREFIX_OVER),
        "root_budget": 260 - (max(rel) if rel else 0) - 1,
    }


if __name__ == "__main__":
    import sys
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                        else "Spider2/spider2-lite/resource/databases")
    s = survey(root)
    print("root                      %s" % root.resolve())
    print("root length               %d chars" % s["root_len"])
    print("files                     %d" % s["files"])
    print("longest relative path     %d chars (median %d)" % (s["rel_max"], s["rel_median"]))
    print("unreadable without \\\\?\\   %d  (%.0f%% -- true of THIS checkout only)"
          % (s["over_260"], 100 * s["over_260"] / max(1, s["files"])))
    print("prefixed by read_text     %d  (threshold %d, deliberately lower)"
          % (s["prefixed"], _PREFIX_OVER))
    print("root budget               %d chars before any file is lost" % s["root_budget"])
    tot = ok = fail = 0
    for f in root.rglob("*.json"):
        tot += 1
        try:
            read_json(f)
            ok += 1
        except Exception:                                # noqa: BLE001
            fail += 1
    print("read back                 %d readable, %d still failing" % (ok, fail))
