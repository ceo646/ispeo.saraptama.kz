"""Build a compact vector basemap (left-bank mask, roads, water, parks) from Overpass JSON.
usage: park_basemap.py <osm_dir> <out.json>"""
import json, sys
from shapely.geometry import LineString, Polygon, MultiPolygon, box, mapping
from shapely.ops import linemerge, polygonize, unary_union

d, out = sys.argv[1], sys.argv[2]
BB = box(71.20, 51.00, 71.65, 51.20)
TOL = 0.00003


def rnd(coords):
    return [[round(x, 5), round(y, 5)] for x, y in coords]


def rings_from_members(members, role="outer"):
    lines = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in members
             if m.get("geometry") and m.get("role", "outer") in (role, "") and len(m["geometry"]) > 1]
    return list(polygonize(linemerge(lines)))


def poly_to_list(g):
    """Polygon/MultiPolygon -> list of polygons, each a list of rings ([outer, holes...])."""
    if g.is_empty:
        return []
    ps = [g] if isinstance(g, Polygon) else [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon)]
    res = []
    for p in ps:
        p = p.simplify(TOL, preserve_topology=True)
        if p.is_empty or p.area < 2e-7:
            continue
        res.append([rnd(p.exterior.coords)] + [rnd(r.coords) for r in p.interiors if Polygon(r).area > 2e-7])
    return res


# districts
dist = json.load(open(f"{d}/districts.json"))
polys = {}
for e in dist["elements"]:
    nm = e["tags"].get("name:ru")
    outer = rings_from_members(e["members"], "outer")
    polys[nm] = unary_union(outer)
left = unary_union([polys["район Есиль"], polys["район Нура"]]).buffer(0)
res = {"districts": {}, "bbox": [71.20, 51.00, 71.65, 51.20]}
for nm in ("район Есиль", "район Нура"):
    res["districts"][nm] = poly_to_list(polys[nm].intersection(BB))
res["left"] = poly_to_list(left.intersection(BB))

# roads
roads = json.load(open(f"{d}/roads.json"))
cls = {"motorway": 1, "trunk": 1, "primary": 1, "motorway_link": 3, "trunk_link": 3, "primary_link": 3,
       "secondary": 2, "secondary_link": 3, "tertiary": 3, "residential": 4, "unclassified": 4, "living_street": 4}
R = []
for e in roads["elements"]:
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

# water
water = json.load(open(f"{d}/water.json"))
W = []
for e in water["elements"]:
    if e["type"] == "way" and e.get("geometry") and len(e["geometry"]) > 3:
        g = Polygon([(p["lon"], p["lat"]) for p in e["geometry"]])
    elif e["type"] == "relation":
        outer = rings_from_members(e["members"], "outer")
        inner = rings_from_members(e["members"], "inner")
        g = unary_union(outer).difference(unary_union(inner)) if inner else unary_union(outer)
    else:
        continue
    if not g.is_valid:
        g = g.buffer(0)
    W += poly_to_list(g.intersection(BB))
res["water"] = W

# parks
green = json.load(open(f"{d}/green.json"))
G = []
for e in green["elements"]:
    t = e["tags"]
    if t.get("landuse") == "grass":
        continue
    if e["type"] == "way" and e.get("geometry") and len(e["geometry"]) > 3:
        g = Polygon([(p["lon"], p["lat"]) for p in e["geometry"]])
    elif e["type"] == "relation":
        g = unary_union(rings_from_members(e["members"], "outer"))
    else:
        continue
    if not g.is_valid:
        g = g.buffer(0)
    if g.area < 1.5e-6:
        continue
    G += poly_to_list(g.intersection(BB))
res["green"] = G
json.dump(res, open(out, "w"), ensure_ascii=False, separators=(",", ":"))
print({k: (len(v) if isinstance(v, list) else len(v)) for k, v in res.items()})
