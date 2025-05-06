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

silence_ssl_warnings()

# Initialize database handler
db_handler = DatabaseHandler()

# Load all accounts once
accounts_file = os.path.join(project_root, 'accounts.json')
with open(accounts_file, 'r') as f:
    accounts = json.load(f)

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
    volume = round(max(float(trade['quantity']), 0.01), 2)
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

    print(f"\n📤 Sending order for {account['login']} -> {order_type.upper()} {symbol} {volume} lots @ {price}")
    print(f"📦 Request: {request}")

    result = mt5.order_send(request)
    mt5.shutdown()

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ Order placed for {account['login']} - {order_type.upper()} {symbol} {volume}")
        
        # ✅ Save MT5 ticket to DB (use str because mt5_ticket is varchar)
        # from src.utils.database_handler import db_handler  # add this import at the top or pass it in
        db_handler.update_mt5_ticket(trade['trade_id'], str(result.order))

        return True
    else:
        print(f"❌ Order failed for {account['login']}: {result.retcode}")
        print(f"⚠️  Error description: {result}")
        return False

def close_trade(account, ticket, symbol, volume, side):
    if not connect_mt5(account):
        print(f"❌ Failed to connect to MT5 for {account['login']}")
        return False
        
    # Ensure ticket is int
    try:
        ticket = int(ticket)
    except Exception as e:
        print(f"❌ Invalid ticket number: {ticket} ({e})")
        mt5.shutdown()
        return False

    # Get correct price
    price = mt5.symbol_info_tick(symbol).bid if side.lower() == "buy" else mt5.symbol_info_tick(symbol).ask
    opposite_type = mt5.ORDER_TYPE_SELL if side.lower() == "buy" else mt5.ORDER_TYPE_BUY

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

    print(f"\n📤 Sending close order for {account['login']} - {symbol} ticket {ticket}")
    print(f"📦 Close request: {request}")

    result = mt5.order_send(request)
    # mt5.shutdown()

    # ✅ Defensive check for None
    if result is None:
        print(f"❌ Close order failed for {account['login']}: No response from MT5 (check terminal, ticket, or market status)")
        mt5.shutdown()
        return False

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ Position closed for {account['login']}. Deal ID: {result.deal}")
        # return True
    else:
        print(f"❌ Close order failed for {account['login']}: {result.retcode}")
        print(f"⚠️  Error: {result.comment}")
        # return False
    
    mt5.shutdown()
    return result.retcode == mt5.TRADE_RETCODE_DONE

def main():
    print("🚀 Group Worker Started")
    while True:
        # Process pending trades
        pending_trades = db_handler.get_pending_trades()
        if pending_trades:
            for trade in pending_trades:
                for account in accounts:
                    place_trade(account, trade)
                db_handler.mark_trade_as_executed(trade['trade_id'])

        # Process pending closes
        pending_closes = db_handler.get_pending_closes()
        if pending_closes:
            for close in pending_closes:
                for account in accounts:
                    close_trade(account, close['mt5_ticket'], close['instrument'], float(close['quantity']), close['side'])
                db_handler.mark_trade_as_closed(close['trade_id'])

        time.sleep(1)  # Check every 1 second

if __name__ == "__main__":
    main()
