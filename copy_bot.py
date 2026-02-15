import os
import time
import threading
import requests
from collections import defaultdict

from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
COPY_WALLET = os.getenv("COPY_WALLET", "")
TRADE_SCALE = float(os.getenv("TRADE_SCALE", 0.1))
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", 1))
POLYM_API = os.getenv("POLYM_API", "https://data-api.polymarket.com")

# ================= STORAGE =================

seen_trades = set()

positions = defaultdict(lambda: {
    "size": 0,
    "avg_price": 0,
    "side": "",
    "realized_pnl": 0
})

trade_history = []

# ================= HELPERS =================

def safe_get(d, key, default=None):
    return d[key] if key in d else default

# ================= TRADE MONITOR =================

def trade_monitor(bot):
    print("High-frequency trade monitor started...")

    while True:
        try:
            if not COPY_WALLET:
                time.sleep(5)
                continue

            url = f"{POLYM_API}/trades?wallet={COPY_WALLET}&limit=50"
            r = requests.get(url, timeout=10)
            trades = r.json()

            for t in trades:

                trade_id = safe_get(t, "id")
                if not trade_id:
                    continue

                if trade_id in seen_trades:
                    continue

                seen_trades.add(trade_id)

                market = safe_get(t, "marketSlug", "unknown-market")
                side = safe_get(t, "side", "BUY")
                price = float(safe_get(t, "price", 0))
                size = float(safe_get(t, "size", 0))

                if price == 0 or size == 0:
                    continue

                my_size = size * TRADE_SCALE

                pos = positions[market]

                # ================= OPEN / CLOSE LOGIC =================

                if pos["size"] == 0:
                    pos["size"] = my_size
                    pos["avg_price"] = price
                    pos["side"] = side

                elif pos["side"] == side:
                    # averaging in
                    total_value = pos["avg_price"] * pos["size"] + price * my_size
                    pos["size"] += my_size
                    pos["avg_price"] = total_value / pos["size"]

                else:
                    # closing trade
                    pnl = (price - pos["avg_price"]) * pos["size"]
                    if pos["side"] == "SELL":
                        pnl *= -1

                    pos["realized_pnl"] += pnl

                    trade_history.append({
                        "market": market,
                        "pnl": pnl
                    })

                    pos["size"] = 0

                # ================= SEND TELEGRAM ALERT =================

                bot.send_message(
                    chat_id=list(user_chats)[0],
                    text=(
                        f"📈 Copied Trade\n\n"
                        f"Market: {market}\n"
                        f"Side: {side}\n"
                        f"Trader Size: ${round(size,2)}\n"
                        f"Your Size: ${round(my_size,2)}\n"
                        f"Price: {price}"
                    )
                )

        except Exception as e:
            print("Trade fetch error:", e)

        time.sleep(POLL_INTERVAL)

# ================= TELEGRAM COMMANDS =================

user_chats = set()

def start(update: Update, context: CallbackContext):
    user_chats.add(update.effective_chat.id)
    update.message.reply_text("🤖 Copy Trading Bot Ready")

def wallet(update: Update, context: CallbackContext):
    global COPY_WALLET
    COPY_WALLET = context.args[0]
    update.message.reply_text(f"Now copying wallet:\n{COPY_WALLET}")

def mode(update: Update, context: CallbackContext):
    global TRADE_SCALE
    val = context.args[0].replace("%", "")
    TRADE_SCALE = float(val) / 100
    update.message.reply_text(f"Trade scale set to {val}%")

def positions_cmd(update: Update, context: CallbackContext):
    msg = "📊 Your Positions:\n\n"

    for market, pos in positions.items():
        if pos["size"] > 0:
            msg += (
                f"{market}\n"
                f"Side: {pos['side']}\n"
                f"Size: ${round(pos['size'],2)}\n"
                f"Avg Price: {round(pos['avg_price'],2)}\n\n"
            )

    if msg == "📊 Your Positions:\n\n":
        msg += "No open positions."

    update.message.reply_text(msg)

def history(update: Update, context: CallbackContext):
    if not trade_history:
        update.message.reply_text("No closed trades yet.")
        return

    total = 0
    msg = "📜 Trade History:\n\n"

    for t in trade_history[-10:]:
        msg += f"{t['market']} → P/L: ${round(t['pnl'],2)}\n"
        total += t["pnl"]

    msg += f"\nTotal Realized P/L: ${round(total,2)}"

    update.message.reply_text(msg)

# ================= MAIN =================

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("wallet", wallet))
    dp.add_handler(CommandHandler("mode", mode))
    dp.add_handler(CommandHandler("positions", positions_cmd))
    dp.add_handler(CommandHandler("history", history))

    updater.start_polling()

    threading.Thread(
        target=trade_monitor,
        args=(updater.bot,),
        daemon=True
    ).start()

    updater.idle()

if __name__ == "__main__":
    main()
