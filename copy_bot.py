import os
import time
from web3 import Web3
import requests
from threading import Thread
from telegram import Bot
from telegram.ext import Updater, CommandHandler

# ------------------------------
# Environment Variables
# ------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")  # your Telegram chat ID
POLYM_API = os.getenv("POLYM_API", "https://data-api.polymarket.com")
POLY_CONTRACT_ADDRESS = os.getenv("POLY_CONTRACT")  # wallet/contract to copy
POLYGON_RPC = os.getenv("POLYGON_RPC")  # Alchemy / Polygon RPC URL
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "1"))  # seconds

# ------------------------------
# Telegram Bot
# ------------------------------
bot = Bot(BOT_TOKEN)
updater = Updater(BOT_TOKEN, use_context=True)

# ------------------------------
# Web3
# ------------------------------
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
if not w3.is_connected():
    print("⚠️ Could not connect to Polygon RPC!")

# ------------------------------
# Data Stores
# ------------------------------
positions = {}  # active positions
closed_positions = []  # list of closed positions

# ------------------------------
# Helper Functions
# ------------------------------
def fetch_trades():
    """Fetch latest trades from Polymarket API"""
    url = f"{POLYM_API}/trades?wallet={POLY_CONTRACT_ADDRESS}&limit=10"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print("Trade fetch error:", e)
        return []

def get_market_price(market):
    """
    Dummy function for current market price.
    Replace with real Polymarket or blockchain query for settlement.
    """
    import random
    if market in positions:
        base_price = positions[market]["avg_price"]
        return base_price * (1 + random.uniform(-0.01, 0.01))
    return 1.0

def calculate_pl(side, avg_price, current_price, size):
    """Calculate P/L for a position"""
    if side.upper() == "BUY":
        return (current_price - avg_price) * size
    else:
        return (avg_price - current_price) * size

# ------------------------------
# Trade Monitor
# ------------------------------
def trade_monitor():
    seen_trades = set()
    while True:
        trades = fetch_trades()
        for t in trades:
            trade_id = t.get("id")
            if not trade_id or trade_id in seen_trades:
                continue
            seen_trades.add(trade_id)

            # Trade info
            side = t.get("side", "BUY")
            market = t.get("market", "unknown-market")
            trader_size = float(t.get("traderSize", 0))
            your_size = round(trader_size * 0.1, 2)  # 10% copy size
            price = float(t.get("price", 0))

            # Telegram notification
            message = (
                f"📈 Copied Trade\n"
                f"Market: {market}\n"
                f"Side: {side}\n"
                f"Trader Size: ${trader_size}\n"
                f"Your Size: ${your_size}\n"
                f"Price: {price}"
            )
            bot.send_message(chat_id=CHAT_ID, text=message)

            # Update active positions
            key = f"{market}-{side}"
            if key not in positions:
                positions[key] = {"size": 0, "avg_price": 0, "market": market, "side": side}

            old_size = positions[key]["size"]
            old_avg = positions[key]["avg_price"]
            new_size = old_size + your_size
            new_avg = ((old_avg * old_size) + (price * your_size)) / new_size
            positions[key]["size"] = new_size
            positions[key]["avg_price"] = new_avg

            # Simulate closure after trade resolution (for demo)
            # In real setup, check blockchain / Polymarket settlement
            import threading
            def close_position_later(key, delay=300):
                """Simulate a 5-min trade closing"""
                time.sleep(delay)
                pos = positions.pop(key, None)
                if pos:
                    final_price = get_market_price(key)
                    pl = calculate_pl(pos["side"], pos["avg_price"], final_price, pos["size"])
                    pos["final_price"] = final_price
                    pos["pl"] = pl
                    closed_positions.append(pos)
                    bot.send_message(chat_id=CHAT_ID,
                                     text=f"✅ Position Closed\nMarket: {pos['market']}\nSide: {pos['side']}\n"
                                          f"Size: ${pos['size']}\nEntry Price: {pos['avg_price']}\n"
                                          f"Final Price: {final_price}\nP/L: ${pl:.2f}")
            threading.Thread(target=close_position_later, args=(key, 300), daemon=True).start()

        time.sleep(POLL_INTERVAL)

# ------------------------------
# Telegram Commands
# ------------------------------
def positions_command(update, context):
    msg = "📊 Active Positions:\n"
    if not positions:
        msg += "No active positions.\n"
    else:
        for k, v in positions.items():
            current_price = get_market_price(k)
            pl = calculate_pl(v["side"], v["avg_price"], current_price, v["size"])
            msg += (f"{v['market']} | {v['side']}\n"
                    f"Size: ${v['size']:.2f}\n"
                    f"Avg Price: {v['avg_price']:.2f}\n"
                    f"Unrealized P/L: ${pl:.2f}\n\n")

    if closed_positions:
        msg += "📌 Closed Positions:\n"
        for v in closed_positions[-10:]:  # last 10 closed positions
            msg += (f"{v['market']} | {v['side']}\n"
                    f"Size: ${v['size']:.2f}\n"
                    f"Entry Price: {v['avg_price']:.2f}\n"
                    f"Final Price: {v['final_price']:.2f}\n"
                    f"P/L: ${v['pl']:.2f}\n\n")
    update.message.reply_text(msg)

updater.dispatcher.add_handler(CommandHandler("positions", positions_command))

# ------------------------------
# Start Trade Monitor Thread
# ------------------------------
Thread(target=trade_monitor, daemon=True).start()

# ------------------------------
# Start Telegram Polling
# ------------------------------
updater.start_polling()
updater.idle()
