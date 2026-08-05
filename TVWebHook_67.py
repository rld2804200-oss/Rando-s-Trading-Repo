"""
TVWebHook_2.0.67
TradingView Webhook Handler for CCXT Trading
"""
from flask import Flask, request, jsonify
import ccxt
import os
import traceback
from dotenv import load_dotenv
from colorama import Fore, init
import math
import time
import asyncio
from datetime import datetime
import json
import sys
import os


if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(base_path, "config.json")

app = Flask(__name__)
init(autoreset=True)
def log(message):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] {message}")

DEFAULTS = {
    "EXCHANGE": "phemex",
    "SYMBOL": "BTC/USD:BTC",
    "TRADE_MODE": "swap",
    "USE_HEDGE_MODE": False,
    "TRADINGVIEW_MESSAGE_MODE": True,
    "USE_WEBHOOK_SYMBOL": True,
    "USE_GEOMETRIC_SIZING": False,
    "GEOMETRIC_MULTIPLIER": 4,
    "MAX_LONG_LOTS": 10000.0,
    "MAX_SHORT_LOTS": 10000.0,
    "MIN_LOT_SIZE": 1,
    "USE_LIMIT_ORDERS": False,
    "LIMIT_OFFSET_POINTS": 200.0,
    "AUTO_CANCEL_ORDERS": False,
    "BUY_SELL_MODE" : "buy",  # Valid values: "buy" | "sell" | "both" | "auto" use "BALANCE_TOLERANCE": 0.001,
    "BALANCE_TOLERANCE": 0.001,
    "PRICE_IMPROVEMENT_MODE": "off",  # "off" | "buy_lower" | "sell_higher" | "both"
    "USE_TP" : True,
    "TP_MODE": "points",  # Valid values: "percent" | "fixed" | "points"
    "TP_PERCENT": 10.0,
    "TP_TRIGGER_POINTS": 500.0,
    "FIXED_TP_PRICE_BUY": 130000,   # used when side == 'buy' and TP_MODE == "fixed"
    "FIXED_TP_PRICE_SELL": 55555,  # used when side == 'sell' and TP_MODE == "fixed"
    "USE_SL": False,
    "SL_MODE": "points",  # Valid values: "percent" | "fixed" | "points"
    "SL_PERCENT": 5.0,
    "SL_TRIGGER_POINTS": 500.0,
    "FIXED_SL_PRICE_BUY": <value>,   # used when side == 'buy' and SL_MODE == "fixed"
    "FIXED_SL_PRICE_SELL": <value>,  # used when side == 'sell' and SL_MODE == "fixed"
    "SANDBOX_MODE": False,
    "ENV_FILE": "ThisNThat.env",
}
# BUY_SELL_MODE = "buy"   # "buy" | "sell" | "both"

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE) as f:
        config = json.load(f)
    config = {**DEFAULTS, **config}
    log(Fore.GREEN + f"✅ Config loaded from {CONFIG_FILE}")
else:
    config = DEFAULTS.copy()
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    log(Fore.YELLOW + f"⚠️ No {CONFIG_FILE} found — created new one with defaults")

EXCHANGE = config["EXCHANGE"]
SYMBOL = config["SYMBOL"]
TRADE_MODE = config["TRADE_MODE"]
USE_HEDGE_MODE = config["USE_HEDGE_MODE"]
TRADINGVIEW_MESSAGE_MODE = config["TRADINGVIEW_MESSAGE_MODE"]
USE_WEBHOOK_SYMBOL = config["USE_WEBHOOK_SYMBOL"]
USE_GEOMETRIC_SIZING = config["USE_GEOMETRIC_SIZING"]
GEOMETRIC_MULTIPLIER = config["GEOMETRIC_MULTIPLIER"]
MAX_LONG_LOTS = config["MAX_LONG_LOTS"]
MAX_SHORT_LOTS = config["MAX_SHORT_LOTS"]
MIN_LOT_SIZE = config["MIN_LOT_SIZE"]
USE_LIMIT_ORDERS = config["USE_LIMIT_ORDERS"]
LIMIT_OFFSET_POINTS = config["LIMIT_OFFSET_POINTS"]
AUTO_CANCEL_ORDERS = config["AUTO_CANCEL_ORDERS"]
BUY_SELL_MODE = config["BUY_SELL_MODE"]  # Valid values: "buy" | "sell" | "both" | "auto" use "BALANCE_TOLERANCE": 0.001,
BALANCE_TOLERANCE = config["BALANCE_TOLERANCE"]
PRICE_IMPROVEMENT_MODE = config["PRICE_IMPROVEMENT_MODE"]  # "off" | "buy_lower" | "sell_higher" | "both"
USE_TP = config["USE_TP"]
TP_MODE = config["TP_MODE"]
TP_PERCENT = config["TP_PERCENT"]
TP_TRIGGER_POINTS = config["TP_TRIGGER_POINTS"]
FIXED_TP_PRICE_BUY = config["FIXED_TP_PRICE_BUY"]
FIXED_TP_PRICE_SELL = config["FIXED_TP_PRICE_SELL"]
USE_SL = config["USE_SL"]
SL_MODE = config["SL_MODE"]
SL_PERCENT = config["SL_PERCENT"]
FIXED_SL_PRICE_BUY = config["FIXED_SL_PRICE_BUY"]
FIXED_SL_PRICE_SELL = config["FIXED_SL_PRICE_SELL"]
SANDBOX_MODE = config["SANDBOX_MODE"]
ENV_FILE = config["ENV_FILE"]

log(Fore.CYAN + "=== CODE LOADED ===")
log(Fore.CYAN + "TVWebHook_2.0.67")

load_dotenv(ENV_FILE)
log(Fore.GREEN + "Loaded " + ENV_FILE)

api_key = os.getenv(f'{EXCHANGE.upper()}_API_KEY')
api_secret = os.getenv(f'{EXCHANGE.upper()}_SECRET')
log(Fore.CYAN + f"API Key: {api_key[:10] if api_key else 'None'}...")
log(Fore.CYAN + f"API Secret: {api_secret[:10] if api_secret else 'None'}...")

# Startup balance check
try:
    temp_exchange = getattr(ccxt, EXCHANGE)({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
    })
    temp_exchange.set_sandbox_mode(SANDBOX_MODE)
    temp_exchange.options['defaultType'] = 'swap'
    bal = temp_exchange.fetch_balance({'type': 'swap', 'code': 'USDT'})
    usdt = bal.get('USDT', {}).get('free', 0) or bal.get('free', {}).get('USDT', 0)
    log(Fore.GREEN + f"Startup USDT free: {usdt}")
except Exception as e:
    log(Fore.YELLOW + f"Startup balance check failed: {e}")

exchange = None
if not USE_WEBHOOK_SYMBOL:
    exchange = getattr(ccxt, EXCHANGE)({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
    })
    exchange.set_sandbox_mode(SANDBOX_MODE)
    if TRADE_MODE == 'swap':
        exchange.options['defaultType'] = 'swap'
    log(Fore.CYAN + "Exchange initialized with default symbol")
else:
    log(Fore.CYAN + "Exchange will be initialized on first webhook, not using default symbol")

if not api_key or not api_secret:
    log(Fore.RED + "Missing API keys in " + ENV_FILE)
    input("Press Enter to exit...")
    sys.exit(1)

def get_leverage(symbol):
    if exchange is None:
        return []
    exchange.load_markets()
    positions = exchange.fetch_positions([symbol])
    for position in positions:
        info = position.get('info', {})
        leverage = info.get('leverageRr', 'N/A')
        print(position['symbol'], 'leverage:', leverage)
    return positions

def execute_order(symbol, order_type, side, amount, limit_price=None, params=None):
    """
    Event handler for order execution with Phemex-specific error handling.
    Returns (order, message) tuple.
    """
    if params is None:
        params = {}

        # Validate we have an exchange instance
    if exchange is None:
        return None, "Exchange not initialized"

        # Validate amount
    if amount is None or amount <= 0:
        return None, f"Invalid order amount: {amount}"

        # Log pre-order state
    log(Fore.CYAN + f"🔧 PRE-ORDER CHECK: {side} {amount} {symbol} @ {limit_price}")
    log(Fore.CYAN + f"🔧 Order params: {params}")

    try:
        # Fetch minimum order size and adjust if needed
        min_size = get_min_order_size(symbol)
        if amount < min_size:
            log(Fore.YELLOW + f"⚠️ Amount {amount} below min {min_size}, adjusting")
            amount = min_size

            # Create the order
        order = exchange.create_order(
            symbol=symbol,
            type=order_type,
            side=side,
            amount=amount,
            price=limit_price,
            params=params
        )

        log(Fore.GREEN + f"✅ Order executed: {order.get('id')} ({side.upper()} {amount} {symbol})")
        return order, "success"

    except ccxt.InvalidOrder as e:
        error_str = str(e)
        if '11058' in error_str:
            # TE_QTY_TOO_SMALL
            min_size = get_min_order_size(symbol)
            log(Fore.YELLOW + f"⚠️ TE_QTY_TOO_SMALL, retrying with min size {min_size}")
            try:
                order = exchange.create_order(symbol, order_type, side, min_size, limit_price, params)
                log(Fore.GREEN + f"✅ Retry successful: {order.get('id')}")
                return order, "success"
            except Exception as retry_e:
                return None, f"Retry failed after TE_QTY_TOO_SMALL: {retry_e}"
        elif '11042' in error_str:
            return None, f"TE_NO_LAST_PRICE: Cannot get valid last market price for TP/SL"
        elif '11040' in error_str:
            return None, f"TE_NO_MARK_PRICE: Cannot get valid mark price"
        elif '11041' in error_str:
            return None, f"TE_NO_INDEX_PRICE: Cannot get valid index price"
        elif '11047' in error_str:
            return None, f"TE_BUY_TP_SHOULD_GT_BASE: Buy TP price must be greater than base price"
        elif '11050' in error_str:
            return None, f"TE_SELL_TP_SHOULD_LT_BASE: Sell TP price must be less than base price"
        elif '11074' in error_str:
            return None, f"TE_CANNOT_ATTACH_TP_SL: Cannot attach TP/SL when account already has positions"
        elif '11083' in error_str:
            return None, f"TE_TAKE_PROFIT_ORDER_DUPLICATED: TP order already exists"
        elif '11084' in error_str:
            return None, f"TE_STOP_LOSS_ORDER_DUPLICATED: SL order already exists"
        else:
            return None, f"InvalidOrder: {e}"

    except ccxt.InsufficientFunds as e:
        return None, f"InsufficientFunds: {e}"

    except ccxt.AuthenticationError as e:
        return None, f"AuthenticationError: {e}"

    except ccxt.NetworkError as e:
        return None, f"NetworkError: {e}"

    except ccxt.ExchangeError as e:
        return None, f"ExchangeError: {e}"

    except Exception as e:
        return None, f"Unexpected error: {e}"

def get_current_price(symbol):
    """
    Get the most reliable current price for TP/SL calculations.
    Phemex 24h ticker often has 0 for close/last on low-volume symbols,
    so we fall back to markPriceRp / indexPriceRp from the raw response.
    """
    try:
        ticker = exchange.fetch_ticker(symbol)
        info = ticker.get('info', {})

        # Linear USDT/USDC swaps: markPriceRp is the most reliable "current" price
        for key in ['markPriceRp', 'indexPriceRp', 'closeRp', 'lastRp']:
            val = info.get(key)
            if val:
                try:
                    fval = float(val)
                    if fval > 0:
                        return fval
                except (ValueError, TypeError):
                    continue

                    # Inverse/coin-m swaps use Ep fields (already scaled by CCXT in ticker)
        if ticker.get('last'):
            return float(ticker['last'])
        if ticker.get('close'):
            return float(ticker['close'])
        if ticker.get('bid') and ticker.get('ask'):
            return (float(ticker['bid']) + float(ticker['ask'])) / 2.0

    except Exception as e:
        log(Fore.YELLOW + f"Warning: Could not fetch ticker for price: {e}")

    return None

def get_margin_type(symbol):
    if ':USDT' in symbol or ':USD' in symbol:
        return 'usdt'
    elif ':BTC' in symbol or ':ETH' in symbol:
        return 'coin'
    return 'usdt'

def initialize_exchange_for_symbol(symbol):
    global exchange
    margin_type = get_margin_type(symbol)
    exchange = getattr(ccxt, EXCHANGE)({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
    })
    exchange.set_sandbox_mode(SANDBOX_MODE)
    if TRADE_MODE == 'swap':
        exchange.options['defaultType'] = 'swap'
    exchange.load_markets()
    try:
        balance = exchange.fetch_balance({'type': 'swap'})
        usdt_free = balance.get('USDT', {}).get('free', 0) or balance.get('free', {}).get('USDT', 0)
        log(Fore.CYAN + f"🔧 USDT free: {usdt_free}")
        log(Fore.CYAN + f"🔧 Balance fetched for {margin_type}-margined trading")
    except Exception as e:
        log(Fore.YELLOW + f"Warning: Could not fetch balance: {e}")

def get_position_sizes(symbol=None):
    if exchange is None:
        return 0.0, 0.0
    if symbol is None:
        symbol = SYMBOL
    max_retries = 3
    for attempt in range(max_retries):
        try:
            positions = exchange.fetch_positions([symbol])
            long_size = 0.0
            short_size = 0.0
            for position in positions:
                if position['symbol'] == symbol:
                    size = float(position.get('contracts', 0) or 0)
                    side = position.get('side', '').lower()
                    pos_side = position.get('info', {}).get('posSide', '').lower()
                    if size > 0:
                        if side == 'long' or pos_side == 'long':
                            long_size = size
                        elif side == 'short' or pos_side == 'short':
                            short_size = size
                    elif size < 0:
                        short_size = abs(size)
            return long_size, short_size
        except Exception as e:
            if attempt < max_retries - 1:
                log(Fore.YELLOW + f"Position fetch failed, retrying... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(0.5)
            else:
                log(Fore.YELLOW + f"Warning: Could not fetch positions: {e}")
                return 0.0, 0.0
    return 0.0, 0.0

def print_swap_positions(symbol=None):
    if exchange is None:
        log(Fore.YELLOW + "Exchange not initialized")
        return
    if symbol is None:
        symbol = SYMBOL
    try:
        positions = exchange.fetch_positions([symbol])
        log(Fore.CYAN + "\n" + "=" * 80)
        log(Fore.CYAN + f"POSITIONS FOR {symbol}")
        print("=" * 80)
        has_positions = False
        for position in positions:
            if position['symbol'] == symbol:
                size = float(position.get('contracts', 0))
                if size != 0:
                    has_positions = True
                    side = position.get('side', 'unknown')
                    entry_price = float(position.get('entryPrice', 0))
                    mark_price = float(position.get('markPrice', 0))
                    pnl = float(position.get('unrealizedPnl', 0))
                    print(f"{Fore.CYAN}{side:<10} {size:<12.6f} {entry_price:<12.2f} {mark_price:<12.2f} {pnl:<10.2f}")
        if not has_positions:
            log(Fore.YELLOW + "No active positions for " + symbol)
        print("=" * 80 + "\n")
    except Exception as e:
        log(Fore.YELLOW + f"Warning: Could not print positions: {e}")

def print_open_orders(symbol=None):
    if exchange is None:
        log(Fore.YELLOW + "Exchange not initialized")
        return []
    if symbol is None:
        symbol = SYMBOL
    try:
        orders = exchange.fetch_open_orders(symbol)
        if not orders:
            log(Fore.CYAN + "No open orders for " + symbol)
            return []
        log(Fore.CYAN + f"{len(orders)} open order(s) for {symbol}:")
        for order in orders:
            log(Fore.CYAN + f"  ID: {order['id']}, Side: {order['side']}, Amount: {order['amount']}, Price: {order.get('price', 'N/A')}")
        return orders
    except Exception as e:
        log(Fore.YELLOW + f"Warning: Could not print open orders: {e}")
        return []

def calculate_close_amount(position_size, symbol):
    min_size = get_min_order_size(symbol)
    close_amount = math.ceil((position_size / 2) / min_size) * min_size
    close_amount = min(close_amount, position_size)
    return round(close_amount, 3)

def fetch_ticker_with_retry(ex, symbol, max_retries=3):
    for attempt in range(max_retries):
        try:
            return ex.fetch_ticker(symbol)
        except ccxt.ExchangeNotAvailable:
            if attempt < max_retries - 1:
                log(Fore.YELLOW + f"{EXCHANGE} API unavailable, retrying... (attempt {attempt + 1}/{max_retries})")
                time.sleep(2)
            else:
                raise
        except Exception:
            raise

def fetch_with_retry(ex, func, *args, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
            if attempt < max_retries - 1:
                log(Fore.YELLOW + f"Retrying... (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
            else:
                raise
        except Exception:
            raise

def get_min_order_size(symbol):
    try:
        market = exchange.market(symbol)
        min_amount = market['limits']['amount']['min']
        if min_amount is not None:
            return float(min_amount)
    except Exception as e:
        log(Fore.YELLOW + f"Warning: Could not get min order size for {symbol}: {e}")
    return MIN_LOT_SIZE

def process_single_symbol(symbol, side, lotsize):
    global exchange

    if USE_WEBHOOK_SYMBOL:
        initialize_exchange_for_symbol(symbol)
        get_leverage(symbol)
    else:
        get_leverage(SYMBOL)

    long_size, short_size = get_position_sizes(symbol)
    log(Fore.CYAN + f"Current position sizes for {symbol}: Long={long_size:.6f}, Short={short_size:.6f}")

    # --- Price improvement check (was ONLY_BUY_LOWER / ONLY_BUY_HIGHER) ---
    if PRICE_IMPROVEMENT_MODE in ("buy_lower", "both") and side == 'buy':
        positions = exchange.fetch_positions([symbol])
        entry_price = None
        for position in positions:
            if position['symbol'] == symbol and float(position.get('contracts', 0) or 0) != 0:
                entry_price = float(position.get('entryPrice', 0))
        if entry_price:
            trade_price = limit_price if (
                        USE_LIMIT_ORDERS and 'limit_price' in locals() and limit_price) else get_current_price(symbol)
            if trade_price is not None and trade_price >= entry_price:
                log(Fore.YELLOW + f"Skipped: buy price {trade_price} not lower than open long entry {entry_price}")
                return None, "Trade price not lower than open long — skipped per PRICE_IMPROVEMENT_MODE"

    if PRICE_IMPROVEMENT_MODE in ("sell_higher", "both") and side == 'sell':
        positions = exchange.fetch_positions([symbol])
        entry_price = None
        for position in positions:
            if position['symbol'] == symbol and float(position.get('contracts', 0) or 0) != 0:
                entry_price = float(position.get('entryPrice', 0))
        if entry_price:
            trade_price = limit_price if (
                        USE_LIMIT_ORDERS and 'limit_price' in locals() and limit_price) else get_current_price(symbol)
            if trade_price is not None and trade_price <= entry_price:
                log(Fore.YELLOW + f"Skipped: sell price {trade_price} not higher than open short entry {entry_price}")
                return None, "Trade price not higher than open short — skipped per PRICE_IMPROVEMENT_MODE"

    # Geometric sizing
    if USE_GEOMETRIC_SIZING:
        current_position = long_size if side == 'buy' else short_size
        min_size = get_min_order_size(symbol)
        if current_position == 0:
            lotsize = lotsize if lotsize > min_size else min_size
        else:
            lotsize = current_position * GEOMETRIC_MULTIPLIER
        log(Fore.CYAN + f"Geometric sizing: position {current_position} → {lotsize}")

    if USE_LIMIT_ORDERS:
        current_price = get_current_price(symbol)
        if current_price is not None:
            if side == 'buy':
                limit_price = current_price - LIMIT_OFFSET_POINTS
            else:
                limit_price = current_price + LIMIT_OFFSET_POINTS
            limit_price = float(exchange.price_to_precision(symbol, limit_price))
            order_type = 'limit'
        else:
            order_type = 'market'
            limit_price = None
    else:
        order_type = 'market'
        limit_price = None

    order_params = {
        'hedged': True,
        'posSide': 'Long' if side == 'buy' else 'Short',
    }

    if USE_SL or USE_TP:
        positions = exchange.fetch_positions([symbol])
        entry_price = None
        leverage = 1
        for position in positions:
            if position['symbol'] == symbol and float(position.get('contracts', 0) or 0) != 0:
                entry_price = float(position.get('entryPrice', 0))
                leverage = abs(float(position.get('info', {}).get('leverageRr', 1)))

        tp_sl_base_price = entry_price if entry_price else get_current_price(symbol)
        log(Fore.CYAN + f"🔧 Base price for TP/SL: {tp_sl_base_price} (leverage: {leverage}x)")

        if tp_sl_base_price is not None:
            if USE_TP:
                if TP_MODE == "percent":
                    tp_price_move = TP_PERCENT / leverage
                    tp_trigger = tp_sl_base_price * (1 + tp_price_move / 100) if side == 'buy' else tp_sl_base_price * (
                                1 - tp_price_move / 100)
                elif TP_MODE == "fixed":
                    tp_trigger = FIXED_TP_PRICE_BUY if side == 'buy' else FIXED_TP_PRICE_SELL
                else:  # "points"
                    tp_trigger = tp_sl_base_price + TP_TRIGGER_POINTS if side == 'buy' else tp_sl_base_price - TP_TRIGGER_POINTS
                order_params['takeProfit'] = {'triggerPrice': tp_trigger}
                log(Fore.CYAN + f"Take Profit set at {tp_trigger:.2f}")

            if USE_SL:
                if SL_MODE == "percent":
                    sl_price_move = SL_PERCENT / leverage
                    sl_trigger = tp_sl_base_price * (1 - sl_price_move / 100) if side == 'buy' else tp_sl_base_price * (
                                1 + sl_price_move / 100)
                elif SL_MODE == "fixed":
                    sl_trigger = FIXED_SL_PRICE_BUY if side == 'buy' else FIXED_SL_PRICE_SELL
                else:  # "points"
                    sl_trigger = tp_sl_base_price - SL_TRIGGER_POINTS if side == 'buy' else tp_sl_base_price + SL_TRIGGER_POINTS
                order_params['stopLoss'] = {'triggerPrice': sl_trigger}
                log(Fore.CYAN + f"Stop Loss set at {sl_trigger:.2f}")
    try:
        order = exchange.create_order(symbol, order_type, side, lotsize, limit_price, params=order_params)
        log(Fore.GREEN + f"✅ Order executed: {order['id']} ({side.upper()} {lotsize} {symbol})")
        return order, None
    except Exception as e:
        log(Fore.RED + f"ERROR placing order for {symbol}: {e}")
        return None, str(e)

@app.route('/', methods=['GET'])
def browser_visit():
    return "RanBot TVWebHook_2.0.67 is online", 200

@app.route('/version', methods=['GET'])
def get_version():
    return jsonify({
        'version': '2.0.67',
        'buy_sell_mode': BUY_SELL_MODE,
        'tp_mode': TP_MODE,
        'sl_mode': SL_MODE,
        'price_improvement_mode': PRICE_IMPROVEMENT_MODE,
        'fixed_tp_price_buy': FIXED_TP_PRICE_BUY,
        'fixed_tp_price_sell': FIXED_TP_PRICE_SELL,
        'fixed_sl_price_buy': FIXED_SL_PRICE_BUY,
        'fixed_sl_price_sell': FIXED_SL_PRICE_SELL,
        'tp_percent': TP_PERCENT,
        'sl_percent': SL_PERCENT,
        'tp_trigger_points': TP_TRIGGER_POINTS,
        'sl_trigger_points': SL_TRIGGER_POINTS,
        'use_tp': USE_TP,
        'use_sl': USE_SL,
        'balance_tolerance': BALANCE_TOLERANCE,
        'tradingview_message_mode': TRADINGVIEW_MESSAGE_MODE,
        'max_long_lots': MAX_LONG_LOTS,
        'max_short_lots': MAX_SHORT_LOTS,
        'symbol': SYMBOL,
        'use_webhook_symbol': USE_WEBHOOK_SYMBOL
    })


@app.route('/', methods=['POST'])
def tradingview_webhook():
    print("\n" + "=" * 80)
    log(Fore.MAGENTA + f"🔍 DEBUG Content-Type: {request.content_type}")
    log(Fore.MAGENTA + f"🔍 DEBUG Raw body: {request.data}")
    log(Fore.BLUE + "WEBHOOK HIT - TradingView Alert Received")
    print("=" * 80)

    try:
        data = request.get_json(force=True, silent=True)
        if data is None:
            raw = request.data.decode('utf-8').strip()
            log(Fore.MAGENTA + f"🔍 DEBUG: Plain text received: {raw}")
            data = {'message': raw, 'lotsize': MIN_LOT_SIZE}
            log(Fore.CYAN + f"📥 Parsed as plain text message: {data}")
        else:
            log(Fore.CYAN + f"📥 Received JSON data: {data}")

        if data.get('test') == 'connection':
            log(Fore.GREEN + "Connection test successful")
            return jsonify({'status': 'ok', 'message': 'Connection successful'})

        # Multi-symbol support
        raw_message = data.get('message', '')
        raw_message = raw_message.replace("'", "").replace('"', '')
        commands = [c.strip() for c in raw_message.split('\n') if c.strip()]

        results = []

        for command in commands:
            parts = command.split()
            if len(parts) < 2:
                continue

            cmd_side = parts[0].lower()
            symbol = parts[1]

            # ============================================================================
            # SIDE DETERMINATION LOGIC
            # BUY_SELL_MODE valid values:
            #   "buy"  -> force every trade to BUY
            #   "sell" -> force every trade to SELL
            #   "both" -> no forcing; side comes from webhook payload/message
            #   "auto" -> pick side automatically based on long/short balance vs BALANCE_TOLERANCE
            # ============================================================================

            if BUY_SELL_MODE == "buy":
                cmd_side = 'buy'
            elif BUY_SELL_MODE == "sell":
                cmd_side = 'sell'
            elif BUY_SELL_MODE == "auto":
                long_size, short_size = get_position_sizes()
                difference = abs(long_size - short_size)
                if long_size == 0 and short_size == 0:
                    cmd_side = 'buy'
                elif difference <= BALANCE_TOLERANCE:
                    cmd_side = 'buy' if long_size <= short_size else 'sell'
                elif long_size < short_size:
                    cmd_side = 'buy'
                elif short_size < long_size:
                    cmd_side = 'sell'
                else:
                    return jsonify({'status': 'skipped', 'message': 'Positions balanced'}), 200
                    # "both" -> leave cmd_side as whatever came from the webhook command (parts[0])

            log(Fore.MAGENTA + f"\n===== ACCOUNT SNAPSHOT BEFORE TRADE: {symbol} =====")
            if USE_WEBHOOK_SYMBOL:
                initialize_exchange_for_symbol(symbol)
            get_leverage(symbol)
            print_swap_positions(symbol)
            print_open_orders(symbol)
            log(Fore.MAGENTA + "=" * 50)

            log(Fore.CYAN + f"\n----- Processing {cmd_side.upper()} {symbol} -----")

            order, error = process_single_symbol(symbol, cmd_side, data.get('lotsize', MIN_LOT_SIZE))

            results.append({
                'symbol': symbol,
                'side': cmd_side,
                'order_id': order['id'] if order else None,
                'error': error
            })

        return jsonify({'status': 'done', 'results': results})

    except Exception as e:
        log(Fore.RED + "ERROR in webhook handler:")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    from waitress import serve
    print(Fore.CYAN + "Starting TVWebHook with Waitress")
    print(Fore.CYAN + f"Version: 2.0.67")
    print(Fore.CYAN + f"Symbol: {SYMBOL}")
    print(Fore.CYAN + "Waiting for TradingView alerts...\n")
    serve(app, host='0.0.0.0', port=5000)