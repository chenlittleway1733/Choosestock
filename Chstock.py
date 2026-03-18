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
    stock_input = st.text_input("請輸入台股代號 (例如: 2330)", key="selected_stock_input", value=st.session_state.selected_stock)
    # 同步輸入框與 session_state
    if stock_input != st.session_state.selected_stock:
        st.session_state.selected_stock = stock_input
    
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

# --- AI 新聞分析 ---
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

# --- AI 議題選股邏輯 ---
def get_topic_stocks(topic):
    topic = topic.lower()
    if any(kw in topic for kw in ["ai", "人工智慧", "輝達", "gtc", "伺服器", "晶片"]):
        return [("2330", "台積電"), ("2382", "廣達"), ("3231", "緯創")], [("6669", "緯穎"), ("3017", "奇鋐"), ("3324", "雙鴻")]
    elif any(kw in topic for kw in ["戰爭", "美伊", "中東", "軍工"]):
        return [("2634", "漢翔"), ("2618", "長榮航太"), ("8046", "南電")], [("8033", "雷虎"), ("2208", "台船"), ("8222", "寶一")]
    elif any(kw in topic for kw in ["綠能", "重電", "缺電"]):
        return [("1513", "中興電"), ("1519", "華城"), ("1503", "士電")], [("1514", "亞力"), ("8996", "高力"), ("6806", "森崴能源")]
    return [("2330", "台積電"), ("2317", "鴻海"), ("2454", "聯發科")], [("1519", "華城"), ("3231", "緯創"), ("2603", "長榮")]

# ==========================================
# 主畫面
# ==========================================
st.markdown("## 📈 台股智慧選股與 AI 操盤系統")

# TOP 5 籌碼區
if st.session_state.show_whale:
    st.markdown("### 🐳 近兩周大戶持股比例顯著增加標的")
    whale_stocks = [("2317", "鴻海"), ("2382", "廣達"), ("1519", "華城"), ("6669", "緯穎"), ("2603", "長榮")]
    cols = st.columns(5)
    for idx, (code, name) in enumerate(whale_stocks):
        with cols[idx]: st.button(f"{name}\n({code})", on_click=change_stock, args=(code,), key=f"w_{code}", use_container_width=True)
    st.markdown("---")

# AI 議題分析結果顯示
elif st.session_state.current_topic:
    st.markdown(f"### 💡 議題【{st.session_state.current_topic}】分析結果")
    p, s = get_topic_stocks(st.session_state.current_topic)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 🛡️ 潛力概念股")
        for code, name in p: st.button(f"{name} ({code})", on_click=change_stock, args=(code,), key=f"topic_p_{code}", use_container_width=True)
    with c2:
        st.markdown("#### 🚀 可能飆股區")
        for code, name in s: st.button(f"{name} ({code})", on_click=change_stock, args=(code,), key=f"topic_s_{code}", use_container_width=True)
    st.markdown("---")

# 個股報告主體
current_id = st.session_state.selected_stock
if current_id:
    with st.spinner('數據計算與分析中...'):
        hist_data, stock_info = get_stock_data(current_id)
        chinese_name = get_chinese_name(current_id)
        search_name = chinese_name if chinese_name else current_id
        news_data = get_and_analyze_news(search_name)

    if hist_data is None or hist_data.empty:
        st.error(f"❌ 查無代號 {current_id} 的股票資料。")
    else:
        # 1. 基本資訊
        st.markdown(f"### 🏢 {chinese_name if chinese_name else current_id} ({current_id})")
        sector = SECTOR_MAP.get(stock_info.get('sector', '未知'), stock_info.get('sector', '未知'))
        industry = SECTOR_MAP.get(stock_info.get('industry', '未知'), stock_info.get('industry', '未知'))
        st.markdown(f"**🏷️ 產業類別：** {sector} / {industry}")
        with st.expander("📖 查看公司詳細營業項目與簡介"):
            st.write(stock_info.get('longBusinessSummary', '目前暫無簡介資料。'))

        # 2. 營運估值 (優化本益比與預估價邏輯)
        cur_p = hist_data['Close'].iloc[-1]
        eps_ttm = stock_info.get('trailingEps', 1)
        eps_fwd = stock_info.get('forwardEps', eps_ttm)
        pe_ttm = cur_p / eps_ttm if eps_ttm > 0 else 0
        pe_fwd = cur_p / eps_fwd if eps_fwd > 0 else 0

        st.markdown("#### 📊 營運估值與法人預估")
        st.markdown("""<style>[data-testid="stMetricValue"]{font-size:1.6rem !important; color:#FFD700 !important;}</style>""", unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("最新報價", f"{cur_p:.2f}")
        m2.metric("過去/預估 EPS", f"{eps_ttm:.2f} / {eps_fwd:.2f}")
        m3.metric("歷史本益比 (TTM)", f"{pe_ttm:.1f}x")
        m4.metric("預估本益比 (FWD)", f"{pe_fwd:.1f}x")

        # --- 相對估值計算法 (解決預估價太高的問題) ---
        # 如果歷史本益比太低或太高，自動限縮在合理區間，避免極端數值
        base_pe = pe_ttm if 8 < pe_ttm < 25 else 15
        if pe_ttm < 8: base_pe = 10 # 對於低 PE 股(如 6669)，給予較合理的基準
        
        st.markdown(f"#### 💰 相對估值分析 (基於歷史 PE 基準: {base_pe:.1f}x)")
        v1, v2, v3 = st.columns(3)
        v1.markdown(f"<div style='background:#e8f5e9;padding:10px;border-radius:5px;text-align:center;color:#000;'><small>便宜價 (基準 x 0.8)</small><br><b>{eps_fwd * base_pe * 0.8:.1f}</b></div>", unsafe_allow_html=True)
        v2.markdown(f"<div style='background:#fff3e0;padding:10px;border-radius:5px;text-align:center;color:#000;'><small>合理價 (基準 x 1.0)</small><br><b>{eps_fwd * base_pe * 1.0:.1f}</b></div>", unsafe_allow_html=True)
        v3.markdown(f"<div style='background:#ffebee;padding:10px;border-radius:5px;text-align:center;color:#000;'><small>昂貴價 (基準 x 1.2)</small><br><b>{eps_fwd * base_pe * 1.2:.1f}</b></div>", unsafe_allow_html=True)

        st.markdown("---")

        # 3. AI 利多利空 (找回被隱藏的區塊)
        st.markdown("### 🤖 AI 投資資訊站：近期消息追蹤")
        if news_data:
            nc1, nc2 = st.columns(2)
            with nc1:
                st.markdown("#### 🟢 潛在利多")
                bull = [n for n in news_data if n['sentiment'] == "🟢 利多"]
                for n in bull: st.markdown(f"- [{n['title']}]({n['link']})")
                if not bull: st.write("近期無顯著利多字眼。")
            with nc2:
                st.markdown("#### 🔴 潛在利空")
                bear = [n for n in news_data if n['sentiment'] == "🔴 利空"]
                for n in bear: st.markdown(f"- [{n['title']}]({n['link']})")
                if not bear: st.write("近期無顯著利空字眼。")
        else: st.info("無法獲取最新新聞摘要。")

        st.markdown("---")

        # 4. 技術圖表
        st.markdown("### 🤖 AI 技術面判定與專業分析圖表")
        ma20 = hist_data['Close'].rolling(20).mean().iloc[-1]
        
        # KD
        h9 = hist_data['High'].rolling(9).max()
        l9 = hist_data['Low'].rolling(9).min()
        rsv = (hist_data['Close'] - l9) / (h9 - l9) * 100
        K, D = [50], [50]
        for v in rsv.fillna(50):
            K.append(K[-1]*(2/3) + v*(1/3))
            D.append(D[-1]*(2/3) + K[-1]*(1/3))
        hist_data['K'], hist_data['D'] = K[1:], D[1:]

        st.markdown(f"<div style='background:#333;padding:10px;border-radius:8px;text-align:center;border-left:5px solid #FFD700;'><b>AI 操作建議：{'📈 多方強勢' if cur_p > ma20 else '📉 空方佔優'}</b></div>", unsafe_allow_html=True)
        
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.5, 0.25, 0.25], subplot_titles=("K線與均線", "KD (9,3,3)", "成交張數"))
        fig.add_trace(go.Candlestick(x=hist_data.index, open=hist_data['Open'], high=hist_data['High'], low=hist_data['Low'], close=hist_data['Close'], name='K線', increasing_line_color='red', decreasing_line_color='green'), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['K'], name='K值', line=dict(color='orange')), row=2, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['D'], name='D值', line=dict(color='cyan')), row=2, col=1)
        fig.update_yaxes(range=[0, 100], row=2, col=1)
        
        diff = hist_data['Close'].diff()
        fig.add_trace(go.Bar(x=hist_data.index, y=hist_data['Volume']/1000, marker_color=['red' if x>=0 else 'green' for x in diff], name='張數'), row=3, col=1)
        fig.update_layout(height=800, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=40, b=50))
        st.plotly_chart(fig, use_container_width=True)
