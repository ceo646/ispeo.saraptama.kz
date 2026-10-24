"""Zone polygons for the map: Voronoi cells of all zone seeds, merged per zone, clipped to the built-up footprint.
usage: pvl_zone_polys.py <osm_dir> <out.json>"""
import json, math, sys
from shapely.geometry import MultiPoint, Point, Polygon, box, shape
from shapely.ops import unary_union, voronoi_diagram

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from zones import ZONES, ORDER

d, out = sys.argv[1], sys.argv[2]
K = math.cos(math.radians(52.28))           # work in a locally isotropic plane: x = lon·cos(lat)
seeds = [(lon * K, lat, z) for z, pts in ZONES.items() for lat, lon in pts]
env = box(76.86 * K, 52.20, 77.08 * K, 52.345)
cells = voronoi_diagram(MultiPoint([(x, y) for x, y, _ in seeds]), envelope=env)
foot = shape(json.load(open(f"{d}/footprint_geojson.json")))
foot = Polygon() if foot.is_empty else foot
foot_k = unary_union([Polygon([(x * K, y) for x, y in p.exterior.coords]) for p in getattr(foot, "geoms", [foot])])
by = {z: [] for z in ORDER}
for c in cells.geoms:
    for x, y, z in seeds:
        if c.contains(Point(x, y)):
            by[z].append(c)
            break
res = {}
for z, cs in by.items():
    g = unary_union(cs).intersection(foot_k).intersection(env).buffer(0)
    polys = [g] if isinstance(g, Polygon) else [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon)]
    rings = []
    for p in polys:
        p = p.simplify(0.0002)
        if p.area < 2e-6:
            continue
        rings.append([[[round(x / K, 5), round(y, 5)] for x, y in p.exterior.coords]] +
                     [[[round(x / K, 5), round(y, 5)] for x, y in r.coords] for r in p.interiors if Polygon(r).area > 2e-6])
    c = unary_union(cs).intersection(foot_k).representative_point()
    res[z] = dict(polys=rings, label=[round(c.x / K, 5), round(c.y, 5)])
json.dump(res, open(out, "w"), ensure_ascii=False, separators=(",", ":"))
print({z: len(v["polys"]) for z, v in res.items()})
