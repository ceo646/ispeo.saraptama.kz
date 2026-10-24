import requests, json, time, sys
BB = "52.18,76.85,52.36,77.10"
Q = {
 "roads": f'[out:json][timeout:180];way["highway"~"^(motorway|trunk|primary|secondary|tertiary|residential|unclassified|living_street|motorway_link|trunk_link|primary_link|secondary_link)$"]({BB});out tags geom;',
 "water": f'[out:json][timeout:180];(way["natural"="water"]({BB});relation["natural"="water"]({BB});way["waterway"="riverbank"]({BB});relation["water"="river"]({BB}););out tags geom;',
 "parks": f'[out:json][timeout:180];(way["leisure"="park"]({BB});relation["leisure"="park"]({BB}););out tags geom;',
 "admin": '[out:json][timeout:180];relation["boundary"="administrative"]["name"="Павлодар Қ.Ә."];out tags geom;',
 "malls": f'[out:json][timeout:180];(nwr["shop"="mall"]({BB});nwr["building"="commercial"]["name"]({BB});nwr["office"]["name"]({BB});nwr["amenity"="marketplace"]({BB}););out tags center;',
 "buildings": f'[out:json][timeout:300];way["building"~"^(apartments|residential|house|yes|commercial|retail|office|detached)$"]({BB});out tags center;',
}
url = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
for k, q in Q.items():
    for a in range(6):
        try:
            r = requests.post(url, data={"data": q}, timeout=320)
            print(k, r.status_code, len(r.content), flush=True)
            if r.status_code == 200:
                open(f"osm/{k}.json", "wb").write(r.content); break
        except Exception as e:
            print(k, "err", type(e).__name__, flush=True)
        time.sleep(5 * (a + 1))
