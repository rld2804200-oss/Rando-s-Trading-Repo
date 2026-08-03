"""
TVWebHook_2.0.59
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

SYMBOL = 'BTC/USD:BTC'    # BTC-margined BTC perpetual (inverse/coin-m)
# SYMBOL OPTIONS - Uncomment the one you want to use:
#SYMBOL = 'BTC/USDT:USDT'  # USDT-margined BTC perpetual (linear)
# SYMBOL = 'ETH/USDT:USDT'  # USDT-margined ETH perpetual (linear)
# SYMBOL = 'ETH/USD:ETH'    # ETH-margined ETH perpetual (inverse/coin-m)
# SYMBOL = 'XRP/USDT:USDT'  # USDT-margined XRP perpetual
# SYMBOL = 'SOL/USDT:USDT'  # USDT-margined SOL perpetual

# Spot - SYMBOL = 'BTC/USDT'  # Spot trading pair

TRADE_MODE = 'swap'  # Options: 'swap' for futures, 'spot' for spot trading
USE_HEDGE_MODE = False  # True = Hedged (can hold both long/short), False = OneWay (single position)
AUTO_SIDE_MODE = False
TRADINGVIEW_MESSAGE_MODE = True
USE_WEBHOOK_SYMBOL = True

BYPASS_ORDER_SIZE_CHECKS = False  # Set to True to get lot size if USE_GEOMETRIC_SIZING = False
USE_GEOMETRIC_SIZING = False  # Enable geometric progression order sizing
GEOMETRIC_MULTIPLIER = 4  # Multiplier for each order (4x = 1, 4, 16, 64...)

MAX_LONG_LOTS = 10000.0
MAX_SHORT_LOTS = 10000.0
MIN_LOT_SIZE = 1  # Smallest lot size Phemex accepts Coin-M
#MIN_LOT_SIZE = 0.001  # Smallest lot size Phemex accepts usdt
BALANCE_TOLERANCE = 0.001

USE_LIMIT_ORDERS = False
LIMIT_OFFSET_POINTS = 200.0 #points offset to place Limit Orders
AUTO_CANCEL_ORDERS = False #For canceling old limits when using limit orders

BUY_ONLY_MODE = True
SELL_ONLY_MODE = False

#You should only enable one mode at a time (ONLY_BUY_LOWER or ONLY_BUY_HIGHER), not both
ONLY_BUY_HIGHER = False
ONLY_BUY_LOWER = True

USE_SL = False
USE_TP = True
USE_PERCENT_TP_SL = True   # Toggle: True = percentage, False = fixed points
TP_PERCENT = 10           # Take profit: 5% above entry for buys
SL_PERCENT = 5           # Stop loss: 2.5% below entry for buys

SL_TRIGGER_POINTS = 500.0
TP_TRIGGER_POINTS = 400.0


SANDBOX_MODE = False

LOCAL_LONG_SIZE = 0.0
LOCAL_SHORT_SIZE = 0.0
LAST_LONG_ORDER_SIZE = 0.0
LAST_SHORT_ORDER_SIZE = 0.0

app = Flask(__name__)
init(autoreset=True)

print(Fore.CYAN + "=== CODE LOADED ===")
print(Fore.CYAN + "TVWebHook_2.0.59")

ENV_FILE = 'TestNet.env' if SANDBOX_MODE else 'ThisNThat.env'
load_dotenv(ENV_FILE)
print(Fore.GREEN + "Loaded " + ENV_FILE)

api_key = os.getenv('PHEMEX_API_KEY')
api_secret = os.getenv('PHEMEX_SECRET')
print(Fore.CYAN + f"API Key: {api_key[:10]}...")
print(Fore.CYAN + f"API Secret: {api_secret[:10]}...")

# Startup balance check
try:
    temp_exchange = ccxt.phemex({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
    })
    temp_exchange.set_sandbox_mode(SANDBOX_MODE)
    temp_exchange.options['defaultType'] = 'swap'
    bal = temp_exchange.fetch_balance({'type': 'swap', 'code': 'USDT'})
    usdt = bal.get('USDT', {}).get('free', 0) or bal.get('free', {}).get('USDT', 0)
    print(Fore.GREEN + f"Startup USDT free: {usdt}")
except Exception as e:
    print(Fore.YELLOW + f"Startup balance check failed: {e}")

exchange = None
if not USE_WEBHOOK_SYMBOL:
    exchange = ccxt.phemex({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
    })
    exchange.set_sandbox_mode(SANDBOX_MODE)
    if TRADE_MODE == 'swap':
        exchange.options['defaultType'] = 'swap'
    print(Fore.CYAN + "Exchange initialized with default symbol")
else:
    print(Fore.CYAN + "Exchange will be initialized on first webhook")

if not api_key or not api_secret:
    raise ValueError("Missing PHEMEX_API_KEY or PHEMEX_SECRET in " + ENV_FILE)

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
    print(Fore.CYAN + f"🔧 PRE-ORDER CHECK: {side} {amount} {symbol} @ {limit_price}")
    print(Fore.CYAN + f"🔧 Order params: {params}")

    try:
        # Fetch minimum order size and adjust if needed
        min_size = get_min_order_size(symbol)
        if amount < min_size:
            print(Fore.YELLOW + f"⚠️ Amount {amount} below min {min_size}, adjusting")
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

        print(Fore.GREEN + f"✅ Order executed: {order.get('id')} ({side.upper()} {amount} {symbol})")
        return order, "success"

    except ccxt.InvalidOrder as e:
        error_str = str(e)
        if '11058' in error_str:
            # TE_QTY_TOO_SMALL
            min_size = get_min_order_size(symbol)
            print(Fore.YELLOW + f"⚠️ TE_QTY_TOO_SMALL, retrying with min size {min_size}")
            try:
                order = exchange.create_order(symbol, order_type, side, min_size, limit_price, params)
                print(Fore.GREEN + f"✅ Retry successful: {order.get('id')}")
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
        print(Fore.YELLOW + f"Warning: Could not fetch ticker for price: {e}")

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
    exchange = ccxt.phemex({
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
        print(Fore.CYAN + f"🔧 USDT free: {usdt_free}")
        print(Fore.CYAN + f"🔧 Balance fetched for {margin_type}-margined trading")
    except Exception as e:
        print(Fore.YELLOW + f"Warning: Could not fetch balance: {e}")

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
                print(Fore.YELLOW + f"Position fetch failed, retrying... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(0.5)
            else:
                print(Fore.YELLOW + f"Warning: Could not fetch positions: {e}")
                return 0.0, 0.0
    return 0.0, 0.0

def print_swap_positions(symbol=None):
    if exchange is None:
        print(Fore.YELLOW + "Exchange not initialized")
        return
    if symbol is None:
        symbol = SYMBOL
    try:
        positions = exchange.fetch_positions([symbol])
        print(Fore.CYAN + "\n" + "=" * 80)
        print(Fore.CYAN + f"POSITIONS FOR {symbol}")
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
            print(Fore.YELLOW + "No active positions for " + symbol)
        print("=" * 80 + "\n")
    except Exception as e:
        print(Fore.YELLOW + f"Warning: Could not print positions: {e}")

def print_open_orders(symbol=None):
    if exchange is None:
        print(Fore.YELLOW + "Exchange not initialized")
        return []
    if symbol is None:
        symbol = SYMBOL
    try:
        orders = exchange.fetch_open_orders(symbol)
        if not orders:
            print(Fore.CYAN + "No open orders for " + symbol)
            return []
        print(Fore.CYAN + f"{len(orders)} open order(s) for {symbol}:")
        for order in orders:
            print(Fore.CYAN + f"  ID: {order['id']}, Side: {order['side']}, Amount: {order['amount']}, Price: {order.get('price', 'N/A')}")
        return orders
    except Exception as e:
        print(Fore.YELLOW + f"Warning: Could not print open orders: {e}")
        return []

def calculate_close_amount(position_size):
    close_amount = math.ceil((position_size / 2) / get_min_order_size(symbol)) * get_min_order_size(symbol)
    close_amount = min(close_amount, position_size)
    return round(close_amount, 3)

def fetch_ticker_with_retry(ex, symbol, max_retries=3):
    for attempt in range(max_retries):
        try:
            return ex.fetch_ticker(symbol)
        except ccxt.ExchangeNotAvailable:
            if attempt < max_retries - 1:
                print(Fore.YELLOW + f"Phemex API unavailable, retrying... (attempt {attempt + 1}/{max_retries})")
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
                print(Fore.YELLOW + f"Retrying... (attempt {attempt + 1}/{max_retries}): {e}")
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
        print(Fore.YELLOW + f"Warning: Could not get min order size for {symbol}: {e}")
    return MIN_LOT_SIZE


def process_single_symbol(symbol, side, amount):
    global exchange

    if USE_WEBHOOK_SYMBOL:
        initialize_exchange_for_symbol(symbol)
        get_leverage(symbol)
    else:
        get_leverage(SYMBOL)

    long_size, short_size = get_position_sizes(symbol)

    print(Fore.CYAN + f"Current position sizes for {symbol}: Long={long_size:.6f}, Short={short_size:.6f}")

    # Geometric sizing
    if USE_GEOMETRIC_SIZING:
        current_position = long_size if side == 'buy' else short_size
        min_size = get_min_order_size(symbol)
        if current_position == 0:
            amount = min_size
        else:
            amount = current_position * GEOMETRIC_MULTIPLIER
        print(Fore.CYAN + f"Geometric sizing: position {current_position} → {amount}")

    order_type = 'market'
    limit_price = None

    order_params = {
        'hedged': True,
        'posSide': 'Long' if side == 'buy' else 'Short',
    }

    if USE_SL or USE_TP:
        # Get actual entry price and leverage from open position
        positions = exchange.fetch_positions([symbol])
        entry_price = None
        leverage = 1
        for position in positions:
            if position['symbol'] == symbol and float(position.get('contracts', 0) or 0) != 0:
                entry_price = float(position.get('entryPrice', 0))
                leverage = abs(float(position.get('info', {}).get('leverageRr', 1)))

        tp_sl_base_price = entry_price if entry_price else get_current_price(symbol)
        print(Fore.CYAN + f"🔧 Base price for TP/SL: {tp_sl_base_price} (leverage: {leverage}x)")
        if tp_sl_base_price is not None:
            if USE_TP:
                if USE_PERCENT_TP_SL:
                    tp_price_move = TP_PERCENT / leverage  # converts ROI% to actual price% move
                    tp_trigger = tp_sl_base_price * (1 + tp_price_move / 100) if side == 'buy' else tp_sl_base_price * (
                            1 - tp_price_move / 100)
                else:
                    tp_trigger = tp_sl_base_price + TP_TRIGGER_POINTS if side == 'buy' else tp_sl_base_price - TP_TRIGGER_POINTS
                order_params['takeProfit'] = {'triggerPrice': tp_trigger}
                print(Fore.CYAN + f"Take Profit set at {tp_trigger:.2f}")
            if USE_SL:
                if USE_PERCENT_TP_SL:
                    tp_price_move = TP_PERCENT / leverage  # converts ROI% to actual price% move
                    tp_trigger = tp_sl_base_price * (1 + tp_price_move / 100) if side == 'buy' else tp_sl_base_price * (
                            1 - tp_price_move / 100)
                else:
                    sl_trigger = tp_sl_base_price - SL_TRIGGER_POINTS if side == 'buy' else tp_sl_base_price + SL_TRIGGER_POINTS
                order_params['stopLoss'] = {'triggerPrice': sl_trigger}
                print(Fore.CYAN + f"Stop Loss set at {sl_trigger:.2f}")

    try:
        order = exchange.create_order(symbol, order_type, side, amount, limit_price, params=order_params)
        print(Fore.GREEN + f"✅ Order executed: {order['id']} ({side.upper()} {amount} {symbol})")
        return order, None
    except Exception as e:
        print(Fore.RED + f"ERROR placing order for {symbol}: {e}")
        return None, str(e)

@app.route('/version', methods=['GET'])
def get_version():
    return jsonify({
        'version': '2.0.59',
        'auto_side_mode': AUTO_SIDE_MODE,
        'balance_tolerance': BALANCE_TOLERANCE,
        'buy_only_mode': BUY_ONLY_MODE,
        'sell_only_mode': SELL_ONLY_MODE,
        'tradingview_message_mode': TRADINGVIEW_MESSAGE_MODE,
        'use_sl': USE_SL,
        'use_tp': USE_TP,
        'sl_trigger_points': SL_TRIGGER_POINTS,
        'tp_trigger_points': TP_TRIGGER_POINTS,
        'max_long_lots': MAX_LONG_LOTS,
        'max_short_lots': MAX_SHORT_LOTS,
        'symbol': SYMBOL,
        'use_webhook_symbol': USE_WEBHOOK_SYMBOL
    })


@app.route('/', methods=['POST'])
def tradingview_webhook():
    global LAST_LONG_ORDER_SIZE, LAST_SHORT_ORDER_SIZE
    global LOCAL_LONG_SIZE, LOCAL_SHORT_SIZE

    print("\n" + "=" * 80)
    print(Fore.MAGENTA + f"🔍 DEBUG Content-Type: {request.content_type}")
    print(Fore.MAGENTA + f"🔍 DEBUG Raw body: {request.data}")
    print(Fore.BLUE + "WEBHOOK HIT - TradingView Alert Received")
    print("=" * 80)

    try:
        data = request.get_json(force=True, silent=True)
        if data is None:
            raw = request.data.decode('utf-8').strip()
            print(Fore.MAGENTA + f"🔍 DEBUG: Plain text received: {raw}")
            data = {'message': raw, 'amount': MIN_LOT_SIZE}
            print(Fore.CYAN + f"📥 Parsed as plain text message: {data}")
        else:
            print(Fore.CYAN + f"📥 Received JSON data: {data}")

        if data.get('test') == 'connection':
            print(Fore.GREEN + "Connection test successful")
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

            if BUY_ONLY_MODE:
                cmd_side = 'buy'
            elif SELL_ONLY_MODE:
                cmd_side = 'sell'

            print(Fore.MAGENTA + f"\n===== ACCOUNT SNAPSHOT BEFORE TRADE: {symbol} =====")
            if USE_WEBHOOK_SYMBOL:
                initialize_exchange_for_symbol(symbol)
            get_leverage(symbol)
            print_swap_positions(symbol)
            print_open_orders(symbol)
            print(Fore.MAGENTA + "=" * 50)

            print(Fore.CYAN + f"\n----- Processing {cmd_side.upper()} {symbol} -----")

            order, error = process_single_symbol(symbol, cmd_side, data.get('amount', MIN_LOT_SIZE))

            results.append({
                'symbol': symbol,
                'side': cmd_side,
                'order_id': order['id'] if order else None,
                'error': error
            })

        return jsonify({'status': 'done', 'results': results})

    except Exception as e:
        print(Fore.RED + "ERROR in webhook handler:")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    print(Fore.CYAN + "Starting TVWebHook")
    print(Fore.CYAN + f"Version: 2.0.59")
    print(Fore.CYAN + f"Symbol: {SYMBOL}")
    print(Fore.CYAN + "Waiting for TradingView alerts...\n")
    app.run(host='0.0.0.0', port=5000)
