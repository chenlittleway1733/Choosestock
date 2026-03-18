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
    st.session_state.show_whale = False
    st.session_state.current_topic = ""

# --- 側邊欄 ---
with st.sidebar:
    st.markdown("### 🔍 個股查詢")
    stock_input = st.text_input("請輸入台股代號 (例如: 2330)", key="selected_stock")
    
    st.markdown("---")
    
    st.markdown("### 🐳 籌碼集中度追蹤")
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

# --- 資料函數 (自動判定上市/上櫃) ---
@st.cache_data(ttl=3600)
def get_stock_data(stock_id):
    try:
        # 先試上市 (.TW)
        ticker = yf.Ticker(f"{stock_id}.TW")
        hist = ticker.history(period="1y")
        if hist.empty:
            # 再試上櫃 (.TWO)
            ticker = yf.Ticker(f"{stock_id}.TWO")
            hist = ticker.history(period="1y")
        
        if hist.empty: return None, None
        return hist, ticker.info
    except: return None, None

@st.cache_data(ttl=86400) 
def get_chinese_name(stock_id):
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        match = re.search(r'<title>(.*?)\(', response.text)
        if match: return match.group(1).strip()
    except: pass
    return None

# --- AI 新聞與情緒分析引擎 ---
@st.cache_data(ttl=1800)
def get_and_analyze_news(stock_name):
    try:
        query = urllib.parse.quote(f"{stock_name} 股票")
        url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        response = requests.get(url, timeout=5)
        root = ET.fromstring(response.text)
        
        bull_kws = ["漲", "創高", "買超", "成長", "獲利", "升評", "突破", "大單", "強勢", "飆"]
        bear_kws = ["跌", "賣超", "衰退", "下修", "降評", "砍單", "虧損", "警訊", "挫", "疲弱"]
        
        news_list = []
        for item in root.findall('.//item')[:8]:
            title = item.find('title').text
            link = item.find('link').text
            score = 0
            for kw in bull_kws:
                if kw in title: score += 1
            for kw in bear_kws:
                if kw in title: score -= 1
            
            sentiment = "🟢 利多" if score > 0 else ("🔴 利空" if score < 0 else "⚪ 中立")
            news_list.append({"title": title, "link": link, "sentiment": sentiment})
        return news_list
    except: return []

# ==========================================
# 主畫面
# ==========================================
st.markdown("## 📈 台股智慧選股與 AI 操盤系統")

if st.session_state.show_whale:
    st.markdown("### 🐳 近兩周大戶持股顯著增加標的")
    whale_stocks = [("2317", "鴻海"), ("2382", "廣達"), ("1519", "華城"), ("6669", "緯穎"), ("2603", "長榮")]
    cols = st.columns(5)
    for idx, (code, name) in enumerate(whale_stocks):
        with cols[idx]: st.button(f"{name}\n({code})", on_click=change_stock, args=(code,), key=f"w_{code}", use_container_width=True)

elif st.session_state.current_topic:
    st.markdown(f"### 💡 議題【{st.session_state.current_topic}】關聯選股")
    # 此處簡單示範聯想邏輯
    st.button("台積電 (2330)", on_click=change_stock, args=("2330",))
    st.button("廣達 (2382)", on_click=change_stock, args=("2382",))

if stock_input:
    with st.spinner('深度數據運算中...'):
        hist_data, stock_info = get_stock_data(stock_input)
        chinese_name = get_chinese_name(stock_input)
        search_name = chinese_name if chinese_name else stock_input
        news_data = get_and_analyze_news(search_name)

    if hist_data is None or hist_data.empty:
        st.error("❌ 查無此股票資料。請確認代號（上市/上櫃代號皆可）。")
    else:
        # 1. 基本簡介
        st.markdown(f"### 🏢 {chinese_name if chinese_name else stock_input} ({stock_input})")
        sector = SECTOR_MAP.get(stock_info.get('sector', '未知'), stock_info.get('sector', '未知'))
        industry = SECTOR_MAP.get(stock_info.get('industry', '未知'), stock_info.get('industry', '未知'))
        st.markdown(f"**🏷️ 產業分類：** {sector} / {industry}")
        with st.expander("📖 查看公司詳細營業項目簡介"):
            st.write(stock_info.get('longBusinessSummary', '目前暫無資料。'))

        # 2. 營運估值
        cur_p = hist_data['Close'].iloc[-1]
        eps_ttm = stock_info.get('trailingEps', 0)
        eps_fwd = stock_info.get('forwardEps', eps_ttm)
        pe_ttm = cur_p / eps_ttm if eps_ttm > 0 else 0
        pe_fwd = cur_p / eps_fwd if eps_fwd > 0 else 0

        st.markdown("#### 📊 營運估值與法人預估")
        st.markdown("""<style>[data-testid="stMetricValue"]{font-size:1.6rem !important; color:#FFD700 !important;}</style>""", unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("最新價", f"{cur_p:.2f}")
        m2.metric("過去/預估 EPS", f"{eps_ttm:.2f} / {eps_fwd:.2f}")
        m3.metric("歷史本益比", f"{pe_ttm:.1f}x")
        m4.metric("預估本益比", f"{pe_fwd:.1f}x")

        # 預估價分析
        v1, v2, v3 = st.columns(3)
        v1.markdown(f"<div style='background:#e8f5e9;padding:10px;border-radius:5px;text-align:center;color:#000;'><small>便宜價 (FWD PE 15x)</small><br><b>{eps_fwd*15:.1f}</b></div>", unsafe_allow_html=True)
        v2.markdown(f"<div style='background:#fff3e0;padding:10px;border-radius:5px;text-align:center;color:#000;'><small>合理價 (FWD PE 20x)</small><br><b>{eps_fwd*20:.1f}</b></div>", unsafe_allow_html=True)
        v3.markdown(f"<div style='background:#ffebee;padding:10px;border-radius:5px;text-align:center;color:#000;'><small>昂貴價 (FWD PE 30x)</small><br><b>{eps_fwd*30:.1f}</b></div>", unsafe_allow_html=True)

        st.markdown("---")

        # 3. AI 利多利空區 (找回被漏掉的區塊)
        st.markdown("### 🤖 AI 投資資訊站：利多與利空追蹤")
        if news_data:
            n_col1, n_col2 = st.columns(2)
            with n_col1:
                st.markdown("#### 🟢 潛在利多")
                bullish = [n for n in news_data if n['sentiment'] == "🟢 利多"]
                for n in bullish: st.markdown(f"- [{n['title']}]({n['link']})")
                if not bullish: st.write("近期暫無明顯利多字眼。")
            with n_col2:
                st.markdown("#### 🔴 潛在利空")
                bearish = [n for n in news_data if n['sentiment'] == "🔴 利空"]
                for n in bearish: st.markdown(f"- [{n['title']}]({n['link']})")
                if not bearish: st.write("近期暫無明顯利空字眼。")
        else: st.info("目前無法獲取最新新聞。")

        st.markdown("---")

        # 4. AI 點位與圖表
        st.markdown("### 🤖 AI 技術面判定與專業分析圖表")
        ma20 = hist_data['Close'].rolling(20).mean().iloc[-1]
        ma60 = hist_data['Close'].rolling(60).mean().iloc[-1]
        
        # KD
        h9 = hist_data['High'].rolling(9).max()
        l9 = hist_data['Low'].rolling(9).min()
        rsv = (hist_data['Close'] - l9) / (h9 - l9) * 100
        K, D = [50], [50]
        for v in rsv.fillna(50):
            K.append(K[-1]*(2/3) + v*(1/3))
            D.append(D[-1]*(2/3) + K[-1]*(1/3))
        hist_data['K'], hist_data['D'] = K[1:], D[1:]

        st.markdown(f"<div style='background:#333;padding:10px;border-radius:8px;text-align:center;border-left:5px solid #FFD700;'><b>AI 建議：{'📈 偏多操作' if cur_p > ma20 else '📉 偏空觀望'}</b></div>", unsafe_allow_html=True)
        
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.5, 0.25, 0.25], subplot_titles=("K線", "KD (9,3,3)", "買賣張數"))
        fig.add_trace(go.Candlestick(x=hist_data.index, open=hist_data['Open'], high=hist_data['High'], low=hist_data['Low'], close=hist_data['Close'], name='K線', increasing_line_color='red', decreasing_line_color='green'), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['K'], name='K值', line=dict(color='orange')), row=2, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['D'], name='D值', line=dict(color='cyan')), row=2, col=1)
        fig.update_yaxes(range=[0, 100], row=2, col=1)
        
        diff = hist_data['Close'].diff()
        fig.add_trace(go.Bar(x=hist_data.index, y=hist_data['Volume']/1000, marker_color=['red' if x>=0 else 'green' for x in diff], name='張數'), row=3, col=1)
        fig.update_layout(height=800, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=40, b=50), legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"))
        st.plotly_chart(fig, use_container_width=True)
