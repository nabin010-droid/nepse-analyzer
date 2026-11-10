"""Daily NEPSE updater (GitHub Actions). Pulls 1 year history from a public community dataset + news RSS.
NOT TESTED by the author (no network in sandbox): if it errors, send the error log."""
import json, os, io, datetime, requests, pandas as pd, feedparser
from concurrent.futures import ThreadPoolExecutor

REPO = "menaceXnadin/nepse-historical-market-data-csv"
LIST = f"https://api.github.com/repos/{REPO}/contents/data/stock/adjusted"
RAW = f"https://raw.githubusercontent.com/{REPO}/master/data/stock/adjusted/"
H = {"User-Agent": "Mozilla/5.0"}
if os.getenv("GITHUB_TOKEN"):
    H["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
KEEP = 260  # ~1 trading year

def one(name):
    sym = name.split("_")[0].upper()
    try:
        df = pd.read_csv(io.StringIO(requests.get(RAW + name, headers=H, timeout=60).text))
        df.columns = [c.strip().lower() for c in df.columns]
        d = next(c for c in df.columns if c in ("time", "date"))
        c = "close" if "close" in df.columns else None
        v = "volume" if "volume" in df.columns else None
        if not c:
            print("close column not found for", sym, list(df.columns)); return sym, []
        df = df.dropna(subset=[c]).tail(KEEP)
        return sym, [{"d": str(r[d])[:10], "c": float(r[c]), "v": float(r[v]) if v else 0} for _, r in df.iterrows()]
    except Exception as e:
        print("skip", sym, e); return sym, []

files = [f["name"] for f in requests.get(LIST, headers=H, timeout=60).json() if f["name"].endswith(".csv")]
with ThreadPoolExecutor(8) as ex:
    P = {s: rows for s, rows in ex.map(one, files) if len(rows) >= 55}

IDX = []  # NEPSE index history for relative-strength comparison
try:
    t = pd.read_csv(io.StringIO(requests.get(RAW.replace("stock/adjusted/", "index/adjusted/") + "NEPSE_adjusted.csv", headers=H, timeout=60).text))
    t.columns = [c.strip().lower() for c in t.columns]
    dc = next(c for c in t.columns if c in ("time", "date"))
    IDX = [{"d": str(r[dc])[:10], "c": float(r["close"])} for _, r in t.dropna(subset=["close"]).tail(KEEP).iterrows()]
except Exception as e:
    print("index skip", e)

FEEDS = ["https://english.onlinekhabar.com/feed"]  # add more RSS you trust
def news(symbols):
    out = []
    for u in FEEDS:
        for e in feedparser.parse(u).entries[:60]:
            T = f" {e.title.upper()} "
            hit = [s for s in symbols if f" {s} " in T] or ["MARKET"]
            out += [{"symbol": h, "title": e.title, "url": e.link} for h in hit]
    return out

F = {}
if os.path.exists("fund.csv"):  # symbol,sector,eps,pe,pbv,roe,div - you maintain from quarterly reports
    for r in pd.read_csv("fund.csv").itertuples():
        F[str(r.symbol).upper()] = {"sector": r.sector, "pe": r.pe, "pbv": r.pbv, "roe": r.roe, "div": r.div}


# ---- Company name + sector (naya) ----
def pk(d, *ks):
    for k in ks:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return str(d[k]).strip()
    return ""

def load_names():
    names, sectors = {}, {}
    try:  # 1) purano data.json: ek patak name aayepachhi jyaun rahancha
        for k, v in (json.load(open("data.json", encoding="utf-8")).get("fund") or {}).items():
            if v.get("name"): names[k.upper()] = v["name"]
            if v.get("sector") not in (None, "", "-"): sectors[k.upper()] = v["sector"]
    except Exception:
        pass
    if os.path.exists("companies.csv"):  # 2) companies.csv: symbol,name,sector (aafaile thapna milcha)
        for r in pd.read_csv("companies.csv").fillna("").itertuples():
            s = str(r.symbol).strip().upper()
            if str(r.name).strip(): names[s] = str(r.name).strip()
            if str(r.sector).strip(): sectors[s] = str(r.sector).strip()
    try:  # 3) NEPSE bata live (pip install nepseman-api). GitHub server block bhaye skip huncha.
        import asyncio
        from nepseman_api import NepseClient
        async def go():
            async with NepseClient() as n:
                return await n.company_list()
        data = asyncio.run(go())
        rows = data if isinstance(data, list) else (data.get("content") or data.get("data") or []) if isinstance(data, dict) else []
        for r in rows:
            s = pk(r, "symbol", "securitySymbol").replace(" ", "").upper()
            if not s: continue
            if pk(r, "securityName", "companyName", "name"): names[s] = pk(r, "securityName", "companyName", "name")
            if pk(r, "sectorName", "sector"): sectors[s] = pk(r, "sectorName", "sector")
        print("live names:", len(rows))
    except Exception as e:
        print("live names skip:", e)
    return names, sectors

NM, SC = load_names()
for s in P:
    f = F.setdefault(s, {})
    if NM.get(s): f["name"] = NM[s]
    if f.get("sector") in (None, "", "-"): f["sector"] = SC.get(s) or "-"
    for k, v in list(f.items()):
        if isinstance(v, float) and v != v: f[k] = None  # NaN JSON ma chaldaina
print("names:", sum(1 for s in P if F[s].get("name")), "/", len(P))

json.dump({"updated": datetime.datetime.now().isoformat(timespec="minutes"), "prices": P, "fund": F, "index": IDX,
           "news": news(list(P))}, open("data.json", "w"))
print("stocks:", len(P))
