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

json.dump({"updated": datetime.datetime.now().isoformat(timespec="minutes"), "prices": P, "fund": F,
           "news": news(list(P))}, open("data.json", "w"))
print("stocks:", len(P))
