"""Rank ~1 km zones by median price per place and check that the winner does not depend on where the hex grid falls.
usage: park_zones.py <final_listings.json> <basemap.json> [types=uc]"""
import json, math, re, statistics, sys
from collections import Counter, defaultdict

F = json.load(open(sys.argv[1]))
B = json.load(open(sys.argv[2]))
types = sys.argv[3] if len(sys.argv) > 3 else "uc"
LAT0 = 51.1
KX, KY = 111320 * math.cos(math.radians(LAT0)), 110540
toM = lambda lat, lon: ((lon - 71.4) * KX, (lat - LAT0) * KY)
HR = 560
rows = [r for r in F if r["t"] in types]


def hexof(x, y):
    q, r = (math.sqrt(3) / 3 * x - y / 3) / HR, (2 / 3 * y) / HR
    rx, ry, rz = round(q), round(-q - r), round(r)
    dx, dy, dz = abs(rx - q), abs(ry + q + r), abs(rz - r)
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        pass
    else:
        rz = -rx - ry
    return rx, rz


majors = []
for c, nm, pts in B["roads"]:
    if c <= 3 and nm:
        nm = re.sub(r"^(проспект|улица|шоссе) ", "", nm)
        pen = (150 if c == 3 else 0) + (400 if re.match(r"[ЕE]-?\d+", nm) else 0)
        majors.append((nm, pen, [toM(p[1], p[0]) for p in pts]))


def segd(p, a, b):
    vx, vy, wx, wy = b[0] - a[0], b[1] - a[1], p[0] - a[0], p[1] - a[1]
    t = max(0, min(1, (wx * vx + wy * vy) / ((vx * vx + vy * vy) or 1)))
    return math.hypot(wx - t * vx, wy - t * vy)


def name(c):
    best = {}
    for nm, pen, pts in majors:
        for k in range(1, len(pts)):
            d = segd(c, pts[k - 1], pts[k]) + pen
            if d < 1100 and d < best.get(nm, 1e9):
                best[nm] = d
    return " × ".join(n for n, _ in sorted(best.items(), key=lambda e: e[1])[:2])


def zones(dx=0.0, dy=0.0, minn=6):
    z = defaultdict(list)
    for r in rows:
        x, y = toM(r["lat"], r["lon"])
        z[hexof(x + dx, y + dy)].append(r)
    out = []
    for k, it in z.items():
        if len(it) < minn:
            continue
        q, rr = k
        cx, cy = HR * math.sqrt(3) * (q + rr / 2) - dx, HR * 1.5 * rr - dy
        out.append(dict(n=len(it), med=statistics.median(r["p"] for r in it), c=(cx, cy),
                        cxs=[n for n, _ in Counter(r["cx"] or "—" for r in it).most_common() if n != "—"],
                        d="Есиль" if sum(r["d"] == "Е" for r in it) >= len(it) / 2 else "Нура"))
    return sorted(out, key=lambda z: -z["med"])


base = zones()
print(f"listings {len(rows)} ({types})")
for k, z in enumerate(base[:12], 1):
    print(f"{k:2d} {z['med'] / 1e6:5.2f} млн  n={z['n']:3d}  {z['d']:5s} {name(z['c'])[:55]:55s} | {', '.join(z['cxs'][:5])}")

# robustness: shift the grid over 9 offsets and record which ЖК sit in the top zone
tops = Counter()
for i in range(3):
    for j in range(3):
        zs = zones(i * HR * 0.6, j * HR * 0.6)
        if zs:
            for cx in zs[0]["cxs"][:4]:
                tops[cx] += 1
            print("offset", i, j, "top:", f"{zs[0]['med'] / 1e6:.2f}", name(zs[0]["c"]), "|", ", ".join(zs[0]["cxs"][:4]))
print("ЖК most often in the top zone:", tops.most_common(8))
by = defaultdict(list)
for r in rows:
    by[r["d"]].append(r["p"])
print({k: (len(v), statistics.median(v)) for k, v in by.items()})
