"""
Find LTC markets on BloFin
"""
import os
import ccxt
from dotenv import load_dotenv

ENV_FILE = "BloFin_Coin_M.env"
SANDBOX = True   # change to False for live

load_dotenv(ENV_FILE)

exchange = ccxt.blofin({
    "apiKey": os.getenv("BLOFIN_API_KEY"),
    "secret": os.getenv("BLOFIN_SECRET"),
    "password": os.getenv("BLOFIN_PASSWORD"),
    "enableRateLimit": True,
})
exchange.set_sandbox_mode(SANDBOX)
exchange.options["defaultType"] = "swap"

markets = exchange.load_markets()

print(f"Sandbox={SANDBOX}  total={len(markets)}\n")

for s in sorted(markets):
    if "LTC" in s.upper():
        m = markets[s]
        print(
            s,
            "inverse=", m.get("inverse"),
            "linear=", m.get("linear"),
            "settle=", m.get("settle"),
            "type=", m.get("type"),
        )