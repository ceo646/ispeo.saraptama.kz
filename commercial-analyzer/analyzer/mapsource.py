"""Bulk coordinate source: krisha map endpoints instead of detail pages.

Strategy
  1. Quadtree over the map GeoJSON endpoint with precision=12 — each request
     returns up to ~250 individual Features (advertId + exact coords + price).
  2. Where adverts share a building (identical geohash) a cluster never splits;
     below `min_span` we stop subdividing and enumerate that cluster's ids via
     the paginated cluster endpoint, assigning the cluster centroid.
  3. Boxes that return nothing are dropped immediately.
"""
import json, sys, time, random, threading
from concurrent.futures import ThreadPoolExecutor
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
_tl = threading.local()
def sess():
    if not hasattr(_tl, "s"):
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "X-Requested-With": "XMLHttpRequest",
                          "Accept-Encoding": "gzip, deflate"})
        _tl.s = s
    return _tl.s

S = {"req": 0, "err": 0, "bytes": 0}
_l = threading.Lock()

def _get(url, params, tries=4):
    for a in range(1, tries + 1):
        try:
            r = sess().get(url, params=params, timeout=30)
            with _l:
                S["req"] += 1; S["bytes"] += len(r.content)
            if r.status_code == 200:
                return r.json()
        except Exception:
            with _l: S["err"] += 1
        time.sleep(0.6 * a + random.random() * 0.4)
    return None

FILTERS = {}

def map_box(path, box, precision=12):
    ne_lat, sw_lon, sw_lat, ne_lon = box
    return _get(f"https://krisha.kz/a/ajax-map/map/{path}",
                dict(FILTERS, bounds=f"{ne_lat},{sw_lon},{sw_lat},{ne_lon}",
                     precision=str(precision)))

def cluster_ids(path, box, max_pages=30):
    """Enumerate advert ids inside a box via the paginated cluster endpoint."""
    ne_lat, sw_lon, sw_lat, ne_lon = box
    url = f"https://krisha.kz/a/ajax-map-cluster/map/{path}"
    base = dict(FILTERS, bounds=f"{ne_lat},{sw_lon},{sw_lat},{ne_lon}")
    out, page = [], 1
    while page <= max_pages:
        js = _get(url, dict(base, page=str(page)))
        if not js:
            break
        ids = js.get("ids") or []
        out.extend(str(i) for i in ids)
        if page >= (js.get("nbPages") or 1) or not ids:
            break
        page += 1
    return out

def harvest(path, bbox, workers=5, min_span=0.002, max_depth=12,
            enum_threshold=40, verbose=True):
    """Returns {advertId: {"lat":.., "lon":.., "icon":.., "exact":bool}}"""
    found = {}
    flock = threading.Lock()
    stuck = []          # (box, centroid, count) needing cluster enumeration

    def work(box):
        js = map_box(path, box)
        if not js:
            return []
        res = js.get("results", [])
        if not res:
            return []
        clusters, subs = [], []
        for r in res:
            if r.get("type") == "Feature":
                aid = str(r.get("id") or r["properties"].get("advertId"))
                lon_lat = r["geometry"]["coordinates"]
                with flock:
                    found[aid] = {"lat": lon_lat[0], "lon": lon_lat[1],
                                  "icon": r["properties"].get("iconContent"),
                                  "exact": True}
            else:
                clusters.append(r)
        if not clusters:
            return []
        ne_lat, sw_lon, sw_lat, ne_lon = box
        span = max(abs(ne_lat - sw_lat), abs(ne_lon - sw_lon))
        # Cost check: enumerating this box costs ceil(n/10) requests, while
        # subdividing costs 4 now plus whatever recursion follows. For small
        # boxes enumeration is strictly cheaper — and always terminates.
        hidden = sum(c.get("number", 0) for c in clusters)
        if span <= min_span or hidden <= enum_threshold:
            # Enumerate each cluster separately inside a tight box around its
            # own centroid — a shared box would hand one cluster's centroid to
            # adverts that actually sit elsewhere in the box.
            for c in clusters:
                cc = c["geometry"]["coordinates"]
                with flock:
                    stuck.append((cc, c.get("number", 0)))
            return []
        mlat, mlon = (ne_lat + sw_lat) / 2, (sw_lon + ne_lon) / 2
        return [(ne_lat, sw_lon, mlat, mlon), (ne_lat, mlon, mlat, ne_lon),
                (mlat, sw_lon, sw_lat, mlon), (mlat, mlon, sw_lat, ne_lon)]

    level, depth = [bbox], 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        while level and depth <= max_depth:
            subs = list(ex.map(work, level))
            nxt = [b for s in subs for b in s]
            if verbose:
                print(f"  d{depth}: {len(level):>4} boxes | {len(found):>5} exact | "
                      f"{len(stuck):>3} stuck | {S['req']:>4} req", flush=True)
            level, depth = nxt, depth + 1

        # resolve co-located clusters
        if stuck:
            seen, todo = set(), []
            for cc, n in stuck:
                key = (round(cc[0], 5), round(cc[1], 5))
                if key in seen:
                    continue
                seen.add(key)
                todo.append((cc, n))
            if verbose:
                print(f"  resolving {len(todo)} co-located clusters...", flush=True)
            pad = 0.0004          # ~45 m around the cluster centroid
            def resolve(item):
                cc, n = item
                tight = (cc[0] + pad, cc[1] - pad, cc[0] - pad, cc[1] + pad)
                for aid in cluster_ids(path, tight):
                    with flock:
                        if aid not in found:
                            found[aid] = {"lat": cc[0], "lon": cc[1],
                                          "icon": None, "exact": False}
            list(ex.map(resolve, todo))
    return found



def coords_for_city(section, bbox, filters=None, workers=5, verbose=False):
    """Harvest {advertId: {lat, lon, exact}} for a section+bounding box.

    section: e.g. "arenda/kommercheskaya-nedvizhimost/"
    bbox:    (ne_lat, sw_lon, sw_lat, ne_lon)
    """
    FILTERS.clear()
    FILTERS.update(filters or {})
    return harvest(section, bbox, workers=workers, verbose=verbose)


def apply_coords(listings, coords):
    """Fill lat/lng on Listing objects from a harvested coord map."""
    n = 0
    for l in listings:
        c = coords.get(str(l.id))
        if c and l.lat is None:
            l.lat, l.lng = c["lat"], c["lon"]
            n += 1
    return n


# Bounding boxes for supported cities (ne_lat, sw_lon, sw_lat, ne_lon)
CITY_BBOX = {
    "astana": (51.35, 71.20, 50.95, 71.75),
    "almaty": (43.40, 76.75, 43.13, 77.10),
    "shymkent": (42.45, 69.45, 42.20, 69.80),
    "burabay": (53.20, 70.05, 52.80, 70.55),
}
