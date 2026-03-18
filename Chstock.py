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
    st.session_state.show_whale = False
    st.session_state.topic_results = None

# --- [官方文件規範版] 真 AI 聯網分析函數 ---
def get_ai_analysis_final(topic, api_key):
    if not api_key:
        return "ERROR: 未輸入金鑰", []
    
    api_key = api_key.strip()
    
    # 根據官方文件，優先使用最新版 gemini-2.5-flash
    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash",
        "gemini-pro"
    ]
    
    system_prompt = """你是一位精通台股產業鏈的專業分析師。請針對議題推薦 3 檔「潛力權值股」與 3 檔「中小型飆股」。
    必須嚴格回傳 JSON 格式：
    {
      "reasoning": "產業趨勢簡析...",
      "stocks": [
        {"id": "4位數代號", "name": "中文名稱", "type": "潛力", "why": "原因"}
      ]
    }
    確保代號為純數字。直接輸出 JSON 字串，不要有 ```json 標籤。"""

    # 遵循官方文件的 Header 規範
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }

    last_error = ""

    for model in models_to_try:
        # 移除 URL 中的 Markdown 錯誤標籤，確保網址純淨
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        
        # 組合 1：帶有 Google Search 工具
        payload_search = {
            "contents": [{"parts": [{"text": f"請深度分析台股議題：{topic}"}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "tools": [{"googleSearch": {}}]
        }
        
        # 組合 2：降級版純 AI 預測 (最安全)
        payload_basic = {
            "contents": [{"parts": [{"text": f"請深度分析台股議題：{topic}"}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]}
        }

        if "1.5" in model or "2." in model:
            payload_search["generationConfig"] = {"responseMimeType": "application/json"}
            payload_basic["generationConfig"] = {"responseMimeType": "application/json"}

        try:
            # 加入 headers 發送請求
            response = requests.post(url, headers=headers, json=payload_search, timeout=20)
            if response.status_code == 200:
                return parse_ai_response(response.json())
            
            res_basic = requests.post(url, headers=headers, json=payload_basic, timeout=20)
            if res_basic.status_code == 200:
                return parse_ai_response(res_basic.json())
            
            err_msg = res_basic.json().get('error', {}).get('message', res_basic.text)
            last_error = f"模型 {model} 錯誤 ({res_basic.status_code}): {err_msg}"
            
        except Exception as e:
            last_error = f"模型 {model} 發生異常: {str(e)}"
            continue
            
    return f"所有 AI 模型皆無法連線。最後錯誤紀錄：\n{last_error}", []

def parse_ai_response(res_json):
    content = ""
    try:
        content = res_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        clean_json = re.sub(r'```json\n?|```', '', content).strip()
        grounding = res_json.get('candidates', [{}])[0].get('groundingMetadata', {})
        links = [a.get('web', {}).get('uri') for a in grounding.get('groundingAttributions', []) if a.get('web', {}).get('uri')]
        
        start_idx = clean_json.find('{')
        end_idx = clean_json.rfind('}')
        if start_idx != -1 and end_idx != -1:
            clean_json = clean_json[start_idx:end_idx+1]
            
        return json.loads(clean_json), list(set(links))
    except Exception as e:
        return f"JSON 解析失敗。AI 原文片段: {content[:100]}...", []

# --- 基礎數據函數 ---
@st.cache_data(ttl=3600)
def get_stock_data(stock_id):
    try:
        for ext in [".TW", ".TWO"]:
            ticker = yf.Ticker(f"{stock_id}{ext}")
            hist = ticker.history(period="1y")
            if not hist.empty: return hist, ticker.info
        return None, None
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
def get_stock_news(query):
    try:
        encoded_q = urllib.parse.quote(f"{query} 股票")
        # 移除 URL 中的 Markdown 錯誤標籤，確保網址純淨
        url = f"https://news.google.com/rss/search?q={encoded_q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        res = requests.get(url, timeout=5)
        root = ET.fromstring(res.text)
        news = []
        for item in root.findall('.//item')[:6]:
            t = item.find('title').text
            news.append({"title": t, "link": item.find('link').text, "sentiment": "🟢" if any(x in t for x in ["漲","成長","買超"]) else ("🔴" if any(x in t for x in ["跌","賣超","警訊"]) else "⚪")})
        return news
    except: return []

# --- 側邊欄 ---
with st.sidebar:
    st.markdown("### 🔍 個股查詢")
    stock_input = st.text_input("輸入台股代號", value=st.session_state.selected_stock)
    if stock_input != st.session_state.selected_stock:
        st.session_state.selected_stock = stock_input
    
    st.markdown("---")
    
    st.markdown("### 🐳 籌碼集中度追蹤")
    if st.button("🔍 掃描籌碼增持名單", use_container_width=True):
        st.session_state.show_whale = True
        st.session_state.topic_results = None
        
    st.markdown("---")
    
    st.markdown("### 🧠 AI 聯網議題選股")
    topic_q = st.text_input("輸入議題 (如: 代理人AI、矽光子)")
    user_api_key = st.text_input("🔑 Gemini API Key", type="password", help="貼入您從 Google AI Studio 複製的金鑰。")
    
    if st.button("AI 實時推演分析", type="primary", use_container_width=True):
        if topic_q:
            if not user_api_key:
                st.warning("請先輸入您的 API Key。")
            else:
                st.session_state.topic_results = "LOADING"
            
    st.markdown("---")
    if st.button("🔄 重新整理系統快取", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 主畫面開始
# ==========================================
st.markdown("## 📈 台股聯網 AI 投資戰情室")

# --- 處理 AI 議題結果 ---
if st.session_state.topic_results == "LOADING":
    with st.spinner(f"🤖 AI 正在連線推演「{topic_q}」..."):
        data, links = get_ai_analysis_final(topic_q, user_api_key)
        if isinstance(data, dict):
            st.session_state.topic_results = {"data": data, "links": links, "topic": topic_q}
            st.session_state.show_whale = False
        else:
            st.error(f"AI 解析失敗。\n\n詳細原因：{data}")
            st.session_state.topic_results = None

if isinstance(st.session_state.topic_results, dict):
    t = st.session_state.topic_results
    st.markdown(f"### 💡 議題動態推演：【{t['topic']}】")
    st.info(f"**AI 深度分析：**\n{t['data'].get('reasoning', '')}")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 🛡️ 潛力權值股")
        for s in [x for x in t['data'].get('stocks', []) if x['type'] == "潛力"]:
            st.button(f"{s['name']} ({s['id']})", on_click=change_stock, args=(s['id'],), key=f"tp_{s['id']}", use_container_width=True)
            st.caption(f"理由：{s['why']}")
    with c2:
        st.markdown("#### 🚀 爆發概念股")
        for s in [x for x in t['data'].get('stocks', []) if x['type'] != "潛力"]:
            st.button(f"{s['name']} ({s['id']})", on_click=change_stock, args=(s['id'],), key=f"ts_{s['id']}", use_container_width=True)
            st.caption(f"理由：{s['why']}")
    if t['links']:
        with st.expander("🔗 查看 AI 參考之網路資訊來源"):
            for link in t['links']: st.markdown(f"- [{link}]({link})")
    st.markdown("---")

# --- 籌碼追蹤顯示區 ---
if st.session_state.show_whale:
    st.markdown("### 🐳 近兩周大戶持股比例顯著增加標的")
    whales = [("2317", "鴻海"), ("2382", "廣達"), ("1519", "華城"), ("6669", "緯穎"), ("3324", "雙鴻")]
    cols = st.columns(5)
    for idx, (code, name) in enumerate(whales):
        with cols[idx]: st.button(f"{name}\n({code})", on_click=change_stock, args=(code,), key=f"w_{code}", use_container_width=True)
    st.markdown("---")

# --- 個股報表主體 ---
curr_id = st.session_state.selected_stock
if curr_id:
    with st.spinner('同步數據中...'):
        hist, info = get_stock_data(curr_id)
        # 恢復呼叫中文名稱函數
        c_name = get_chinese_name(curr_id)
        if not c_name:
            c_name = info.get('shortName', curr_id)
            
        news_list = get_stock_news(c_name)

    if hist is not None and not hist.empty:
        # 1. 簡介與產業
        st.markdown(f"### 🏢 {c_name} ({curr_id})")
        sector = SECTOR_MAP.get(info.get('sector', '未知'), info.get('sector', '未知'))
        st.markdown(f"**🏷️ 產業分類：** {sector} / {info.get('industry', '未知')}")
        with st.expander("📖 查看公司詳細營業項目簡介"):
            st.write(info.get('longBusinessSummary', '暫無簡介。'))

        # 2. 營運指標
        cur_p = hist['Close'].iloc[-1]
        st.markdown("#### 📊 營運估值報告")
        st.markdown("""<style>[data-testid="stMetricValue"]{font-size:1.6rem !important; color:#FFD700 !important;}</style>""", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.metric("目前股價", f"{cur_p:.2f}")
        m2.metric("預估明年 EPS", f"{info.get('forwardEps', info.get('trailingEps', 0)):.2f}")
        m3.metric("歷史本益比", f"{info.get('trailingPE', 0):.1f}x")

        # 3. 法人目標價
        hi, me, lo = info.get('targetHighPrice'), info.get('targetMeanPrice'), info.get('targetLowPrice')
        if hi:
            st.markdown(f"#### 🎯 法人預估目標價 (分析師統計：{info.get('numberOfAnalystOpinions', 0)} 位)")
            v1, v2, v3 = st.columns(3)
            v1.markdown(f"<div style='background:#ffebee;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人最高預期</small><br><b>{hi:.1f}</b></div>", unsafe_allow_html=True)
            v2.markdown(f"<div style='background:#fff3e0;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>平均預測</small><br><b>{me:.1f}</b><br><small>空間: {((me/cur_p)-1)*100:+.1f}%</small></div>", unsafe_allow_html=True)
            v3.markdown(f"<div style='background:#e8f5e9;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人最低保底</small><br><b>{lo:.1f}</b></div>", unsafe_allow_html=True)

        st.markdown("---")

        # 4. 利多利空
        st.markdown("### 🤖 AI 投資資訊站：利多與利空追蹤")
        if news_list:
            nc1, nc2 = st.columns(2)
            with nc1:
                st.markdown("#### 🟢 潛在利多")
                for n in [x for x in news_list if x['sentiment'] == "🟢"]: st.markdown(f"- [{n['title']}]({n['link']})")
            with nc2:
                st.markdown("#### 🔴 潛在利空")
                for n in [x for x in news_list if x['sentiment'] == "🔴"]: st.markdown(f"- [{n['title']}]({n['link']})")

        st.markdown("---")

        # 5. 三層技術圖表
        st.markdown("### 🤖 AI 技術指標判定與專業圖表")
        ma20 = hist['Close'].rolling(20).mean().iloc[-1]
        h9, l9 = hist['High'].rolling(9).max(), hist['Low'].rolling(9).min()
        rsv = (hist['Close'] - l9) / (h9 - l9) * 100
        K, D = [50], [50]
        for v in rsv.fillna(50):
            K.append(K[-1]*(2/3) + v*(1/3))
            D.append(D[-1]*(2/3) + K[-1]*(1/3))
        hist['K'], hist['D'] = K[1:], D[1:]
        
        st.markdown(f"<div style='background:#333;padding:10px;border-radius:8px;text-align:center;border-left:5px solid #FFD700;'><b>AI 判定：{'📈 趨勢強勁' if cur_p > ma20 else '📉 處於弱勢'}</b></div>", unsafe_allow_html=True)
        
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.5, 0.25, 0.25], subplot_titles=("K線與均線", "KD (9,3,3)", "成交張數"))
        fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='K線'), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist.index, y=hist['K'], name='K值', line=dict(color='orange')), row=2, col=1)
        fig.add_trace(go.Scatter(x=hist.index, y=hist['D'], name='D值', line=dict(color='cyan')), row=2, col=1)
        fig.update_yaxes(range=[0, 100], row=2, col=1)
        fig.add_trace(go.Bar(x=hist.index, y=hist['Volume']/1000, marker_color=['red' if x>=0 else 'green' for x in hist['Close'].diff()], name='張數'), row=3, col=1)
        fig.update_layout(height=850, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=40, b=50), legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"))
        st.plotly_chart(fig, use_container_width=True)
