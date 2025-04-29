import json
import MetaTrader5 as mt5
import time
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, project_root)

from src.utils.database_handler import get_pending_trades, mark_trade_as_executed
from src.utils.ssl_handler import silence_ssl_warnings

silence_ssl_warnings()

def connect_mt5(account):
    return mt5.initialize(
        path=account['path'],
        login=account['login'],
        password=account['password'],
        server=account['server']
    )

def place_trade(account, trade):
    if not connect_mt5(account):
        print(f"❌ Failed to connect to MT5 for {account['login']}")
        return False

    symbol = trade['instrument']
    volume = float(trade['quantity'])
    order_type = trade['side'].lower()

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None or not symbol_info.visible:
        if not mt5.symbol_select(symbol, True):
            print(f"❌ Symbol {symbol} not available for {account['login']}")
            mt5.shutdown()
            return False

    if order_type == "buy":
        price = mt5.symbol_info_tick(symbol).ask
        order_type_code = mt5.ORDER_TYPE_BUY
    elif order_type == "sell":
        price = mt5.symbol_info_tick(symbol).bid
        order_type_code = mt5.ORDER_TYPE_SELL
    else:
        print(f"❌ Unknown order type: {order_type}")
        mt5.shutdown()
        return False

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type_code,
        "price": price,
        "deviation": 10,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    result = mt5.order_send(request)
    mt5.shutdown()

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ Order placed for {account['login']} - {order_type.upper()} {symbol} {volume}")
        return True
    else:
        print(f"❌ Order failed for {account['login']}: {result.retcode}")
        return False

def main():
    print("🚀 Group Worker Started")
    while True:
        pending_trades = get_pending_trades()
        if pending_trades:
            for trade in pending_trades:
                with open('accounts.json', 'r') as f:
                    accounts = json.load(f)

                for account in accounts:
                    place_trade(account, trade)

                mark_trade_as_executed(trade['trade_id'])

        time.sleep(1)  # Check every 1 second

if __name__ == "__main__":
    main()
