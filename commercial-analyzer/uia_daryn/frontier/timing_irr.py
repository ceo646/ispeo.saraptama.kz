"""Does a late handover pay off? Calendar-based ramp + payment timing, IRR vs a tenge deposit.
Month 0 = Oct 2026. The market maturity of rents in the ÜIA cluster grows with the calendar
(residents arrive 2027-2029), not with a given unit's keys: 0.60 of mature in Jan 2027 rising
linearly to 1.0 in Jan 2030. A lease is signed at today's maturity and reset every 36 months.
Months from keys to the first tenant shrink as the cluster fills.
Exit at month 62 (Dec 2031) at the purchase price (no nominal gain or loss) to isolate timing."""

def maturity(m):
    return 0.55 if m < 3 else min(1.0, 0.60 + 0.40 * (m - 3) / 36)

def lag(keys_m):
    return 10 if keys_m < 9 else 8 if keys_m < 15 else 6 if keys_m < 27 else 4

def flows(area, price, M, keys_m, pay_now_share=1.0, horizon=62):
    cf = [0.0] * (horizon + 1)
    cf[0] -= price * pay_now_share
    cf[keys_m] -= price * (1 - pay_now_share)
    start = keys_m + lag(keys_m)
    rent = 0.0
    for m in range(keys_m, horizon + 1):
        cf[m] -= 0.005 * price / 12                      # property tax from keys
        if m < start:
            cf[m] -= 150 * area                          # ОСИ + heating while empty
            continue
        if (m - start) % 36 == 0:
            rent = M * 0.9 * maturity(m)                 # contract at signing, reset every 3 years
        cf[m] += rent * 0.85 * area * 0.96 - 260_000 / 12
    cf[horizon] += price                                 # exit at purchase price
    return cf

def irr(cf):
    lo, hi = -0.5, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        r = (1 + mid) ** (1 / 12) - 1
        npv = sum(c / (1 + r) ** i for i, c in enumerate(cf))
        lo, hi = (mid, hi) if npv > 0 else (lo, mid)
    return mid

def income_to_2029(cf, price):
    return sum(c for c in cf[1:40] if c > 0) / price  # gross-ish cash in by end-2029

CASES = [
    ("G-12 142,3 млн, 100% сейчас, ключи 09.2027", 173.53, 142.29e6, 6216, 11, 1.0),
    ("G-12 142,3 млн, 100% сейчас, ключи 03.2028 (+2 кв.)", 173.53, 142.29e6, 6216, 17, 1.0),
    ("G-12 142,3 млн, 30% сейчас / 70% при ключах 09.2027", 173.53, 142.29e6, 6216, 11, 0.3),
    ("G-12 173,5 млн (цена листка), 100% сейчас, 09.2027", 173.53, 173.53e6, 6216, 11, 1.0),
    ("C-19 65,6 млн, 100% сейчас, ключи 03.2027", 96.59, 65.58e6, 6848, 5, 1.0),
    ("C-19 65,6 млн, 100% сейчас, ключи 09.2027 (+2 кв.)", 96.59, 65.58e6, 6848, 11, 1.0),
    ("C-19 65,6 млн, 30% сейчас / 70% при ключах 03.2027", 96.59, 65.58e6, 6848, 5, 0.3),
    ("C-15 76,6 млн, 100% сейчас, ключи 03.2027", 115.24, 76.63e6, 6790, 5, 1.0),
]
for name, area, price, M, km, share in CASES:
    cf = flows(area, price, M, km, share)
    print(f"{name:55s} IRR {irr(cf)*100:5.1f}%   первый арендатор ~мес {km + lag(km):2d}")
