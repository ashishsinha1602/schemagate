import json, math, sys
def tier(s):
    return 1.0 if s >= 2 else 0.75 if s >= 1.2 else 0.5 if s >= 1 else 0.25 if s >= 0.5 else 0.0
rows = list({json.loads(l)["id"]: json.loads(l) for l in open(sys.argv[1])}.values())
N = int(sys.argv[2]) if len(sys.argv) > 2 else len(rows)
ok = [r for r in rows if str(r.get("is_match")) in ("True", "true", "1") or r.get("is_match") is True]
sp = [float(r.get("speedup") or 0) for r in ok]
rves = 100 * sum(tier(s) for s in sp) / N
cov = 100 * sum(1 for s in sp if s >= 2) / N
gms = math.exp(sum(math.log(max(s, 1e-9)) for s in sp) / len(sp)) if sp else 0
print(f"scored={len(rows)} N={N} match={len(ok)} ({100*len(ok)/max(len(rows),1):.1f}%) R-VES={rves:.2f} Coverage@2x={cov:.2f} GMS={gms:.4f}")
bad = [(r["id"], r.get("is_match"), r.get("speedup"), r.get("error_type")) for r in rows
       if r not in ok or float(r.get("speedup") or 0) < 1.2]
print("below 1.2x or wrong:", bad)
