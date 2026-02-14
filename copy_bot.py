import os
import time
import requests
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, CallbackContext

# === CONFIGURATION ===
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")  # BotFather token
COPY_PERCENT = int(os.environ.get("COPY_PERCENT", 10))  # % of trades to copy
MODE = os.environ.get("MODE", "paper")  # "paper" or "live"

# Store wallets and positions
tracked_wallets = set()
seen_trades = set()
positions = {}

# Telegram bot setup
bot = Bot(token=BOT_TOKEN)
updater = Updater(bot=bot, use_context=True)
dispatcher = updater.dispatcher

# === TELEGRAM COMMANDS ===

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Polymarket Copy Trader Bot Ready!\n"
        "Commands:\n"
        "/wallet WALLET_ADDRESS - start tracking a wallet\n"
        "/percent VALUE - set copy percentage\n"
        "/positions - view open positions\n"
        "/stats - view P/L stats\n"
        "/paper on/off - enable/disable paper mode"
    )

def add_wallet(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        update.message.reply_text("Usage: /wallet WALLET_ADDRESS")
        return
    wallet = context.args[0]
    tracked_wallets.add(wallet)
    update.message.reply_text(f"Tracking wallet: {wallet}")

def set_percent(update: Update, context: CallbackContext):
    global COPY_PERCENT
    if len(context.args) != 1:
        update.message.reply_text("Usage: /percent VALUE")
        return
    try:
        COPY_PERCENT = int(context.args[0])
        update.message.reply_text(f"Copy percentage set to {COPY_PERCENT}%")
    except ValueError:
        update.message.reply_text("Please enter a valid number")

def view_positions(update: Update, context: CallbackContext):
    if not positions:
        update.message.reply_text("No positions yet.")
        return
    msg = "Open Positions:\n"
    for trade_id, pos in positions.items():
        msg += f"{pos['market']} | Size: {pos['size']}$ | Entry: {pos['entry']}$ | Current: {pos['current']}$\n"
    update.message.reply_text(msg)

def view_stats(update: Update, context: CallbackContext):
    total_pnl = sum(pos['current'] - pos['entry'] for pos in positions.values())
    update.message.reply_text(f"Total simulated P/L: ${total_pnl:.2f}")

def toggle_paper(update: Update, context: CallbackContext):
    global MODE
    if len(context.args) != 1:
        update.message.reply_text("Usage: /paper on/off")
        return
    arg = context.args[0].lower()
    if arg not in ["on", "off"]:
        update.message.reply_text("Please use 'on' or 'off'")
        return
    MODE = "paper" if arg == "on" else "live"
    update.message.reply_text(f"Paper trading mode: {MODE}")

# Add command handlers
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("wallet", add_wallet))
dispatcher.add_handler(CommandHandler("percent", set_percent))
dispatcher.add_handler(CommandHandler("positions", view_positions))
dispatcher.add_handler(CommandHandler("stats", view_stats))
dispatcher.add_handler(CommandHandler("paper", toggle_paper))

# === POLYMARKET MONITORING ===

def fetch_trades(wallet):
    """
    Fetch latest trades from Polymarket API for a given wallet.
    Adjusted to use 'transactionHash' instead of 'id'.
    """
    url = f"https://api.polymarket.com/trades?wallet={wallet}&limit=10"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()  # Returns list of trades
    except Exception as e:
        print(f"Error fetching trades for {wallet}: {e}")
        return []

def process_trades():
    while True:
        for wallet in tracked_wallets:
            trades = fetch_trades(wallet)
            for trade in trades:
                trade_id = trade.get("transactionHash")
                if not trade_id or trade_id in seen_trades:
                    continue  # Already processed

                seen_trades.add(trade_id)
                market = trade.get("marketName", "Unknown Market")
                size = trade.get("amount", 0) * (COPY_PERCENT / 100)
                entry_price = trade.get("price", 0)
                current_price = entry_price  # Initial, updated later

                # Save position
                positions[trade_id] = {
                    "market": market,
                    "size": size,
                    "entry": entry_price,
                    "current": current_price
                }

                # Notify user
                msg = (
                    f"New trade copied!\n"
                    f"Market: {market}\n"
                    f"Size: {size}$ ({COPY_PERCENT}% scale)\n"
                    f"Entry price: {entry_price}$\n"
                    f"Mode: {MODE}"
                )
                try:
                    bot.send_message(chat_id=bot.get_me().id, text=msg)
                except Exception as e:
                    print(f"Error sending Telegram message: {e}")

        time.sleep(15)  # Check every 15 seconds

# === START BOT ===
if __name__ == "__main__":
    import threading
    # Run trade monitor in a separate thread
    t = threading.Thread(target=process_trades)
    t.daemon = True
    t.start()
    # Start Telegram bot
    updater.start_polling()
    updater.idle()
