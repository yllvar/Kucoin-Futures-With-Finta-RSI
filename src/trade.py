import asyncio
import os
import csv
from pathlib import Path
from dotenv import load_dotenv
import ccxt.async_support as ccxt
from typing import Optional

load_dotenv()

class CCXTTrade:
    def __init__(self, api_key: str, secret_key: str, passphrase: str, test_mode: bool = True):
        self.exchange = ccxt.kucoinfutures({
            'apiKey': api_key,
            'secret': secret_key,
            'password': passphrase,
            'enableRateLimit': True
        })
        self.test_mode = test_mode
        self.history_file = 'ccxt_history.csv'
        self.initialize_history_file()
        self.active_order = None

    async def get_futures_balance(self, symbol: str):
        await self.exchange.load_markets()
        balance = await self.exchange.fetch_balance()
        quote_currency = self.exchange.market(symbol)['quote']
        return balance[quote_currency]['free']

    async def create_order(self, symbol: str, order_type: str, side: str, amount: float, price: Optional[float] = None, params: dict = {}):
        if self.active_order:
            print("An active order is still in place. New order creation skipped.")
            return None
        
        await self.exchange.load_markets()
        market = self.exchange.market(symbol)
        
        params['test'] = self.test_mode
        params['leverage'] = 5

        if not self.test_mode:
            balance = await self.get_futures_balance(symbol)
            amount = balance / price if price else balance

        orderRequest = self.exchange.create_contract_order_request(symbol, order_type, side, amount, price, params)
        
        if self.test_mode:
            response = await self.exchange.futuresPrivatePostOrdersTest(orderRequest)
        else:
            response = await self.exchange.create_order(symbol, order_type, side, amount, price, params)
        
        data = self.exchange.safe_dict(response, 'data', {})
        parsed_order = self.exchange.parse_order(data, market)
        await self.track_trade(symbol, side, amount, price, data['orderId'], order_type, 'created')

        self.active_order = parsed_order
        return parsed_order

    async def create_stop_loss_order(self, symbol: str, side: str, amount: float, stop_loss_price: float, params: dict = {}):
        if not self.active_order:
            print("No active order found. Cannot create stop loss order.")
            return None

        params.update({
            'stop': 'down' if side == 'buy' else 'up',
            'stopPrice': stop_loss_price,
            'reduceOnly': True
        })
        order = await self.create_order(symbol, 'limit', side, amount, stop_loss_price, params)
        await self.track_trade(symbol, side, amount, stop_loss_price, order['id'], 'stop_loss', 'created')
        return order

    async def create_take_profit_order(self, symbol: str, side: str, amount: float, take_profit_price: float, params: dict = {}):
        if not self.active_order:
            print("No active order found. Cannot create take profit order.")
            return None

        params.update({
            'stop': 'up' if side == 'buy' else 'down',
            'stopPrice': take_profit_price,
            'reduceOnly': True
        })
        order = await self.create_order(symbol, 'limit', side, amount, take_profit_price, params)
        await self.track_trade(symbol, side, amount, take_profit_price, order['id'], 'take_profit', 'created')
        return order

    async def track_trade(self, symbol: str, side: str, amount: float, entry_price: float, order_id: str, order_type: str, status: str):
        trade_data = {
            'symbol': symbol,
            'side': side,
            'amount': amount,
            'entry_price': entry_price,
            'order_id': order_id,
            'order_type': order_type,
            'status': status,
        }
        
        filename = self.history_file
        with open(filename, mode='a', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=trade_data.keys())
            if os.stat(filename).st_size == 0:
                writer.writeheader()
            writer.writerow(trade_data)

        if status in ['closed', 'canceled']:
            self.active_order = None

    def initialize_history_file(self):
        filename = self.history_file
        if not Path(filename).is_file():
            with open(filename, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(['symbol', 'side', 'amount', 'entry_price', 'order_id', 'order_type', 'status'])

    async def close(self):
        await self.exchange.close()

async def main():
    API_KEY = os.getenv('API_KEY')
    SECRET_KEY = os.getenv('SECRET_KEY')
    PASSPHRASE = os.getenv('PASSPHRASE')

    symbol = 'SOL/USDT:USDT'
    order_type = 'limit'
    side = 'buy'
    amount = 1.0
    price = 20.0
    stop_loss_price = 18.0
    take_profit_price = 25.0

    trader = CCXTTrade(API_KEY, SECRET_KEY, PASSPHRASE, test_mode=False)

    try:
        order = await trader.create_order(symbol, order_type, side, amount, price)
        if order:
            print(f"Main order executed: {order}")

            stop_loss = await trader.create_stop_loss_order(symbol, 'sell', amount, stop_loss_price)
            if stop_loss:
                print(f"Stop loss order created: {stop_loss}")

            take_profit = await trader.create_take_profit_order(symbol, 'sell', amount, take_profit_price)
            if take_profit:
                print(f"Take profit order created: {take_profit}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await trader.close()

if __name__ == "__main__":
    asyncio.run(main())
