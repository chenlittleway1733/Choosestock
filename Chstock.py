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

def change_stock(stock_code):
    st.session_state.selected_stock = stock_code
    # 點選股票後清空搜尋結果，讓畫面聚焦
    st.session_state.topic_results = None

# --- Gemini 2.5 聯網分析引擎 (移除內建知識庫，全面動態分析) ---
def get_real_ai_analysis(topic):
    apiKey = "" # 執行環境自動提供
    # 使用最新支援 Google Search 的模型
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={apiKey}"
    
    system_prompt = """你是一位精通台股與全球半導體、AI 產業鏈的資深投資長。
    請針對使用者輸入的議題，結合最新的市場趨勢與搜尋結果，進行深度的產業鏈邏輯推演。
    
    你的任務：
    1. 推薦 3 檔受惠最直接的「潛力權值股」與 3 檔具備爆發力的「中小型概念股」。
    2. 為每檔股票提供簡短的「受惠邏輯分析」。
    3. 嚴格以 JSON 格式回傳，格式如下：
    {
      "reasoning": "整體產業趨勢的深度分析簡述",
      "stocks": [
        {"id": "代號", "name": "名稱", "type": "潛力", "why": "具體受惠原因"},
        ...
      ]
    }
    請務必確保台股代號為 4 位數字。回傳內容僅限 JSON，不要有其他文字。"""
    
    payload = {
        "contents": [{"parts": [{"text": f"請深度分析此議題在台股的佈局機會：{topic}"}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "tools": [{"google_search": {}}], # 開啟 Google Search 功能
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    # 指數退避重試
    for i in range(5):
        try:
            response = requests.post(url, json=payload, timeout=25)
            if response.status_code == 200:
                res_json = response.json()
                content = res_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                # 提取聯網來源連結
                sources = res_json.get('candidates', [{}])[0].get('groundingMetadata', {}).get('groundingAttributions', [])
                links = [s.get('web', {}).get('uri') for s in sources if s.get('web', {}).get('uri')]
                return json.loads(content), list(set(links))
            elif response.status_code == 429:
                time.sleep(2 ** i)
        except:
            time.sleep(1)
    return None, []

# --- 側邊欄 ---
with st.sidebar:
    st.markdown("### 🔍 個股查詢")
    stock_input = st.text_input("請輸入台股代號 (例如: 2330)", value=st.session_state.selected_stock)
    if stock_input != st.session_state.selected_stock:
        st.session_state.selected_stock = stock_input
    
    st.markdown("---")
    
    st.markdown("### 🧠 AI 聯網議題選股 (Google Search)")
    st.markdown("<small>輸入時事議題，AI 將即時搜尋並推演產業鏈</small>", unsafe_allow_html=True)
    topic_q = st.text_input("輸入議題 (如: 矽光子、Agent AI、B300)")
    if st.button("AI 實時分析", type="primary", use_container_width=True):
        if topic_q:
            with st.spinner(f"🤖 AI 正在聯網搜尋並分析「{topic_q}」..."):
                data, links = get_real_ai_analysis(topic_q)
                if data:
                    st.session_state.topic_results = {"topic": topic_q, "data": data, "links": links}
                else:
                    st.error("AI 引擎忙碌中，請稍後再試。")
    
    st.markdown("---")
    if st.button("🔄 重整系統快取", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- 資料獲取函數 ---
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

# ==========================================
# 主畫面開始
# ==========================================
st.markdown("## 📈 台股聯網 AI 投資戰情室")

# --- AI 聯網分析結果顯示區 ---
if st.session_state.topic_results:
    t_res = st.session_state.topic_results
    st.markdown(f"### 💡 議題動態推演：【{t_res['topic']}】")
    
    with st.container():
        st.info(f"**AI 深度分析邏輯：**\n{t_res['data']['reasoning']}")
        
        # 顯示推薦股票
        p_stocks = [s for s in t_res['data']['stocks'] if s['type'] == "潛力"]
        s_stocks = [s for s in t_res['data']['stocks'] if s['type'] != "潛力"]
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 🛡️ 潛力權值股")
            for s in p_stocks:
                st.button(f"{s['name']} ({s['id']})", on_click=change_stock, args=(s['id'],), key=f"btn_{s['id']}", use_container_width=True)
                st.caption(f"受惠：{s['why']}")
        with c2:
            st.markdown("#### 🚀 爆發概念股")
            for s in s_stocks:
                st.button(f"{s['name']} ({s['id']})", on_click=change_stock, args=(s['id'],), key=f"btn_{s['id']}", use_container_width=True)
                st.caption(f"受惠：{s['why']}")
                
        # 顯示參考連結
        if t_res['links']:
            with st.expander("🔗 查看 AI 參考之網路資訊來源"):
                for link in t_res['links']:
                    st.markdown(f"- [{link}]({link})")
    st.markdown("---")

# --- 個股綜合報告主體 ---
current_id = st.session_state.selected_stock
if current_id:
    with st.spinner('同步法人與技術數據中...'):
        hist_data, info = get_stock_data(current_id)
        chinese_name = get_chinese_name(current_id)

    if hist_data is not None and not hist_data.empty:
        # 1. 基本資訊與公司簡介
        st.markdown(f"### 🏢 {chinese_name if chinese_name else current_id} ({current_id})")
        sector = SECTOR_MAP.get(info.get('sector', '未知'), info.get('sector', '未知'))
        industry = SECTOR_MAP.get(info.get('industry', '未知'), info.get('industry', '未知'))
        st.markdown(f"**🏷️ 產業類別：** {sector} / {industry}")
        with st.expander("📖 查看公司詳細營業項目與簡介"):
            st.write(info.get('longBusinessSummary', '目前暫無簡介資料。'))

        # 2. 營運與法人預估價
        cur_p = hist_data['Close'].iloc[-1]
        eps_fwd = info.get('forwardEps', info.get('trailingEps', 0))
        target_high = info.get('targetHighPrice')
        target_low = info.get('targetLowPrice')
        target_mean = info.get('targetMeanPrice')

        st.markdown("#### 📊 營運估值報告")
        st.markdown("""<style>[data-testid="stMetricValue"]{font-size:1.6rem !important; color:#FFD700 !important;}</style>""", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.metric("目前收盤價", f"{cur_p:.2f}")
        m2.metric("預估明年 EPS", f"{eps_fwd:.2f}" if eps_fwd else "N/A")
        m3.metric("歷史本益比", f"{info.get('trailingPE', 0):.1f}x")

        # 顯示法人目標價區塊
        if target_high:
            st.markdown(f"#### 🎯 法人預估目標價 (統計自 {info.get('numberOfAnalystOpinions', 0)} 位分析師)")
            v1, v2, v3 = st.columns(3)
            v1.markdown(f"<div style='background:#ffebee;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人預期最高價</small><br><b style='font-size:1.3rem;'>{target_high:.1f}</b></div>", unsafe_allow_html=True)
            upside = ((target_mean / cur_p) - 1) * 100 if target_mean else 0
            v2.markdown(f"<div style='background:#fff3e0;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人預期平均價</small><br><b style='font-size:1.3rem;'>{target_mean:.1f}</b><br><small>空間: {upside:+.1f}%</small></div>", unsafe_allow_html=True)
            v3.markdown(f"<div style='background:#e8f5e9;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人預期最低價</small><br><b style='font-size:1.3rem;'>{target_low:.1f}</b></div>", unsafe_allow_html=True)

        st.markdown("---")

        # 3. 技術判定與圖表
        st.markdown("### 🤖 AI 技術面判定與專業圖表")
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

        ai_status = "📈 多方強勢 (守穩均線)" if cur_p > ma20 else "📉 空方佔優 (建議減碼)"
        st.markdown(f"<div style='background:#333;padding:10px;border-radius:8px;text-align:center;border-left:5px solid #FFD700;'><b>AI 指標判定：{ai_status}</b></div>", unsafe_allow_html=True)
        
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.5, 0.25, 0.25], subplot_titles=("K線", "KD (9,3,3)", "成交張數"))
        fig.add_trace(go.Candlestick(x=hist_data.index, open=hist_data['Open'], high=hist_data['High'], low=hist_data['Low'], close=hist_data['Close'], name='K線', increasing_line_color='red', decreasing_line_color='green'), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['K'], name='K值', line=dict(color='orange')), row=2, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['D'], name='D值', line=dict(color='cyan')), row=2, col=1)
        fig.update_yaxes(range=[0, 100], row=2, col=1)
        fig.add_trace(go.Bar(x=hist_data.index, y=hist_data['Volume']/1000, marker_color=['red' if x>=0 else 'green' for x in hist_data['Close'].diff()], name='張數'), row=3, col=1)
        fig.update_layout(height=850, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=40, b=50), legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"))
        st.plotly_chart(fig, use_container_width=True)
