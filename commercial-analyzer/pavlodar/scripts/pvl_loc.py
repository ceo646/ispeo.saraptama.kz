"""Location quality of every listing: first line, district activity, population density.

  first line  krisha attribute com.location_line = первая линия; when the attribute is missing, the card text
              («первая линия», «красная линия», «фасад», «выход на проспект») or an entrance from the street within
              45 m of a main road (OSM primary/secondary/tertiary).
  activity    z-score sum of: OSM shops, cafés, offices, banks, clinics within 400 m (log); all krisha commercial
              listings within 400 m (log, commerce concentration); transit stops within 300 m; footfall anchors
              (2GIS rating counts of the big trade centres, station, markets) with distance decay.
  density     residents per km² around the point: Kontur population H3 cells (res 8, 2023) within 700 m,
              inverse-distance weighted over inhabited cells (≥50 people), averaged (as z-scores) with the number of
              krisha apartment-sale listings within 500 m and the floors of ≥5-storey OSM buildings within 400 m —
              Kontur rests on ~2020 data and misses new blocks, the other two see them.
usage: pvl_loc.py <rows.json> <list_all.json> <kontur.gpkg> <osm dir> <out loc.json>"""
import json, math, re, sqlite3, sys
import h3
import numpy as np

ROWS, LIST, GPKG, OSM, OUT = sys.argv[1:6]
K = math.cos(math.radians(52.28))


def xy(lat, lon):  # km in a local plane
    return np.array([lon * 111.32 * K, lat * 110.57])


rows = json.load(open(ROWS))
det_all = {r["id"]: r for r in rows}

# --- population (Kontur H3 res 8) inside the Pavlodar box
con = sqlite3.connect(GPKG)
cells = []
for h, pop in con.execute("select h3, population from population"):
    lat, lon = h3.cell_to_latlng(h)
    if 52.15 <= lat <= 52.38 and 76.80 <= lon <= 77.15:
        cells.append((lat, lon, pop, h))
cxy = np.array([xy(a, b) for a, b, _, _ in cells]); cpop = np.array([p for _, _, p, _ in cells])
CELL_KM2 = h3.average_hexagon_area(8, unit="km^2")


def density(lat, lon, r=0.7):
    d = np.linalg.norm(cxy - xy(lat, lon), axis=1)
    m = (d <= r) & (cpop >= 50)      # inhabited cells only, so the river and empty lots do not dilute riverside blocks
    if not m.any():
        return 0.0
    w = 1 / (0.25 + d[m])
    return float((cpop[m] / CELL_KM2 * w).sum() / w.sum())


# --- activity layers
P = json.load(open(f"{OSM}/pois.json"))["elements"]
pxy = np.array([xy((e.get("center") or e)["lat"], (e.get("center") or e)["lon"]) for e in P])
S = json.load(open(f"{OSM}/stops.json"))["elements"]
sxy = np.array([xy(e["lat"], e["lon"]) for e in S])
L = json.load(open(LIST))
lxy = np.array([xy(r["lat"], r["lon"]) for r in rows if r.get("lat")])
# footfall anchors: 2GIS rating counts collected by the research (number of ratings ≈ visitors)
ANCH = [("Batyr Mall", 52.2749, 76.9898, 26073), ("ТД Квазар и центральный рынок", 52.2804, 76.9594, 6636),
        ("ТД Артур и Ярмарка", 52.2865, 76.9711, 5468), ("ТД Манакбай", 52.2878, 76.9520, 4892),
        ("ТД Гулливер", 52.2885, 76.9690, 3920), ("ТД Orange", 52.2440, 76.9890, 3922), ("ЦУМ", 52.2835, 76.9440, 2570),
        ("ТД Отау", 52.2975, 76.9640, 3389), ("Ж/д вокзал и автовокзал", 52.3003, 76.9717, 10493),
        ("«12 месяцев»", 52.2496, 76.9708, 2590), ("Торайгыров университет", 52.2690, 76.9550, 2000),
        ("Центральная набережная", 52.2880, 76.9370, 3000)]
axy = np.array([xy(a[1], a[2]) for a in ANCH]); aw = np.array([math.log10(a[3]) for a in ANCH])

# multi-storey residential floors (OSM buildings with ≥5 levels or tagged apartments)
TB = []
for e in json.load(open(f"{OSM}/buildings.json"))["elements"]:
    t = e["tags"]
    try:
        lv = float(str(t.get("building:levels", "0")).replace(",", "."))
    except ValueError:
        lv = 0
    if (lv >= 5 or t.get("building") == "apartments") and e.get("center"):
        TB.append((xy(e["center"]["lat"], e["center"]["lon"]), max(lv, 5)))
txy = np.array([t[0] for t in TB]); tlv = np.array([t[1] for t in TB])


def floors(lat, lon, r=0.4):
    d = np.linalg.norm(txy - xy(lat, lon), axis=1)
    return float(tlv[d <= r].sum())


# housing stock incl. new blocks: krisha apartment-sale listings (map coordinates) within 500 m
FL = json.load(open(f"{OSM}/../flats_coords.json"))
fxy = np.array([xy(v["lat"], v["lon"]) for v in FL.values()])


def flats(lat, lon, r=0.5):
    return int((np.linalg.norm(fxy - xy(lat, lon), axis=1) <= r).sum())


R = json.load(open(f"{OSM}/roads.json"))["elements"]
MAIN = {"primary", "secondary", "tertiary", "primary_link", "secondary_link", "trunk"}
segs = []
for e in R:
    if e["tags"].get("highway") in MAIN and e.get("geometry"):
        g = [xy(p["lat"], p["lon"]) for p in e["geometry"]]
        for a, b in zip(g, g[1:]):
            segs.append((a, b, e["tags"].get("name:ru") or e["tags"].get("name") or ""))
A_ = np.array([s[0] for s in segs]); B_ = np.array([s[1] for s in segs])


def road_dist(p):
    ab = B_ - A_
    t = np.clip(((p - A_) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
    d = np.linalg.norm(A_ + ab * t[:, None] - p, axis=1)
    i = int(d.argmin())
    return float(d[i] * 1000), segs[i][2]


def raw_activity(lat, lon):
    p = xy(lat, lon)
    poi = int((np.linalg.norm(pxy - p, axis=1) <= 0.4).sum())
    lst = int((np.linalg.norm(lxy - p, axis=1) <= 0.4).sum())
    stp = int((np.linalg.norm(sxy - p, axis=1) <= 0.3).sum())
    da = np.linalg.norm(axy - p, axis=1)
    anc = float((aw * np.exp(-da / 0.6)).sum())
    return poi, lst, stp, anc


FIRST = re.compile(r"перв\w* лини|1[- ]?я лини|красн\w* лини|фасад|выход\w* на (?:проспект|улиц|дорог)|вдоль (?:проспекта|дороги)|на (?:оживл|проходн)\w* (?:улиц|мест)", re.I)
YARD = re.compile(r"во двор|внутри квартал|вторая линия|2[- ]?я линия", re.I)

out = []
for r in rows:
    if r["excluded"] or not r.get("lat"):
        continue
    poi, lst, stp, anc = raw_activity(r["lat"], r["lon"])
    rd, rname = road_dist(xy(r["lat"], r["lon"]))
    text = (r.get("desc") or "") + " " + (r.get("title") or "")
    ent = r.get("entrance") or ""
    if r["line"] == "первая линия":
        fl, why = True, "атрибут krisha"
    elif r["line"] in ("во дворе", "частный сектор"):
        fl, why = False, r["line"]
    elif YARD.search(text):
        fl, why = False, "текст: во дворе"
    elif FIRST.search(text):
        fl, why = True, "текст объявления"
    elif "көшеден" in ent and rd <= 45:
        fl, why = True, f"вход с улицы, {rd:.0f} м до {rname or 'магистрали'}"
    else:
        fl, why = False, "нет признаков"
    out.append(dict(id=r["id"], deal=r["deal"], lat=r["lat"], lon=r["lon"], first_line=fl, fl_why=why,
                    road_m=round(rd), road=rname, poi=poi, lst=lst, stops=stp, anchors=round(anc, 3),
                    density=round(density(r["lat"], r["lon"])), floors=floors(r["lat"], r["lon"]), flats=flats(r["lat"], r["lon"])))

# activity index: z-scores over all cleaned listings
def z(v):
    v = np.array(v, float)
    return (v - v.mean()) / (v.std() or 1)


act = z(np.log1p([o["poi"] for o in out])) + z(np.log1p([o["lst"] for o in out])) + z([o["stops"] for o in out]) + z([o["anchors"] for o in out])
dens = (z([o["density"] for o in out]) + z(np.log1p([o["flats"] for o in out])) + z(np.log1p([o["floors"] for o in out]))) / 3
for o, a, dn in zip(out, act, dens):
    o["activity"] = round(float(a), 3)
    o["dens_idx"] = round(float(dn), 3)
A70, D70 = float(np.percentile(act, 70)), float(np.percentile(dens, 70))
for o in out:
    o["active"] = o["activity"] >= A70
    o["dense"] = o["dens_idx"] >= D70
    o["top"] = o["first_line"] and (o["active"] or o["dense"])

# grid for the map: H3 res 9 cells over the built-up area with density and activity
grid = []
seen = set()
for lat, lon, pop, h in cells:
    for ch in h3.cell_to_children(h, 9):
        if ch in seen:
            continue
        seen.add(ch)
        la, lo = h3.cell_to_latlng(ch)
        if not (52.22 <= la <= 52.33 and 76.89 <= lo <= 77.06):
            continue
        poi, lst, stp, anc = raw_activity(la, lo)
        grid.append(dict(h=ch, lat=round(la, 5), lon=round(lo, 5), density=round(density(la, lo)), floors=floors(la, lo), flats=flats(la, lo), poi=poi, lst=lst, stops=stp, anchors=anc))
# activity on the grid with the listing z-score parameters
def zz(vals, ref):
    ref = np.array(ref, float); v = np.array(vals, float)
    return (v - ref.mean()) / (ref.std() or 1)


ga = (zz(np.log1p([g["poi"] for g in grid]), np.log1p([o["poi"] for o in out])) + zz(np.log1p([g["lst"] for g in grid]), np.log1p([o["lst"] for o in out]))
      + zz([g["stops"] for g in grid], [o["stops"] for o in out]) + zz([g["anchors"] for g in grid], [o["anchors"] for o in out]))
gd = (zz([g["density"] for g in grid], [o["density"] for o in out]) + zz(np.log1p([g["flats"] for g in grid]), np.log1p([o["flats"] for o in out]))
      + zz(np.log1p([g["floors"] for g in grid]), np.log1p([o["floors"] for o in out]))) / 3
for g, a, dn in zip(grid, ga, gd):
    g["activity"] = round(float(a), 3)
    g["dens_idx"] = round(float(dn), 3)
    g["active"], g["dense"] = bool(a >= A70), bool(dn >= D70)
    g["boundary"] = [[round(y, 5), round(x, 5)] for x, y in h3.cell_to_boundary(g["h"])]

json.dump(dict(listings=out, grid=grid, thresholds=dict(activity=A70, density=D70), anchors=[dict(name=a[0], lat=a[1], lon=a[2], ratings=a[3]) for a in ANCH]),
          open(OUT, "w"), ensure_ascii=False)
fl = sum(o["first_line"] for o in out)
print("listings", len(out), "first line", fl, "grid", len(grid))
from collections import Counter
print(Counter(o["fl_why"].split(",")[0] for o in out))
d = np.array([o["density"] for o in out]); a = np.array([o["activity"] for o in out])
print("top", sum(o["top"] for o in out), "rent", sum(o["top"] and o["deal"] == "rent" for o in out), "sale", sum(o["top"] and o["deal"] == "sale" for o in out),
      "active", sum(o["active"] for o in out), "dense", sum(o["dense"] for o in out))
print("density pct", np.percentile(d, [10, 25, 50, 70, 80, 90]).round()); print("activity pct", np.percentile(a, [10, 25, 50, 70, 80, 90]).round(2))
