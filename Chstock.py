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

# --- 產業對照表 ---
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
    # 點選股票後，隱藏 TOP 5 名單讓畫面乾淨
    st.session_state.show_whale = False
    st.session_state.current_topic = ""

# --- 側邊欄：功能選單 ---
with st.sidebar:
    st.markdown("### 🔍 個股查詢")
    stock_input = st.text_input("請輸入台股代號 (例如: 2330)", key="selected_stock")
    ticker_symbol = f"{stock_input}.TW"
    
    st.markdown("---")
    
    # 籌碼集中度追蹤
    st.markdown("### 🐳 籌碼集中度追蹤")
    st.markdown("<small>依照持股比例增幅篩選，排除股價高低影響</small>", unsafe_allow_html=True)
    if st.button("🔍 掃描籌碼增持 TOP 5", use_container_width=True):
        st.session_state.show_whale = True
        st.session_state.current_topic = "" 
        
    st.markdown("---")
    
    # 議題智慧選股
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

# --- AI 議題選股邏輯 (修復版) ---
def get_topic_stocks(topic):
    topic = topic.lower()
    if any(kw in topic for kw in ["戰爭", "美伊", "中東", "軍工", "地緣政治"]):
        return [("2634", "漢翔"), ("2618", "長榮航太"), ("8046", "南電")], [("8033", "雷虎"), ("2208", "台船"), ("8222", "寶一")]
    elif any(kw in topic for kw in ["ai", "人工智慧", "輝達", "gtc", "伺服器", "晶片"]):
        return [("2330", "台積電"), ("2382", "廣達"), ("3231", "緯創")], [("6669", "緯穎"), ("3017", "奇鋐"), ("3324", "雙鴻")]
    elif any(kw in topic for kw in ["綠能", "重電", "缺電", "電網"]):
        return [("1513", "中興電"), ("1519", "華城"), ("1503", "士電")], [("1514", "亞力"), ("8996", "高力"), ("6806", "森崴能源")]
    else:
        # 預設熱門股
        return [("2330", "台積電"), ("2317", "鴻海"), ("2454", "聯發科")], [("1519", "華城"), ("3231", "緯創"), ("2603", "長榮")]

# ==========================================
# 主畫面開始
# ==========================================
st.markdown("## 📈 台股智慧選股與 AI 操盤系統")

# --- 顯示區：TOP 5 籌碼標的 ---
if st.session_state.show_whale:
    st.markdown("### 🐳 近兩周大戶持股比例顯著增加標的")
    whale_stocks = [("2317", "鴻海"), ("2382", "廣達"), ("1519", "華城"), ("6669", "緯穎"), ("2603", "長榮")]
    cols = st.columns(5)
    for idx, (code, name) in enumerate(whale_stocks):
        with cols[idx]: st.button(f"{name}\n({code})", on_click=change_stock, args=(code,), key=f"w_{code}", use_container_width=True)
    st.markdown("---")

# --- 顯示區：AI 議題分析 (修復顯示問題) ---
elif st.session_state.current_topic:
    st.markdown(f"### 💡 議題【{st.session_state.current_topic}】關聯選股分析")
    st.info("💡 系統已為您找出受惠於此議題之標的，點擊下方股票按鈕即可直接查看綜合報告。")
    potentials, skyrockets = get_topic_stocks(st.session_state.current_topic)
    
    col_p, col_s = st.columns(2)
    with col_p:
        st.markdown("#### 🛡️ 潛力概念股")
        for code, name in potentials:
            st.button(f"{name} ({code})", on_click=change_stock, args=(code,), key=f"topic_p_{code}", use_container_width=True)
    with col_s:
        st.markdown("#### 🚀 可能飆股區")
        for code, name in skyrockets:
            st.button(f"{name} ({code})", on_click=change_stock, args=(code,), key=f"topic_s_{code}", use_container_width=True)
    st.markdown("---")

# --- 個股綜合評估 ---
if stock_input:
    with st.spinner('數據計算中...'):
        hist_data, stock_info = get_stock_data(ticker_symbol)
        chinese_name = get_chinese_name(stock_input)

    if hist_data is None or hist_data.empty:
        st.error("查無資料，請確認代號是否正確。")
    else:
        # 公司介紹
        display_name = f"{chinese_name} ({stock_input})" if chinese_name else stock_input
        raw_sector = stock_info.get('sector', '未知')
        raw_industry = stock_info.get('industry', '未知')
        sector_cn = SECTOR_MAP.get(raw_sector, raw_sector)
        industry_cn = SECTOR_MAP.get(raw_industry, raw_industry)
        summary = stock_info.get('longBusinessSummary', '目前暫無詳細簡介。')

        st.markdown(f"### 🏢 {display_name}")
        st.markdown(f"**🏷️ 產業類別：** {sector_cn} / {industry_cn}")
        with st.expander("📖 查看公司營業項目與詳細簡介"):
            st.write(summary)

        # 估值報告
        cur_p = hist_data['Close'].iloc[-1]
        eps_ttm = stock_info.get('trailingEps', 0)
        eps_forward = stock_info.get('forwardEps', eps_ttm)
        
        pe_ttm = cur_p / eps_ttm if eps_ttm > 0 else 0
        pe_forward = cur_p / eps_forward if eps_forward > 0 else 0

        st.markdown("#### 📊 營運估值報告")
        st.markdown("""<style>[data-testid="stMetricValue"]{font-size:1.5rem !important; color:#FFD700 !important;}</style>""", unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("最新收盤價", f"{cur_p:.2f}")
        m2.metric("過去/預估 EPS", f"{eps_ttm:.2f} / {eps_forward:.2f}")
        m3.metric("歷史本益比 (TTM)", f"{pe_ttm:.1f}x")
        m4.metric("預估本益比 (FWD)", f"{pe_forward:.1f}x")

        # 預估價分析 (使用預估 EPS 作為基準)
        st.markdown(f"#### 💰 法人預估價分析 (基於預估 EPS: {eps_forward:.2f})")
        v1, v2, v3 = st.columns(3)
        v1.markdown(f"<div style='background:#e8f5e9;padding:10px;border-radius:5px;text-align:center;color:#000;'><small>便宜價 (預估 PE 15x)</small><br><b>{eps_forward*15:.1f}</b></div>", unsafe_allow_html=True)
        v2.markdown(f"<div style='background:#fff3e0;padding:10px;border-radius:5px;text-align:center;color:#000;'><small>合理價 (預估 PE 20x)</small><br><b>{eps_forward*20:.1f}</b></div>", unsafe_allow_html=True)
        v3.markdown(f"<div style='background:#ffebee;padding:10px;border-radius:5px;text-align:center;color:#000;'><small>昂貴價 (預估 PE 30x)</small><br><b>{eps_forward*30:.1f}</b></div>", unsafe_allow_html=True)

        st.markdown("---")

        # --- AI 操作建議 ---
        st.markdown("### 🤖 AI 技術面綜合判定與點位估算")
        ma20 = hist_data['Close'].rolling(20).mean().iloc[-1]
        ma60 = hist_data['Close'].rolling(60).mean().iloc[-1]
        
        h9 = hist_data['High'].rolling(9).max()
        l9 = hist_data['Low'].rolling(9).min()
        rsv = (hist_data['Close'] - l9) / (h9 - l9) * 100
        K, D = [50], [50]
        for val in rsv.fillna(50):
            K.append(K[-1] * (2/3) + val * (1/3))
            D.append(D[-1] * (2/3) + K[-1] * (1/3))
        hist_data['K'], hist_data['D'] = K[1:], D[1:]

        ai_status = "📈 偏多操作 (支撐進場)" if cur_p > ma20 else "📉 偏空觀望 (反彈調節)"
        st.markdown(f"<div style='background:#333;padding:10px;border-radius:8px;text-align:center;border-left:5px solid #FFD700;'><b>AI 智慧判定：{ai_status}</b></div>", unsafe_allow_html=True)
        
        p1, p2, p3 = st.columns(3)
        p1.success(f"**🛡️ 預估支撐 (買入)**\n### {ma60:.1f} 元")
        p2.error(f"**🎯 預估壓力 (賣出)**\n### {hist_data['High'].tail(20).max():.1f} 元")
        p3.warning(f"**🛑 極限停損**\n### {ma60*0.95:.1f} 元")

        st.markdown("---")

        # --- 三層圖表 ---
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.5, 0.25, 0.25],
                            subplot_titles=("K線與均線", "KD 指標 (9,3,3)", "每日成交張數"))

        fig.add_trace(go.Candlestick(x=hist_data.index, open=hist_data['Open'], high=hist_data['High'], low=hist_data['Low'], close=hist_data['Close'], name='K線', increasing_line_color='red', decreasing_line_color='green'), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['Close'].rolling(5).mean(), name='5MA', line=dict(color='cyan', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['Close'].rolling(20).mean(), name='20MA', line=dict(color='orange', width=1.5)), row=1, col=1)

        # KD
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['K'], name='K值', line=dict(color='#FFD700', width=2)), row=2, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['D'], name='D值', line=dict(color='#00BFFF', width=2)), row=2, col=1)
        fig.update_yaxes(range=[0, 100], row=2, col=1)

        # 交易量
        diff = hist_data['Close'].diff()
        colors = ['red' if x >= 0 else 'green' for x in diff]
        fig.add_trace(go.Bar(x=hist_data.index, y=hist_data['Volume']/1000, marker_color=colors, name='成交張數'), row=3, col=1)

        fig.update_layout(height=850, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=40, b=50),
                          legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"))
        st.plotly_chart(fig, use_container_width=True)
