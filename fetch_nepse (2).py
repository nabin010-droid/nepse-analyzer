#!/usr/bin/env python3
"""NEPSE bata data.json banaune (company name, sector, 1 barsa ko price/volume).
Chalaune: pip install nepseman-api && python fetch_nepse.py
data.json ko path badalna paryo vane: OUT=public/data.json python fetch_nepse.py
Purano data.json ma bhayeko fundamental (pe, pbv, roe, div) ra news jyaun rakhincha."""
import asyncio, datetime as dt, json, os, sys
from nepseman_api import NepseClient

OUT = os.environ.get("OUT", "data.json")
DAYS = 400
NST = dt.timezone(dt.timedelta(hours=5, minutes=45))

def pick(d, *keys):
    if isinstance(d, dict):
        for k in keys:
            if d.get(k) not in (None, ""):
                return d[k]
    return None

def num(x):
    try:
        return float(str(x).replace(",", ""))
    except Exception:
        return None

def rows(x):
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        for k in ("content", "data", "items", "result"):
            if isinstance(x.get(k), list):
                return x[k]
    return []

def sym(r):
    return str(pick(r, "symbol", "securitySymbol", "ticker") or "").replace(" ", "").upper()

async def main():
    old = {}
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT, encoding="utf-8"))
        except Exception:
            pass
    async with NepseClient() as n:
        companies = rows(await n.company_list())
        today = rows(await n.today_price())
        names, sector = {}, {}
        for r in companies + today:
            s = sym(r)
            if not s:
                continue
            nm, sc = pick(r, "securityName", "companyName", "name"), pick(r, "sectorName", "sector")
            if nm: names[s] = str(nm).strip()
            if sc: sector[s] = str(sc).strip()
        syms = sorted({sym(r) for r in today if sym(r)})
        if not syms:
            sys.exit("today_price khali aayo, data.json chhoina")
        start = (dt.date.today() - dt.timedelta(days=DAYS)).isoformat()
        hist = await n.bulk_price_history(syms, start_date=start, concurrency=5)

        idx = list(old.get("index") or [])
        try:
            for r in rows(await n.nepse_index()):
                if str(pick(r, "index", "indexName") or "").strip().upper() in ("NEPSE INDEX", "NEPSE"):
                    v = num(pick(r, "currentValue", "close", "value"))
                    d = str(pick(today[0], "businessDate", "date") or "")[:10]
                    if v and d and all(x.get("d") != d for x in idx):
                        idx.append({"c": v, "d": d})
        except Exception as e:
            print("index skip:", e)

    prices = {}
    for s, h in (hist or {}).items():
        pts = {}
        for r in rows(h):
            d = str(pick(r, "businessDate", "date") or "")[:10]
            c = num(pick(r, "closePrice", "close", "lastTradedPrice"))
            v = num(pick(r, "totalTradedQuantity", "totalTradeQuantity", "volume")) or 0
            if d and c and c > 0:
                pts[d] = {"c": c, "v": v, "d": d}
        if pts:
            prices[sym({"symbol": s})] = [pts[k] for k in sorted(pts)]
    if not prices:
        sys.exit("price history khali aayo, data.json chhoina")

    oldf = {str(k).replace(" ", "").upper(): v for k, v in (old.get("fund") or {}).items()}
    fund = {}
    for s in prices:
        f = dict(oldf.get(s, {}))
        f["sector"] = sector.get(s) or f.get("sector") or "-"
        if s in names:
            f["name"] = names[s]
        fund[s] = f

    out = {"updated": dt.datetime.now(NST).strftime("%Y-%m-%d %H:%M NST"),
           "prices": prices, "fund": fund,
           "names": {s: names[s] for s in prices if s in names},
           "index": idx or None, "news": old.get("news", [])}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(len(prices), "stock,", len(out["names"]), "name, sector:", sorted(set(f["sector"] for f in fund.values()))[:12])

asyncio.run(main())
