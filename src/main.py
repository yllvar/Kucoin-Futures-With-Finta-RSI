import asyncio
import os
import time
from dotenv import load_dotenv
import ccxt.async_support as ccxt
import pandas as pd
from finta import TA
from ccxt_trade import CCXTTrade

# Load environment variables
load_dotenv()

# Global variables
API_KEY = os.getenv('API_KEY')
SECRET_KEY = os.getenv('SECRET_KEY')
PASSPHRASE = os.getenv('PASSPHRASE')
SYMBOL = 'SOL/USDT:USDT'
TIMEFRAME = '1m'
SLEEP_INTERVAL = 2  # Sleep interval in seconds
MAX_RETRIES = 5
RETRY_DELAY = 5  # Delay between retries in seconds

# Strategy parameters
RSI_OVERBOUGHT = 75
RSI_OVERSOLD = 25
BBANDS_PERIOD = 20
BBANDS_STD_MULTIPLIER = 2

class CryptoTrader:
    def __init__(self):
        self.exchange = None
        self.ccxt_trade = None

    async def initialize(self):
        self.exchange = ccxt.kucoinfutures({
            'apiKey': API_KEY,
            'secret': SECRET_KEY,
            'password': PASSPHRASE,
            'enableRateLimit': True
        })
        self.ccxt_trade = CCXTTrade(API_KEY, SECRET_KEY, PASSPHRASE)

    async def fetch_and_analyze_ohlcv(self):
        while True:
            try:
                # Fetch OHLCV data
                ohlcv = await self.exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                # Ensure all necessary columns are numeric
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # Calculate RSI
                df['RSI'] = TA.RSI(df)
                
                # Calculate Bollinger Bands
                bbands = TA.BBANDS(df, period=BBANDS_PERIOD, std_multiplier=BBANDS_STD_MULTIPLIER)
                df = df.join(bbands)

                # Generate trading signals
                signal_rsi_threshold = self.generate_signal_rsi_threshold(df)
                signal_rsi_divergence = self.generate_signal_rsi_divergence(df)
                
                # Execute trade if a signal is generated
                if signal_rsi_threshold != "NEUTRAL" or signal_rsi_divergence != "NEUTRAL":
                    await self.execute_trade(df, signal_rsi_threshold, signal_rsi_divergence)

                print(f"Timestamp: {df.iloc[-1]['timestamp']}")
                print(f"Close: {df.iloc[-1]['close']:.2f}, RSI: {df.iloc[-1]['RSI']:.2f}")
                print(f"Signal (RSI Threshold): {signal_rsi_threshold}")
                print(f"Signal (RSI Divergence): {signal_rsi_divergence}")
                print("--------------------")
                
                await asyncio.sleep(SLEEP_INTERVAL)
            except Exception as e:
                print(f"Error fetching or analyzing data: {e}")
                await asyncio.sleep(SLEEP_INTERVAL)

    def generate_signal_rsi_threshold(self, df):
        # Check for RSI conditions
        rsi_overbought = df.iloc[-1]['RSI'] > RSI_OVERBOUGHT
        rsi_oversold = df.iloc[-1]['RSI'] < RSI_OVERSOLD
        
        if rsi_oversold:
            return "LONG"
        elif rsi_overbought:
            return "SHORT"
        else:
            return "NEUTRAL"

    def generate_signal_rsi_divergence(self, df):
        # Implement refined RSI divergence strategy
        prices = df['close'].values[-3:]
        rsi_values = df['RSI'].values[-3:]
        
        # Use finer thresholds for detecting rapid divergences
        bullish_divergence = (prices[-1] < prices[-3] and prices[-2] < prices[-3] and
                              rsi_values[-1] > rsi_values[-3] and rsi_values[-2] > rsi_values[-3])
        
        bearish_divergence = (prices[-1] > prices[-3] and prices[-2] > prices[-3] and
                              rsi_values[-1] < rsi_values[-3] and rsi_values[-2] < rsi_values[-3])
        
        if bullish_divergence:
            return "LONG"
        elif bearish_divergence:
            return "SHORT"
        else:
            return "NEUTRAL"

    def dynamic_stop_loss_take_profit(self, df, signal):
        # Calculate dynamic stop loss and take profit levels using Bollinger Bands
        last_row = df.iloc[-1]
        upper_band = last_row['BB_UPPER']
        lower_band = last_row['BB_LOWER']

        if signal == "LONG":
            stop_loss = lower_band
            take_profit = upper_band
        elif signal == "SHORT":
            stop_loss = upper_band
            take_profit = lower_band
        else:
            stop_loss = None
            take_profit = None

        return stop_loss, take_profit

    async def execute_trade(self, df, signal_rsi_threshold, signal_rsi_divergence):
        signal = signal_rsi_threshold if signal_rsi_threshold != "NEUTRAL" else signal_rsi_divergence
        
        if signal == "NEUTRAL":
            return

        last_price = df.iloc[-1]['close']
        amount = 1.0  # You may want to adjust this based on your risk management strategy
        
        stop_loss, take_profit = self.dynamic_stop_loss_take_profit(df, signal)

        for attempt in range(MAX_RETRIES):
            try:
                # Create main order
                order_type = 'market'
                side = 'buy' if signal == "LONG" else 'sell'
                main_order = await self.ccxt_trade.create_order(SYMBOL, order_type, side, amount)
                print(f"Main order executed: {main_order}")

                # Create stop loss order
                stop_loss_side = 'sell' if signal == "LONG" else 'buy'
                stop_loss_order = await self.ccxt_trade.create_stop_loss_order(SYMBOL, stop_loss_side, amount, stop_loss)
                print(f"Stop loss order created: {stop_loss_order}")

                # Create take profit order
                take_profit_side = 'sell' if signal == "LONG" else 'buy'
                take_profit_order = await self.ccxt_trade.create_take_profit_order(SYMBOL, take_profit_side, amount, take_profit)
                print(f"Take profit order created: {take_profit_order}")

                break  # If successful, break out of the retry loop
            except Exception as e:
                print(f"Error executing trade (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    print("Max retries reached. Unable to execute trade.")
                    
async def main():
    while True:
        try:
            trader = CryptoTrader()
            await trader.initialize()
            await trader.fetch_and_analyze_ohlcv()
        except Exception as e:
            print(f"An error occurred in the main loop: {e}")
            print("Restarting the trading process...")
            await asyncio.sleep(RETRY_DELAY)

if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("Trading bot stopped by user.")
            break
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            print("Restarting the entire process...")
            time.sleep(RETRY_DELAY)
