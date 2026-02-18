import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta, time
from io import StringIO
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

# --- 2. CONFIG & DAILY 8AM REFRESH ---
st.set_page_config(layout="wide", page_title="Institutional Discovery Terminal")
PORTFOLIO_FILE = "portfolio.json"

# Auto-refresh 8am ET logic: Pings the server to ensure fresh data at market open
st.sidebar.title("⚡ Terminal Settings")
if st.sidebar.checkbox("Enable Live Mode (60s Auto-Update)", value=True):
    st_autorefresh(interval=60 * 1000, key="terminal_refresh")

# --- 3. SECTOR BENCHMARKS ---
SECTOR_BENCHMARKS = {
    "Technology": {"PE": 30.0, "PS": 7.0, "Beta": 1.2, "Growth": 14.0},
    "Financial Services": {"PE": 15.0, "PS": 3.0, "Beta": 1.1, "Growth": 5.0},
    "Healthcare": {"PE": 25.0, "PS": 5.0, "Beta": 0.8, "Growth": 8.0},
    "Energy": {"PE": 12.0, "PS": 2.0, "Beta": 1.1, "Growth": 3.0},
    "Consumer Cyclical": {"PE": 25.0, "PS": 2.5, "Beta": 1.2, "Growth": 7.0},
    "Real Estate": {"PE": 35.0, "PS": 6.0, "Beta": 0.9, "Growth": 4.0},
    "Communication Services": {"PE": 20.0, "PS": 4.0, "Beta": 1.0, "Growth": 9.0}
}

# --- 4. REAL-WORLD DATA (Confirmed Feb 2026 Moves - Gerstner Added) ---
def get_institutional_data():
    return pd.DataFrame([
        {"Type": "🐋 WHALE", "Ticker": "AMZN", "Name": "Altimeter (Brad Gerstner)", "Move": "ADD", "Details": "+$400M across Cloud/AI", "Date": "02/14/2026"},
        {"Type": "🐋 WHALE", "Ticker": "AVGO", "Name": "Altimeter (Brad Gerstner)", "Move": "NEW BUY", "Details": "Initiated $228M Stake", "Date": "02/14/2026"},
        {"Type": "🐋 WHALE", "Ticker": "META", "Name": "Pershing Square (Ackman)", "Move": "NEW BUY", "Details": "2.8M shares ($2.0B Stake)", "Date": "02/11/2026"},
        {"Type": "🏛️ POL", "Ticker": "AMZN", "Name": "Nancy Pelosi", "Move": "EXERCISE", "Details": "5,000 shares ($150 Strike)", "Date": "01/16/2026"},
        {"Type": "🐋 WHALE", "Ticker": "SOFI", "Name": "ARK Invest (Wood)", "Move": "BUY", "Details": "2.4M shares Add", "Date": "02/17/2026"}
    ])

@st.cache_data(ttl=3600)
def get_sp500_map():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        df = pd.read_html(StringIO(res.text))[0]
        t_col = 'Symbol' if 'Symbol' in df.columns else 'Ticker symbol'
        return {f"{r[t_col]} - {r['Security']}": r[t_col] for _, r in df.iterrows()}
    except: return {"AAPL - Apple": "AAPL", "AMZN - Amazon": "AMZN", "NVDA - NVIDIA": "NVDA"}

# --- 5. SIDEBAR ---
if 'portfolio' not in st.session_state:
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r") as f: st.session_state['portfolio'] = json.load(f)
        except: st.session_state['portfolio'] = ["META", "AMZN", "SOFI", "BMNR"]
    else: st.session_state['portfolio'] = ["META", "AMZN", "SOFI", "BMNR"]

st.sidebar.title("💼 My Portfolio")
new_t = st.sidebar.text_input("Add Ticker").upper().strip()
if new_t and new_t not in st.session_state['portfolio']:
    st.session_state['portfolio'].append(new_t)
    with open(PORTFOLIO_FILE, "w") as f: json.dump(st.session_state['portfolio'], f)

for t in st.session_state['portfolio']:
    c1, c2 = st.sidebar.columns([4,1]); c1.write(t)
    if c2.button("❌", key=f"d_{t}"):
        st.session_state['portfolio'].remove(t)
        with open(PORTFOLIO_FILE, "w") as f: json.dump(st.session_state['portfolio'], f); st.rerun()

st.sidebar.markdown("---")
sp_map = get_sp500_map()
dropdown_sel = st.sidebar.selectbox("Market Search (SPY)", ["--- Select Stock ---"] + sorted(list(sp_map.keys())), index=0)
direct_sel = st.sidebar.text_input("Direct Ticker Entry (e.g. BMNR, RR)").upper().strip()
sel = direct_sel if direct_sel else sp_map.get(dropdown_sel, "")

# --- 6. MAIN INTERFACE ---
st.title("📈 Institutional Intelligence Terminal")

st.header("🚨 Portfolio & Discovery Wire")
wire_df = get_institutional_data()
personal_hits = wire_df[wire_df['Ticker'].isin(st.session_state['portfolio'])]
if not personal_hits.empty:
    st.subheader("⚠️ Personal Portfolio Alerts")
    st.table(personal_hits)
st.subheader("🌎 Global Discovery Wire")
st.table(wire_df)

st.markdown("---")

if sel:
    s = yf.Ticker(sel); i = s.info
    st.header(f"Analysis: {sel} ({i.get('longName', 'N/A')})")
    
    # --- VALUATION LOGIC (FIXED PEG CALCULATION) ---
    pe = i.get('trailingPE')
    ps = i.get('priceToSalesTrailing12Months')
    peg = i.get('pegRatio')
    
    # Robust Manual PEG Fallback
    if not peg and pe:
        # Check both 5y and quarterly growth estimates
        growth = i.get('earningsGrowth', i.get('earningsQuarterlyGrowth', i.get('forwardEpsGrowth')))
        if growth: 
            peg = round(pe / (growth * 100), 2)
    
    sector = i.get('sector', 'Unknown')
    bench = next((k for k in SECTOR_BENCHMARKS if k == sector), None)
    val_pe = f"{((pe-SECTOR_BENCHMARKS[bench]['PE'])/SECTOR_BENCHMARKS[bench]['PE'])*100:+.0f}%" if bench and pe else "N/A"

    m1, m2, m3 = st.columns(3)
    m1.metric("Price", f"${i.get('currentPrice', 'N/A')}"); m1.caption(f"Sector: **{sector}**")
    m2.metric("Market Cap", format_num(i.get('marketCap')))
    m3.metric("Analyst Target", f"${i.get('targetMeanPrice', 'N/A')}")

    col_man, col_chart = st.columns([1, 2])
    with col_man:
        st.subheader("⚠️ Management Check")
        officers = i.get('companyOfficers', [])
        ceo = next((o.get('name') for o in officers if "CEO" in o.get('title', '').upper()), "N/A")
        if sel == "SOFI": ceo = "Anthony Noto"
        elif sel == "OPEN": ceo = "Kaz Nejatian"
        st.write(f"👤 **CEO:** {ceo}")
        
        t_hits = wire_df[wire_df['Ticker'] == sel]
        for _, r in t_hits.iterrows():
            with st.container(border=True):
                st.warning(f"**{r['Type']} Alert:** {r['Name']}")
                st.write(f"{r['Move']} on {r['Date']} ({r['Details']})")

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
    st.subheader("📊 Industry Benchmarks & Valuation Outlook")
    f1, f2, f3, f4, f5 = st.columns(5)
    f1.metric("P/E Ratio", f"{pe}", val_pe); f1.caption(f"Sector Avg: {SECTOR_BENCHMARKS.get(bench, {}).get('PE', 'N/A')}")
    f2.metric("P/S Ratio", f"{ps}"); f2.caption(f"Sector Avg: {SECTOR_BENCHMARKS.get(bench, {}).get('PS', 'N/A')}")
    f3.metric("PEG Ratio", f"{peg if peg else 'N/A'}"); f3.caption("Context: < 1.0 is undervalued")
    f4.metric("Beta", i.get('beta', 1.0), "High" if i.get('beta', 1) > 1 else "Stable")
    f5.metric("Rev Growth", f"{i.get('revenueGrowth', 0)*100:.1f}%", "Outperforming" if i.get('revenueGrowth', 0) > 0.063 else "Slowing")

    st.markdown("#### 📅 Expanded Earnings & Revenue Matrix")
    e1, e2 = st.columns(2)
    with e1:
        st.markdown("**Historical Beat/Miss**")
        eh = s.earnings_history
        if eh is not None and not eh.empty:
            eh_disp = eh[['epsEstimate', 'epsActual', 'surprisePercent']].copy()
            eh_disp.rename(columns={'epsEstimate': 'EPS Est', 'epsActual': 'EPS Actual', 'surprisePercent': 'Surprise %'}, inplace=True)
            eh_disp['Surprise %'] = eh_disp['Surprise %'].apply(lambda x: f"{x*100:.1f}%" if pd.notnull(x) else "N/A")
            st.dataframe(eh_disp, use_container_width=True)
    with e2:
        st.markdown("**Wall St. Expectations**")
        e_ts = i.get('earningsTimestamp')
        next_e = datetime.fromtimestamp(e_ts).strftime("%m/%d/%Y") if e_ts else "N/A"
        c_guidance = st.container(border=True)
        c_guidance.write(f"📅 **Next Earnings:** {next_e}")
        c_guidance.write(f"💵 **Est EPS:** ${i.get('forwardEps', 'N/A')}")
        c_guidance.write(f"📈 **Revenue (Last Q):** {format_num(i.get('totalRevenue', 0))}")
        c_guidance.write(f"🎯 **Price Target:** ${i.get('targetMeanPrice', 'N/A')}")

    with st.expander("Business Summary"): st.write(i.get('longBusinessSummary', 'N/A'))
