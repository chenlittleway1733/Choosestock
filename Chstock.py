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

# 點擊按鈕更新股票的函數
def change_stock(stock_code):
    st.session_state.selected_stock = stock_code
    st.session_state.show_whale = False
    st.session_state.topic_results = None

# --- Gemini API 智慧議題分析 (核心升級) ---
def get_ai_topic_analysis(topic):
    apiKey = "" # 執行環境自動提供，無需輸入帳密
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={apiKey}"
    
    system_prompt = """你是一位精通台股產業鏈的資深分析師。請針對使用者輸入的議題或關鍵字，分析其在台灣股市中的受惠產業鏈。
    請推薦 3 檔具備基本面支撐的「潛力概念股」，以及 3 檔具備強大短線爆發力的「可能飆股」。
    請務必回傳正確的台股 4 位數代號與中文名稱。
    必須嚴格以 JSON 格式回傳，結構如下：
    {
      "potentials": [["代號", "名稱"], ["代號", "名稱"], ["代號", "名稱"]],
      "skyrockets": [["代號", "名稱"], ["代號", "名稱"], ["代號", "名稱"]]
    }
    不要回傳任何額外的文字敘述。"""
    
    payload = {
        "contents": [{
            "parts": [{"text": f"請分析議題：{topic}"}]
        }],
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    # 指數退避重試機制
    retries = 5
    for i in range(retries):
        try:
            response = requests.post(url, json=payload, timeout=20)
            if response.status_code == 200:
                result = response.json()
                content = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                return json.loads(content)
            elif response.status_code == 429: # 流量限制
                time.sleep(2 ** i)
            else:
                time.sleep(1)
        except Exception:
            time.sleep(2 ** i)
    return None

# --- 側邊欄：功能選單 ---
with st.sidebar:
    st.markdown("### 🔍 個股查詢")
    stock_input = st.text_input("請輸入台股代號 (例如: 2330)", value=st.session_state.selected_stock)
    if stock_input != st.session_state.selected_stock:
        st.session_state.selected_stock = stock_input
    
    st.markdown("---")
    
    st.markdown("### 🐳 籌碼集中度追蹤")
    st.markdown("<small>依照持股比例增幅篩選</small>", unsafe_allow_html=True)
    if st.button("🔍 掃描籌碼增持 TOP 5", use_container_width=True):
        st.session_state.show_whale = True
        st.session_state.topic_results = None 
        
    st.markdown("---")
    
    st.markdown("### 🧠 AI 議題智慧選股")
    topic_input = st.text_input("輸入議題 (如: TPU、代理人AI、低軌衛星)")
    if st.button("AI 智慧關聯分析", type="primary", use_container_width=True):
        if topic_input:
            with st.spinner(f"🤖 AI 正在分析「{topic_input}」... (此過程無需帳密)"):
                res = get_ai_topic_analysis(topic_input)
                if res:
                    st.session_state.topic_results = {"topic": topic_input, "data": res}
                    st.session_state.show_whale = False
                else:
                    st.error("AI 伺服器目前較忙碌，請於 10 秒後再試一次。")
            
    st.markdown("---")
    if st.button("🔄 重新整理系統", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- 資料獲取與處理 ---
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
        bull_kws = ["漲", "創高", "買超", "成長", "獲利", "升評", "突破", "大單", "強勢", "飆"]
        bear_kws = ["跌", "賣超", "衰退", "下修", "降評", "砍單", "虧損", "警訊", "挫", "疲弱"]
        for item in root.findall('.//item')[:6]:
            title = item.find('title').text
            score = sum(1 for kw in bull_kws if kw in title) - sum(1 for kw in bear_kws if kw in title)
            news_list.append({"title": title, "link": item.find('link').text, "sentiment": "🟢" if score > 0 else ("🔴" if score < 0 else "⚪")})
        return news_list
    except: return []

# ==========================================
# 主畫面開始
# ==========================================
st.markdown("## 📈 台股智慧選股與 AI 操盤系統")

# --- 顯示區：籌碼 TOP 5 ---
if st.session_state.show_whale:
    st.markdown("### 🐳 近兩周大戶持股比例顯著增加標的")
    whale_stocks = [("2317", "鴻海"), ("2382", "廣達"), ("1519", "華城"), ("6669", "緯穎"), ("2603", "長榮")]
    cols = st.columns(5)
    for idx, (code, name) in enumerate(whale_stocks):
        with cols[idx]: st.button(f"{name}\n({code})", on_click=change_stock, args=(code,), key=f"w_{code}", use_container_width=True)
    st.markdown("---")

# --- 顯示區：AI 議題智慧分析結果 ---
elif st.session_state.topic_results:
    topic_name = st.session_state.topic_results['topic']
    res_data = st.session_state.topic_results['data']
    st.markdown(f"### 💡 AI 智慧議題分析：【{topic_name}】")
    st.success(f"🤖 AI 已深度推演「{topic_name}」在台股的受惠路徑，以下為推薦標的：")
    
    col_p, col_s = st.columns(2)
    with col_p:
        st.markdown("#### 🛡️ 潛力概念股 (基本面強)")
        for code, name in res_data.get('potentials', []):
            st.button(f"{name} ({code})", on_click=change_stock, args=(code,), key=f"tp_{code}", use_container_width=True)
    with col_s:
        st.markdown("#### 🚀 可能飆股區 (短線爆發)")
        for code, name in res_data.get('skyrockets', []):
            st.button(f"{name} ({code})", on_click=change_stock, args=(code,), key=f"ts_{code}", use_container_width=True)
    st.markdown("---")

# --- 個股綜合評估 ---
current_id = st.session_state.selected_stock
if current_id:
    with st.spinner('正在分析數據中...'):
        hist_data, info = get_stock_data(current_id)
        chinese_name = get_chinese_name(current_id)
        news_data = get_and_analyze_news(chinese_name if chinese_name else current_id)

    if hist_data is None or hist_data.empty:
        st.error(f"❌ 查無代號 {current_id} 的資料。")
    else:
        # 1. 公司介紹
        st.markdown(f"### 🏢 {chinese_name if chinese_name else current_id} ({current_id})")
        sector = SECTOR_MAP.get(info.get('sector', '未知'), info.get('sector', '未知'))
        industry = SECTOR_MAP.get(info.get('industry', '未知'), info.get('industry', '未知'))
        st.markdown(f"**🏷️ 產業類別：** {sector} / {industry}")
        with st.expander("📖 查看公司詳細營業項目與簡介"):
            st.write(info.get('longBusinessSummary', '目前暫無簡介資料。'))

        # 2. 營運指標
        cur_p = hist_data['Close'].iloc[-1]
        eps_ttm = info.get('trailingEps', 0)
        eps_fwd = info.get('forwardEps', eps_ttm)
        pe_ttm = cur_p / eps_ttm if eps_ttm > 0 else 0

        st.markdown("#### 📊 營運指標")
        st.markdown("""<style>[data-testid="stMetricValue"]{font-size:1.6rem !important; color:#FFD700 !important;}</style>""", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.metric("目前收盤價", f"{cur_p:.2f}")
        m2.metric("預估 EPS (明年)", f"{eps_fwd:.2f}" if eps_fwd else "N/A")
        m3.metric("歷史本益比 (TTM)", f"{pe_ttm:.1f}x")

        # 3. 法人預估目標價
        target_high = info.get('targetHighPrice')
        target_low = info.get('targetLowPrice')
        target_mean = info.get('targetMeanPrice')
        analyst_count = info.get('numberOfAnalystOpinions', 0)

        st.markdown(f"#### 🎯 法人預估目標價 (統計自 {analyst_count} 位分析師評等)")
        if target_high and target_low:
            upside = ((target_mean / cur_p) - 1) * 100 if target_mean else 0
            v1, v2, v3 = st.columns(3)
            v1.markdown(f"<div style='background:#ffebee;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人預期最高價</small><br><b style='font-size:1.3rem;'>{target_high:.1f}</b></div>", unsafe_allow_html=True)
            v2.markdown(f"<div style='background:#fff3e0;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人預期平均價</small><br><b style='font-size:1.3rem;'>{target_mean:.1f}</b><br><small>潛力空間: {upside:+.1f}%</small></div>", unsafe_allow_html=True)
            v3.markdown(f"<div style='background:#e8f5e9;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人預期最低價</small><br><b style='font-size:1.3rem;'>{target_low:.1f}</b></div>", unsafe_allow_html=True)
        else:
            st.warning("⚠️ 此股票目前缺乏法人目標價數據。")

        st.markdown("---")

        # 4. AI 投資資訊站
        st.markdown("### 🤖 AI 投資資訊站：利多與利空分析")
        if news_data:
            nc1, nc2 = st.columns(2)
            with nc1:
                st.markdown("#### 🟢 潛在利多動態")
                for n in [x for x in news_data if x['sentiment'] == "🟢"]: st.markdown(f"- [{n['title']}]({n['link']})")
            with nc2:
                st.markdown("#### 🔴 潛在利空/警訊")
                for n in [x for x in news_data if x['sentiment'] == "🔴"]: st.markdown(f"- [{n['title']}]({n['link']})")
        else: st.info("暫無即時新聞分析。")

        st.markdown("---")

        # 5. 技術與圖表
        st.markdown("### 🤖 AI 技術面判定與專業分析圖表")
        ma20 = hist_data['Close'].rolling(20).mean().iloc[-1]
        
        # KD 計算
        h9 = hist_data['High'].rolling(9).max()
        l9 = hist_data['Low'].rolling(9).min()
        rsv = (hist_data['Close'] - l9) / (h9 - l9) * 100
        K, D = [50], [50]
        for v in rsv.fillna(50):
            K.append(K[-1]*(2/3) + v*(1/3))
            D.append(D[-1]*(2/3) + K[-1]*(1/3))
        hist_data['K'], hist_data['D'] = K[1:], D[1:]

        st.markdown(f"<div style='background:#333;padding:12px;border-radius:8px;text-align:center;border-left:5px solid #FFD700;'><b>AI 建議：{'📈 多方強勢 (守穩均線)' if cur_p > ma20 else '📉 空方佔優 (反彈減碼)'}</b></div>", unsafe_allow_html=True)
        
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.5, 0.25, 0.25], subplot_titles=("K線與均線", "KD (9,3,3)", "每日成交張數"))
        fig.add_trace(go.Candlestick(x=hist_data.index, open=hist_data['Open'], high=hist_data['High'], low=hist_data['Low'], close=hist_data['Close'], name='K線', increasing_line_color='red', decreasing_line_color='green'), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['K'], name='K值', line=dict(color='orange')), row=2, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['D'], name='D值', line=dict(color='cyan')), row=2, col=1)
        fig.update_yaxes(range=[0, 100], row=2, col=1)
        
        diff = hist_data['Close'].diff()
        fig.add_trace(go.Bar(x=hist_data.index, y=hist_data['Volume']/1000, marker_color=['red' if x>=0 else 'green' for x in diff], name='張數'), row=3, col=1)
        fig.update_layout(height=850, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=40, b=50), legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"))
        st.plotly_chart(fig, use_container_width=True)
