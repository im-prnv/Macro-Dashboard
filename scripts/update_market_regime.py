import yfinance as yf
import json
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "backend" / "data"
DATA_DIR.mkdir(exist_ok=True)

REGIME_FILE = DATA_DIR / "market_regime.json"

# Fetch data
t = yf.Ticker("^NSEI")
df = t.history(period="max")

if df.empty or len(df) < 200:
    raise Exception("Not enough data to calculate EMA")

# Calculate EMAs
df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

close = float(df["Close"].iloc[-1])
ema50 = float(df["EMA50"].iloc[-1])
ema200 = float(df["EMA200"].iloc[-1])

# Regime logic
if close > ema50 and ema50 > ema200:
    regime = "Bullish"
elif close < ema50 and close > ema200:
    regime = "Correction"
else:
    regime = "Bearish"

output = {
    "index": "NIFTY 50",
    "trend_regime": regime,
    "close": round(close, 2),
    "ema50": round(ema50, 2),
    "ema200": round(ema200, 2),
    "based_on": "Previous daily close"
}

# Write file
with open(REGIME_FILE, "w") as f:
    json.dump(output, f, indent=2)

print("Market regime updated:", output)