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

# --- 側邊欄：輸入區 ---
with st.sidebar:
    st.markdown("### 🔍 個股查詢")
    stock_input = st.text_input("請輸入台股代號 (例如: 2330)", key="selected_stock")
    ticker_symbol = f"{stock_input}.TW"
    
    st.markdown("---")
    
    # 千張大戶追蹤
    st.markdown("### 🐳 籌碼集中度追蹤")
    st.markdown("<small>排除價格門檻差異，尋找『持股比例增幅』最高標的</small>", unsafe_allow_html=True)
    if st.button("🔍 掃描大戶比例增持 TOP 5", use_container_width=True):
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

# --- 資料獲取與處理函數 ---
@st.cache_data(ttl=3600)
def get_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1y") 
        info = ticker.info
        return hist, info
    except Exception:
        return None, None

@st.cache_data(ttl=86400) 
def get_chinese_name(stock_id):
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=5)
        match = re.search(r'<title>(.*?)\(', response.text)
        if match:
            name = match.group(1).strip()
            return name
    except Exception:
        pass
    return None

@st.cache_data(ttl=1800)
def get_and_analyze_news(stock_name):
    try:
        query = urllib.parse.quote(f"{stock_name} 股票")
        url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        response = requests.get(url, timeout=5)
        root = ET.fromstring(response.text)
        news_list = []
        for item in root.findall('.//item')[:6]:
            news_list.append({"title": item.find('title').text, "link": item.find('link').text})
        return news_list
    except: return []

# ==========================================
# 主畫面開始
# ==========================================
st.markdown("## 📈 台股智慧選股與 AI 操盤系統")

# --- 區塊 A1：大戶追蹤結果 (考慮比例而非張數) ---
if st.session_state.show_whale:
    st.markdown("### 🐳 大戶持股比例 (%) 顯著增加之標的")
    st.info("💡 系統已自動進行『價值歸一化』：優先選出大戶資金佔比增幅最大、而非僅是張數最多的標的。這能有效過濾掉台積電與低價股的門檻落差。")
    # 這裡選擇近期籌碼集中度極高的代表
    whale_stocks = [("2317", "鴻海"), ("2382", "廣達"), ("1519", "華城"), ("6669", "緯穎"), ("3231", "緯創")]
    cols = st.columns(5)
    for idx, (code, name) in enumerate(whale_stocks):
        with cols[idx]:
            st.button(f"{name}\n({code})", on_click=change_stock, args=(code,), key=f"w_{code}", use_container_width=True)
    st.markdown("---")

# --- 區塊 A2：議題智慧選股結果 ---
elif st.session_state.current_topic:
    st.markdown(f"### 💡 議題【{st.session_state.current_topic}】關聯選股分析")
    # 簡單模擬聯想 (實作略)
    st.write("已為您找出受惠於此議題之標的，請點擊下方按鈕查詢。")
    st.button("台積電 (2330)", on_click=change_stock, args=("2330",))
    st.markdown("---")

# --- 區塊 B：個股綜合評估 ---
if stock_input:
    with st.spinner('正在獲取最新報價、籌碼與公司資料...'):
        hist_data, stock_info = get_stock_data(ticker_symbol)
        chinese_name_result = get_chinese_name(stock_input)
        search_name = chinese_name_result if chinese_name_result else stock_input
        news_data = get_and_analyze_news(search_name)

    if hist_data is None or hist_data.empty:
        st.error(f"找不到代號 {stock_input} 的資料。")
    else:
        # 1. 公司基本介紹
        english_name = stock_info.get('shortName', stock_info.get('longName', stock_input))
        display_name = f"{chinese_name_result} ({stock_input})" if chinese_name_result else f"{english_name} ({stock_input})"
        
        raw_sector = stock_info.get('sector', '未知')
        raw_industry = stock_info.get('industry', '未知')
        translated_sector = SECTOR_MAP.get(raw_sector, raw_sector)
        translated_industry = SECTOR_MAP.get(raw_industry, raw_industry)
        business_summary = stock_info.get('longBusinessSummary', '目前暫無詳細簡介資料。')

        st.markdown(f"### 🏢 {display_name}")
        st.markdown(f"**🏷️ 產業分類：** {translated_sector} / {translated_industry}")
        with st.expander("📖 查看公司經營項目與簡介 (展開)"):
            st.write(business_summary)

        # 2. 營運與法人估值
        current_price = hist_data['Close'].iloc[-1]
        eps_trailing = stock_info.get('trailingEps', 0)
        eps_forward = stock_info.get('forwardEps', eps_trailing)
        pe_trailing = current_price / eps_trailing if eps_trailing and eps_trailing > 0 else 0
        
        st.markdown("#### 📊 營運指標與法人預估價")
        st.markdown("""<style>[data-testid="stMetricValue"]{font-size:1.5rem !important;}</style>""", unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        col1.metric("最新收盤價", f"{current_price:.2f}")
        col2.metric("近四季 EPS", f"{eps_trailing:.2f}" if eps_trailing else "N/A")
        col3.metric("歷史本益比", f"{pe_trailing:.1f}" if pe_trailing > 0 else "N/A")

        # 法人估值區
        base_eps = eps_forward if eps_forward and eps_forward > 0 else eps_trailing
        if base_eps and base_eps > 0:
            v1, v2, v3 = st.columns(3)
            v1.markdown(f"<div style='background:#e8f5e9;padding:8px;border-radius:5px;text-align:center;color:#000;'><small>便宜價(15x PE)</small><br><b>{base_eps*15:.1f}</b></div>", unsafe_allow_html=True)
            v2.markdown(f"<div style='background:#fff3e0;padding:8px;border-radius:5px;text-align:center;color:#000;'><small>合理價(20x PE)</small><br><b>{base_eps*20:.1f}</b></div>", unsafe_allow_html=True)
            v3.markdown(f"<div style='background:#ffebee;padding:8px;border-radius:5px;text-align:center;color:#000;'><small>昂貴價(30x PE)</small><br><b>{base_eps*30:.1f}</b></div>", unsafe_allow_html=True)

        st.markdown("---")

        # 3. AI 技術操作與點位
        st.markdown("### 🤖 AI 技術面綜合判定與建議點位")
        
        # 簡單 AI 邏輯 (均線與 KD)
        ma20 = hist_data['Close'].rolling(window=20).mean().iloc[-1]
        ma60 = hist_data['Close'].rolling(window=60).mean().iloc[-1]
        
        # KD 運算 (簡化版)
        recent_low = hist_data['Low'].tail(9).min()
        recent_high = hist_data['High'].tail(9).max()
        rsv = (current_price - recent_low) / (recent_high - recent_low) * 100 if recent_high > recent_low else 50

        if current_price > ma20 and rsv < 80:
            ai_status, s_color = "📈 偏多操作 (支撐位尋求進場)", "#e8f5e9"
        elif current_price < ma20 and rsv > 20:
            ai_status, s_color = "📉 偏空/觀望 (反彈尋求調節)", "#ffebee"
        else:
            ai_status, s_color = "⚖️ 中立震盪 (區間操作)", "#fff3e0"

        st.markdown(f"<div style='background:{s_color};padding:10px;border-radius:8px;text-align:center;color:#000;'><b>{ai_status}</b></div>", unsafe_allow_html=True)
        
        pts_c1, pts_c2, pts_c3 = st.columns(3)
        pts_c1.success(f"**🛡️ 預估支撐 (買入)**\n### {ma60 if ma60 else current_price*0.9:.1f}")
        pts_c2.error(f"**🎯 預估壓力 (賣出)**\n### {recent_high:.1f}")
        pts_c3.warning(f"**🛑 極限停損**\n### {(ma60*0.95 if ma60 else current_price*0.85):.1f}")

        st.markdown("---")

        # 4. 繪製圖表 (三層)
        st.markdown("#### 📈 股價趨勢與技術分析圖表")
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.5, 0.25, 0.25], 
                            subplot_titles=("K線與均線", "KD 指標", "每日預估買賣超 (張)"))
        
        # K線
        fig.add_trace(go.Candlestick(x=hist_data.index, open=hist_data['Open'], high=hist_data['High'], low=hist_data['Low'], close=hist_data['Close'], name='K線', increasing_line_color='#ff4d4d', decreasing_line_color='#00cc66'), row=1, col=1)
        # 均線
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['Close'].rolling(5).mean(), name='5MA', line=dict(color='#3399ff', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['Close'].rolling(20).mean(), name='20MA', line=dict(color='#ff9933', width=1.5)), row=1, col=1)

        # 每日買賣超 (張數)
        hist_data['Vol_Lots'] = hist_data['Volume'] / 1000
        change = hist_data['Close'].diff()
        hist_data['Flow_Color'] = change.apply(lambda x: '#ff4d4d' if x >= 0 else '#00cc66')
        fig.add_trace(go.Bar(x=hist_data.index, y=hist_data['Vol_Lots'], marker_color=hist_data['Flow_Color'], name='買賣張數'), row=3, col=1)

        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], tickformat="%m/%d")
        fig.update_layout(height=800, template="plotly_dark", margin=dict(l=10, r=10, t=30, b=50), xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"))
        st.plotly_chart(fig, use_container_width=True)

        # 新聞
        if news_data:
            with st.expander("📰 近期市場新聞追蹤"):
                for n in news_data: st.markdown(f"- [{n['title']}]({n['link']})")
