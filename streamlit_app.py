import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import json
import os
from streamlit_autorefresh import st_autorefresh

# --- 1. GLOBAL HELPERS ---
def format_num(num):
    if not num: return "N/A"
    if num >= 1e12: return f"${num/1e12:.2f} T"
    elif num >= 1e9: return f"${num/1e9:.2f} B"
    elif num >= 1e6: return f"${num/1e6:.2f} M"
    return f"${num:,.2f}"

def calculate_rsi(data, window=14):
    delta = data.diff(); gain = (delta.where(delta > 0, 0)).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window).mean()
    rs = gain / loss; return 100 - (100 / (1 + rs))

# --- 2. CONFIG ---
st.set_page_config(layout="wide", page_title="Institutional Discovery Terminal")
PORTFOLIO_FILE = "portfolio.json"

st.sidebar.title("⚡ Terminal Settings")
if st.sidebar.checkbox("Enable Live Mode (60s Refresh)", value=True):
    st_autorefresh(interval=60 * 1000, key="terminal_refresh")

# --- 3. FMP API INTEGRATION ---
st.sidebar.title("🔑 Data Engine")
fmp_key = st.sidebar.text_input("FMP API Key (Free Tier)", type="password", help="Get this from site.financialmodelingprep.com")

@st.cache_data(ttl=300)
def get_live_insider_feed(portfolio, api_key):
    if not api_key: return pd.DataFrame()
    feed = []
    for ticker in portfolio:
        try:
            url = f"https://financialmodelingprep.com/api/v4/insider-trading?symbol={ticker}&page=0&apikey={api_key}"
            data = requests.get(url, timeout=5).json()
            if isinstance(data, list):
                # Filter for Buys only (Acquisition)
                buys = [x for x in data if x.get('acquistionOrDisposition') == 'A' or 'P-Purchase' in str(x.get('transactionType', ''))]
                for b in buys[:3]: # Top 3 recent buys per ticker
                    feed.append({
                        "Ticker": ticker,
                        "Date": b.get('transactionDate', '')[:10],
                        "Insider": b.get('reportingName', 'Unknown').title(),
                        "Title": b.get('typeOfOwner', 'Exec').title(),
                        "Shares": f"{b.get('securitiesTransacted', 0):,}",
                        "Price": f"${b.get('price', 0):.2f}",
                        "Value": f"${(b.get('securitiesTransacted', 0) * b.get('price', 0)):,.0f}"
                    })
        except: pass
    
    if feed:
        return pd.DataFrame(feed).sort_values(by="Date", ascending=False)
    return pd.DataFrame(columns=["Ticker", "Date", "Insider", "Title", "Shares", "Price", "Value"])

def get_verified_earnings(ticker, api_key):
    if not api_key: return "API Key Required"
    try:
        url = f"https://financialmodelingprep.com/api/v3/historical/earning_calendar/{ticker}?limit=10&apikey={api_key}"
        data = requests.get(url, timeout=5).json()
        if isinstance(data, list) and len(data) > 0:
            sorted_data = sorted(data, key=lambda x: x['date'])
            for item in sorted_data:
                if datetime.strptime(item['date'], '%Y-%m-%d') >= datetime.now():
                    return datetime.strptime(item['date'], '%Y-%m-%d').strftime('%m/%d/%Y')
    except: pass
    return "N/A"

# --- 4. FEATURED WHALE MOVES (Hardcoded) ---
def get_global_data():
    return pd.DataFrame([
        {"Type": "🐋 WHALE", "Ticker": "PLTR", "Name": "Scion (Michael Burry)", "Move": "BIG SHORT", "Details": "Bought Puts on 5M shares", "Date": "02/14/2026"},
        {"Type": "🐋 WHALE", "Ticker": "AMZN", "Name": "Altimeter (Brad Gerstner)", "Move": "ADD", "Details": "+$400M Cloud/AI Bet", "Date": "02/14/2026"},
        {"Type": "🐋 WHALE", "Ticker": "DPZ", "Name": "Berkshire (Buffett)", "Move": "NEW BUY", "Details": "New Stake in Domino's", "Date": "02/14/2026"},
        {"Type": "🐋 WHALE", "Ticker": "CMG", "Name": "Third Point (Dan Loeb)", "Move": "NEW BUY", "Details": "$175M New Stake", "Date": "02/14/2026"},
        {"Type": "🐋 WHALE", "Ticker": "META", "Name": "Pershing Sq (Ackman)", "Move": "NEW BUY", "Details": "$2.0B Stake Initiation", "Date": "02/11/2026"},
        {"Type": "🏛️ POL", "Ticker": "NVDA", "Name": "Nancy Pelosi", "Move": "EXERCISE", "Details": "5,000 shares ($80 Strike)", "Date": "01/16/2026"},
        {"Type": "🐋 WHALE", "Ticker": "SOFI", "Name": "ARK Invest (Wood)", "Move": "BUY", "Details": "2.4M shares Add", "Date": "02/17/2026"}
    ])

# --- 5. SIDEBAR ---
if 'portfolio' not in st.session_state:
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r") as f: st.session_state['portfolio'] = json.load(f)
        except: st.session_state['portfolio'] = ["META", "AMZN", "SOFI", "BMNR", "PLTR", "OPEN"]
    else: st.session_state['portfolio'] = ["META", "AMZN", "SOFI", "BMNR", "PLTR", "OPEN"]

st.sidebar.title("💼 My Portfolio")
new_ticker = st.sidebar.text_input("Add Ticker").upper().strip()
if new_ticker and new_ticker not in st.session_state['portfolio']:
    st.session_state['portfolio'].append(new_ticker)
    with open(PORTFOLIO_FILE, "w") as f: json.dump(st.session_state['portfolio'], f)

for t in st.session_state['portfolio']:
    side_col1, side_col2 = st.sidebar.columns([4, 1])
    side_col1.write(t)
    if side_col2.button("❌", key=f"del_{t}"):
        st.session_state['portfolio'].remove(t)
        with open(PORTFOLIO_FILE, "w") as f: json.dump(st.session_state['portfolio'], f); st.rerun()

st.sidebar.markdown("---")
sel = st.sidebar.text_input("Direct Ticker Entry (e.g. BMNR)", "OPEN").upper().strip()

# --- 6. MAIN INTERFACE ---
st.title("📈 Institutional Intelligence Terminal")

st.header("🚨 Live Insider Action (FMP API)")
if fmp_key:
    with st.spinner("Pulling real-time insider trades..."):
        insider_df = get_live_insider_feed(st.session_state['portfolio'], fmp_key)
    if not insider_df.empty:
        st.dataframe(insider_df, hide_index=True, use_container_width=True)
    else:
        st.info("No recent C-Suite purchases found for your portfolio.")
else:
    st.warning("⚠️ Paste your FMP API Key in the sidebar to unlock live Insider Data and Earnings Dates.")

st.subheader("🌎 Featured 2026 Whale Moves")
wire_df = get_global_data()
st.table(wire_df)

st.markdown("---")

# B. ANALYSIS
if sel:
    s = yf.Ticker(sel); i = s.info
    st.header(f"Analysis: {sel} ({i.get('longName', 'N/A')})")
    
    pe, ps, peg = i.get('trailingPE'), i.get('priceToSalesTrailing12Months'), i.get('pegRatio')
    if not peg and pe:
        growth = i.get('earningsGrowth', i.get('earningsQuarterlyGrowth', i.get('forwardEpsGrowth')))
        if growth: peg = round(pe / (growth * 100), 2)
    
    rev_growth, ebitda_margin = i.get('revenueGrowth', 0), i.get('ebitdaMargins', 0)
    rule_of_40 = (rev_growth + ebitda_margin) * 100

    m1, m2, m3 = st.columns(3)
    m1.metric("Price", f"${i.get('currentPrice', 'N/A')}")
    m2.metric("Market Cap", format_num(i.get('marketCap')))
    m3.metric("Rule of 40", f"{rule_of_40:.1f}%", "Elite" if rule_of_40 >= 40 else "Sub-40")

    col_man, col_chart = st.columns([1, 2])
    with col_man:
        st.subheader("⚠️ Management Check")
        officers = i.get('companyOfficers', [])
        ceo = next((o.get('name') for o in officers if "CEO" in o.get('title', '').upper()), "N/A")
        if sel == "SOFI": ceo = "Anthony Noto"
        elif sel == "OPEN": ceo = "Kaz Nejatian"
        st.write(f"👤 **CEO:** {ceo}")

        t_hits = wire_df[wire_df['Ticker'] == sel]
        if not t_hits.empty:
            st.markdown("#### 🐋 Whale Alerts")
            for _, r in t_hits.iterrows():
                st.warning(f"**{r['Type']}:** {r['Name']} ({r['Move']})")

    with col_chart:
        h = s.history(period="1y")
        if not h.empty:
            h['MA50'] = h['Close'].rolling(50).mean(); h['MA200'] = h['Close'].rolling(200).mean(); h['RSI'] = calculate_rsi(h['Close'])
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
            fig.add_trace(go.Candlestick(x=h.index, open=h['Open'], high=h['High'], low=h['Low'], close=h['Close'], name='Price'), 1, 1)
            fig.add_trace(go.Scatter(x=h.index, y=h['MA50'], name='50MA', line=dict(color='orange')), 1, 1)
            fig.add_trace(go.Scatter(x=h.index, y=h['MA200'], name='200MA', line=dict(color='red')), 1, 1)
            fig.add_trace(go.Scatter(x=h.index, y=h['RSI'], name='RSI', line=dict(color='blue')), 2, 1)
            fig.update_layout(height=450, xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("#### 📅 Earnings Surprises & API-Verified Guidance")
    e1, e2 = st.columns(2)
    with e1:
        st.markdown("**Historical Matrix**")
        eh = s.earnings_history
        if eh is not None and not eh.empty:
            eh_disp = eh[['epsEstimate', 'epsActual', 'surprisePercent']].copy()
            eh_disp.rename(columns={'epsEstimate': 'EPS Est', 'epsActual': 'EPS Actual', 'surprisePercent': 'Surprise %'}, inplace=True)
            eh_disp['Surprise %'] = eh_disp['Surprise %'].apply(lambda x: f"{x*100:.1f}%" if pd.notnull(x) else "N/A")
            st.dataframe(eh_disp, use_container_width=True)
    with e2:
        st.markdown("**Forward Guidance**")
        next_e = get_verified_earnings(sel, fmp_key) if fmp_key else "Missing API Key"
        c_guidance = st.container(border=True)
        c_guidance.write(f"📅 **Confirmed Next:** {next_e}")
        c_guidance.write(f"💵 **Est EPS:** ${i.get('forwardEps', 'N/A')}")
        c_guidance.write(f"📈 **Revenue Growth (YoY):** {rev_growth*100:.1f}%")
        c_guidance.write(f"🎯 **Price Target:** ${i.get('targetMeanPrice', 'N/A')}")
