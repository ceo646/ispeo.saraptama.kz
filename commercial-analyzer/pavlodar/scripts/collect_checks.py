import json, sys
base = '/root/.claude/projects/-home-user-ispeo-saraptama-kz/9c75da6f-017a-59fc-9a5e-c9e0d03d9df9/subagents/workflows/'
out = {}
for w in ["wf_774c6aff-918", "wf_eb34ba6e-2b3", "wf_772e1d34-7ba", "wf_bcdc1372-db2"]:
    for l in open(base + w + "/journal.jsonl"):
        r = json.loads(l)
        if r.get("type") != "result": continue
        x = r["result"]; d = out.setdefault(x["id"], {"id": x["id"]})
        d["object" if "verdict" in x else "rent"] = x
json.dump(list(out.values()), open("checks.json", "w"), ensure_ascii=False, indent=1)
from collections import Counter
print(len(out), Counter(d.get("object", {}).get("verdict") for d in out.values()), sum(1 for d in out.values() if "rent" in d))
for d in sorted(out.values(), key=lambda d: -(d.get("rent", {}).get("net_yield") or 0)):
    o, r = d.get("object", {}), d.get("rent", {})
    print(f"{d['id']:11s} {o.get('verdict','?'):7s} gross {r.get('gross_yield',0)*100:5.1f} net {r.get('net_yield',0)*100:5.1f} rent {r.get('realistic_rent_per_m2',0):5.0f} | {o.get('what_is_sold','')[:100]}")
