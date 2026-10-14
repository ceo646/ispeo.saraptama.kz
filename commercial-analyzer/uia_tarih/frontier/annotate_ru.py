"""Labelled Sentinel-2 crop of the ÜIA cluster with Russian captions.
usage: annotate_ru.py <tci_url> <out.png>"""
import sys, math
import numpy as np, rasterio
from rasterio.windows import from_bounds
from pyproj import Transformer
from PIL import Image, ImageDraw, ImageFont

url, out = sys.argv[1], sys.argv[2]
C_LAT, C_LON, HALF, SCALE = 51.1040, 71.3525, 1.1, 8
with rasterio.Env(GDAL_HTTP_MAX_RETRY=5, GDAL_HTTP_RETRY_DELAY=2, AWS_NO_SIGN_REQUEST="YES"):
    with rasterio.open(url) as src:
        tr = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        x0, y0 = tr.transform(C_LON, C_LAT)
        h = HALF * 1000
        arr = src.read(window=from_bounds(x0 - h, y0 - h, x0 + h, y0 + h, src.transform), boundless=True)
img = np.transpose(arr[:3], (1, 2, 0)).astype(np.float32)
lo, hi = np.percentile(img, 1), np.percentile(img, 99.5)
img = np.clip((img - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
im = Image.fromarray(img).resize((img.shape[1] * SCALE, img.shape[0] * SCALE), Image.LANCZOS).convert("RGB")
W, H = im.size
ppm = W / (2 * h)  # pixels per metre


def px(lat, lon):
    x, y = tr.transform(lon, lat)
    return (W / 2 + (x - x0) * ppm, H / 2 - (y - y0) * ppm)


d = ImageDraw.Draw(im, "RGBA")
F = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
big, mid, small = ImageFont.truetype(F, 34), ImageFont.truetype(F, 26), ImageFont.truetype(F, 21)


def label(xy, text, font=mid, fill=(255, 255, 255), bg=(0, 0, 0, 150)):
    x, y = xy
    b = d.multiline_textbbox((x, y), text, font=font, anchor="mm", align="center")
    d.rounded_rectangle((b[0] - 8, b[1] - 6, b[2] + 8, b[3] + 6), 8, fill=bg)
    d.multiline_text((x, y), text, font=font, fill=fill, anchor="mm", align="center")


def box(lat1, lon1, lat2, lon2, color):
    (xa, ya), (xb, yb) = px(lat1, lon1), px(lat2, lon2)
    d.rectangle((min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)), outline=color, width=4)


# TARIH blocks (positions from the imagery track, ±15 m)
box(51.1018, 71.3488, 51.1028, 71.3510, (255, 80, 80))
box(51.1028, 71.3494, 51.1040, 71.3512, (255, 200, 0))
box(51.1027, 71.3514, 51.1037, 71.3529, (80, 220, 120))
box(51.1026, 71.3532, 51.1036, 71.3544, (80, 180, 255))
label(px(51.1015, 71.3499), "TARIH B\nB-16/B-17 — на западной стороне", small, bg=(150, 0, 0, 190))
label(px(51.1043, 71.3480), "A", mid, bg=(120, 90, 0, 190))
label(px(51.10225, 71.35215), "C\nC-13/15/19", small, bg=(0, 110, 40, 190))
label(px(51.10225, 71.3538), "E", mid, bg=(0, 70, 140, 190))
label(px(51.1053, 71.3555), "DARYN (часть домов уже с ключами)", small)
label(px(51.10512, 71.36465), "пр. Улы Дала\n(единственная магистраль)", small, bg=(0, 0, 0, 170))
label(px(51.1105, 71.3470), "ул. Айтматова\n(кончается на Улы Дала)", small)
label(px(51.1108, 71.3592), "Ellington Mall\n(строится, ~2028)", small)
label(px(51.0985, 71.3440), "ПУСТЫРЬ / СТЕПЬ\nничего не строится", big, fill=(255, 230, 120))
label(px(51.0990, 71.3560), "ПУСТЫРЬ\nпотом лесопитомник", big, fill=(255, 230, 120))
label(px(51.1050, 71.3400), "степь →\nболота Талдыколя", mid, fill=(255, 230, 120))
# north arrow + scale bar
d.polygon([(W - 60, 40), (W - 75, 90), (W - 45, 90)], fill=(255, 255, 255))
d.text((W - 60, 110), "С", font=mid, fill=(255, 255, 255), anchor="mm")
sb = 200 * ppm
d.rectangle((40, H - 60, 40 + sb, H - 50), fill=(255, 255, 255))
d.text((40 + sb / 2, H - 80), "200 м", font=small, fill=(255, 255, 255), anchor="mm")
d.text((W - 20, H - 20), "Sentinel-2, 13.10.2026", font=small, fill=(255, 255, 255), anchor="rs")
im.save(out, optimize=True)
print(out, im.size)
