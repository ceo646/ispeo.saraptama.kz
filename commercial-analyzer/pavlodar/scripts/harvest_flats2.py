"""Re-harvest apartment-sale coordinates on a fixed grid of tiles (each tile retried until it answers), union with earlier runs."""
import json, sys, time
sys.path.insert(0, "/home/user/ispeo.saraptama.kz/commercial-analyzer")
from analyzer import mapsource
mapsource.FILTERS.clear()
allc = json.load(open("flats_coords.json"))
tiles = []
la, lo = 52.20, 76.86
while la < 52.345:
    lo = 76.86
    while lo < 77.08:
        tiles.append((round(la + 0.025, 4), round(lo, 4), round(la, 4), round(lo + 0.04, 4)))
        lo += 0.04
    la += 0.025
print("tiles", len(tiles), flush=True)
for i, t in enumerate(tiles):
    for attempt in range(3):
        c = mapsource.harvest("prodazha/kvartiry/", t, workers=3, verbose=False)
        new = {k: v for k, v in c.items() if k not in allc}
        allc.update(c)
        js = mapsource.map_box("prodazha/kvartiry/", t, precision=12)
        if js is not None:
            break
        time.sleep(5)
    print(i, t, "tile", len(c), "new", len(new), "total", len(allc), flush=True)
json.dump(allc, open("flats_coords.json", "w"))
print("DONE", len(allc), mapsource.S, flush=True)
