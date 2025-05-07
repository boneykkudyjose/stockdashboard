import streamlit as st
import yfinance as yf
import pandas as pd
from pytrends.request import TrendReq
import requests
from bs4 import BeautifulSoup
import feedparser
import datetime
import json
import plotly.express as px

st.set_page_config(page_title="Stock Research Tool", layout="wide")

st.title("📊 Stock Research Dashboard")

ticker = st.text_input("Enter Stock Ticker (e.g., GME, TSLA):", "GME").upper()

import re

def get_yahoo_finance_rss(ticker):
    feed_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    feed = feedparser.parse(feed_url)
    headlines = []
    for entry in feed.entries[:5]:  # Get top 5 news items
        headlines.append((entry.title, entry.link))
    return headlines

def calculate_mid_price(df):
    # Calculate the mid price as the average of bid and ask
    df["mid_price"] = (df["bid"] + df["ask"]) / 2
    return df

def get_option_expirations(ticker):
    stock = yf.Ticker(ticker)
    try:
        return stock.options  # List of strings like ['2024-05-10', '2024-05-17', ...]
    except Exception as e:
        return []

def get_option_chain(ticker, expiry, option_type='calls'):
    stock = yf.Ticker(ticker)
    try:
        opt = stock.option_chain(expiry)
        return opt.calls if option_type == 'calls' else opt.puts
    except Exception as e:
        return None
def categorize_strikes(df, current_price):
    # Define thresholds for ATM, ITM, and OTM
    atm_threshold = current_price * 0.02  # 2% tolerance for ATM

    df["category"] = df["strike"].apply(
        lambda x: "ATM" if abs(x - current_price) <= atm_threshold else ("ITM" if (x < current_price) else "OTM")
    )
    return df

def calculate_category_changes(df):
    # Group by categories and calculate percentage change for Open Interest and Volume
    df['oi_pct_change'] = df.groupby('category')['openInterest'].pct_change() * 100
    df['volume_pct_change'] = df.groupby('category')['volume'].pct_change() * 100
    return df
def plot_open_interest_by_category(df_calls, df_puts, option_type, expiry, current_price):
    # Categorize strikes for calls and puts
    df_calls = categorize_strikes(df_calls, current_price)
    df_puts = categorize_strikes(df_puts, current_price)

    # Add mid price to both calls and puts
    df_calls = calculate_mid_price(df_calls)
    df_puts = calculate_mid_price(df_puts)

    # Calculate percentage changes in Open Interest and Volume
    df_calls = calculate_category_changes(df_calls)
    df_puts = calculate_category_changes(df_puts)

    # Create a combined dataframe for calls and puts
    combined_df = pd.concat([df_calls, df_puts])

    # Plotting options by category
    fig = px.bar(
        combined_df,
        x="strike",
        y="openInterest",
        color="category",
        hover_data=["volume", "bid", "ask", "mid_price", "oi_pct_change", "volume_pct_change"],
        title=f"Open Interest by Category for {expiry}",
        labels={"strike": "Strike Price", "openInterest": "Open Interest"},
        color_discrete_map={"ATM": "orange", "ITM": "green", "OTM": "gray"}
    )

    fig.update_layout(
        xaxis_title="Strike Price",
        yaxis_title="Open Interest",
        height=500,
        template="plotly_dark"
    )

    # Calculate Put/Call Open Interest Ratio
    total_call_oi = df_calls["openInterest"].sum()
    total_put_oi = df_puts["openInterest"].sum()
    ratio = total_put_oi / total_call_oi if total_call_oi != 0 else 0

    fig.add_annotation(
        x=0.5,
        y=0.95,
        text=f"Put/Call Open Interest Ratio: {ratio:.2f}",
        showarrow=False,
        font=dict(size=14, color="white"),
        align="center"
    )

    return fig



def get_earnings_date(ticker):
    try:
        stock = yf.Ticker(ticker)
        cal = stock.calendar  # This returns a dictionary

        # Check if 'Earnings Date' exists in the dictionary
        if 'Earnings Date' in cal:
            earnings_date = cal['Earnings Date']

            # If the earnings date is a list, extract the first date
            if isinstance(earnings_date, list):
                earnings_date = earnings_date[0]
            
            # Check if the earnings date is a datetime.date object
            if isinstance(earnings_date, pd.Timestamp):
                return earnings_date.strftime('%Y-%m-%d')
            elif isinstance(earnings_date, datetime.date):
                # If it's a datetime.date object, convert it to string
                return earnings_date.strftime('%Y-%m-%d')
            else:
                return "Unsupported date format"
        else:
            return "Earnings Date not available"
    except Exception as e:
        print(f"[ERROR] Failed to get earnings date for {ticker}: {e}")
        return "Error"


        
def get_reddit_mentions(ticker):
    url = f"https://www.reddit.com/search/?q={ticker}&sort=new"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        posts = soup.find_all("h3")
        mentions = [post.text for post in posts if ticker.upper() in post.text.upper()]
        return len(mentions)
    except Exception as e:
        return f"Error: {e}"

if ticker:
    stock = yf.Ticker(ticker)
    hist = stock.history(period="1mo")

    # Calculate volume spike
    hist["Avg Volume"] = hist["Volume"].rolling(10).mean()
    hist["Volume Spike"] = hist["Volume"] / hist["Avg Volume"]
    latest_spike = hist["Volume Spike"].iloc[-1]

    tabs = st.tabs(["🏢 Overview", "📈 Volume Spike", "🏦 Holders", "📊 Retail Interest" , "🔥Short Squeeze","📰 News","📉 Option Interest","Earnings"])

    # Tab 1: Overview
    with tabs[0]:
        st.subheader(f"{stock.info.get('shortName', ticker)} ({ticker})")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Price", stock.info.get("regularMarketPrice"))
        with col2:
            st.metric("Market Cap", f"{stock.info.get('marketCap', 0):,}")
        with col3:
            st.metric("P/E Ratio", stock.info.get("trailingPE", "N/A"))

        st.markdown("### 📉 Recent Price Chart")
        st.line_chart(hist["Close"])

    # Tab 2: Volume Spike
    with tabs[1]:
        st.subheader("📊 Volume Spike Analysis")
        st.line_chart(hist[["Volume", "Avg Volume"]])

        st.markdown("### 🚨 Short Squeeze Signal")
        if latest_spike > 3:
            st.success(f"High volume spike: {latest_spike:.2f}x average 🚀")
        elif latest_spike > 2:
            st.warning(f"Moderate spike: {latest_spike:.2f}x average ⚠️")
        else:
            st.info(f"Low spike: {latest_spike:.2f}x average 🧊")

    # Tab 3: Institutional Holders
    with tabs[2]:
        st.subheader("🏦 Major Institutional Holders")
        try:
            holders = stock.institutional_holders
            if holders is not None:
                st.dataframe(holders)
            else:
                st.warning("No institutional holder data found.")
        except Exception:
            st.error("Error loading holder data.")

        st.markdown("### 🧾 Major Holders (Summary)")
        try:
            st.dataframe(stock.major_holders)
        except Exception:
            st.warning("Major holder data not available.")

    # Tab 4: Retail Interest
    with tabs[3]:
        # Use this inside your Streamlit app:
        st.markdown("### 🧠 Reddit Mentions")
        reddit_hits = get_reddit_mentions(ticker)
        if isinstance(reddit_hits, int):
            st.write(f"🔎 Reddit mentions in recent posts: **{reddit_hits}**")
            if reddit_hits > 10:
                st.success("Strong Reddit chatter! 🚀")
            elif reddit_hits > 3:
                st.info("Moderate Reddit interest.")
            else:
                st.warning("Low Reddit activity.")
        else:
            st.error(reddit_hits)

    with tabs[4]:
        st.title("🔥 Short Squeeze Detector")

        if ticker:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period="1mo")

            # Volume Spike
            hist["Volume Avg"] = hist["Volume"].rolling(window=10).mean()
            hist["Volume Spike"] = hist["Volume"] / hist["Volume Avg"]
            latest_volume_spike = hist["Volume Spike"].iloc[-1]

            # Display Chart
            st.subheader("📈 Volume Spike Chart")
            st.line_chart(hist[["Volume", "Volume Avg"]])

            st.subheader("🧠 Volume Spike Score")
            st.write(f"Latest volume is {latest_volume_spike:.2f}x the 10-day average volume.")

            # Placeholder for Short Interest Data (you'll need an API key from FMP, Ortex, or others)
            st.subheader("📉 Short Interest Data (Example)")
            short_interest_data = {
                "Short Interest % Float": 25.4,
                "Days to Cover": 3.2
            }
            st.write(short_interest_data)

            # Squeeze Potential
            st.subheader("🚨 Squeeze Potential Rating (Unofficial)")
            if latest_volume_spike > 3 and short_interest_data["Short Interest % Float"] > 20:
                st.success("High Squeeze Potential 🚀")
            elif latest_volume_spike > 2:
                st.warning("Moderate Potential ⚠️")
            else:
                st.info("Low Squeeze Indicators 🧊")
    with tabs[5]:
        st.subheader("📰 Latest News Headlines")
        try:
            news_items = get_yahoo_finance_rss(ticker)
            if news_items:
                for title, url in news_items:
                    st.markdown(f"- [{title}]({url})")
            else:
                st.info("No news found.")
        except Exception as e:
            st.error(f"Failed to fetch news: {e}")
    
    with tabs[6]:
        expiries = get_option_expirations(ticker)
        if not expiries:
            st.warning("Could not fetch expiration dates.")
        else:
            selected_expiry = st.selectbox("Choose expiration date", expiries)
            opt_type = st.radio("Option Type", ["Calls", "Puts", "Both"], horizontal=True)

            # Fetch historical options data for calls and puts
            df_calls = get_option_chain(ticker, selected_expiry, "calls")
            df_puts = get_option_chain(ticker, selected_expiry, "puts")
            current_price = yf.Ticker(ticker).info.get("regularMarketPrice", 0)

            if df_calls is not None and not df_calls.empty and df_puts is not None and not df_puts.empty:
                if opt_type == "Both":
                    st.dataframe(pd.concat([df_calls, df_puts]))
                    st.plotly_chart(
                        plot_open_interest_by_category(df_calls, df_puts, "Calls and Puts", selected_expiry, current_price),
                        use_container_width=True
                    )
                elif opt_type == "Calls":
                    st.dataframe(df_calls)
                    st.plotly_chart(
                        plot_open_interest_by_category(df_calls, df_puts, "Calls", selected_expiry, current_price),
                        use_container_width=True
                    )
                else:
                    st.dataframe(df_puts)
                    st.plotly_chart(
                        plot_open_interest_by_category(df_calls, df_puts, "Puts", selected_expiry, current_price),
                        use_container_width=True
                    )
            else:
                st.warning("No options data available for this expiry.")

    with tabs[7]:  # Assuming this is the overview tab
        st.subheader("📅 Earnings Information")

        earnings_date = get_earnings_date(ticker)
        st.markdown(f"**Next Earnings Date:** {earnings_date}")
