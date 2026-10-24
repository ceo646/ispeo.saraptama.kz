"""Collect the top-location verification results (object + rent agent per id) from the workflow journals."""
import json, sys
base = '/root/.claude/projects/-home-user-ispeo-saraptama-kz/9c75da6f-017a-59fc-9a5e-c9e0d03d9df9/subagents/workflows/'
out = {}
for w in sys.argv[2:]:
    for l in open(base + w + "/journal.jsonl"):
        r = json.loads(l)
        if r.get("type") != "result":
            continue
        x = r["result"]; d = out.setdefault(x["id"], {"id": x["id"]})
        d["object" if "verdict" in x else "rent"] = x
json.dump(list(out.values()), open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
print(len(out))
