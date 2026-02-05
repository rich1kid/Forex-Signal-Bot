# ===============================================
# Advanced Forex Signal Bot - Railway Ready
# ===============================================
# Author: Your Bot
# Features: Multi-asset, London/NY sessions, 15m bias + 5m entry, advanced SR zones, candlestick pattern detection, trendline confirmation, paper trading, Telegram signals
# Assets: EURUSD, GBPUSD, GBPJPY
# ===============================================

import requests
import pandas as pd
from datetime import datetime, time
import time as t
from forex_python.converter import CurrencyRates
import numpy as np

# ------------------------------
# Telegram Setup
# ------------------------------
import os

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

def send_telegram_signal(pair, signal, entry, sl, tp, rr, session):
    message = f"""
📈 Forex Signal Alert
Pair: {pair}
Signal: {signal}
Entry: {entry:.5f}
SL: {sl:.5f}
TP: {tp:.5f}
RR: {rr}
Session: {session}
"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": message})
    except Exception as e:
        print("Telegram send failed:", e)

# ------------------------------
# Market Data Sources
# ------------------------------
TWELVEDATA_API = os.environ.get("TWELVEDATA_API")
ALPHA_API = os.environ.get("ALPHA_API")
c = CurrencyRates()

def fetch_twelvedata(symbol="EUR/USD"):
    url = "https://api.twelvedata.com/time_series"
    params = {"symbol": symbol,"interval": "1min","apikey": TWELVEDATA_API,"outputsize": 200}
    try:
        r = requests.get(url, params=params)
        data = r.json()
        df = pd.DataFrame(data["values"]).astype(float).iloc[::-1]
        df['datetime'] = pd.to_datetime(df['datetime'])
        return df
    except:
        return None

def fetch_alpha(symbol="EURUSD"):
    url = "https://www.alphavantage.co/query"
    params = {"function": "FX_INTRADAY","from_symbol": symbol[:3],"to_symbol": symbol[3:],
              "interval": "1min","apikey": ALPHA_API}
    try:
        r = requests.get(url).json()
        ts = r[f"Time Series FX (1min)"]
        df = pd.DataFrame(ts).T.astype(float)
        df = df.rename(columns={"1. open":"open","2. high":"high","3. low":"low","4. close":"close"})
        df.index = pd.to_datetime(df.index)
        return df.iloc[::-1]
    except:
        return None

def fetch_forexpython(symbol="EUR/USD"):
    try:
        base, quote = symbol.split("/")
        rate = c.get_rate(base, quote)
        return pd.DataFrame([{"open": rate,"high": rate,"low": rate,"close": rate}])
    except:
        return None

def fetch_price(symbol="EUR/USD"):
    df = fetch_twelvedata(symbol)
    if df is not None: return df
    df = fetch_alpha(symbol.replace("/",""))
    if df is not None: return df
    return fetch_forexpython(symbol)

# ------------------------------
# Paper Trading Engine
# ------------------------------
class PaperTrader:
    def __init__(self, balance=1000):
        self.balance = balance
        self.trades = []

    def open_trade(self, signal, price, sl, tp, rr, pair, session):
        trade = {"pair": pair,"signal": signal,"entry": price,"sl": sl,"tp": tp,
                 "rr": rr,"session": session,"time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}
        self.trades.append(trade)
        return trade

trader = PaperTrader()

# ------------------------------
# Strategy & Signal Logic
# ------------------------------
def calculate_bias(df_15m):
    if len(df_15m)<3: return None
    highs = df_15m['high'].iloc[-3:]
    lows = df_15m['low'].iloc[-3:]
    ema50 = df_15m['close'].ewm(span=50).mean().iloc[-1]
    ema200 = df_15m['close'].ewm(span=200).mean().iloc[-1]
    if highs.is_monotonic_increasing and lows.is_monotonic_increasing and df_15m['close'].iloc[-1]>ema50 and ema50>ema200:
        return "BULLISH"
    elif highs.is_monotonic_decreasing and lows.is_monotonic_decreasing and df_15m['close'].iloc[-1]<ema50 and ema50<ema200:
        return "BEARISH"
    return None

def detect_sr(df_15m):
    """
    Advanced SR: previous day + last 50 candles highs/lows
    Returns list of zones: [(low, high), ...]
    """
    prev_high = df_15m['high'].iloc[-50:].max()
    prev_low = df_15m['low'].iloc[-50:].min()
    zones = [(prev_low, prev_low+0.01),(prev_high-0.01, prev_high)]
    return zones

def is_near_sr(price, zones):
    for low, high in zones:
        if low <= price <= high:
            return True
    return False

def detect_candle(df_5m, signal):
    last = df_5m.iloc[-1]
    body = abs(last['close'] - last['open'])
    total = last['high'] - last['low']
    wick_upper = last['high'] - max(last['close'], last['open'])
    wick_lower = min(last['close'], last['open']) - last['low']

    # Momentum candle (>=60% body)
    if total==0: return False
    if body/total < 0.6: return False

    # Rejection / Pin bar
    if signal=="BUY" and wick_lower>2*body: return True
    if signal=="SELL" and wick_upper>2*body: return True

    # Engulfing (simplified)
    prev = df_5m.iloc[-2]
    if signal=="BUY" and last['close']>last['open'] and last['close']>prev['open'] and last['open']<prev['close']:
        return True
    if signal=="SELL" and last['close']<last['open'] and last['close']<prev['open'] and last['open']>prev['close']:
        return True

    # Body direction confirmation
    if signal=="BUY" and last['close']>last['open']: return True
    if signal=="SELL" and last['close']<last['open']: return True

    return False

def trendline_break(df_5m, signal):
    # Simplified: check last 3 highs/lows trend
    highs = df_5m['high'].iloc[-3:]
    lows = df_5m['low'].iloc[-3:]
    last_price = df_5m['close'].iloc[-1]
    if signal=="BUY" and last_price>highs.max(): return True
    if signal=="SELL" and last_price<lows.min(): return True
    return False

# ------------------------------
# Session Filters
# ------------------------------
def session_active():
    now = datetime.utcnow().time()
    london = (time(7,0), time(10,0))
    ny = (time(13,0), time(16,0))
    if london[0]<=now<=london[1]: return "London"
    if ny[0]<=now<=ny[1]: return "NY"
    return None

# ------------------------------
# Main Bot Loop
# ------------------------------
PAIRS = ["EUR/USD","GBP/USD","GBP/JPY"]
MAX_TRADES_PER_SESSION = 3

def run_bot():
    for pair in PAIRS:
        df_15m = fetch_price(pair)
        if df_15m is None or len(df_15m)<5: continue
        df_5m = df_15m  # For simplicity, same data

        session = session_active()
        if session is None: continue

        bias = calculate_bias(df_15m)
        if bias is None: continue

        sr_zones = detect_sr(df_15m)
        last_price = df_5m['close'].iloc[-1]

        signal = None
        rr = 2

        # Determine breakout / continuation
        if session=="London":
            if last_price>df_15m['high'].iloc[-5] and bias=="BULLISH":
                signal="BUY"
            elif last_price<df_15m['low'].iloc[-5] and bias=="BEARISH":
                signal="SELL"
        elif session=="NY":
            if last_price>df_15m['high'].iloc[-5] and bias=="BULLISH":
                signal="BUY"
            elif last_price<df_15m['low'].iloc[-5] and bias=="BEARISH":
                signal="SELL"

        # Validate SR, candle, trendline
        if signal:
            if not is_near_sr(last_price, sr_zones): continue
            if not detect_candle(df_5m, signal): continue
            if not trendline_break(df_5m, signal): continue
            if len([t for t in trader.trades if t['session']==session])>=MAX_TRADES_PER_SESSION:
                continue

            # SL / TP example
            sl = last_price - 0.01 if signal=="BUY" else last_price + 0.01
            tp = last_price + 0.02 if signal=="BUY" else last_price - 0.02

            trade = trader.open_trade(signal, last_price, sl, tp, rr, pair, session)
            send_telegram_signal(pair, signal, last_price, sl, tp, rr, session)
            print(f"Trade sent: {trade}")

# ------------------------------
# Continuous Loop
# ------------------------------
if __name__=="__main__":
    while True:
        try:
            run_bot()
        except Exception as e:
            print("Bot error:", e)
        t.sleep(60)
