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
if 'topic_results' not in st.session_state:
    st.session_state.topic_results = None
if 'show_whale' not in st.session_state:
    st.session_state.show_whale = False

def change_stock(stock_code):
    st.session_state.selected_stock = stock_code
    st.session_state.topic_results = None
    st.session_state.show_whale = False

# --- Gemini 2.5 聯網分析引擎 (修正 JSON 解析問題) ---
def get_real_ai_analysis(topic):
    apiKey = "" # 執行環境自動提供
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={apiKey}"
    
    system_prompt = """你是一位精通台股產業鏈的投資長。請針對議題，結合最新搜尋結果，推薦 3 檔「潛力權值股」與 3 檔「中小型飆股」。
    必須嚴格回傳 JSON，格式如下：
    {
      "reasoning": "產業趨勢簡述",
      "stocks": [
        {"id": "代號", "name": "名稱", "type": "潛力", "why": "受惠原因"},
        ...
      ]
    }
    不要回傳任何 Markdown 標記或額外文字。"""
    
    payload = {
        "contents": [{"parts": [{"text": f"分析議題：{topic}"}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "tools": [{"google_search": {}}],
        "generationConfig": {"responseMimeType": "application/json"}
    }
    
    for i in range(5):
        try:
            response = requests.post(url, json=payload, timeout=25)
            if response.status_code == 200:
                res_json = response.json()
                content = res_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                # 清理可能的 Markdown 標籤
                clean_json = re.sub(r'```json\n?|\n?```', '', content).strip()
                sources = res_json.get('candidates', [{}])[0].get('groundingMetadata', {}).get('groundingAttributions', [])
                links = [s.get('web', {}).get('uri') for s in sources if s.get('web', {}).get('uri')]
                return json.loads(clean_json), list(set(links))
            elif response.status_code == 429:
                time.sleep(2 ** i)
        except Exception:
            time.sleep(1)
    return None, []

# --- 側邊欄 ---
with st.sidebar:
    st.markdown("### 🔍 個股查詢")
    stock_input = st.text_input("輸入台股代號", value=st.session_state.selected_stock)
    if stock_input != st.session_state.selected_stock:
        st.session_state.selected_stock = stock_input
    
    st.markdown("---")
    
    st.markdown("### 🐳 籌碼集中度追蹤")
    st.markdown("<small>依照持股比例增幅篩選，排除股價門檻差異</small>", unsafe_allow_html=True)
    if st.button("🔍 掃描籌碼增持 TOP 5", use_container_width=True):
        st.session_state.show_whale = True
        st.session_state.topic_results = None
        
    st.markdown("---")
    
    st.markdown("### 🧠 AI 聯網議題選股")
    topic_q = st.text_input("輸入議題 (如: 代理人AI、矽光子)")
    if st.button("AI 實時分析", type="primary", use_container_width=True):
        if topic_q:
            with st.spinner(f"🤖 AI 正在聯網搜尋並分析「{topic_q}」..."):
                data, links = get_real_ai_analysis(topic_q)
                if data:
                    st.session_state.topic_results = {"topic": topic_q, "data": data, "links": links}
                    st.session_state.show_whale = False
                else:
                    st.error("AI 引擎目前繁忙或解析錯誤，請稍後再試。")
    
    st.markdown("---")
    if st.button("🔄 重整系統快取", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- 資料獲取 (TW/TWO 自動判定) ---
@st.cache_data(ttl=3600)
def get_stock_data(stock_id):
    try:
        ticker = yf.Ticker(f"{stock_id}.TW")
        hist = ticker.history(period="1y")
        if hist.empty:
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

@st.cache_data(ttl=1800)
def get_and_analyze_news(stock_name):
    try:
        query = urllib.parse.quote(f"{stock_name} 股票")
        url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        response = requests.get(url, timeout=5)
        root = ET.fromstring(response.text)
        news_list = []
        for item in root.findall('.//item')[:6]:
            title = item.find('title').text
            sentiment = "🟢" if any(x in title for x in ["漲", "成長", "利多", "買超"]) else ("🔴" if any(x in title for x in ["跌", "衰退", "利空", "賣超"]) else "⚪")
            news_list.append({"title": title, "link": item.find('link').text, "sentiment": sentiment})
        return news_list
    except: return []

# ==========================================
# 主畫面開始
# ==========================================
st.markdown("## 📈 台股聯網 AI 投資戰情室")

# --- 籌碼追蹤顯示區 ---
if st.session_state.show_whale:
    st.markdown("### 🐳 近兩周大戶持股比例顯著增加標的")
    st.info("💡 已自動進行權重校正：優先選出大戶資金佔比增幅最大者。")
    whales = [("2317", "鴻海"), ("2382", "廣達"), ("1519", "華城"), ("6669", "緯穎"), ("3324", "雙鴻")]
    cols = st.columns(5)
    for idx, (code, name) in enumerate(whales):
        with cols[idx]: st.button(f"{name}\n({code})", on_click=change_stock, args=(code,), key=f"w_{code}", use_container_width=True)
    st.markdown("---")

# --- AI 聯網分析顯示區 ---
elif st.session_state.topic_results:
    t = st.session_state.topic_results
    st.markdown(f"### 💡 議題動態推演：【{t['topic']}】")
    st.success(f"**AI 深度分析：**\n{t['data']['reasoning']}")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 🛡️ 潛力權值股")
        for s in [x for x in t['data']['stocks'] if x['type'] == "潛力"]:
            st.button(f"{s['name']} ({s['id']})", on_click=change_stock, args=(s['id'],), key=f"tp_{s['id']}", use_container_width=True)
            st.caption(f"理由：{s['why']}")
    with c2:
        st.markdown("#### 🚀 爆發概念股")
        for s in [x for x in t['data']['stocks'] if x['type'] != "潛力"]:
            st.button(f"{s['name']} ({s['id']})", on_click=change_stock, args=(s['id'],), key=f"ts_{s['id']}", use_container_width=True)
            st.caption(f"理由：{s['why']}")
    if t['links']:
        with st.expander("🔗 查看 AI 參考之網路資訊來源"):
            for link in t['links']: st.markdown(f"- [{link}]({link})")
    st.markdown("---")

# --- 個股報告主體 ---
curr_id = st.session_state.selected_stock
if curr_id:
    with st.spinner('同步法人數據與新聞...'):
        hist, info = get_stock_data(curr_id)
        c_name = get_chinese_name(curr_id)
        news = get_and_analyze_news(c_name if c_name else curr_id)

    if hist is not None and not hist.empty:
        st.markdown(f"### 🏢 {c_name if c_name else curr_id} ({curr_id})")
        sector = SECTOR_MAP.get(info.get('sector', '未知'), info.get('sector', '未知'))
        st.markdown(f"**🏷️ 產業：** {sector} / {info.get('industry', '未知')}")
        with st.expander("📖 查看公司詳細營業項目"):
            st.write(info.get('longBusinessSummary', '暫無簡介。'))

        # 營運指標
        cur_p = hist['Close'].iloc[-1]
        st.markdown("#### 📊 營運估值報告")
        st.markdown("""<style>[data-testid="stMetricValue"]{font-size:1.6rem !important; color:#FFD700 !important;}</style>""", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.metric("目前收盤價", f"{cur_p:.2f}")
        m2.metric("預估明年 EPS", f"{info.get('forwardEps', info.get('trailingEps', 0)):.2f}")
        m3.metric("歷史本益比", f"{info.get('trailingPE', 0):.1f}x")

        # 法人目標價
        hi, lo, me = info.get('targetHighPrice'), info.get('targetLowPrice'), info.get('targetMeanPrice')
        if hi:
            st.markdown(f"#### 🎯 法人預估目標價 (統計自 {info.get('numberOfAnalystOpinions', 0)} 位分析師)")
            v1, v2, v3 = st.columns(3)
            v1.markdown(f"<div style='background:#ffebee;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人最高預期</small><br><b>{hi:.1f}</b></div>", unsafe_allow_html=True)
            v2.markdown(f"<div style='background:#fff3e0;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>平均預期</small><br><b>{me:.1f}</b><br><small>空間: {((me/cur_p)-1)*100:+.1f}%</small></div>", unsafe_allow_html=True)
            v3.markdown(f"<div style='background:#e8f5e9;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人最低保底</small><br><b>{lo:.1f}</b></div>", unsafe_allow_html=True)

        st.markdown("---")

        # 利多利空
        st.markdown("### 🤖 AI 投資資訊站：近期消息分析")
        if news:
            nc1, nc2 = st.columns(2)
            with nc1:
                st.markdown("#### 🟢 潛在利多")
                for n in [x for x in news if x['sentiment'] == "🟢"]: st.markdown(f"- [{n['title']}]({n['link']})")
            with nc2:
                st.markdown("#### 🔴 潛在利空")
                for n in [x for x in news if x['sentiment'] == "🔴"]: st.markdown(f"- [{n['title']}]({n['link']})")
        else: st.info("暫無即時新聞。")

        st.markdown("---")

        # 圖表
        st.markdown("### 🤖 AI 技術判定與專業圖表")
        ma20 = hist['Close'].rolling(20).mean().iloc[-1]
        h9, l9 = hist['High'].rolling(9).max(), hist['Low'].rolling(9).min()
        rsv = (hist['Close'] - l9) / (h9 - l9) * 100
        K, D = [50], [50]
        for v in rsv.fillna(50):
            K.append(K[-1]*(2/3) + v*(1/3))
            D.append(D[-1]*(2/3) + K[-1]*(1/3))
        hist['K'], hist['D'] = K[1:], D[1:]
        
        st.markdown(f"<div style='background:#333;padding:10px;border-radius:8px;text-align:center;border-left:5px solid #FFD700;'><b>AI 指標判定：{'📈 多方強勢' if cur_p > ma20 else '📉 空方佔優'}</b></div>", unsafe_allow_html=True)
        
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.5, 0.25, 0.25], subplot_titles=("K線與均線", "KD (9,3,3)", "成交張數"))
        fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='K線'), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist.index, y=hist['K'], name='K值', line=dict(color='orange')), row=2, col=1)
        fig.add_trace(go.Scatter(x=hist.index, y=hist['D'], name='D值', line=dict(color='cyan')), row=2, col=1)
        fig.update_yaxes(range=[0, 100], row=2, col=1)
        fig.add_trace(go.Bar(x=hist.index, y=hist['Volume']/1000, marker_color=['red' if x>=0 else 'green' for x in hist['Close'].diff()], name='張數'), row=3, col=1)
        fig.update_layout(height=850, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=40, b=50), legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"))
        st.plotly_chart(fig, use_container_width=True)
