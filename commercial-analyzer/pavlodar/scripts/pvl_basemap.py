"""Compact vector basemap of Pavlodar from Overpass JSON: built-up footprint, roads, water, parks.
usage: pvl_basemap.py <osm_dir> <out.json>"""
import json, sys
from shapely.geometry import LineString, Point, Polygon, box, mapping
from shapely.ops import linemerge, polygonize, unary_union

d, out = sys.argv[1], sys.argv[2]
BB = box(76.86, 52.20, 77.08, 52.345)
TOL = 0.00004


def rnd(coords):
    return [[round(x, 5), round(y, 5)] for x, y in coords]


def polys(g, min_area=2e-7, tol=TOL):
    if g.is_empty:
        return []
    ps = [g] if isinstance(g, Polygon) else [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon)]
    res = []
    for p in ps:
        p = p.simplify(tol, preserve_topology=True)
        if p.is_empty or p.area < min_area:
            continue
        res.append([rnd(p.exterior.coords)] + [rnd(r.coords) for r in p.interiors if Polygon(r).area > min_area])
    return res


def rings(members, role):
    lines = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in members
             if m.get("geometry") and m.get("role", "outer") in (role, "") and len(m["geometry"]) > 1]
    return list(polygonize(linemerge(lines))) if lines else []


res = {"bbox": [76.86, 52.20, 77.08, 52.345]}

# built-up footprint: buildings buffered ~120 m, small holes closed
b = json.load(open(f"{d}/buildings.json"))["elements"]
pts = [Point(e["center"]["lon"], e["center"]["lat"]) for e in b if e.get("center")]
foot = unary_union([p.buffer(0.0018, 6) for p in pts]).buffer(-0.0008).intersection(BB)
foot = unary_union([p for p in getattr(foot, "geoms", [foot]) if p.area > 2e-6])
res["footprint"] = polys(foot, 1e-6, 0.0003)
json.dump(mapping(foot), open(f"{d}/footprint_geojson.json", "w"))

# multi-storey buildings (≥5 floors) as a residential-density proxy
ms = []
for e in b:
    t = e["tags"]
    try:
        lv = float(str(t.get("building:levels", "0")).replace(",", "."))
    except ValueError:
        lv = 0
    if lv >= 5 or t.get("building") == "apartments":
        ms.append([round(e["center"]["lon"], 5), round(e["center"]["lat"], 5), int(lv)])
res["tall"] = ms

roads = json.load(open(f"{d}/roads.json"))["elements"]
cls = {"motorway": 1, "trunk": 1, "primary": 1, "motorway_link": 3, "trunk_link": 3, "primary_link": 3,
       "secondary": 2, "secondary_link": 3, "tertiary": 3, "residential": 4, "unclassified": 4, "living_street": 4}
R = []
for e in roads:
    g = e.get("geometry")
    if not g or len(g) < 2:
        continue
    ls = LineString([(p["lon"], p["lat"]) for p in g]).intersection(BB)
    if ls.is_empty:
        continue
    parts = [ls] if isinstance(ls, LineString) else [x for x in getattr(ls, "geoms", []) if isinstance(x, LineString)]
    c = cls[e["tags"]["highway"]]
    for p in parts:
        p = p.simplify(TOL if c <= 3 else TOL * 2)
        if len(p.coords) < 2:
            continue
        nm = e["tags"].get("name:ru") or e["tags"].get("name") or ""
        R.append([c, nm if c <= 3 else "", rnd(p.coords)])
res["roads"] = R


def area_layer(fn):
    out = []
    for e in json.load(open(fn))["elements"]:
        if e["type"] == "way" and e.get("geometry") and len(e["geometry"]) > 3:
            g = Polygon([(p["lon"], p["lat"]) for p in e["geometry"]]).buffer(0)
        elif e["type"] == "relation":
            o, i = rings(e.get("members", []), "outer"), rings(e.get("members", []), "inner")
            g = unary_union(o).difference(unary_union(i)) if i else unary_union(o)
        else:
            continue
        out.append(g.intersection(BB))
    return unary_union(out) if out else Polygon()


res["water"] = polys(area_layer(f"{d}/water.json"))
res["parks"] = polys(area_layer(f"{d}/parks.json"), 5e-7)
json.dump(res, open(out, "w"), ensure_ascii=False, separators=(",", ":"))
print({k: len(v) for k, v in res.items() if isinstance(v, list)}, round(len(open(out).read()) / 1e6, 2), "MB")
