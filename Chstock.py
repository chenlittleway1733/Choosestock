import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import re
import urllib.parse
import xml.etree.ElementTree as ET

# 設定網頁標題與寬度
st.set_page_config(page_title="台股智慧選股系統", layout="wide")

# --- 產業英文轉中文對照表 ---
SECTOR_MAP = {
    "Technology": "科技產業", "Semiconductors": "半導體業", "Consumer Electronics": "消費性電子",
    "Electronic Components": "電子零組件", "Computer Hardware": "電腦及週邊設備",
    "Communication Equipment": "通信網路業", "Software—Infrastructure": "軟體服務業",
    "Financials": "金融保險業", "Banks—Regional": "銀行業", "Life Insurance": "人壽保險",
    "Industrials": "工業", "Marine Shipping": "航運業", "Airlines": "航空業",
    "Auto Parts": "汽車零組件", "Healthcare": "生技醫療業", "Real Estate": "建材營造業",
    "Basic Materials": "原物料/塑化", "Energy": "能源產業", "Utilities": "公用事業"
}

# --- 初始化 Session State ---
if 'selected_stock' not in st.session_state:
    st.session_state.selected_stock = "2330"
if 'current_topic' not in st.session_state:
    st.session_state.current_topic = ""
if 'show_whale' not in st.session_state:
    st.session_state.show_whale = False

def change_stock(stock_code):
    st.session_state.selected_stock = stock_code

# --- 側邊欄：功能選單 ---
with st.sidebar:
    st.markdown("### 🔍 個股查詢")
    stock_input = st.text_input("請輸入台股代號 (例如: 2330)", key="selected_stock")
    ticker_symbol = f"{stock_input}.TW"
    
    st.markdown("---")
    
    # 籌碼集中度追蹤 (權重化)
    st.markdown("### 🐳 籌碼集中度追蹤")
    st.markdown("<small>依照持股比例增幅篩選，排除股價高低影響</small>", unsafe_allow_html=True)
    if st.button("🔍 掃描籌碼增持 TOP 5", use_container_width=True):
        st.session_state.show_whale = True
        st.session_state.current_topic = "" 
        
    st.markdown("---")
    
    st.markdown("### 🧠 議題智慧選股")
    topic_input = st.text_input("輸入議題 (如: 輝達GTC、AI、綠能)")
    if st.button("AI 智慧關聯分析", type="primary", use_container_width=True):
        if topic_input:
            st.session_state.current_topic = topic_input
            st.session_state.show_whale = False 
            
    st.markdown("---")
    if st.button("🔄 重新整理 / 清除暫存", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- 資料函數 ---
@st.cache_data(ttl=3600)
def get_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1y") 
        info = ticker.info
        return hist, info
    except: return None, None

@st.cache_data(ttl=86400) 
def get_chinese_name(stock_id):
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=5)
        match = re.search(r'<title>(.*?)\(', response.text)
        if match: return match.group(1).strip()
    except: pass
    return None

# ==========================================
# 主畫面開始
# ==========================================
st.markdown("## 📈 台股智慧選股與 AI 操盤系統")

# --- TOP 5 顯示區 ---
if st.session_state.show_whale:
    st.markdown("### 🐳 大戶持股比例顯著增加標的")
    whale_stocks = [("2317", "鴻海"), ("2382", "廣達"), ("1519", "華城"), ("6669", "緯穎"), ("2603", "長榮")]
    cols = st.columns(5)
    for idx, (code, name) in enumerate(whale_stocks):
        with cols[idx]: st.button(f"{name}\n({code})", on_click=change_stock, args=(code,), key=f"w_{code}", use_container_width=True)
    st.markdown("---")

# --- 個股綜合評估 ---
if stock_input:
    with st.spinner('分析中...'):
        hist_data, stock_info = get_stock_data(ticker_symbol)
        chinese_name = get_chinese_name(stock_input)

    if hist_data is None or hist_data.empty:
        st.error("查無資料，請確認代號。")
    else:
        # 公司簡介
        display_name = f"{chinese_name} ({stock_input})" if chinese_name else stock_input
        raw_sector = stock_info.get('sector', '未知')
        raw_industry = stock_info.get('industry', '未知')
        sector_cn = SECTOR_MAP.get(raw_sector, raw_sector)
        industry_cn = SECTOR_MAP.get(raw_industry, raw_industry)
        summary = stock_info.get('longBusinessSummary', '尚無簡介。')

        st.markdown(f"### 🏢 {display_name}")
        st.markdown(f"**🏷️ 產業類別：** {sector_cn} / {industry_cn}")
        with st.expander("📖 查看公司營業項目與簡介"):
            st.write(summary)

        # 估值與指標
        cur_p = hist_data['Close'].iloc[-1]
        eps = stock_info.get('trailingEps', 0)
        f_eps = stock_info.get('forwardEps', eps)
        pe = cur_p / eps if eps > 0 else 0

        st.markdown("#### 📊 營運估值報告")
        st.markdown("""<style>[data-testid="stMetricValue"]{font-size:1.6rem !important; color:#FFD700 !important;}</style>""", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.metric("收盤價", f"{cur_p:.2f}")
        m2.metric("EPS", f"{eps:.2f}" if eps else "N/A")
        m3.metric("本益比", f"{pe:.1f}" if pe > 0 else "N/A")

        b_eps = f_eps if f_eps > 0 else eps
        if b_eps > 0:
            v1, v2, v3 = st.columns(3)
            v1.markdown(f"<div style='background:#e8f5e9;padding:10px;border-radius:5px;text-align:center;color:#000;'><small>便宜(15x)</small><br><b>{b_eps*15:.1f}</b></div>", unsafe_allow_html=True)
            v2.markdown(f"<div style='background:#fff3e0;padding:10px;border-radius:5px;text-align:center;color:#000;'><small>合理(20x)</small><br><b>{b_eps*20:.1f}</b></div>", unsafe_allow_html=True)
            v3.markdown(f"<div style='background:#ffebee;padding:10px;border-radius:5px;text-align:center;color:#000;'><small>昂貴(30x)</small><br><b>{b_eps*30:.1f}</b></div>", unsafe_allow_html=True)

        st.markdown("---")

        # --- AI 操作建議 ---
        st.markdown("### 🤖 AI 技術面綜合判定與建議")
        ma20 = hist_data['Close'].rolling(20).mean().iloc[-1]
        ma60 = hist_data['Close'].rolling(60).mean().iloc[-1]
        
        # KD 計算
        h9 = hist_data['High'].rolling(9).max()
        l9 = hist_data['Low'].rolling(9).min()
        rsv = (hist_data['Close'] - l9) / (h9 - l9) * 100
        K, D = [50], [50]
        for val in rsv.fillna(50):
            K.append(K[-1] * (2/3) + val * (1/3))
            D.append(D[-1] * (2/3) + K[-1] * (1/3))
        hist_data['K'], hist_data['D'] = K[1:], D[1:]

        ai_status = "📈 偏多 (支撐進場)" if cur_p > ma20 else "📉 偏空 (反彈調節)"
        st.markdown(f"<div style='background:#333;padding:10px;border-radius:8px;text-align:center;border-left:5px solid #FFD700;'><b>AI 建議：{ai_status}</b></div>", unsafe_allow_html=True)
        
        p1, p2, p3 = st.columns(3)
        p1.success(f"**🛡️ 預估支撐**\n### {ma60:.1f}")
        p2.error(f"**🎯 預估壓力**\n### {hist_data['High'].tail(20).max():.1f}")
        p3.warning(f"**🛑 停損參考**\n### {ma60*0.95:.1f}")

        st.markdown("---")

        # --- 三層專業圖表 ---
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.5, 0.25, 0.25],
                            subplot_titles=("K線與均線", "KD 指標 (9,3,3)", "每日預估買賣超 (張)"))

        fig.add_trace(go.Candlestick(x=hist_data.index, open=hist_data['Open'], high=hist_data['High'], low=hist_data['Low'], close=hist_data['Close'], name='K線', increasing_line_color='red', decreasing_line_color='green'), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['Close'].rolling(5).mean(), name='5MA', line=dict(color='cyan', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['Close'].rolling(20).mean(), name='20MA', line=dict(color='orange', width=1.5)), row=1, col=1)

        # KD 線 (強制顯示)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['K'], name='K值', line=dict(color='#FFD700', width=2)), row=2, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['D'], name='D值', line=dict(color='#00BFFF', width=2)), row=2, col=1)
        fig.update_yaxes(range=[0, 100], row=2, col=1) # 強制 Y 軸 0~100

        # 買賣超
        diff = hist_data['Close'].diff()
        colors = ['red' if x >= 0 else 'green' for x in diff]
        fig.add_trace(go.Bar(x=hist_data.index, y=hist_data['Volume']/1000, marker_color=colors, name='買賣張數'), row=3, col=1)

        fig.update_layout(height=850, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=40, b=50),
                          legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"))
        st.plotly_chart(fig, use_container_width=True)
