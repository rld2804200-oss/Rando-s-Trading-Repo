"""
TVWebHook_2.0.32
TradingView Webhook Handler for CCXT Trading

Version History:
- 2.0.32: Added position closing functionality with 'close' keyword
- 2.0.31: Added limit order toggle with adjustable points offset from current price
- 2.0.30: Fixed indentation issue in ORDER EXECUTION section
- 2.0.29: Changed SL/TP from percentage-based to points-based trigger calculation
- 2.0.28: Added stop loss and take profit toggles for opening orders
- 2.0.27: Changed max lots configuration to 0.003 for both long and short positions
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




# SYMBOL OPTIONS - Uncomment the one you want to use:
SYMBOL = 'BTC/USDT:USDT'  # USDT-margined BTC perpetual (linear)
# SYMBOL = 'ETH/USDT:USDT'  # USDT-margined ETH perpetual (linear)
# SYMBOL = 'BTC/USD:BTC'    # BTC-margined BTC perpetual (inverse/coin-m)
# SYMBOL = 'ETH/USD:ETH'    # ETH-margined ETH perpetual (inverse/coin-m)
# SYMBOL = 'XRP/USDT:USDT'  # USDT-margined XRP perpetual
# SYMBOL = 'SOL/USDT:USDT'  # USDT-margined SOL perpetual

MIN_LOT_SIZE = 0.001  # Smallest lot size Phemex accepts
USE_HEDGE_MODE = True  # True = Hedged (can hold both long/short), False = OneWay (single position)
MAX_LONG_LOTS = 0.004
MAX_SHORT_LOTS = 0.004
AUTO_CANCEL_ORDERS = True
AUTO_SIDE_MODE = False
BALANCE_TOLERANCE = 0.001
BUY_ONLY_MODE = False
SELL_ONLY_MODE = False
TRADINGVIEW_MESSAGE_MODE = True
USE_SL = False
USE_TP = True
SL_TRIGGER_POINTS = 500.0
TP_TRIGGER_POINTS = 400.0
USE_LIMIT_ORDERS = False
LIMIT_OFFSET_POINTS = 200.0
SANDBOX_MODE = True  # Set to False for mainnet or True for TestNet

app = Flask(__name__)
init(autoreset=True)
print(Fore.CYAN + "=== CODE LOADED ===")
print(Fore.CYAN + "TVWebHook_2.0.34")

if SANDBOX_MODE:
    ENV_FILE = 'test.env'
else:
    ENV_FILE = '.env'

load_dotenv(ENV_FILE)
print(Fore.GREEN + "Loaded " + ENV_FILE)

api_key = os.getenv('PHEMEX_API_KEY')
api_secret = os.getenv('PHEMEX_SECRET')

print(Fore.CYAN + f"API Key: {api_key[:10]}...")
print(Fore.CYAN + f"API Secret: {api_secret[:10]}...")
exchange = ccxt.phemex({
    'apiKey': api_key,
    'secret': api_secret,
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'},
})

exchange.set_sandbox_mode(SANDBOX_MODE)
print(Fore.GREEN + "Sandbox mode enabled")

# Set position mode (hedged vs one-way)
if USE_HEDGE_MODE:
    try:
        exchange.set_position_mode(True, SYMBOL)  # True = Hedged mode
        print(Fore.GREEN + "Position mode set to Hedged")
    except Exception as e:
        print(Fore.YELLOW + f"Warning: Could not set position mode: {e}")
else:
    try:
        exchange.set_position_mode(False, SYMBOL)  # False = OneWay mode
        print(Fore.GREEN + "Position mode set to OneWay")
    except Exception as e:
        print(Fore.YELLOW + f"Warning: Could not set position mode: {e}")

if not api_key or not api_secret:
    raise ValueError("Missing PHEMEX_API_KEY or PHEMEX_SECRET in " + ENV_FILE)

def get_position_sizes():
    try:
        positions = exchange.fetch_positions([SYMBOL])
        long_size = 0.0
        short_size = 0.0
        for position in positions:
            if position['symbol'] == SYMBOL:
                size = float(position.get('contracts', 0))
                if size > 0:
                    pos_side = position.get('info', {}).get('posSide', position.get('side', ''))
                    if pos_side == 'Long':
                        long_size = size
                    elif pos_side == 'Short':
                        short_size = size
                elif size < 0:
                    short_size = abs(size)
        return long_size, short_size
    except Exception as e:
        print(Fore.YELLOW + f"Warning: Could not fetch positions: {e}")
        return 0.0, 0.0

def print_swap_positions():
    try:
        positions = exchange.fetch_positions([SYMBOL])
        print(Fore.CYAN + "\n" + "=" * 80)
        print(Fore.CYAN + f"POSITIONS FOR {SYMBOL}")
        print("=" * 80)
        has_positions = False
        for position in positions:
            if position['symbol'] == SYMBOL:
                size = float(position.get('contracts', 0))
                if size != 0:
                    has_positions = True
                    side = position.get('side', 'unknown')
                    entry_price = float(position.get('entryPrice', 0))
                    mark_price = float(position.get('markPrice', 0))
                    pnl = float(position.get('unrealizedPnl', 0))
                    print(f"{Fore.CYAN}{side:<10} {size:<12.6f} {entry_price:<12.2f} {mark_price:<12.2f} {pnl:<10.2f}")
        if not has_positions:
            print(Fore.YELLOW + "No active positions for " + SYMBOL)
        print("=" * 80 + "\n")
    except Exception as e:
        print(Fore.YELLOW + f"Warning: Could not print positions: {e}")

def print_open_orders():
    try:
        orders = exchange.fetch_open_orders(SYMBOL)
        if not orders:
            print(Fore.CYAN + "No open orders for " + SYMBOL)
            return []
        print(Fore.CYAN + f"{len(orders)} open order(s) for {SYMBOL}:")
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
    print("\n" + "=" * 80)
    # DEBUG: Log everything about the incoming request
    print(Fore.MAGENTA + f"🔍 DEBUG Content-Type: {request.content_type}")
    print(Fore.MAGENTA + f"🔍 DEBUG Raw body: {request.data}")
    print(Fore.MAGENTA + f"🔍 DEBUG Headers: {dict(request.headers)}")
    print(Fore.BLUE + "WEBHOOK HIT - TradingView Alert Received")
    print("=" * 80)
    try:
        data = request.get_json(force=True, silent=True)
        if data is None:
            # TradingView sent plain text (e.g. just the word "close", "buy", or "sell")
            raw = request.data.decode('utf-8').strip().lower()
            print(Fore.MAGENTA + f"🔍 DEBUG: Plain text received: {raw}")
            data = {'message': raw, 'amount': 0.001}
            print(Fore.CYAN + f"📥 Parsed as plain text message: {data}")
        else:
            print(Fore.CYAN + f"📥 Received JSON data: {data}")
        if data.get('test') == 'connection':
            print(Fore.GREEN + "Connection test successful")
            return jsonify({'status': 'ok', 'message': 'Connection successful'})
        amount = float(data.get('amount', 0.001))
        side = data.get('side', 'buy').lower()
        order_params = {}

        if BUY_ONLY_MODE:
            side = 'buy'
            print(Fore.MAGENTA + "BUY ONLY MODE: Forced to BUY")
        elif SELL_ONLY_MODE:
            side = 'sell'
            print(Fore.MAGENTA + "SELL ONLY MODE: Forced to SELL")
        elif TRADINGVIEW_MESSAGE_MODE:
            message = data.get('message', '').lower()
            print(Fore.CYAN + f"Received message: {message}")

            if 'close' in message and 'long' in message:
                long_size, short_size = get_position_sizes()
                if long_size > 0:
                    amount = calculate_close_amount(long_size)
                    side = 'sell'
                    order_params['reduceOnly'] = True
                    print(Fore.MAGENTA + f"CLOSING LONG: {long_size} → closing {amount}")
                else:
                    return jsonify({'status': 'skipped', 'message': 'No long position'}), 200

            elif 'close' in message and 'short' in message:
                long_size, short_size = get_position_sizes()
                if short_size > 0:
                    amount = calculate_close_amount(short_size)
                    side = 'buy'
                    order_params['reduceOnly'] = True
                    print(Fore.MAGENTA + f"CLOSING SHORT: {short_size} → closing {amount}")
                else:
                    return jsonify({'status': 'skipped', 'message': 'No short position'}), 200

            elif 'close' in message and 'buy' in message:
                long_size, short_size = get_position_sizes()
                if long_size > 0:
                    amount = calculate_close_amount(long_size)
                    side = 'sell'
                    order_params['reduceOnly'] = True
                    print(Fore.MAGENTA + f"CLOSING LONG: {long_size} → closing {amount}")
                else:
                    return jsonify({'status': 'skipped', 'message': 'No long position'}), 200

            elif 'close' in message and 'sell' in message:
                long_size, short_size = get_position_sizes()
                if short_size > 0:
                    amount = calculate_close_amount(short_size)
                    side = 'buy'
                    order_params['reduceOnly'] = True
                    print(Fore.MAGENTA + f"CLOSING SHORT: {short_size} → closing {amount}")
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
            long_size, short_size = get_position_sizes()
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

        long_size, short_size = get_position_sizes()
        print(Fore.CYAN + f"Current position sizes: Long={long_size:.6f}, Short={short_size:.6f}")

        # Buy side check
        if side == 'buy' and 'reduceOnly' not in order_params:
            if long_size + amount > MAX_LONG_LOTS:
                print(Fore.RED + f"❌ ERROR: Buy order would exceed max long lots ({MAX_LONG_LOTS})")
                return jsonify({
                    'status': 'error',
                    'message': f'Buy order would exceed max long lots ({MAX_LONG_LOTS})'
                }), 429
        # Sell side check
        if side == 'sell' and 'reduceOnly' not in order_params:
            if short_size + amount > MAX_SHORT_LOTS:
                print(Fore.RED + f"❌ ERROR: Sell order would exceed max short lots ({MAX_SHORT_LOTS})")
                return jsonify({
                    'status': 'error',
                    'message': f'Sell order would exceed max short lots ({MAX_SHORT_LOTS})'
                }), 429
        open_orders = print_open_orders()
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

        if AUTO_CANCEL_ORDERS:
            try:
                open_orders = exchange.fetch_open_orders(SYMBOL)
                if open_orders:
                    exchange.cancel_all_orders(SYMBOL)
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
                ticker = fetch_ticker_with_retry(exchange, SYMBOL)
                current_price = ticker['last']
                print(Fore.MAGENTA + f"DEBUG: Current market price: {current_price}")
                if side == 'buy':
                    limit_price = current_price - LIMIT_OFFSET_POINTS
                else:
                    limit_price = current_price + LIMIT_OFFSET_POINTS
                limit_price = float(exchange.price_to_precision(SYMBOL, limit_price))
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
                    ticker = fetch_ticker_with_retry(exchange, SYMBOL)
                tp_sl_base_price = ticker['last']

        if 'reduceOnly' not in order_params:
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
                order = fetch_with_retry(exchange, exchange.create_order, SYMBOL, order_type, side, amount, limit_price,
                                         params=order_params)
                print(Fore.GREEN + f"Order executed: {order['id']} ({side.upper()} {amount})")
            except ccxt.NetworkError as e:
                print(Fore.RED + f"Network error: Could not execute order - {e}")
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

        print_swap_positions()
        print_open_orders()

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
        'version': '2.0.32',
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
        'symbol': SYMBOL
    })


if __name__ == '__main__':
    print(Fore.CYAN + "Starting TVWebHook")
    print(Fore.CYAN + f"Version: 2.0.32")
    print(Fore.CYAN + f"Symbol: {SYMBOL}")
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