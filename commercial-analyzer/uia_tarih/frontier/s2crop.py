"""Crop a Sentinel-2 TCI COG around a lat/lon and save an upscaled PNG with a km grid.
usage: s2crop.py <tci_url> <lat> <lon> <half_km> <out.png> [scale]"""
import sys, math
import numpy as np, rasterio
from rasterio.windows import from_bounds
from pyproj import Transformer
from PIL import Image, ImageDraw
url, lat, lon, half, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
scale = int(sys.argv[6]) if len(sys.argv) > 6 else 4
with rasterio.Env(GDAL_HTTP_MAX_RETRY=5, GDAL_HTTP_RETRY_DELAY=2, AWS_NO_SIGN_REQUEST="YES"):
    with rasterio.open(url) as src:
        tr = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        x, y = tr.transform(lon, lat)
        h = half * 1000
        win = from_bounds(x - h, y - h, x + h, y + h, src.transform)
        arr = src.read(window=win, boundless=True)
img = np.transpose(arr[:3], (1, 2, 0)).astype(np.float32)
# contrast stretch
lo, hi = np.percentile(img, 1), np.percentile(img, 99.5)
img = np.clip((img - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
im = Image.fromarray(img).resize((img.shape[1] * scale, img.shape[0] * scale), Image.LANCZOS)
d = ImageDraw.Draw(im)
W, H = im.size
px_per_km = W / (2 * half)
# grid every 500 m, centre cross
for k in np.arange(-half, half + 1e-6, 0.5):
    p = W / 2 + k * px_per_km
    d.line([(p, 0), (p, H)], fill=(255, 255, 0) if abs(k) < 1e-6 else (255, 255, 255), width=1)
    q = H / 2 + k * px_per_km
    d.line([(0, q), (W, q)], fill=(255, 255, 0) if abs(k) < 1e-6 else (255, 255, 255), width=1)
d.text((5, 5), f"S2 TCI {url.split('/')[-2]}  grid=500m  centre={lat},{lon}  N up (UTM)", fill=(255, 0, 0))
im.save(out)
print(out, im.size, f"{px_per_km:.0f}px/km")
