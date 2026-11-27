"""Re-time every final prediction against the ORIGINAL query with our own tool (never the hidden reference).
Writes self_check.jsonl: id, identical, speedup_vs_original. Used only to pick tasks for a second agent pass."""
import json, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

files = [Path(p) for p in sys.argv[1:-1]]
out = Path(sys.argv[-1])
done = {json.loads(l)["id"] for l in open(out, encoding="utf-8")} if out.exists() else set()
preds = {}
for f in files:
    for l in open(f, encoding="utf-8"):
        r = json.loads(l)
        preds[str(r["id"])] = r
todo = [r for i, r in preds.items() if i not in done]
fh = open(out, "a", encoding="utf-8")

def check(r):
    m = re.findall(r"```sql\s*(.*?)```", r["prediction"], re.S | re.I)
    sql = m[-1].strip() if m else r["base_sql"]
    p = subprocess.run([sys.executable, r"E:\effisql\work\effi_sql.py", str(r["id"]), "compare"], input=sql,
                       capture_output=True, text=True, encoding="utf-8", timeout=3600)
    try:
        res = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        res = {"error": (p.stdout + p.stderr)[-300:]}
    rec = {"id": str(r["id"]), "db": r["db"], "identical": res.get("identical_results"),
           "speedup_vs_original": res.get("speedup"), "kept_original": sql.strip() == r["base_sql"].strip(),
           "err": res.get("error")}
    fh.write(json.dumps(rec) + "\n"); fh.flush()
    print(rec, flush=True)

with ThreadPoolExecutor(8) as ex:
    list(ex.map(check, todo))
