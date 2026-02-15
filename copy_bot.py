import os
import time
import threading
import requests
from telegram.ext import Updater, CommandHandler

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ================= SETTINGS =================

COPY_WALLET = "0x1d0034134e339a309700ff2d34e99fa2d48b0313"

COPY_MODE = "percent"  # "percent" or "fixed"
COPY_PERCENT = 10
FIXED_AMOUNT = 5

positions = {}  # market_id -> position data

# ============================================


def fetch_trades():
    try:
        url = f"https://data-api.polymarket.com/trades?user={COPY_WALLET}"
        res = requests.get(url, timeout=10)
        return res.json()
    except Exception as e:
        print("Trade fetch error:", e)
        return []


def simulate_trade(trade):
    global positions

    market = trade["market_slug"]
    price = float(trade["price"])
    size = float(trade["size"])
    side = trade["side"]

    if COPY_MODE == "percent":
        my_size = size * (COPY_PERCENT / 100)
    else:
        my_size = FIXED_AMOUNT

    if market not in positions:
        positions[market] = {
            "size": 0,
            "avg_price": 0,
            "side": side
        }

    pos = positions[market]

    total_cost = pos["avg_price"] * pos["size"] + price * my_size
    pos["size"] += my_size
    pos["avg_price"] = total_cost / pos["size"]
    pos["side"] = side


def trade_monitor(bot):
    seen = set()

    while True:
        trades = fetch_trades()

        for t in trades:
            trade_id = t["id"]
            if trade_id in seen:
                continue

            seen.add(trade_id)

            simulate_trade(t)

            msg = (
                "📈 Copied Trade\n\n"
                f"Market: {t['market_slug']}\n"
                f"Side: {t['side']}\n"
                f"Trader Size: ${t['size']}\n"
                f"Your Size: ${round((float(t['size']) * COPY_PERCENT/100),2)}\n"
                f"Price: {t['price']}"
            )

            bot.send_message(chat_id=CHAT_ID, text=msg)

        time.sleep(5)


# ================= TELEGRAM COMMANDS =================


CHAT_ID = None


def start(update, context):
    global CHAT_ID
    CHAT_ID = update.message.chat_id
    update.message.reply_text(
        "🤖 Polymarket Copy Bot (Paper Mode)\n\n"
        "Default: Copying at 10% scale.\n\n"
        "Commands:\n"
        "/positions\n"
        "/mode percent 10\n"
        "/mode fixed 5"
    )


def positions_cmd(update, context):
    if not positions:
        update.message.reply_text("No positions yet.")
        return

    msg = "📊 Your Positions:\n\n"

    for market, p in positions.items():
        msg += (
            f"{market}\n"
            f"Side: {p['side']}\n"
            f"Size: ${round(p['size'],2)}\n"
            f"Avg Price: {round(p['avg_price'],3)}\n\n"
        )

    update.message.reply_text(msg)


def mode_cmd(update, context):
    global COPY_MODE, COPY_PERCENT, FIXED_AMOUNT

    try:
        mode = context.args[0]
        value = float(context.args[1])

        if mode == "percent":
            COPY_MODE = "percent"
            COPY_PERCENT = value
            update.message.reply_text(f"✅ Copy mode set to {value}%")

        elif mode == "fixed":
            COPY_MODE = "fixed"
            FIXED_AMOUNT = value
            update.message.reply_text(f"✅ Fixed copy set to ${value}")

    except:
        update.message.reply_text("Usage:\n/mode percent 10\n/mode fixed 5")


# ================= MAIN =================


def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("positions", positions_cmd))
    dp.add_handler(CommandHandler("mode", mode_cmd))

    updater.start_polling()

    print("Trade monitor started...")

    threading.Thread(target=trade_monitor, args=(updater.bot,), daemon=True).start()

    updater.idle()


if __name__ == "__main__":
    main()
