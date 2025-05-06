import json
import MetaTrader5 as mt5
import time
import os
import sys
import argparse
from pathlib import Path

# Argument parser to load specific config file
parser = argparse.ArgumentParser()
parser.add_argument('--config', default='accounts.json', help='Path to accounts JSON file')
args = parser.parse_args()

# Set project root and add to sys path
project_root = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, project_root)

from src.utils.ssl_handler import silence_ssl_warnings

silence_ssl_warnings()

# Load accounts from config file
accounts_file = os.path.join(project_root, args.config)
with open(accounts_file, 'r') as f:
    accounts = json.load(f)

leader = next(acc for acc in accounts if acc['role'] == 'leader')
followers = [acc for acc in accounts if acc['role'] == 'follower']

last_tickets = set()

def connect_mt5(account):
    return mt5.initialize(
        path=account['path'],
        login=account['login'],
        password=account['password'],
        server=account['server']
    )

def copy_trade_to_followers(symbol, volume, side, sl, tp):
    for account in followers:
        if not connect_mt5(account):
            print(f"❌ Failed to connect to follower {account['login']}")
            continue

        price = mt5.symbol_info_tick(symbol).ask if side == 'buy' else mt5.symbol_info_tick(symbol).bid
        order_type = mt5.ORDER_TYPE_BUY if side == 'buy' else mt5.ORDER_TYPE_SELL

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": 10,
            "sl": sl if sl > 0 else 0.0,
            "tp": tp if tp > 0 else 0.0,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        mt5.shutdown()

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Copied trade to follower {account['login']}: {side.upper()} {symbol} {volume}")
        else:
            print(f"❌ Failed to copy to {account['login']}: {result.retcode} {result.comment}")

def main():
    print(f"🚀 Worker started for leader {leader['login']}")
    while True:
        if not connect_mt5(leader):
            print(f"❌ Failed to connect to leader {leader['login']}")
            time.sleep(5)
            continue

        positions = mt5.positions_get()
        current_tickets = set()

        if positions:
            for pos in positions:
                symbol = pos.symbol
                ticket = pos.ticket
                current_tickets.add(ticket)

                if ticket not in last_tickets:
                    side = 'buy' if pos.type == mt5.ORDER_TYPE_BUY else 'sell'
                    print(f"📥 New trade by leader {leader['login']}: {symbol} {pos.volume} {side}")
                    copy_trade_to_followers(symbol, pos.volume, side, pos.sl, pos.tp)

        closed_tickets = last_tickets - current_tickets
        if closed_tickets:
            print(f"📤 Trades closed by leader {leader['login']} — Manual close handling can be added here.")

        last_tickets.clear()
        last_tickets.update(current_tickets)
        mt5.shutdown()
        time.sleep(2)

if __name__ == "__main__":
    main()
