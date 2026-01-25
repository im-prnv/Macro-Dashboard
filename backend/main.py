from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import json
from pathlib import Path
import feedparser
from datetime import datetime
from fastapi import HTTPException, Query
import time
from functools import wraps


        # Simple in-memory cache
CACHE = {}

def ttl_cache(ttl_seconds: int):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = func.__name__ + str(args) + str(kwargs)
            now = time.time()

            if key in CACHE:
                cached_time, cached_value = CACHE[key]
                if now - cached_time < ttl_seconds:
                    return cached_value

            result = func(*args, **kwargs)
            CACHE[key] = (now, result)
            return result

        return wrapper
    return decorator


app = FastAPI()

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://im-prnv.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- SAFE FETCH ----------------
def fetch_1d_change(symbols):
    """
    Try multiple symbols safely.
    Never throws. Returns (value, pct) or (None, None)
    """
    for symbol in symbols:
        try:
            t = yf.Ticker(symbol)
            h = t.history(period="5d")

            if h.empty or len(h) < 2:
                continue

            latest = float(h["Close"].iloc[-1])
            prev = float(h["Close"].iloc[-2])
            pct = round(((latest - prev) / prev) * 100, 2)

            return round(latest, 2), pct
        except Exception:
            continue

    return None, None

# ---------------- HEALTH ----------------
@app.get("/")
def health():
    return {"status": "Backend running"}

# ---------------- MACRO ----------------
@app.get("/dxy")
@ttl_cache(300)  # 5 minutes
def dxy():
    v, p = fetch_1d_change(["DX-Y.NYB", "DXY", "USDX"])
    return {"dxy": v, "pct_change": p}

@app.get("/usd-jpy")
@ttl_cache(300)  # 5 minutes
def usd_jpy():
    v, p = fetch_1d_change(["JPY=X"])
    return {"usd_jpy": v, "pct_change": p}

@app.get("/usd-inr")
@ttl_cache(300)  # 5 minutes
def usd_inr():
    v, p = fetch_1d_change(["INR=X"])
    return {"price": v, "pct_change": p}

@app.get("/crude")
@ttl_cache(300)  # 5 minutes
def crude():
    v, p = fetch_1d_change(["BZ=F"])
    return {"price": v, "pct_change": p}

@app.get("/us-yields")
@ttl_cache(600)  # 5 minutes
def us_yields():
    y10, y10p = fetch_1d_change(["^TNX"])
    y2, y2p = fetch_1d_change(["^IRX"])

    if y10 is None or y2 is None:
        return {
            "us_10y": None,
            "us_10y_pct": None,
            "us_2y": None,
            "us_2y_pct": None,
            "yield_spread": None
        }

    return {
        "us_10y": y10,
        "us_10y_pct": y10p,
        "us_2y": y2,
        "us_2y_pct": y2p,
        "yield_spread": round(y10 - y2, 2)
    }

# ---------------- FII / DII ----------------
@app.get("/fii-dii")
def fii_dii():
    path = Path("backend/data/fii_dii.json")
    with open(path) as f:
        return json.load(f)


#----------------Market News----------------

@app.get("/news")
@ttl_cache(600)
def market_news(region: str = Query("global", enum=["global", "india"])):
    if region == "india":
        FEED_URL = (
            "https://news.google.com/rss/search?"
            "q=India+markets+OR+India+economy+OR+RBI+OR+Nifty+OR+Sensex"
            "&hl=en-IN&gl=IN&ceid=IN:en"
        )
        source = "India News (via Google News)"
    else:
        FEED_URL = (
            "https://news.google.com/rss/search?"
            "q=Reuters+markets+OR+Reuters+economy+OR+global+stocks+OR+USD"
            "&hl=en-IN&gl=IN&ceid=IN:en"
        )
        source = "Global News (via Google News)"

    feed = feedparser.parse(FEED_URL)

    if not feed.entries:
        raise HTTPException(status_code=502, detail="News feed unavailable")

    items = []
    for entry in feed.entries[:15]:
        items.append({
            "title": entry.title,
            "link": entry.link,
            "published": entry.get("published", "")
        })

    return {
        "source": source,
        "region": region,
        "updated": datetime.utcnow().isoformat(),
        "items": items
    }
