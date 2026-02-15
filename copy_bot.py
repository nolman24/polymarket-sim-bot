import os
import time
import threading
from web3 import Web3
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# === CONFIGURATION ===
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")   # BotFather token
POLYGON_RPC = os.environ.get("POLYGON_RPC")   # Polygon Mainnet RPC
COPY_PERCENT = int(os.environ.get("COPY_PERCENT", 10))  # % of original trade
MODE = os.environ.get("MODE", "paper")        # "paper" or "live"

# Minimal Polymarket Trade ABI
POLY_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "user", "type": "address"},
            {"indexed": True, "name": "marketId", "type": "uint256"},
            {"indexed": False, "name": "amount", "type": "uint256"},
            {"indexed": False, "name": "price", "type": "uint256"},
        ],
        "name": "Trade",
        "type": "event"
    }
]

# === STATE ===
tracked_wallets = set()
tracked_contracts = {}  # wallet_address -> list of contracts
seen_trades = set()
positions = {}

# === SETUP ===
bot = Bot(token=BOT_TOKEN)
updater = Updater(bot=bot, use_context=True)
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))

# === TELEGRAM COMMANDS ===
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Polymarket Copy-Trader Bot Ready!\n"
        "/wallet WALLET_ADDRESS - track a wallet\n"
        "/percent VALUE - set copy %\n"
        "/positions - view positions\n"
        "/stats - view P/L\n"
        "/paper on/off - toggle paper trading"
    )

def add_wallet(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        update.message.reply_text("Usage: /wallet WALLET_ADDRESS")
        return
    wallet = w3.to_checksum_address(context.args[0])
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
        update.message.reply_text("Use 'on' or 'off'")
        return
    MODE = "paper" if arg == "on" else "live"
    update.message.reply_text(f"Paper trading mode: {MODE}")

# Register command handlers
dispatcher = updater.dispatcher
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("wallet", add_wallet))
dispatcher.add_handler(CommandHandler("percent", set_percent))
dispatcher.add_handler(CommandHandler("positions", view_positions))
dispatcher.add_handler(CommandHandler("stats", view_stats))
dispatcher.add_handler(CommandHandler("paper", toggle_paper))

# === CONTRACT DETECTION ===
def detect_contracts_for_wallet(wallet):
    """Detects contracts that emit Trade events for this wallet in recent blocks."""
    contracts = set()
    current_block = w3.eth.block_number
    lookback = 5000  # last 5000 blocks (~1 day)
    for block in range(max(0, current_block - lookback), current_block + 1):
        block_data = w3.eth.get_block(block, full_transactions=True)
        for tx in block_data.transactions:
            if tx['from'].lower() == wallet.lower() and tx['to']:
                try:
                    contract = w3.eth.contract(address=tx['to'], abi=POLY_ABI)
                    events = contract.events.Trade.createFilter(fromBlock=block, toBlock=block).get_all_entries()
                    if events:
                        contracts.add(tx['to'])
                except:
                    continue
    return list(contracts)

# === MONITOR TRADES ===
def monitor_trades():
    print("Trade monitor started...")
    last_block = w3.eth.block_number
    while True:
        current_block = w3.eth.block_number
        for wallet in tracked_wallets:
            if wallet not in tracked_contracts:
                tracked_contracts[wallet] = detect_contracts_for_wallet(wallet)
            for contract_addr in tracked_contracts[wallet]:
                contract = w3.eth.contract(address=contract_addr, abi=POLY_ABI)
                events = contract.events.Trade.createFilter(
                    fromBlock=last_block + 1,
                    toBlock=current_block
                ).get_all_entries()
                for e in events:
                    if e["args"]["user"].lower() != wallet.lower():
                        continue
                    trade_id = f"{e['transactionHash'].hex()}_{e['logIndex']}"
                    if trade_id in seen_trades:
                        continue
                    seen_trades.add(trade_id)
                    market = str(e["args"]["marketId"])
                    amount = e["args"]["amount"] * (COPY_PERCENT / 100)
                    price = e["args"]["price"]
                    positions[trade_id] = {
                        "market": market,
                        "size": amount,
                        "entry": price,
                        "current": price
                    }
                    bot.send_message(chat_id=bot.get_me().id,
                                     text=f"New trade copied!\nWallet: {wallet}\nMarket: {market}\nSize: {amount}$ ({COPY_PERCENT}%)\nEntry: {price}$\nMode: {MODE}")
        last_block = current_block
        time.sleep(15)

# === START BOT ===
if __name__ == "__main__":
    t = threading.Thread(target=monitor_trades)
    t.daemon = True
    t.start()
    updater.start_polling()
    updater.idle()
