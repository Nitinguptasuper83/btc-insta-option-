import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
import time

st.set_page_config(page_title="BTC ATM Options Chart", layout="wide")
st.title("📈 BTC ATM Options - Combined Call + Put OHLC with VWAP & Supertrend (20,2)")

# --- Supertrend Function ---
def calculate_supertrend(df, period=20, multiplier=2):
    hl2 = (df['high'] + df['low']) / 2
    df['atr'] = df['high'].rolling(period).max() - df['low'].rolling(period).min()
    df['upperband'] = hl2 + (multiplier * df['atr'])
    df['lowerband'] = hl2 - (multiplier * df['atr'])

    supertrend = []
    in_uptrend = True

    for i in range(len(df)):
        if i == 0:
            supertrend.append(None)
            continue

        if df['close'][i] > df['upperband'][i - 1]:
            in_uptrend = True
        elif df['close'][i] < df['lowerband'][i - 1]:
            in_uptrend = False

        supertrend.append(df['lowerband'][i] if in_uptrend else df['upperband'][i])

    df['supertrend'] = supertrend
    return df

# --- Get Spot Price ---
spot_url = "https://api.delta.exchange/v2/tickers/BTCUSDT"
spot_data = requests.get(spot_url).json()
spot_price = float(spot_data.get("close", 0) or spot_data.get("ticker", {}).get("last_price", 0))
st.subheader(f"📌 BTC Spot Price: ${spot_price:,.2f}")

# --- Get BTC Options ---
products = requests.get("https://api.delta.exchange/v2/products").json().get("result", [])
btc_options = [p for p in products if p['contract_type'] == 'option' and p['asset_symbol'] == 'BTC']

# Filter ATM strike (same call & put)
atm_strike = min(set([p['strike_price'] for p in btc_options]), key=lambda x: abs(x - spot_price))
atm_call = next((p for p in btc_options if p['option_type'] == 'call' and p['strike_price'] == atm_strike), None)
atm_put = next((p for p in btc_options if p['option_type'] == 'put' and p['strike_price'] == atm_strike), None)

if not atm_call or not atm_put:
    st.error("❌ Could not find both ATM call and put options.")
    st.stop()

# --- Fetch 1m Candle Data ---
def get_candles(symbol):
    url = f"https://api.delta.exchange/v2/markets/{symbol}/candles?resolution=1m&limit=100"
    return pd.DataFrame(requests.get(url).json().get("result", []))

df_call = get_candles(atm_call['symbol'])
df_put = get_candles(atm_put['symbol'])

if df_call.empty or df_put.empty:
    st.warning("No candle data available for selected options.")
    st.stop()

# --- Preprocess & Merge ---
df_call['timestamp'] = pd.to_datetime(df_call['time'], unit='s')
df_put['timestamp'] = pd.to_datetime(df_put['time'], unit='s')

df = pd.merge(df_call, df_put, on='timestamp', suffixes=('_call', '_put'))
df = df[['timestamp']]
df['open'] = (df_call['open'] + df_put['open']) / 2
df['high'] = df_call['high'].combine(df_put['high'], max)
df['low'] = df_call['low'].combine(df_put['low'], min)
df['close'] = (df_call['close'] + df_put['close']) / 2
df['volume'] = df_call['volume'] + df_put['volume']

# --- VWAP ---
tp = (df['high'] + df['low'] + df['close']) / 3
vwap = (tp * df['volume']).cumsum() / df['volume'].cumsum()
df['vwap'] = vwap

# --- Supertrend ---
df = calculate_supertrend(df)

# --- Plot ---
fig = go.Figure()

fig.add_trace(go.Candlestick(
    x=df['timestamp'],
    open=df['open'],
    high=df['high'],
    low=df['low'],
    close=df['close'],
    name='Combined ATM'
))

fig.add_trace(go.Scatter(
    x=df['timestamp'],
    y=df['vwap'],
    mode='lines',
    name='VWAP',
    line=dict(color='blue', width=1.5)
))

fig.add_trace(go.Scatter(
    x=df['timestamp'],
    y=df['supertrend'],
    mode='lines',
    name='Supertrend (20,2)',
    line=dict(color='green', width=1.5)
))

fig.update_layout(
    xaxis_rangeslider_visible=False,
    title="ATM BTC Options - Combined Candles",
    height=700
)

st.plotly_chart(fig, use_container_width=True)

st.info("🔁 Chart refreshes every 60 seconds.")
st.experimental_rerun()

