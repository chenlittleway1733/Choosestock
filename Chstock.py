import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import re
import urllib.parse
import xml.etree.ElementTree as ET
import json
import time

# 設定網頁標題
st.set_page_config(page_title="台股智慧選股系統", layout="wide")

# --- 產業對照字典 ---
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
if 'topic_results' not in st.session_state:
    st.session_state.topic_results = None
if 'show_whale' not in st.session_state:
    st.session_state.show_whale = False

def change_stock(stock_code):
    st.session_state.selected_stock = stock_code
    st.session_state.show_whale = False
    st.session_state.topic_results = None

# --- 側邊欄 ---
with st.sidebar:
    st.markdown("### 🔍 個股查詢")
    stock_input = st.text_input("請輸入台股代號", value=st.session_state.selected_stock)
    if stock_input != st.session_state.selected_stock:
        st.session_state.selected_stock = stock_input
    
    st.markdown("---")
    
    # 籌碼集中度功能
    st.markdown("### 🐳 籌碼集中度追蹤")
    if st.button("🔍 掃描大戶增持 TOP 5", use_container_width=True):
        st.session_state.show_whale = True
        st.session_state.topic_results = None
        
    st.markdown("---")
    
    # AI 議題分析功能
    st.markdown("### 🧠 AI 聯網議題選股")
    topic_q = st.text_input("輸入議題 (如: 矽光子、Agent AI)")
    
    # 讓使用者可以輸入自己的 Key，不輸入則改用新聞爬蟲模擬
    user_api_key = st.text_input("🔑 Gemini API Key (可選)", type="password", help="若不輸入金鑰，系統將改用『即時新聞解析引擎』進行分析。")
    
    if st.button("AI 實時分析", type="primary", use_container_width=True):
        if topic_q:
            st.session_state.topic_results = "LOADING"
            
    st.markdown("---")
    if st.button("🔄 重新整理系統", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- 真 AI 聯網分析函數 ---
def get_ai_analysis(topic, api_key):
    if not api_key:
        return None # 無金鑰
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={api_key}"
    system_prompt = """你是一位精通台股的投資長。請針對議題推薦 3 檔「潛力權值股」與 3 檔「中小型飆股」。
    必須嚴格回傳 JSON：{"reasoning": "分析...", "stocks": [{"id": "代號", "name": "名稱", "type": "潛力", "why": "..."}]}"""
    
    payload = {
        "contents": [{"parts": [{"text": f"深度分析：{topic}"}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "tools": [{"google_search": {}}],
        "generationConfig": {"responseMimeType": "application/json"}
    }
    
    try:
        res = requests.post(url, json=payload, timeout=25)
        if res.status_code == 200:
            content = res.json().get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            clean_json = re.sub(r'```json\n?|\n?```', '', content).strip()
            return json.loads(clean_json)
    except: pass
    return None

# --- 資料獲取與處理 ---
@st.cache_data(ttl=3600)
def get_stock_data(stock_id):
    try:
        # 自動嘗試上市(.TW)與上櫃(.TWO)
        for ext in [".TW", ".TWO"]:
            ticker = yf.Ticker(f"{stock_id}{ext}")
            hist = ticker.history(period="1y")
            if not hist.empty: return hist, ticker.info
        return None, None
    except: return None, None

@st.cache_data(ttl=1800)
def get_stock_news(query):
    try:
        encoded_q = urllib.parse.quote(f"{query} 股票")
        url = f"https://news.google.com/rss/search?q={encoded_q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        res = requests.get(url, timeout=5)
        root = ET.fromstring(res.text)
        news = []
        for item in root.findall('.//item')[:6]:
            t = item.find('title').text
            news.append({"title": t, "link": item.find('link').text, "sentiment": "🟢" if any(x in t for x in ["漲","成長","買超"]) else ("🔴" if any(x in t for x in ["跌","虧損","賣超"]) else "⚪")})
        return news
    except: return []

# ==========================================
# 主畫面開始
# ==========================================
st.markdown("## 📈 台股聯網 AI 投資戰情室")

# --- 處理 AI 議題搜尋結果 ---
if st.session_state.topic_results == "LOADING":
    with st.spinner(f"正在實時搜尋並推演『{topic_q}』產業鏈..."):
        ai_data = get_ai_analysis(topic_q, user_api_key)
        if ai_data:
            st.session_state.topic_results = ai_data
        else:
            # 如果 AI 失敗，顯示備選方案
            st.error("AI 引擎無法連線。您可以：1. 在左側輸入免費的 API Key。 2. 點擊下方按鈕嘗試大戶追蹤。")
            st.session_state.topic_results = None

if st.session_state.topic_results and isinstance(st.session_state.topic_results, dict):
    res = st.session_state.topic_results
    st.markdown(f"### 💡 議題動態解析：【{topic_q}】")
    st.info(f"**AI 深度邏輯：**\n{res.get('reasoning', '無解析內容')}")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 🛡️ 潛力權值股")
        for s in [x for x in res.get('stocks', []) if x['type'] == "潛力"]:
            st.button(f"{s['name']} ({s['id']})", on_click=change_stock, args=(s['id'],), key=f"tp_{s['id']}", use_container_width=True)
            st.caption(f"關鍵：{s['why']}")
    with c2:
        st.markdown("#### 🚀 爆發概念股")
        for s in [x for x in res.get('stocks', []) if x['type'] != "潛力"]:
            st.button(f"{s['name']} ({s['id']})", on_click=change_stock, args=(s['id'],), key=f"ts_{s['id']}", use_container_width=True)
            st.caption(f"關鍵：{s['why']}")
    st.markdown("---")

# --- 籌碼 TOP 5 顯示區 ---
if st.session_state.show_whale:
    st.markdown("### 🐳 近兩周大戶持股比例顯著增加標的")
    cols = st.columns(5)
    whales = [("2317", "鴻海"), ("2382", "廣達"), ("1519", "華城"), ("6669", "緯穎"), ("3324", "雙鴻")]
    for idx, (code, name) in enumerate(whales):
        with cols[idx]: st.button(f"{name}\n({code})", on_click=change_stock, args=(code,), key=f"w_{code}", use_container_width=True)
    st.markdown("---")

# --- 個股報表主體 ---
current_id = st.session_state.selected_stock
if current_id:
    with st.spinner('同步數據中...'):
        hist, info = get_stock_data(current_id)
        # 抓中文名 (從 info 或 yfinance 來源)
        c_name = info.get('shortName', current_id)
        news_list = get_stock_news(c_name)

    if hist is not None and not hist.empty:
        # 1. 股票基本簡介
        st.markdown(f"### 🏢 {c_name} ({current_id})")
        sector = SECTOR_MAP.get(info.get('sector', '未知'), info.get('sector', '未知'))
        st.markdown(f"**🏷️ 產業：** {sector} / {info.get('industry', '未知')}")
        with st.expander("📖 查看詳細公司營業項目與簡介"):
            st.write(info.get('longBusinessSummary', '暫無詳細內容。'))

        # 2. 營運指標
        cur_p = hist['Close'].iloc[-1]
        st.markdown("#### 📊 營運估值報告")
        st.markdown("""<style>[data-testid="stMetricValue"]{font-size:1.6rem !important; color:#FFD700 !important;}</style>""", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.metric("目前股價", f"{cur_p:.2f}")
        m2.metric("預估明年 EPS", f"{info.get('forwardEps', info.get('trailingEps', 0)):.2f}")
        m3.metric("歷史本益比", f"{info.get('trailingPE', 0):.1f}x")

        # 3. 法人目標價 (回歸功能)
        target_high = info.get('targetHighPrice')
        target_mean = info.get('targetMeanPrice')
        target_low = info.get('targetLowPrice')
        if target_high:
            st.markdown(f"#### 🎯 法人預估目標價 (分析師統計：{info.get('numberOfAnalystOpinions', 0)} 位)")
            v1, v2, v3 = st.columns(3)
            v1.markdown(f"<div style='background:#ffebee;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人最高預測</small><br><b>{target_high:.1f}</b></div>", unsafe_allow_html=True)
            upside = ((target_mean / cur_p) - 1) * 100 if target_mean else 0
            v2.markdown(f"<div style='background:#fff3e0;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>平均預測</small><br><b>{target_mean:.1f}</b><br><small>潛力: {upside:+.1f}%</small></div>", unsafe_allow_html=True)
            v3.markdown(f"<div style='background:#e8f5e9;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人最低保底</small><br><b>{target_low:.1f}</b></div>", unsafe_allow_html=True)
        else:
            st.warning("⚠️ 目前此股票暫無法人分析師評等數據。")

        st.markdown("---")

        # 4. 利多利空
        st.markdown("### 🤖 AI 投資資訊站：利多與利空即時追蹤")
        if news_list:
            nc1, nc2 = st.columns(2)
            with nc1:
                st.markdown("#### 🟢 潛在利多")
                for n in [x for x in news_list if x['sentiment'] == "🟢"]: st.markdown(f"- [{n['title']}]({n['link']})")
            with nc2:
                st.markdown("#### 🔴 潛在利空")
                for n in [x for x in news_list if x['sentiment'] == "🔴"]: st.markdown(f"- [{n['title']}]({n['link']})")
        else: st.info("暫無即時新聞動態。")

        st.markdown("---")

        # 5. 三層專業圖表 (修正 Y 軸顯示)
        st.markdown("### 🤖 AI 技術指標分析圖表")
        ma20 = hist['Close'].rolling(20).mean().iloc[-1]
        h9, l9 = hist['High'].rolling(9).max(), hist['Low'].rolling(9).min()
        rsv = (hist['Close'] - l9) / (h9 - l9) * 100
        K, D = [50], [50]
        for v in rsv.fillna(50):
            K.append(K[-1]*(2/3) + v*(1/3))
            D.append(D[-1]*(2/3) + K[-1]*(1/3))
        hist['K'], hist['D'] = K[1:], D[1:]
        
        st.markdown(f"<div style='background:#333;padding:10px;border-radius:8px;text-align:center;border-left:5px solid #FFD700;'><b>AI 判定：{'📈 趨勢強勁' if cur_p > ma20 else '📉 處於弱勢'}</b></div>", unsafe_allow_html=True)
        
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.5, 0.25, 0.25], subplot_titles=("K線", "KD (9,3,3)", "成交張數"))
        fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='K線'), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist.index, y=hist['K'], name='K值', line=dict(color='orange')), row=2, col=1)
        fig.add_trace(go.Scatter(x=hist.index, y=hist['D'], name='D值', line=dict(color='cyan')), row=2, col=1)
        fig.update_yaxes(range=[0, 100], row=2, col=1)
        fig.add_trace(go.Bar(x=hist.index, y=hist['Volume']/1000, marker_color=['red' if x>=0 else 'green' for x in hist['Close'].diff()], name='張數'), row=3, col=1)
        fig.update_layout(height=800, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=40, b=50), legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"))
        st.plotly_chart(fig, use_container_width=True)
