import time, random, requests
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept-Language": "ru"})
def get(u, params=None, tries=6):
    for a in range(tries):
        try:
            r = S.get(u, params=params, timeout=30)
            if r.status_code == 200: return r.text
            print("HTTP", r.status_code, u)
            if r.status_code in (403, 429, 468): time.sleep(60*(a+1))
            elif r.status_code == 404: return None
        except requests.RequestException as e:
            pass
        time.sleep(3*2**a + random.random())
    return None
