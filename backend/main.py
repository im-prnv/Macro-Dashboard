from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import json
from pathlib import Path
import feedparser
from datetime import datetime
import time
from functools import wraps
import pandas as pd

# ---------------- CACHE ----------------
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

# ---------------- HEALTH ----------------
@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return Response(status_code=200)

# ---------------- SAFE FETCH ----------------
def fetch_1d_change(symbols):
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

# ---------------- MACRO ----------------
@app.get("/dxy")
@ttl_cache(300)
def dxy():
    v, p = fetch_1d_change(["DX-Y.NYB", "DXY", "USDX"])
    return {"dxy": v, "pct_change": p}

@app.get("/usd-jpy")
@ttl_cache(300)
def usd_jpy():
    v, p = fetch_1d_change(["JPY=X"])
    return {"usd_jpy": v, "pct_change": p}

@app.get("/usd-inr")
@ttl_cache(300)
def usd_inr():
    v, p = fetch_1d_change(["INR=X"])
    return {"price": v, "pct_change": p}

@app.get("/crude")
@ttl_cache(300)
def crude():
    v, p = fetch_1d_change(["BZ=F"])
    return {"price": v, "pct_change": p}

@app.get("/us-yields")
@ttl_cache(600)
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

# ---------------- NEWS ----------------
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
        return {
            "source": source,
            "region": region,
            "updated": datetime.utcnow().isoformat(),
            "items": []
        }

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

# ---------------- MARKET REGIME (FINAL FIX) ----------------
@app.get("/market-regime")
@ttl_cache(86400)  # once per day
def market_regime():
    try:
        t = yf.Ticker("^NSEI")
        df = t.history(period="max")

        if df is None or df.empty or len(df) < 200:
            return {
                "trend_regime": "Unavailable",
                "note": "Yahoo data unavailable"
            }

        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

        close = round(float(df["Close"].iloc[-1]), 2)
        ema50 = round(float(df["EMA50"].iloc[-1]), 2)
        ema200 = round(float(df["EMA200"].iloc[-1]), 2)

        if close > ema50 and ema50 > ema200:
            regime = "Bullish"
        elif close < ema50 and close > ema200:
            regime = "Corrective"
        else:
            regime = "Bearish"

        return {
            "index": "NIFTY 50",
            "trend_regime": regime,
            "close": close,
            "ema50": ema50,
            "ema200": ema200,
            "based_on": "Previous daily close"
        }

    except Exception as e:
        return {
            "trend_regime": "Unavailable",
            "error": str(e)
        }
