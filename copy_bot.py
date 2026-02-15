import os
import time
import threading
import queue
import requests
from telegram import Bot
from telegram.ext import Updater, CommandHandler, CallbackContext, Update

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # Telegram bot token
COPY_WALLET = ""  # Wallet to copy trades from
TRADE_SCALE = 0.1  # 10% of original trade by default
TRADE_FETCH_INTERVAL = 1  # seconds
NOTIFICATION_INTERVAL = 1  # seconds for batched notifications
POLYM_API = "https://data-api.polymarket.com"
# ----------------------------------------

bot = Bot(token=BOT_TOKEN)

# ---------------- STORAGE ----------------
trade_queue = queue.Queue()        # Queue for new trades
open_trades = {}                   # Active trades
closed_trades = []                 # Resolved trades
seen_trades = set()                # Already processed trades
wallet_address = COPY_WALLET

# ---------------- TELEGRAM COMMANDS ----------------
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🚀 Copy-Trade Bot Active!\nUse /wallet <address> to start copying trades."
    )

def positions(update: Update, context: CallbackContext):
    if not open_trades:
        update.message.reply_text("📊 No Open Positions Yet")
        return
    msg = "📊 Active Positions:\n\n"
    for t in open_trades.values():
        pl_text = f"${t.get('current_pl', 0):.2f}" if 'current_pl' in t else "Pending"
        msg += (
            f"Market: {t['market_name']}\n"
            f"Side: {t['side']}\n"
            f"Size: ${t['your_size']:.2f}\n"
            f"Entry Price: {t['price']:.2f}\n"
            f"Current P/L: {pl_text}\n\n"
        )
    update.message.reply_text(msg.strip())

def history(update: Update, context: CallbackContext):
    if not closed_trades:
        update.message.reply_text("📜 No Resolved Trades Yet")
        return
    msg = "📜 Trade History (Last 20):\n\n"
    for t in closed_trades[-20:]:
        pl_sign = "✅" if t['pl'] >= 0 else "❌"
        msg += (
            f"Market: {t['market_name']}\n"
            f"Side: {t['side']}\n"
            f"Size: ${t['your_size']:.2f}\n"
            f"Entry Price: {t['price']:.2f}\n"
            f"Exit Price: {t['exit_price']:.2f}\n"
            f"P/L: ${t['pl']:.2f} {pl_sign}\n\n"
        )
    update.message.reply_text(msg.strip())

def mode(update: Update, context: CallbackContext):
    global TRADE_SCALE
    try:
        arg = context.args[0]
        if arg.endswith('%'):
            percent = float(arg[:-1])
            TRADE_SCALE = percent / 100
            update.message.reply_text(f"✅ Trade scale set to {percent}% of copied wallet trades.")
        else:
            fixed = float(arg)
            TRADE_SCALE = fixed
            update.message.reply_text(f"✅ Trade scale set to fixed ${fixed} per trade.")
    except Exception:
        update.message.reply_text("Usage: /mode 10%  or /mode 5")

def wallet(update: Update, context: CallbackContext):
    global wallet_address
    if context.args:
        wallet_address = context.args[0]
        update.message.reply_text(f"✅ Now copying wallet: {wallet_address}")
    else:
        update.message.reply_text("Usage: /wallet <wallet_address>")

# ---------------- TRADE FUNCTIONS ----------------
def fetch_trades():
    if not wallet_address:
        return []
    try:
        url = f"{POLYM_API}/trades?wallet={wallet_address}&limit=20"
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        return res.json().get("trades", [])
    except Exception as e:
        print("Trade fetch error:", e)
        return []

def fetch_market_result(market_id):
    try:
        url = f"{POLYM_API}/markets/{market_id}"
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        if data.get("resolved"):
            return data.get("winning_side"), data.get("payout_per_dollar", 1)
        return None, None
    except Exception as e:
        print("Market fetch error:", e)
        return None, None

# ---------------- MONITOR THREADS ----------------
def trade_fetcher():
    while True:
        trades = fetch_trades()
        for t in trades:
            trade_id = t.get("id")
            if not trade_id or trade_id in seen_trades:
                continue
            seen_trades.add(trade_id)
            trade_queue.put(t)
        time.sleep(TRADE_FETCH_INTERVAL)

def trade_processor():
    notifications = []
    last_notify = time.time()
    while True:
        try:
            t = trade_queue.get(timeout=NOTIFICATION_INTERVAL)
        except:
            t = None

        if t:
            trader_size = t.get("size_usd", 0)
            your_size = trader_size * TRADE_SCALE if TRADE_SCALE <= 1 else TRADE_SCALE
            trade_info = {
                "trade_id": t["id"],
                "market_id": t.get("market_id"),
                "market_name": t.get("market_name", "unknown-market"),
                "side": t.get("side", "BUY"),
                "price": t.get("price", 0),
                "your_size": your_size,
                "resolved": False,
                "exit_price": None,
                "pl": None
            }
            open_trades[t["id"]] = trade_info
            notifications.append(trade_info)

        # Batch notifications every NOTIFICATION_INTERVAL
        if time.time() - last_notify >= NOTIFICATION_INTERVAL and notifications:
            msg = f"📈 Copied {len(notifications)} trades\n"
            for n in notifications:
                msg += (
                    f"Market: {n['market_name']}, "
                    f"Side: {n['side']}, "
                    f"Your Size: ${n['your_size']:.2f}\n"
                )
            try:
                bot.send_message(chat_id=bot.get_me().id, text=msg.strip())
            except Exception as e:
                print("Telegram send error:", e)
            notifications.clear()
            last_notify = time.time()

def trade_resolver():
    while True:
        for t_id, t_info in list(open_trades.items()):
            winning_side, payout = fetch_market_result(t_info['market_id'])
            if winning_side:
                if t_info['side'] == winning_side:
                    pl = (payout - t_info['price']) * t_info['your_size']
                else:
                    pl = (1 - t_info['price']) * t_info['your_size'] * -1

                t_info['exit_price'] = payout
                t_info['pl'] = pl
                t_info['resolved'] = True

                closed_trades.append(t_info)
                del open_trades[t_id]

                # Telegram notification
                try:
                    bot.send_message(
                        chat_id=bot.get_me().id,
                        text=(
                            f"📌 Trade Resolved!\n"
                            f"Market: {t_info['market_name']}\n"
                            f"Side: {t_info['side']}\n"
                            f"Size: ${t_info['your_size']:.2f}\n"
                            f"P/L: ${pl:.2f} {'✅' if pl >= 0 else '❌'}"
                        )
                    )
                except Exception as e:
                    print("Telegram send error:", e)
        time.sleep(1)

# ---------------- MAIN ----------------
def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("positions", positions))
    dp.add_handler(CommandHandler("history", history))
    dp.add_handler(CommandHandler("mode", mode))
    dp.add_handler(CommandHandler("wallet", wallet))

    threading.Thread(target=trade_fetcher, daemon=True).start()
    threading.Thread(target=trade_processor, daemon=True).start()
    threading.Thread(target=trade_resolver, daemon=True).start()

    updater.start_polling()
    print("High-frequency trade monitor started...")
    updater.idle()

if __name__ == "__main__":
    main()
