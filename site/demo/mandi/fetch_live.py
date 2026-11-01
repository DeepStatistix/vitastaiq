"""Fetch today's mandi prices from data.gov.in (Agmarknet "current daily price" resource) and
write a compact aggregate for the dashboard.

Usage:
    python fetch_live.py [--env path/to/.env] [--out live.js]

The API key is read from the DATA_GOV_API_KEY environment variable, or from a .env file
(DATA_GOV_API_KEY / DATA_GOV_CURRENT_PRICE_API_KEY). The key is never written to the output.
Standard library only.
"""
import argparse
import http.client
import json
import os
import re
import ssl
import statistics
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"
HOST = "api.data.gov.in"
PAGE = 1000
STATES = [
    "Andaman and Nicobar", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh",
    "Chattisgarh", "Dadra and Nagar Haveli", "Daman and Diu", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Lakshadweep",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "NCT of Delhi", "Nagaland",
    "Odisha", "Pondicherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttrakhand", "West Bengal",
]


def find_key(env_path):
    key = os.getenv("DATA_GOV_API_KEY")
    if key:
        return key
    if env_path and Path(env_path).exists():
        text = Path(env_path).read_text(encoding="utf-8")
        for name in ("DATA_GOV_API_KEY", "DATA_GOV_CURRENT_PRICE_API_KEY"):
            m = re.search(rf"^{name}\s*=\s*(\S+)", text, re.M)
            if m:
                return m.group(1).strip("'\"")
    sys.exit("No API key: set DATA_GOV_API_KEY or pass --env path/to/.env")


def call(key, params, tries=5, timeout=12):
    path = f"/resource/{RESOURCE}?{urllib.parse.urlencode({'api-key': key, 'format': 'json', **params})}"
    err = None
    for i in range(tries):
        conn = None
        try:
            conn = http.client.HTTPSConnection(HOST, 443, timeout=timeout, context=ssl.create_default_context())
            conn.request("GET", path)
            r = conn.getresponse()
            body = r.read()
            if r.status == 429:
                time.sleep(10 * (i + 1))
                err = "rate limited"
                continue
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}")
            return json.loads(body)
        except Exception as e:  # timeouts happen on this API; wait and retry
            err = str(e).replace(key, "***")
            time.sleep(min(2 ** i, 15))
        finally:
            if conn:
                conn.close()
    raise RuntimeError(f"gave up after {tries} tries: {err}")


def fetch_state(key, state):
    rows, offset, total = [], 0, None
    while total is None or offset < total:
        d = call(key, {"limit": PAGE, "offset": offset, "filters[state.keyword]": state})
        total = int(d.get("total") or 0)
        recs = d.get("records") or []
        if not recs:
            break
        rows += recs
        offset += len(recs)
        time.sleep(0.3)
    return rows


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def aggregate(rows):
    dates = Counter(r.get("arrival_date") for r in rows)
    day = dates.most_common(1)[0][0]
    rows = [r for r in rows if r.get("arrival_date") == day]
    # The feed has no unit field. Agmarknet's convention is Rs/quintal, but some markets send Rs/kg
    # (e.g. cauliflower 24.2 next to 2,400). Per commodity, take the median of values >= 100 as the
    # reference; a value far below it that becomes plausible after x100 is treated as Rs/kg and
    # converted; anything else far from the reference is dropped as anomalous.
    # Uzhavar Sandhai (Tamil Nadu) are farmer-run retail markets; comparing them with wholesale APMC
    # prices would manufacture fake "price gaps", so they are left out and counted separately.
    recs = defaultdict(list)  # commodity -> [(state, market, modal)]
    retail = 0
    for r in rows:
        p = num(r.get("modal_price"))
        if not p or p <= 0:
            continue
        if "uzhavar" in r["market"].lower():
            retail += 1
            continue
        recs[r["commodity"].strip()].append((r["state"].strip(), r["market"].strip(), p))
    by = defaultdict(lambda: defaultdict(list))  # commodity -> state -> [(modal, market)]
    markets, adjusted, dropped = set(), 0, 0
    for c, lst in recs.items():
        big = [p for _, _, p in lst if p >= 100]
        ref = statistics.median(big) if big else statistics.median(p for _, _, p in lst)
        for s, m, p in lst:
            if p < ref / 20:
                if ref / 4 <= p * 100 <= ref * 4:
                    p, adjusted = p * 100, adjusted + 1
                else:
                    dropped += 1
                    continue
            elif p > ref * 20:
                dropped += 1
                continue
            markets.add((s, m))
            by[c][s].append((p, m))
    out = {}
    for c, states in by.items():
        allp = [p for v in states.values() for p, _ in v]
        mk = {(s, m) for s, v in states.items() for _, m in v}
        if len(mk) < 3:
            continue
        slist = []
        for s, v in states.items():
            ps = [p for p, _ in v]
            slist.append({"s": s, "p": round(statistics.median(ps)), "m": len({m for _, m in v}),
                          "lo": round(min(ps)), "hi": round(max(ps))})
        slist.sort(key=lambda x: x["p"])
        flat = [(p, s, m) for s, v in states.items() for p, m in v]
        lo, hi = min(flat), max(flat)
        out[c] = {"rows": len(allp), "markets": len(mk), "p": round(statistics.median(allp)), "states": slist,
                  "cheap": {"p": round(lo[0]), "s": lo[1], "m": lo[2]},
                  "dear": {"p": round(hi[0]), "s": hi[1], "m": hi[2]}}
    return {
        "date": datetime.strptime(day, "%d/%m/%Y").strftime("%Y-%m-%d"),
        "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "rows": len(rows), "markets": len(markets), "states": len({s for s, _ in markets}),
        "adjusted": adjusted, "dropped": dropped, "retail": retail,
        "commodities": out,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env")
    ap.add_argument("--out", default=str(Path(__file__).parent / "live.js"))
    a = ap.parse_args()
    key = find_key(a.env)
    rows = []
    for st in STATES:
        try:
            got = fetch_state(key, st)
        except RuntimeError as e:
            print(f"  {st}: FAILED ({e})")
            continue
        print(f"  {st}: {len(got)} rows")
        rows += got
    if not rows:
        sys.exit("no rows fetched")
    data = aggregate(rows)
    Path(a.out).write_text("window.LIVE=" + json.dumps(data, separators=(",", ":")) + ";", encoding="utf-8")
    print(f"date {data['date']}: {data['rows']} rows, {data['markets']} markets, {data['states']} states, "
          f"{len(data['commodities'])} commodities -> {a.out} ({Path(a.out).stat().st_size} bytes)")


if __name__ == "__main__":
    main()
