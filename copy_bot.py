import os
import time
import threading
import requests
from telegram.ext import Updater, CommandHandler

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ====== SIMPLE MEMORY STORAGE ======
wallet_to_copy = None

# ====== TELEGRAM COMMANDS ======

def start(update, context):
    update.message.reply_text(
        "Polymarket Copy Bot (Polling Mode)\n\n"
        "/wallet <address> — set wallet to monitor\n"
        "/status — show current wallet"
    )

def set_wallet(update, context):
    global wallet_to_copy
    if len(context.args) == 0:
        update.message.reply_text("Usage: /wallet <wallet_address>")
        return
    
    wallet_to_copy = context.args[0]
    update.message.reply_text(f"Now monitoring wallet:\n{wallet_to_copy}")

def status(update, context):
    if wallet_to_copy:
        update.message.reply_text(f"Monitoring:\n{wallet_to_copy}")
    else:
        update.message.reply_text("No wallet set.")

# ====== TRADE MONITOR LOOP (SIMULATION ONLY) ======

def monitor_trades():
    print("Trade monitor started...")
    
    while True:
        if wallet_to_copy:
            try:
                url = f"https://data-api.polymarket.com/trades?maker={wallet_to_copy}&limit=5"
                r = requests.get(url, timeout=10)
                
                if r.status_code == 200:
                    trades = r.json()
                    if trades:
                        print("Detected trade from copied wallet")
                else:
                    print("No trades found")

            except Exception as e:
                print("Error:", e)

        time.sleep(10)

# ====== MAIN ======

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("wallet", set_wallet))
    dp.add_handler(CommandHandler("status", status))

    # Start background monitoring thread
    threading.Thread(target=monitor_trades, daemon=True).start()

    # START POLLING (NO WEBHOOKS)
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
