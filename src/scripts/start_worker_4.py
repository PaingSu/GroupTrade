import json
import MetaTrader5 as mt5
import time
import os
import sys
from pathlib import Path

# Set project root and add to sys path
project_root = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, project_root)

from src.utils.ssl_handler import silence_ssl_warnings

silence_ssl_warnings()

# Load all accounts from JSON
accounts_file = os.path.join(project_root, 'accounts.json')
with open(accounts_file, 'r') as f:
    accounts = json.load(f)

# Separate leaders and followers
leaders = [acc for acc in accounts if acc['role'] == 'leader']
followers = [acc for acc in accounts if acc['role'] == 'follower']

# Store previously seen trades to detect new ones
last_tickets = {}

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
            print(f"✅ Trade copied to follower {account['login']}: {side.upper()} {symbol} {volume} lots")
        else:
            print(f"❌ Failed to copy trade to {account['login']}: {result.retcode} - {result.comment}")

def close_trade_on_followers(symbol, volume, side):
    for account in followers:
        if not connect_mt5(account):
            print(f"❌ Failed to connect to follower {account['login']}")
            continue

        positions = mt5.positions_get(symbol=symbol)
        if positions:
            for pos in positions:
                if pos.type == (0 if side == 'buy' else 1):
                    close_price = mt5.symbol_info_tick(symbol).bid if side == 'buy' else mt5.symbol_info_tick(symbol).ask
                    opposite_type = mt5.ORDER_TYPE_SELL if side == 'buy' else mt5.ORDER_TYPE_BUY
                    close_request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": symbol,
                        "volume": pos.volume,
                        "type": opposite_type,
                        "position": pos.ticket,
                        "price": close_price,
                        "deviation": 10,
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }

                    result = mt5.order_send(close_request)
                    if result.retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"✅ Closed follower trade {account['login']} - {symbol} {pos.volume} lots")
                    else:
                        print(f"❌ Failed to close follower trade {account['login']}: {result.retcode}")
        mt5.shutdown()

def main():
    print("🚀 Multi-Leader Group Worker Started")
    while True:
        for leader in leaders:
            if not connect_mt5(leader):
                print(f"❌ Failed to connect to leader {leader['login']}")
                continue

            positions = mt5.positions_get()
            current_tickets = set()

            if positions:
                for pos in positions:
                    symbol = pos.symbol
                    ticket = pos.ticket
                    current_tickets.add(ticket)

                    if ticket not in last_tickets.get(leader['login'], set()):
                        print(f"📥 New trade by Leader {leader['login']}: {symbol} {pos.volume} {pos.type}")
                        side = 'buy' if pos.type == mt5.ORDER_TYPE_BUY else 'sell'
                        copy_trade_to_followers(symbol, pos.volume, side, pos.sl, pos.tp)

            # Detect closed trades
            previous = last_tickets.get(leader['login'], set())
            closed = previous - current_tickets
            for closed_ticket in closed:
                print(f"📤 Trade closed by Leader {leader['login']} - Ticket: {closed_ticket}")
                # For simplicity, just assume we close all follower positions for same symbol
                for pos in positions:
                    if pos.ticket == closed_ticket:
                        symbol = pos.symbol
                        side = 'buy' if pos.type == mt5.ORDER_TYPE_BUY else 'sell'
                        close_trade_on_followers(symbol, pos.volume, side)

            last_tickets[leader['login']] = current_tickets
            mt5.shutdown()

        time.sleep(2)

if __name__ == "__main__":
    main()
