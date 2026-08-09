"""
List BloFin markets via CCXT (standalone)
"""
import os
import ccxt
from dotenv import load_dotenv

# --- edit these if needed ---
ENV_FILE = "BloFin_Coin_M.env"   # or "APIGoesHere.env"
EXCHANGE_ID = "blofin"
SANDBOX = True                   # True = testnet
# ----------------------------

load_dotenv(ENV_FILE)

api_key = os.getenv("BLOFIN_API_KEY")
api_secret = os.getenv("BLOFIN_SECRET")
api_password = os.getenv("BLOFIN_PASSWORD")

print("Key:", "set" if api_key else "MISSING")
print("Secret:", "set" if api_secret else "MISSING")
print("Password:", "set" if api_password else "MISSING")

if not api_key or not api_secret or not api_password:
    print("Missing credentials in", ENV_FILE)
    raise SystemExit(1)

exchange = getattr(ccxt, EXCHANGE_ID)({
    "apiKey": api_key,
    "secret": api_secret,
    "password": api_password,
    "enableRateLimit": True,
})
exchange.set_sandbox_mode(SANDBOX)
exchange.options["defaultType"] = "swap"

print("Loading markets...")
markets = exchange.load_markets()

print(f"\nTotal markets: {len(markets)}\n")

# Show swap / futures style symbols (most useful for the bot)
swap_symbols = sorted(
    s for s, m in markets.items()
    if m.get("swap") or m.get("future") or m.get("type") in ("swap", "future")
)

print("=== SWAP / FUTURE SYMBOLS ===")
for s in swap_symbols:
    m = markets[s]
    inv = "inverse" if m.get("inverse") else "linear"
    print(f"{s:30}  {inv}")

print("\n=== ALL SYMBOLS (first 50) ===")
for s in sorted(markets.keys())[:50]:
    print(s)

print("\nDone. Copy a symbol exactly as shown into SYMBOL / WATCH_SYMBOLS.")