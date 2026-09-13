"""Read a file whose path is too long for the Windows API.

Spider 2.0 nests a table's JSON under
`databases/<engine>/<db>/<project.dataset>/<table>.json`, and those run to 337
characters. Windows refuses to open a path over 260 unless it is prefixed
`\\?\`, so `open()` raised FileNotFoundError on 3,056 of 7,892 files -- 39% of
the benchmark -- and a `except Exception: continue` in the loader turned that
into "this database has fewer tables" rather than an error.

Retrieval scored against a schema that is missing two fifths of its tables is
easier than the benchmark intends, so this is not a cosmetic bug: it inflates
the result.
"""
import json
import pathlib


def read_text(path) -> str:
    p = pathlib.Path(path).resolve()
    s = str(p)
    if len(s) > 250 and not s.startswith("\\\\"):
        s = "\\\\?\\" + s
    with open(s, encoding="utf-8") as fh:
        return fh.read()


def read_json(path):
    return json.loads(read_text(path))


if __name__ == "__main__":
    root = pathlib.Path("Spider2/spider2-lite/resource/databases").resolve()
    tot = ok = fail = 0
    for f in root.rglob("*.json"):
        tot += 1
        try:
            read_json(f)
            ok += 1
        except Exception:                                # noqa: BLE001
            fail += 1
    print("files %d | readable %d | still failing %d" % (tot, ok, fail))
