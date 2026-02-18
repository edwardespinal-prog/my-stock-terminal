import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import feedparser
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

# --- 3. SECTOR BENCHMARKS ---
SECTOR_BENCHMARKS = {
    "Technology": {"PE": 30.0, "PS": 7.0, "Beta": 1.2, "Growth": 14.0},
    "Financial Services": {"PE": 15.0, "PS": 3.0, "Beta": 1.1, "Growth": 5.0},
    "Healthcare": {"PE": 25.0, "PS": 5.0, "Beta": 0.8, "Growth": 8.0},
    "Consumer Cyclical": {"PE": 25.0, "PS": 2.5, "Beta": 1.2, "Growth": 7.0},
    "Communication Services": {"PE": 20.0, "PS": 4.0, "Beta": 1.0, "Growth": 9.0}
}

# --- 4. DATA SOURCES ---
@st.cache_data(ttl=300)
def get_sec_feed(ticker_cik_map):
    feed_data = []
    headers = {'User-Agent': 'Ed Espinal Portfolio App (edwardespinal@example.com)'}
    
    # Scan Portfolio CIKs
    for ticker, cik in ticker_cik_map.items():
        if not cik: continue
        try:
            url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&CIK={cik}&type=&company=&dateb=&owner=include&start=0&count=20&output=atom"
            feed = feedparser.parse(url, request_headers=headers)
            for entry in feed.entries:
                # Filter for impact filings
                if any(x in entry.title for x in ['13D', '13G', 'Form 4', '8-K']):
                    feed_data.append({
                        "Source": f"🔔 {ticker}",
                        "Filing": entry.title.split('-')[0].strip(),
                        "Description": entry.title,
                        "Date": entry.updated[:10],
                        "Link": entry.link
                    })
        except: pass
    
    # CRITICAL FIX: Return empty DF if no data found
    if not feed_data:
        return pd.DataFrame()
        
    return pd.DataFrame(feed_data).sort_values(by="Date", ascending=False).head(10)

def get_global_data():
    return pd.DataFrame([
        {"Type": "🐋 WHALE", "Ticker": "PLTR", "Name": "Scion (Michael Burry)", "Move": "BIG SHORT", "Details": "Bought Puts on 5M shares", "Date": "02/14/2026"},
        {"Type": "🐋 WHALE", "Ticker": "AMZN", "Name": "Altimeter (Brad Gerstner)", "Move": "ADD", "Details": "+$400M Cloud/AI Bet", "Date": "02/14/2026"},
        {"Type": "🐋 WHALE", "Ticker": "DPZ", "Name": "Berkshire (Buffett)", "Move": "NEW BUY", "Details": "New Stake in Domino's", "Date": "02/14/2026"},
        {"Type": "🐋 WHALE", "Ticker": "GS", "Name": "Duquesne (Druckenmiller)", "Move": "NEW BUY", "Details": "Initiated Position", "Date": "02/14/2026"},
        {"Type": "🐋 WHALE", "Ticker": "CMG", "Name": "Third Point (Dan Loeb)", "Move": "NEW BUY", "Details": "$175M New Stake", "Date": "02/14/2026"},
        {"Type": "🐋 WHALE", "Ticker": "META", "Name": "Pershing Square (Ackman)", "Move": "NEW BUY", "Details": "$2.0B Stake Initiation", "Date": "02/11/2026"},
        {"Type": "🏛️ POL", "Ticker": "PLTR", "Name": "Nancy Pelosi", "Move": "HOLD", "Details": "Maintaining Stake", "Date": "01/22/2026"},
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
    except: return {"AAPL - Apple": "AAPL", "PLTR - Palantir": "PLTR", "SOFI - SoFi": "SOFI"}

# --- 5. SIDEBAR ---
if 'portfolio' not in st.session_state:
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r") as f:
                st.session_state['portfolio'] = json.load(f)
        except:
            st.session_state['portfolio'] = ["META", "AMZN", "SOFI", "BMNR", "PLTR", "OPEN"]
    else:
        st.session_state['portfolio'] = ["META", "AMZN", "SOFI", "BMNR", "PLTR", "OPEN"]

st.sidebar.title("💼 My Portfolio")
new_ticker = st.sidebar.text_input("Add Ticker").upper().strip()
if new_ticker and new_ticker not in st.session_state['portfolio']:
    st.session_state['portfolio'].append(new_ticker)
    with open(PORTFOLIO_FILE, "w") as f: json.dump(st.session_state['portfolio'], f)

for t in st.session_state['portfolio']:
    c1, c2 = st.sidebar.columns([4, 1])
    c1.write(t)
    if c2.button("❌", key=f"del_{t}"):
        st.session_state['portfolio'].remove(t)
        with open(PORTFOLIO_FILE, "w") as f: json.dump(st.session_state['portfolio'], f); st.rerun()

st.sidebar.markdown("---")
sp_map = get_sp500_map()
dropdown_sel = st.sidebar.selectbox("Market Search (SPY)", ["--- Search S&P 500 ---"] + sorted(list(sp_map.keys())), index=0)
direct_sel = st.sidebar.text_input("Direct Ticker Entry (e.g. BMNR, RR)").upper().strip()
sel = direct_sel if direct_sel else sp_map.get(dropdown_sel, "")

# --- 6. DATA PREP ---
portfolio_ciks = {}
for t in st.session_state['portfolio']:
    try:
        inf = yf.Ticker(t).info
        if 'cik' in inf: portfolio_ciks[t] = inf['cik']
    except: pass

# --- 7. MAIN INTERFACE ---
st.title("📈 Institutional Intelligence Terminal")

st.header("🚨 Regulatory & Discovery Wire")
with st.spinner("Scanning SEC Database..."):
    sec_df = get_sec_feed(portfolio_ciks)

if not sec_df.empty:
    st.subheader("🔥 Live SEC Filings (Portfolio)")
    for index, row in sec_df.iterrows():
        st.markdown(f"**{row['Date']}** | {row['Source']} | [{row['Description']}]({row['Link']})")
else:
    st.info("No recent SEC filings (13D/G/Form 4) for your portfolio.")

st.subheader("🌎 Featured 2026 Whale Moves")
wire_df = get_global_data()
st.table(wire_df)

st.markdown("---")

if sel:
    s = yf.Ticker(sel); i = s.info
    st.header(f"Analysis: {sel} ({i.get('longName', 'N/A')})")
    
    # Valuation & Rule of 40
    pe, ps, peg = i.get('trailingPE'), i.get('priceToSalesTrailing12Months'), i.get('pegRatio')
    if not peg and pe:
        growth = i.get('earningsGrowth', i.get('earningsQuarterlyGrowth', i.get('forwardEpsGrowth')))
        if growth: peg = round(pe / (growth * 100), 2)
    
    rev_growth = i.get('revenueGrowth', 0)
    ebitda_margin = i.get('ebitdaMargins', 0)
    rule_of_40 = (rev_growth + ebitda_margin) * 100

    sector = i.get('sector', 'Unknown')
    bench = next((k for k in SECTOR_BENCHMARKS if k == sector), None)
    val_pe = f"{((pe-SECTOR_BENCHMARKS[bench]['PE'])/SECTOR_BENCHMARKS[bench]['PE'])*100:+.0f}%" if bench and pe else "N/A"

    m1, m2, m3 = st.columns(3)
    m1.metric("Price", f"${i.get('currentPrice', 'N/A')}"); m1.caption(f"Sector: **{sector}**")
    m2.metric("Market Cap", format_num(i.get('marketCap')))
    m3.metric("Rule of 40", f"{rule_of_40:.1f}%", "Elite" if rule_of_40 >= 40 else "Sub-40")

    col_man, col_chart = st.columns([1, 2])
    with col_man:
        st.subheader("⚠️ Management Check")
        officers = i.get('companyOfficers', [])
        ceo = next((o.get('name') for o in officers if "CEO" in o.get('title', '').upper()), "N/A")
        if sel == "SOFI": ceo = "Anthony Noto"
        elif sel == "OPEN": ceo = "Kaz Nejatian"
        elif sel == "PLTR": ceo = "Alex Karp"
        st.write(f"👤 **CEO:** {ceo}")
        
        t_hits = wire_df[wire_df['Ticker'] == sel]
        for _, r in t_hits.iterrows():
            with st.container(border=True):
                st.warning(f"**{r['Type']} Alert:** {r['Name']}")
                st.write(f"{r['Move']} on {r['Date']}")
        
        if not sec_df.empty:
            sec_hits = sec_df[sec_df['Description'].str.contains(sel, case=False)]
            if not sec_hits.empty:
                st.error(f"🚨 **SEC ALERT:** Recent filing found!")
                for _, r in sec_hits.iterrows():
                    st.write(f"[{r['Filing']}]({r['Link']}) on {r['Date']}")

    with col_chart:
        st.subheader("Technical Outlook")
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
    st.subheader("📊 Industry Benchmarks & Growth Efficiency")
    f1, f2, f3, f4, f5 = st.columns(5)
    f1.metric("P/E Ratio", f"{pe}", val_pe); f1.caption(f"Sector Avg: {SECTOR_BENCHMARKS.get(bench, {}).get('PE', 'N/A')}")
    f2.metric("P/S Ratio", f"{ps}"); f2.caption(f"Sector Avg: {SECTOR_BENCHMARKS.get(bench, {}).get('PS', 'N/A')}")
    f3.metric("PEG Ratio", f"{peg if peg else 'N/A'}"); f3.caption("Undervalued: < 1.0")
    f4.metric("Beta", i.get('beta', 1.0), "High" if i.get('beta', 1) > 1 else "Stable")
    f5.metric("Rev Growth", f"{rev_growth*100:.1f}%", "Outperforming" if rev_growth > 0.063 else "Slowing")

    st.markdown("#### 📅 Earnings Surprises & Verified Guidance")
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
        st.markdown("**Forward Guidance (2026 Hardcoded)**")
        HARDCODED_DATES = {"PLTR": "05/04/2026", "SOFI": "04/28/2026", "BMNR": "04/15/2026", "AMZN": "04/30/2026", "META": "04/29/2026"}
        next_e = HARDCODED_DATES.get(sel, "N/A")
        label = "✅ Confirmed Date"
        if next_e == "N/A":
            try:
                ed = s.get_earnings_dates(limit=5)
                if ed is not None and not ed.empty:
                    future = ed[ed.index > datetime.now()]
                    if not future.empty:
                        next_e = future.index[0].strftime("%m/%d/%Y"); label = "✅ Calendar Date"
                    else:
                        next_e = (ed.index[0] + timedelta(days=90)).strftime("%m/%d/%Y"); label = "🔮 Projected (90-Day)"
            except: pass
        
        c_guidance = st.container(border=True)
        c_guidance.write(f"📅 **{label}:** {next_e}")
        c_guidance.write(f"💵 **Est EPS:** ${i.get('forwardEps', 'N/A')}")
        c_guidance.write(f"📈 **Revenue (Last Q):** {format_num(i.get('totalRevenue', 0))}")
        c_guidance.write(f"🎯 **Price Target:** ${i.get('targetMeanPrice', 'N/A')}")

    with st.expander("Read Business Summary"): st.write(i.get('longBusinessSummary', 'N/A'))
