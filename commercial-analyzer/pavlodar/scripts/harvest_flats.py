import json, sys, re, time
sys.path.insert(0, "/home/user/ispeo.saraptama.kz/commercial-analyzer")
sys.path.insert(0, ".")
from analyzer import mapsource
from kget import get
h = get("https://krisha.kz/prodazha/kvartiry/pavlodar/")
m = re.search(r"Найдено\s*<span>([\d\s\xa0]+)</span>", h or ""); print("found on site", m and m.group(1), flush=True)
t0 = time.time()
c = mapsource.coords_for_city("prodazha/kvartiry/", (52.345, 76.86, 52.20, 77.08), workers=3, verbose=True)
json.dump(c, open("flats_coords.json", "w"))
print("harvested", len(c), "in", round(time.time() - t0), "s", mapsource.S, flush=True)
