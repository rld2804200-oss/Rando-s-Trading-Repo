"""
TVWebHook_2.0.52
TradingView Webhook Handler for CCXT Trading
"""

from flask import Flask, request, jsonify
import ccxt
import os
import traceback
from dotenv import load_dotenv
from datetime import datetime
from colorama import Fore, Style, init
import math
import time

symbol = 'BTC/USD:BTC'    # BTC-margined BTC perpetual (inverse/coin-m)
# symbol OPTIONS - Uncomment the one you want to use:
#symbol = 'BTC/USDT:USDT'  # USDT-margined BTC perpetual (linear)
# symbol = 'ETH/USDT:USDT'  # USDT-margined ETH perpetual (linear)
# symbol = 'ETH/USD:ETH'    # ETH-margined ETH perpetual (inverse/coin-m)
# symbol = 'XRP/USDT:USDT'  # USDT-margined XRP perpetual
# symbol = 'SOL/USDT:USDT'  # USDT-margined SOL perpetual

# Spot - symbol = 'BTC/USDT'  # Spot trading pair

TRADE_MODE = 'swap'  # Options: 'swap' for futures, 'spot' for spot trading
USE_HEDGE_MODE = False  # True = Hedged (can hold both long/short), False = OneWay (single position)
USE_WEBHOOK_symbol = False  # True = use symbol from webhook, False = use default symbol
MAX_LONG_LOTS = 10000.0
MAX_SHORT_LOTS = 10000.0
MIN_LOT_SIZE = 1.0  # Smallest lot size Phemex accepts Coin-M
#MIN_LOT_SIZE = 0.001  # Smallest lot size Phemex accepts usdt
BALANCE_TOLERANCE = 0.001

BYPASS_ORDER_SIZE_CHECKS = True  # Set to True to get lot size if USE_GEOMETRIC_SIZING = False
USE_GEOMETRIC_SIZING = True  # Enable geometric progression order sizing
GEOMETRIC_MULTIPLIER = 4  # Multiplier for each order (4x = 1, 4, 16, 64...)

TRADINGVIEW_MESSAGE_MODE = True
AUTO_SIDE_MODE = False

USE_LIMIT_ORDERS = False
LIMIT_OFFSET_POINTS = 200.0 #points offset to place Limit Orders
AUTO_CANCEL_ORDERS = False #For canceling old limits when using limit orders

BUY_ONLY_MODE = True
SELL_ONLY_MODE = False

#You should only enable one mode at a time (ONLY_BUY_LOWER or ONLY_BUY_HIGHER), not both
ONLY_BUY_HIGHER = False  # Only allow buy orders higher than last buy, and short orders lower than last short
ONLY_BUY_LOWER = True  # Only allow buy orders lower than last buy, and short orders higher than last short

USE_SL = False
USE_TP = True
SL_TRIGGER_POINTS = 500.0
TP_TRIGGER_POINTS = 1000.0

SANDBOX_MODE = True  # Set to False for mainnet or True for TestNet

# Track position size locally for geometric sizing
LOCAL_LONG_SIZE = 0.0
LOCAL_SHORT_SIZE = 0.0
LAST_LONG_ORDER_SIZE = 0.0  # Track last order size for geometric sizing
LAST_SHORT_ORDER_SIZE = 0.0

app = Flask(__name__)
init(autoreset=True)
print(Fore.CYAN + "=== CODE LOADED ===")
print(Fore.CYAN + "TVWebHook_2.0.51")

if SANDBOX_MODE:
    #ENV_FILE = 'test.env'
    ENV_FILE = 'testCoinM.env'
else:
    ENV_FILE = '.env'

load_dotenv(ENV_FILE)
print(Fore.GREEN + "Loaded " + ENV_FILE)

api_key = os.getenv('PHEMEX_API_KEY')
api_secret = os.getenv('PHEMEX_SECRET')

print(Fore.CYAN + f"API Key: {api_key[:10]}...")
print(Fore.CYAN + f"API Secret: {api_secret[:10]}...")

# symbol configuration based on trade mode
if TRADE_MODE == 'swap':
    symbol = 'BTC/USD:BTC'  # Perpetual swap (inverse/coin-margined)
    # symbol = 'BTC/USDT:USDT'  # USDT-margined perpetual (linear)
else:
    symbol = 'BTC/USDT'  # Spot trading pair

# Exchange configuration
exchange = ccxt.phemex({
    'apiKey': api_key,
    'secret': api_secret,
    'enableRateLimit': True,
})

# Only set swap-specific options if in swap mode
if TRADE_MODE == 'swap':
    exchange.options['defaultType'] = 'swap'

if TRADE_MODE == 'swap':
    if USE_HEDGE_MODE:
        try:
            exchange.set_position_mode(True, symbol)
            print(Fore.GREEN + "Position mode set to Hedged")
        except Exception as e:
            print(Fore.YELLOW + f"Warning: Could not set position mode: {e}")
    else:
        try:
            exchange.set_position_mode(False, symbol)
            print(Fore.GREEN + "Position mode set to OneWay")
        except Exception as e:
            print(Fore.YELLOW + f"Warning: Could not set position mode: {e}")


exchange.set_sandbox_mode(SANDBOX_MODE)
print(Fore.GREEN + "Sandbox mode enabled")

# Set position mode (hedged vs one-way)

if not api_key or not api_secret:
    raise ValueError("Missing PHEMEX_API_KEY or PHEMEX_SECRET in " + ENV_FILE)


def get_position_sizes(symbol=None):
    if symbol is None:
        symbol = symbol
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
    if symbol is None:
        symbol = symbol
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
    if symbol is None:
        symbol = symbol
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
    # Always close the ceiling of 50% (larger half), rounded up to nearest 0.001
    close_amount = math.ceil((position_size / 2) / MIN_LOT_SIZE) * MIN_LOT_SIZE
    # Cap at full position size (safety check)
    close_amount = min(close_amount, position_size)
    return round(close_amount, 3)

def fetch_ticker_with_retry(exchange, symbol, max_retries=3):
    """Fetch ticker with retry logic for exchange API errors."""
    for attempt in range(max_retries):
        try:
            return exchange.fetch_ticker(symbol)
        except ccxt.ExchangeNotAvailable as e:
            if attempt < max_retries - 1:
                print(Fore.YELLOW + f"Phemex API unavailable, retrying... (attempt {attempt + 1}/{max_retries})")
                time.sleep(2)
            else:
                raise
        except Exception as e:
            raise
def fetch_with_retry(exchange, func, *args, max_retries=3, **kwargs):
    """Execute exchange function with retry logic for network errors."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except ccxt.NetworkError as e:
            if attempt < max_retries - 1:
                print(Fore.YELLOW + f"Network error, retrying... (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
            else:
                raise
        except ccxt.ExchangeNotAvailable as e:
            if attempt < max_retries - 1:
                print(Fore.YELLOW + f"Exchange unavailable, retrying... (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(5)
            else:
                raise
        except Exception as e:
            raise


@app.route('/', methods=['POST'])
def tradingview_webhook():
    global LAST_LONG_ORDER_SIZE, LAST_SHORT_ORDER_SIZE
    global LOCAL_LONG_SIZE, LOCAL_SHORT_SIZE

    print("\n" + "=" * 80)
    print(Fore.MAGENTA + f"🔍 DEBUG Content-Type: {request.content_type}")
    print(Fore.MAGENTA + f"🔍 DEBUG Raw body: {request.data}")
    print(Fore.MAGENTA + f"🔍 DEBUG Headers: {dict(request.headers)}")
    print(Fore.BLUE + "WEBHOOK HIT - TradingView Alert Received")
    print("=" * 80)

    try:
        data = request.get_json(force=True, silent=True)
        if data is None:
            raw = request.data.decode('utf-8').strip().lower()
            print(Fore.MAGENTA + f"🔍 DEBUG: Plain text received: {raw}")
            data = {'message': raw, 'amount': MIN_LOT_SIZE}
            print(Fore.CYAN + f"📥 Parsed as plain text message: {data}")
        else:
            print(Fore.CYAN + f"📥 Received JSON data: {data}")

        if data.get('test') == 'connection':
            print(Fore.GREEN + "Connection test successful")
            return jsonify({'status': 'ok', 'message': 'Connection successful'})

            # TOGGLE: Determine symbol source
        if USE_WEBHOOK_symbol:
            symbol = data.get('symbol', symbol)  # Use webhook symbol, fallback to default
            print(Fore.CYAN + f"🔧 WEBHOOK symbol MODE: Using symbol from webhook: {symbol}")
        else:
            symbol = symbol  # Use default hardcoded symbol
            print(Fore.CYAN + f"🔧 REGULAR MODE: Using default symbol: {symbol}")

        amount = float(data.get('amount', 0.001))
        side = data.get('side', 'buy').lower()
        order_params = {}

        if BUY_ONLY_MODE:
            side = 'buy'
            print(Fore.MAGENTA + "BUY ONLY MODE: Forced to BUY")
        elif SELL_ONLY_MODE:
            side = 'sell'
            print(Fore.MAGENTA + "SELL ONLY MODE: Forced to SELL")

        # Warning if sell is attempted when SELL_ONLY_MODE is False
        if side == 'sell' and not SELL_ONLY_MODE and not BUY_ONLY_MODE:
            print(Fore.RED + "⚠️ WARNING: Sell order attempted but SELL_ONLY_MODE is False")

        # Warning if buy is attempted when BUY_ONLY_MODE is False
        if side == 'buy' and not BUY_ONLY_MODE and not SELL_ONLY_MODE:
            print(Fore.RED + "⚠️ WARNING: Buy order attempted but BUY_ONLY_MODE is False")

        if TRADINGVIEW_MESSAGE_MODE:
            message = data.get('message', '').lower()
            print(Fore.CYAN + f"Received message: {message}")

            if 'close' in message and 'long' in message:
                long_size, short_size = get_position_sizes(symbol)
                if long_size > 0:
                    amount = calculate_close_amount(long_size)
                    side = 'sell'
                    order_params['reduceOnly'] = True
                    print(Fore.MAGENTA + f"CLOSING LONG: {long_size} → closing {amount}")
                    if USE_GEOMETRIC_SIZING:
                        LOCAL_LONG_SIZE = 0.0
                        print(Fore.CYAN + "Reset local long position size to 0")
                else:
                    return jsonify({'status': 'skipped', 'message': 'No long position'}), 200

            elif 'close' in message and 'short' in message:
                long_size, short_size = get_position_sizes(symbol)
                if short_size > 0:
                    amount = calculate_close_amount(short_size)
                    side = 'buy'
                    order_params['reduceOnly'] = True
                    print(Fore.MAGENTA + f"CLOSING SHORT: {short_size} → closing {amount}")
                    if USE_GEOMETRIC_SIZING:
                        LOCAL_SHORT_SIZE = 0.0
                        print(Fore.CYAN + "Reset local short position size to 0")
                else:
                    return jsonify({'status': 'skipped', 'message': 'No short position'}), 200

            elif 'close' in message and 'buy' in message:
                long_size, short_size = get_position_sizes(symbol)
                if long_size > 0:
                    amount = calculate_close_amount(long_size)
                    side = 'sell'
                    order_params['reduceOnly'] = True
                    print(Fore.MAGENTA + f"CLOSING LONG: {long_size} → closing {amount}")
                    if USE_GEOMETRIC_SIZING:
                        LOCAL_LONG_SIZE = 0.0
                        print(Fore.CYAN + "Reset local long position size to 0")
                else:
                    return jsonify({'status': 'skipped', 'message': 'No long position'}), 200

            elif 'close' in message and 'sell' in message:
                long_size, short_size = get_position_sizes(symbol)
                if short_size > 0:
                    amount = calculate_close_amount(short_size)
                    side = 'buy'
                    order_params['reduceOnly'] = True
                    print(Fore.MAGENTA + f"CLOSING SHORT: {short_size} → closing {amount}")
                    if USE_GEOMETRIC_SIZING:
                        LOCAL_SHORT_SIZE = 0.0
                        print(Fore.CYAN + "Reset local short position size to 0")
                else:
                    return jsonify({'status': 'skipped', 'message': 'No short position'}), 200

            elif 'long' in message:
                side = 'buy'

            elif 'short' in message:
                side = 'sell'

            elif 'buy' in message:
                side = 'buy'

            elif 'sell' in message:
                side = 'sell'

            else:
                print(Fore.YELLOW + f"Unknown message: {message}")
                return jsonify({'status': 'skipped', 'message': 'Unknown message'}), 200

        elif AUTO_SIDE_MODE:
            long_size, short_size = get_position_sizes(symbol)
            difference = abs(long_size - short_size)
            print(Fore.CYAN + f"Position sizes: Long={long_size:.6f}, Short={short_size:.6f}, Diff={difference:.6f}")
            if long_size == 0 and short_size == 0:
                side = 'buy'
                print(Fore.MAGENTA + f"AUTO SIDE MODE: No positions, opening {side}")
            elif difference <= BALANCE_TOLERANCE:
                side = 'buy' if long_size <= short_size else 'sell'
                print(Fore.MAGENTA + f"AUTO SIDE MODE: Within tolerance, {side}")
            elif long_size < short_size:
                side = 'buy'
                print(Fore.MAGENTA + "AUTO SIDE MODE: BUYING")
            elif short_size < long_size:
                side = 'sell'
                print(Fore.MAGENTA + "AUTO SIDE MODE: SELLING")
            else:
                print(Fore.MAGENTA + "AUTO SIDE MODE: Balanced, no trade")
                return jsonify({'status': 'skipped', 'message': 'Positions balanced'}), 200
        else:
            side = data.get('side', 'buy').lower()

        print(Fore.CYAN + f"Trading parameters: Side={side}, Amount={amount}")

        long_size, short_size = get_position_sizes(symbol)
        print(Fore.CYAN + f"Current position sizes: Long={long_size:.6f}, Short={short_size:.6f}")

        # Buy side check
        if side == 'buy' and 'reduceOnly' not in order_params:
            if not BYPASS_ORDER_SIZE_CHECKS and long_size + amount > MAX_LONG_LOTS:
                print(Fore.RED + f"❌ ERROR: Buy order would exceed max long lots ({MAX_LONG_LOTS})")
                return jsonify({
                    'status': 'error',
                    'message': f'Buy order would exceed max long lots ({MAX_LONG_LOTS})'
                }), 429

        # Sell side check
        if side == 'sell' and 'reduceOnly' not in order_params:
            if not BYPASS_ORDER_SIZE_CHECKS and short_size + amount > MAX_SHORT_LOTS:
                print(Fore.RED + f"❌ ERROR: Sell order would exceed max short lots ({MAX_SHORT_LOTS})")
                return jsonify({
                    'status': 'error',
                    'message': f'Sell order would exceed max short lots ({MAX_SHORT_LOTS})'
                }), 429

        # One-way mode opposite position warning
        if not USE_HEDGE_MODE and 'reduceOnly' not in order_params:
            if side == 'buy' and short_size > 0:
                print(
                    Fore.RED + "⚠️ WARNING: OneWay mode - Cannot open LONG while SHORT position exists. Close short position first.")
                return jsonify(
                    {'status': 'skipped', 'message': 'Close short position before opening long in OneWay mode'}), 200
            elif side == 'sell' and long_size > 0:
                print(
                    Fore.RED + "⚠️ WARNING: OneWay mode - Cannot open SHORT while LONG position exists. Close long position first.")
                return jsonify(
                    {'status': 'skipped', 'message': 'Close long position before opening short in OneWay mode'}), 200

        # Only_Buy_Lower / Only_Buy_Higher price check
        if (ONLY_BUY_LOWER or ONLY_BUY_HIGHER) and 'reduceOnly' not in order_params:
            try:
                # Get current price
                ticker = fetch_ticker_with_retry(exchange, symbol)
                current_price = ticker['last']

                # Fetch recent orders to find the last buy/short price
                orders = exchange.fetch_orders(symbol, limit=10)

                if side == 'buy':
                    # Find the most recent buy order
                    last_buy_order = None
                    for order in orders:
                        if order['side'] == 'buy' and order['status'] == 'closed':
                            last_buy_order = order
                            break

                    if last_buy_order:
                        last_buy_price = last_buy_order['average'] or last_buy_order['price']
                        if ONLY_BUY_LOWER and current_price >= last_buy_price:
                            print(
                                Fore.RED + f"⚠️ WARNING: Only_Buy_Lower mode - Current price {current_price:.2f} is not lower than last buy {last_buy_price:.2f}")
                            return jsonify({'status': 'skipped',
                                            'message': f'Price {current_price:.2f} not lower than last buy {last_buy_price:.2f}'}), 200
                        elif ONLY_BUY_HIGHER and current_price <= last_buy_price:
                            print(
                                Fore.RED + f"⚠️ WARNING: Only_Buy_Higher mode - Current price {current_price:.2f} is not higher than last buy {last_buy_price:.2f}")
                            return jsonify({'status': 'skipped',
                                            'message': f'Price {current_price:.2f} not higher than last buy {last_buy_price:.2f}'}), 200

                elif side == 'sell':
                    # Find the most recent short order
                    last_short_order = None
                    for order in orders:
                        if order['side'] == 'sell' and order['status'] == 'closed':
                            last_short_order = order
                            break

                    if last_short_order:
                        last_short_price = last_short_order['average'] or last_short_order['price']
                        if ONLY_BUY_LOWER and current_price <= last_short_price:
                            print(
                                Fore.RED + f"⚠️ WARNING: Only_Buy_Lower mode - Current price {current_price:.2f} is not higher than last short {last_short_price:.2f}")
                            return jsonify({'status': 'skipped',
                                            'message': f'Price {current_price:.2f} not higher than last short {last_short_price:.2f}'}), 200
                        elif ONLY_BUY_HIGHER and current_price >= last_short_price:
                            print(
                                Fore.RED + f"⚠️ WARNING: Only_Buy_Higher mode - Current price {current_price:.2f} is not lower than last short {last_short_price:.2f}")
                            return jsonify({'status': 'skipped',
                                            'message': f'Price {current_price:.2f} not lower than last short {last_short_price:.2f}'}), 200
            except Exception as e:
                print(Fore.YELLOW + f"Warning: Could not fetch orders for price check: {e}")

        #Geometric sizing calculation
        if USE_GEOMETRIC_SIZING and 'reduceOnly' not in order_params:
            if side == 'buy':
                current_position = long_size
                max_lots = MAX_LONG_LOTS
            else:
                current_position = short_size
                max_lots = MAX_SHORT_LOTS

            if current_position == 0:
                geometric_amount = MIN_LOT_SIZE
            else:
                geometric_amount = current_position * GEOMETRIC_MULTIPLIER

                # Cap based on total position size, not individual order size
            if current_position + geometric_amount > max_lots:
                geometric_amount = max_lots - current_position

                # Prevent negative or zero order sizes if position already at max
            if geometric_amount <= 0:
                print(Fore.RED + f"⚠️ WARNING: Position already at maximum ({max_lots}). Cannot add more.")
                return jsonify({'status': 'skipped', 'message': 'Position at maximum size'}), 200

            amount = geometric_amount
            print(
                Fore.CYAN + f"Geometric sizing: position {current_position} → {amount} (total will be {current_position + amount})")

        # Cancel existing TP orders before placing a new opening order
        if 'reduceOnly' not in order_params:
            try:
                open_orders = exchange.fetch_open_orders(symbol)
                for o in open_orders:
                    # These are the TP orders (amount 0.0, side opposite)
                    if float(o.get('amount', 0) or 0) == 0:
                        exchange.cancel_order(o['id'], symbol)
                        print(Fore.YELLOW + f"Cancelled old TP order: {o['id']}")
            except Exception as e:
                print(Fore.YELLOW + f"Warning: Could not cancel old TP orders - {e}")

        open_orders = print_open_orders(symbol)
        if open_orders:
            print(Fore.YELLOW + f"Warning: {len(open_orders)} open orders exist")

        if 'reduceOnly' in order_params:
            # Closing a position: posSide is the position being closed
            # Selling to close a long → posSide must be 'Long'
            # Buying to close a short → posSide must be 'Short'
            pos_side = 'Long' if side == 'sell' else 'Short'
        else:
            # Opening a position: posSide matches the order direction
            pos_side = 'Long' if side == 'buy' else 'Short'
        order = None

        if not order_params:
            order_params = {'hedged': True, 'posSide': pos_side}
        else:
            order_params['hedged'] = True
            order_params['posSide'] = pos_side

        """# Block new orders in OneWay mode if any open orders exist
        if not USE_HEDGE_MODE:
            open_orders = exchange.fetch_open_orders(symbol)
            if open_orders:
                print(Fore.RED + f"❌ ERROR: {len(open_orders)} open order(s) exist. No new trade in OneWay mode.")
                return jsonify({
                    'status': 'error',
                    'message': f'{len(open_orders)} open order(s) exist. Cannot place new order in one-way mode.'
                }), 409
        """

        if AUTO_CANCEL_ORDERS:
            try:
                open_orders = exchange.fetch_open_orders(symbol)
                if open_orders:
                    exchange.cancel_all_orders(symbol)
                    print(Fore.YELLOW + f"Auto-cancelled all {len(open_orders)} open order(s)")
                else:
                    print(Fore.YELLOW + "Warning: No open orders to cancel")
            except ccxt.NetworkError as e:
                print(Fore.YELLOW + f"Warning: Network error fetching orders - {e}")
            except Exception as e:
                print(Fore.YELLOW + f"Warning: Could not fetch orders - {e}")

        if USE_LIMIT_ORDERS:
            try:
                print(Fore.MAGENTA + "DEBUG: Attempting to set up limit order...")
                ticker = fetch_ticker_with_retry(exchange, symbol)
                current_price = ticker['last']
                print(Fore.MAGENTA + f"DEBUG: Current market price: {current_price}")
                if side == 'buy':
                    limit_price = current_price - LIMIT_OFFSET_POINTS
                else:
                    limit_price = current_price + LIMIT_OFFSET_POINTS
                limit_price = float(exchange.price_to_precision(symbol, limit_price))
                order_type = 'limit'
                order_params['hedged'] = USE_HEDGE_MODE
                print(Fore.GREEN + f"DEBUG: Limit order price set at {limit_price:.2f}")
            except Exception as e:
                print(Fore.RED + f"DEBUG: Exception: {type(e).__name__}: {str(e)}")
                print(Fore.YELLOW + "Warning: Could not set limit price, skipping order")
                limit_price = None
                order_type = None
        else:
            print(Fore.MAGENTA + "DEBUG: USE_LIMIT_ORDERS is False, using market order")
            order_type = 'market'
            limit_price = None

        print(Fore.MAGENTA + f"DEBUG: Final order_type: {order_type}, price: {limit_price}")

        if order_type == 'limit' and limit_price is not None:
            tp_sl_base_price = limit_price
        else:
            if USE_SL or USE_TP:
                if 'ticker' not in locals():
                    ticker = fetch_ticker_with_retry(exchange, symbol)
                tp_sl_base_price = ticker['last']

        if TRADE_MODE == 'swap':
            if 'reduceOnly' not in order_params:
                # Check if this order would close a position
                is_closing_order = False
                if side == 'sell' and long_size > 0:
                    is_closing_order = True
                elif side == 'buy' and short_size > 0:
                    is_closing_order = True

                if is_closing_order:
                    print(
                        Fore.YELLOW + "⚠️ WARNING: Skipping TP/SL for closing order (Phemex doesn't allow TP/SL on close orders)")
                else:
                    if USE_SL:
                        try:
                            sl_trigger = tp_sl_base_price - SL_TRIGGER_POINTS if side == 'buy' else tp_sl_base_price + SL_TRIGGER_POINTS
                            order_params['stopLoss'] = {'triggerPrice': sl_trigger}
                            print(Fore.CYAN + f"Stop Loss set at {sl_trigger:.2f}")
                        except Exception as e:
                            print(Fore.YELLOW + f"Warning: Could not set stop loss: {e}")
                    if USE_TP:
                        try:
                            tp_trigger = tp_sl_base_price + TP_TRIGGER_POINTS if side == 'buy' else tp_sl_base_price - TP_TRIGGER_POINTS
                            order_params['takeProfit'] = {'triggerPrice': tp_trigger}
                            print(Fore.CYAN + f"Take Profit set at {tp_trigger:.2f}")
                        except Exception as e:
                            print(Fore.YELLOW + f"Warning: Could not set take profit: {e}")

        if order_type is not None:
            try:
                order = fetch_with_retry(exchange, exchange.create_order, symbol, order_type, side, amount, limit_price,
                                         params=order_params)
                print(Fore.GREEN + f"Order executed: {order['id']} ({side.upper()} {amount})")

                if USE_GEOMETRIC_SIZING and 'reduceOnly' not in order_params:
                    if side == 'buy':
                        LAST_LONG_ORDER_SIZE = amount
                        print(Fore.CYAN + f"Last long order size set to {LAST_LONG_ORDER_SIZE}")
                    else:
                        LAST_SHORT_ORDER_SIZE = amount
                        print(Fore.CYAN + f"Last short order size set to {LAST_SHORT_ORDER_SIZE}")

            except ccxt.InsufficientFunds as e:
                print(Fore.YELLOW + f"⚠️ WARNING: Insufficient funds - {e}")
                return jsonify({'status': 'warning', 'message': f'Insufficient funds: {str(e)}'}), 200
            except ccxt.NetworkError as e:
                return jsonify({'status': 'error', 'message': f'Network error: {str(e)}'}), 503
            except ccxt.ExchangeNotAvailable as e:
                print(Fore.RED + f"Exchange unavailable: Could not execute order - {e}")
                return jsonify({'status': 'error', 'message': f'Exchange unavailable: {str(e)}'}), 503
            except ccxt.AuthenticationError as e:
                print(Fore.RED + f"Authentication error: {e}")
                return jsonify({'status': 'error', 'message': f'Authentication error: {str(e)}'}), 401
            except Exception as e:
                print(Fore.RED + "ERROR in webhook handler:")
                traceback.print_exc()
                return jsonify({'status': 'error', 'message': str(e)}), 500
        else:
            print(Fore.YELLOW + "No order placed (limit order setup failed or USE_LIMIT_ORDERS is False).")
            return jsonify({'status': 'skipped', 'message': 'No order placed'}), 200

        print_swap_positions(symbol)
        print_open_orders(symbol)

        if order_type is not None:
            return jsonify({
                'status': 'success',
                'order_id': order['id'],
                'side': side,
                'amount': amount,
                'long_size': long_size,
                'short_size': short_size
            })

    except Exception as e:
        print(Fore.RED + "ERROR in webhook handler:")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/version', methods=['GET'])
def get_version():
    return jsonify({
        'version': '2.0.52',
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
        'symbol': symbol,
        'use_webhook_symbol': USE_WEBHOOK_symbol
    })


if __name__ == '__main__':
    print(Fore.CYAN + "Starting TVWebHook")
    print(Fore.CYAN + f"Version: 2.0.51")
    print(Fore.CYAN + f"symbol: {symbol}")
    print(Fore.CYAN + f"Max long lots: {MAX_LONG_LOTS}")
    print(Fore.CYAN + f"Max short lots: {MAX_SHORT_LOTS}")
    print(Fore.CYAN + f"Auto Side Mode enabled: {AUTO_SIDE_MODE}")
    print(Fore.CYAN + f"Buy Only Mode: {BUY_ONLY_MODE}")
    print(Fore.CYAN + f"Sell Only Mode: {SELL_ONLY_MODE}")
    print(Fore.CYAN + f"TradingView Message Mode enabled: {TRADINGVIEW_MESSAGE_MODE}")
    print(Fore.CYAN + f"Use SL: {USE_SL}")
    print(Fore.CYAN + f"Use TP: {USE_TP}")
    print(Fore.CYAN + "Waiting for TradingView alerts...\n")
    app.run(host='0.0.0.0', port=5000)