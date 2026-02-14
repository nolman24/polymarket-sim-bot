import requests
import json
import time
import threading
from telegram.ext import Updater, CommandHandler

TELEGRAM_TOKEN = "PUT_YOUR_TELEGRAM_TOKEN_HERE"

DATA_FILE = "positions.json"

tracked_wallet = None
scale_mode = "percent"
scale_value = 10
positions = {}

### ---------------- LOAD/SAVE ----------------

def load_data():
    global positions
    try:
        with open(DATA_FILE, "r") as f:
            positions = json.load(f)
    except:
        positions = {}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(positions, f, indent=2)

### ---------------- TELEGRAM COMMANDS ----------------

def start(update, context):
    update.message.reply_text("🤖 Polymarket Copy Trade Bot Ready!")

def set_wallet(update, context):
    global tracked_wallet
    tracked_wallet = context.args[0]
    update.message.reply_text(f"Tracking wallet: {tracked_wallet}")

def set_percent(update, context):
    global scale_mode, scale_value
    scale_mode = "percent"
    scale_value = float(context.args[0])
    update.message.reply_text(f"Scaling set to {scale_value}%")

def set_fixed(update, context):
    global scale_mode, scale_value
    scale_mode = "fixed"
    scale_value = float(context.args[0])
    update.message.reply_text(f"Fixed trade size set to ${scale_value}")

def positions_cmd(update, context):
    msg = "📊 OPEN POSITIONS\n\n"
    for m in positions:
        p = positions[m]
        current = get_market_price(m)
        pnl = (current - p["entry"]) * p["size"]
        msg += f"{m}\nEntry: {p['entry']}\nCurrent: {current}\nSize: {p['size']}\nP/L: {round(pnl,2)}\n\n"
    update.message.reply_text(msg)

def stats(update, context):
    total = 0
    wins = 0
    losses = 0
    for p in positions.values():
        if "closed" in p:
            total += p["profit"]
            if p["profit"] > 0:
                wins += 1
            else:
                losses += 1
    update.message.reply_text(f"Total P/L: ${round(total,2)}\nWins: {wins}\nLosses: {losses}")

### ---------------- POLYMARKET ----------------

def get_trades(wallet):
    url = f"https://data-api.polymarket.com/trades?maker={wallet}"
    return requests.get(url).json()

def get_market_price(market_id):
    url = f"https://clob.polymarket.com/price/{market_id}"
    r = requests.get(url).json()
    return float(r["price"])

### ---------------- COPY ENGINE ----------------

def copy_loop():
    seen = set()
    while True:
        try:
            if tracked_wallet:
                trades = get_trades(tracked_wallet)
                for t in trades:
                    tid = t["id"]
                    if tid in seen:
                        continue
                    seen.add(tid)

                    market = t["market"]
                    price = float(t["price"])
                    size = float(t["size"])

                    if scale_mode == "percent":
                        my_size = size * (scale_value / 100)
                    else:
                        my_size = scale_value

                    positions[market] = {
                        "entry": price,
                        "size": my_size
                    }

                    save_data()
                    print(f"Copied trade on {market}")

        except Exception as e:
            print("Error:", e)

        time.sleep(15)

### ---------------- MAIN ----------------

load_data()

updater = Updater(TELEGRAM_TOKEN, use_context=True)
dp = updater.dispatcher

dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("wallet", set_wallet))
dp.add_handler(CommandHandler("percent", set_percent))
dp.add_handler(CommandHandler("fixed", set_fixed))
dp.add_handler(CommandHandler("positions", positions_cmd))
dp.add_handler(CommandHandler("stats", stats))

threading.Thread(target=copy_loop).start()

updater.start_polling()
updater.idle()
