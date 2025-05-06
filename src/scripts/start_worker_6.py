import json
import MetaTrader5 as mt5
import time
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, project_root)

from src.utils.database_handler import DatabaseHandler
from src.utils.ssl_handler import silence_ssl_warnings

# Setup
project_root = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, project_root)
silence_ssl_warnings()
db_handler = DatabaseHandler()

# Load accounts
accounts_file = os.path.join(project_root, 'accounts.json')
with open(accounts_file, 'r') as f:
    accounts = json.load(f)

leaders = [acc for acc in accounts if acc['role'] == 'leader']
followers = [acc for acc in accounts if acc['role'] == 'follower']

def connect_mt5(account):
    return mt5.initialize(
        path=account['path'],
        login=account['login'],
        password=account['password'],
        server=account['server']
    )

def place_trade(account, trade):
    if not connect_mt5(account):
        print(f"❌ Failed to connect: {account['login']}")
        return False

    symbol = trade['instrument']
    volume = max(float(trade['quantity']), 0.01)
    order_type = trade['side'].lower()
    sl = float(trade.get('sl', 0))
    tp = float(trade.get('tp', 0))

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None or not symbol_info.visible:
        if not mt5.symbol_select(symbol, True):
            print(f"❌ Symbol {symbol} not available: {account['login']}")
            mt5.shutdown()
            return False

    price = mt5.symbol_info_tick(symbol).ask if order_type == "buy" else mt5.symbol_info_tick(symbol).bid
    order_code = mt5.ORDER_TYPE_BUY if order_type == "buy" else mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": round(volume, 2),
        "type": order_code,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    mt5.shutdown()
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ Order placed {account['login']} - {order_type.upper()} {symbol} {volume}")
        return True
    else:
        print(f"❌ Order failed {account['login']}: {result.retcode} - {result.comment}")
        return False

def close_trade(account, ticket, symbol, volume, side):
    if not connect_mt5(account):
        print(f"❌ Failed to connect: {account['login']}")
        return False

    price = mt5.symbol_info_tick(symbol).bid if side == "buy" else mt5.symbol_info_tick(symbol).ask
    opposite_type = mt5.ORDER_TYPE_SELL if side == "buy" else mt5.ORDER_TYPE_BUY

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": opposite_type,
        "position": ticket,
        "price": price,
        "deviation": 10,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    mt5.shutdown()
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ Closed position {account['login']} - {symbol} ticket {ticket}")
        return True
    else:
        print(f"❌ Close failed {account['login']}: {result.retcode} - {result.comment}")
        return False

def main():
    print("🚀 Multi-Leader Group Worker Started")
    while True:
        pending_trades = db_handler.get_pending_trades()
        if pending_trades:
            for trade in pending_trades:
                # Identify if trade is from leader or global signal
                leader_login = trade.get('leader_login')
                target_accounts = []
                if leader_login:
                    target_accounts = [acc for acc in accounts if acc['login'] == leader_login or acc['role'] == 'follower']
                else:
                    target_accounts = accounts

                # Place trade
                for account in target_accounts:
                    place_trade(account, trade)

                db_handler.mark_trade_as_executed(trade['trade_id'])

        # Check for close signals
        pending_closes = db_handler.get_pending_closes()
        if pending_closes:
            for close in pending_closes:
                for account in accounts:
                    close_trade(account, close['ticket'], close['symbol'], close['volume'], close['side'])
                db_handler.mark_close_as_executed(close['close_id'])

        time.sleep(1)

if __name__ == "__main__":
    main()
