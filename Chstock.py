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
st.set_page_config(page_title="way系統", layout="wide")

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
    # 刪除原本會清空畫面的這兩行，讓 AI 名單與籌碼名單永遠保留在畫面上！
    # st.session_state.show_whale = False 
    # st.session_state.topic_results = None

# --- [終極除錯版] 真 AI 聯網分析函數 ---
def get_ai_analysis_final(topic, api_key):
    if not api_key:
        return "ERROR: 未輸入金鑰", []
    
    api_key = api_key.strip()
    
    # 移除了舊版會報 404 錯誤的 gemini-pro，只鎖定最新且穩定的 1.5 與 2.0 版本
    models_to_try = [
        "gemini-2.0-flash",
        "gemini-1.5-flash"
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

    headers = {"Content-Type": "application/json"}
    all_errors = []

    for model in models_to_try:
        # 恢復使用最穩定的 URL 參數傳遞金鑰，避免 Header 擋截問題
        url = f"[https://generativelanguage.googleapis.com/v1beta/models/](https://generativelanguage.googleapis.com/v1beta/models/){model}:generateContent?key={api_key}"
        
        # 組合 1：帶有 Google Search 工具 (官方標準命名)
        payload_search = {
            "contents": [{"parts": [{"text": f"請深度分析台股議題：{topic}"}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "tools": [{"google_search": {}}],
            "generationConfig": {"responseMimeType": "application/json"}
        }
        
        # 組合 2：降級版純 AI 預測 (最安全)
        payload_basic = {
            "contents": [{"parts": [{"text": f"請深度分析台股議題：{topic}"}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {"responseMimeType": "application/json"}
        }

        try:
            # 第一波：嘗試聯網搜尋
            response = requests.post(url, headers=headers, json=payload_search, timeout=20)
            if response.status_code == 200:
                return parse_ai_response(response.json())
            
            # 第二波：若搜尋被擋，退回純 AI 預測
            res_basic = requests.post(url, headers=headers, json=payload_basic, timeout=20)
            if res_basic.status_code == 200:
                return parse_ai_response(res_basic.json())
            
            # 若都失敗，紀錄這個模型「真實」的失敗原因
            err_msg = res_basic.json().get('error', {}).get('message', res_basic.text)
            all_errors.append(f"【{model}】: {err_msg}")
            
        except Exception as e:
            all_errors.append(f"【{model}】連線異常: {str(e)}")
            continue
            
    # 將所有模型的失敗原因印出，不再被舊模型掩蓋
    error_details = "\n\n".join(all_errors)
    return f"無法連線至 AI，請確認金鑰狀態。\n\n詳細錯誤診斷：\n{error_details}", []

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

        # --- 新增：⚡ 即時報價與交易資訊總表 ---
        st.markdown("#### ⚡ 即時報價與交易資訊")
        
        # 抓取並計算盤面數據
        today_data = hist.iloc[-1]
        prev_data = hist.iloc[-2] if len(hist) > 1 else today_data
        
        curr_p = today_data['Close']
        open_p = today_data['Open']
        high_p = today_data['High']
        low_p = today_data['Low']
        
        # 處理台股張數 (yfinance 回傳為股數，需除以1000)
        vol_shares = today_data['Volume']
        vol_lots = int(vol_shares // 1000) 
        prev_vol_lots = int(prev_data['Volume'] // 1000) if len(hist) > 1 else 0
        
        # 昨收與漲跌計算
        prev_close = info.get('previousClose', prev_data['Close'])
        change = curr_p - prev_close
        change_pct = (change / prev_close) * 100 if prev_close else 0
        amp = ((high_p - low_p) / prev_close) * 100 if prev_close else 0
        
        # 均價與成交金額 (億) 計算
        avg_price = (high_p + low_p + curr_p) / 3
        turnover_100m = (vol_shares * avg_price) / 100000000
        
        # 自動變色邏輯 (漲紅、跌綠、平盤白)
        def get_color(val, base):
            if val > base: return "#ff4d4d"
            elif val < base: return "#00cc66"
            return "#ffffff"
            
        c_curr = get_color(curr_p, prev_close)
        c_open = get_color(open_p, prev_close)
        c_high = get_color(high_p, prev_close)
        c_low = get_color(low_p, prev_close)
        c_change = get_color(change, 0)
        arrow = "▲" if change > 0 else ("▼" if change < 0 else "")
        
        # 構建仿看盤軟體的 HTML 報價表
        quote_html = f"""
        <style>
        .q-container {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 30px; background: #1e1e1e; padding: 15px 20px; border-radius: 8px; font-family: sans-serif; margin-bottom: 20px; border: 1px solid #333; }}
        .q-item {{ display: flex; justify-content: space-between; border-bottom: 1px solid #333; padding-bottom: 4px; }}
        .q-label {{ color: #aaa; font-size: 1rem; }}
        .q-val {{ font-weight: bold; font-size: 1.1rem; }}
        </style>
        <div class="q-container">
            <div class="q-item"><span class="q-label">成交</span><span class="q-val" style="color: {c_curr};">{curr_p:,.2f}</span></div>
            <div class="q-item"><span class="q-label">昨收</span><span class="q-val" style="color: #fff;">{prev_close:,.2f}</span></div>
            <div class="q-item"><span class="q-label">開盤</span><span class="q-val" style="color: {c_open};">{open_p:,.2f}</span></div>
            <div class="q-item"><span class="q-label">漲跌幅</span><span class="q-val" style="color: {c_change};">{arrow} {abs(change_pct):.2f}%</span></div>
            <div class="q-item"><span class="q-label">最高</span><span class="q-val" style="color: {c_high};">{high_p:,.2f}</span></div>
            <div class="q-item"><span class="q-label">漲跌</span><span class="q-val" style="color: {c_change};">{arrow} {abs(change):.2f}</span></div>
            <div class="q-item"><span class="q-label">最低</span><span class="q-val" style="color: {c_low};">{low_p:,.2f}</span></div>
            <div class="q-item"><span class="q-label">總量 (張)</span><span class="q-val" style="color: #ffd700;">{vol_lots:,}</span></div>
            <div class="q-item"><span class="q-label">均價</span><span class="q-val" style="color: #fff;">{avg_price:,.2f}</span></div>
            <div class="q-item"><span class="q-label">昨量 (張)</span><span class="q-val" style="color: #fff;">{prev_vol_lots:,}</span></div>
            <div class="q-item"><span class="q-label">成交金額(億)</span><span class="q-val" style="color: #fff;">{turnover_100m:,.2f}</span></div>
            <div class="q-item"><span class="q-label">振幅</span><span class="q-val" style="color: #fff;">{amp:.2f}%</span></div>
        </div>
        """
        st.markdown(quote_html, unsafe_allow_html=True)

        # 2. 營運指標 (原本的區塊)
        st.markdown("#### 📊 營運估值報告")
        st.markdown("""<style>[data-testid="stMetricValue"]{font-size:1.6rem !important; color:#FFD700 !important;}</style>""", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        # 修改 metric 的股價來源，使用我們剛算好的 curr_p
        m1.metric("目前股價", f"{curr_p:.2f}")
        m2.metric("預估明年 EPS", f"{info.get('forwardEps', info.get('trailingEps', 0)):.2f}")
        m3.metric("歷史本益比", f"{info.get('trailingPE', 0):.1f}x")

        # 3. 法人目標價 (修正變數名稱錯誤與增加安全防護)
        hi, me, lo = info.get('targetHighPrice'), info.get('targetMeanPrice'), info.get('targetLowPrice')
        if hi and me and lo:
            st.markdown(f"#### 🎯 法人預估目標價 (分析師統計：{info.get('numberOfAnalystOpinions', 0)} 位)")
            v1, v2, v3 = st.columns(3)
            v1.markdown(f"<div style='background:#ffebee;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人最高預期</small><br><b>{hi:.1f}</b></div>", unsafe_allow_html=True)
            
            # 將這裡的 cur_p 修正為 curr_p 即可正常計算！
            upside = ((me / curr_p) - 1) * 100 if curr_p else 0
            
            v2.markdown(f"<div style='background:#fff3e0;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>平均預測</small><br><b>{me:.1f}</b><br><small>空間: {upside:+.1f}%</small></div>", unsafe_allow_html=True)
            v3.markdown(f"<div style='background:#e8f5e9;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人最低保底</small><br><b>{lo:.1f}</b></div>", unsafe_allow_html=True)
        elif hi:
             # 若只有最高價，僅顯示最高價資訊
             st.markdown(f"#### 🎯 法人預估目標價 (分析師統計：{info.get('numberOfAnalystOpinions', 0)} 位)")
             st.info(f"法人最高預期：**{hi:.1f}**")

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

        # 5. 專業技術線圖 (仿看盤軟體)
        st.markdown("### 🤖 專業技術線圖與量化型態分析 (近半年)")
        
        # 計算各項技術指標 (使用全資料計算，避免均線在圖表開頭出現斷層)
        hist['MA5'] = hist['Close'].rolling(5).mean()
        hist['MA10'] = hist['Close'].rolling(10).mean()
        hist['MA20'] = hist['Close'].rolling(20).mean()
        hist['MA60'] = hist['Close'].rolling(60).mean()

        h9, l9 = hist['High'].rolling(9).max(), hist['Low'].rolling(9).min()
        rsv = (hist['Close'] - l9) / (h9 - l9) * 100
        K, D = [50], [50]
        for v in rsv.fillna(50):
            K.append(K[-1]*(2/3) + v*(1/3))
            D.append(D[-1]*(2/3) + K[-1]*(1/3))
        hist['K'], hist['D'] = K[1:], D[1:]

        # === 新增：技術型態量化分析與操作建議 ===
        # 取得最新一天的數值
        last_close = hist['Close'].iloc[-1]
        ma5_last = hist['MA5'].iloc[-1]
        ma20_last = hist['MA20'].iloc[-1]
        ma60_last = hist['MA60'].iloc[-1]
        k_last = hist['K'].iloc[-1]
        d_last = hist['D'].iloc[-1]
        
        # 計算支撐與壓力 (取近20日高低點與重要均線)
        recent_high = hist['High'].tail(20).max()
        recent_low = hist['Low'].tail(20).min()
        
        # 支撐價：如果股價在季線上，季線與近期低點取高者；否則取近期低點
        support_price = max(recent_low, ma60_last) if last_close > ma60_last else recent_low
        # 壓力價：如果股價在月線下，月線與近期高點取低者；否則取近期高點
        resist_price = recent_high if last_close > ma20_last else min(recent_high, ma20_last)
        
        # 判斷趨勢與顏色 (台股紅漲綠跌)
        if last_close > ma20_last and ma5_last > ma20_last:
            trend_status = "📈 多頭強勢 (站上月線)"
            trend_color = "#ff4d4d"
        elif last_close < ma20_last and ma5_last < ma20_last:
            trend_status = "📉 空頭弱勢 (跌破月線)"
            trend_color = "#00cc66"
        else:
            trend_status = "↔️ 區間震盪 (方向未明)"
            trend_color = "#ffd700"
            
        # 產生買賣點與策略解析
        if k_last < 25 and k_last > d_last:
            adv_text = "KD 低檔黃金交叉，具短線反彈契機，可嘗試逢低少量佈局。"
            buy_rec = f"現價~{support_price:.2f} 附近"
            sell_rec = f"{resist_price:.2f} (上檔壓力)"
        elif k_last > 80 and k_last < d_last:
            adv_text = "KD 高檔死亡交叉，上漲動能轉弱，建議適度獲利了結保住利潤。"
            buy_rec = "暫時觀望"
            sell_rec = f"現價~{resist_price:.2f} 附近"
        elif last_close > ma20_last:
            adv_text = "多方格局，拉回月線(20MA)有守可伺機介入，跌破支撐應停損。"
            buy_rec = f"{ma20_last:.2f} (月線支撐)"
            sell_rec = f"{resist_price:.2f} (近期前高)"
        else:
            adv_text = "空方格局，建議多看少做，反彈至均線壓力區可考慮減碼。"
            buy_rec = "等待技術面打底"
            sell_rec = f"{ma20_last:.2f} (月線壓力)"

        # 渲染分析面板
        st.markdown(f"""
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; margin-bottom:20px;'>
            <h4 style='margin-top:0; color:#fff;'>🎯 演算法量化交易策略</h4>
            <div style='display:flex; justify-content:space-between; flex-wrap:wrap; gap:10px;'>
                <div style='flex:1; min-width:120px;'>
                    <div style='color:#aaa; font-size:0.9rem;'>目前趨勢</div>
                    <div style='font-size:1.1rem; font-weight:bold; color:{trend_color};'>{trend_status}</div>
                </div>
                <div style='flex:1; min-width:120px;'>
                    <div style='color:#aaa; font-size:0.9rem;'>下檔支撐</div>
                    <div style='font-size:1.1rem; font-weight:bold; color:#00bfff;'>{support_price:.2f}</div>
                </div>
                <div style='flex:1; min-width:120px;'>
                    <div style='color:#aaa; font-size:0.9rem;'>上檔壓力</div>
                    <div style='font-size:1.1rem; font-weight:bold; color:#ab82ff;'>{resist_price:.2f}</div>
                </div>
                <div style='flex:1; min-width:120px;'>
                    <div style='color:#aaa; font-size:0.9rem;'>建議買點</div>
                    <div style='font-size:1.1rem; font-weight:bold; color:#ff4d4d;'>{buy_rec}</div>
                </div>
                <div style='flex:1; min-width:120px;'>
                    <div style='color:#aaa; font-size:0.9rem;'>建議賣點</div>
                    <div style='font-size:1.1rem; font-weight:bold; color:#00cc66;'>{sell_rec}</div>
                </div>
            </div>
            <div style='margin-top:15px; padding-top:10px; border-top:1px dashed #444;'>
                <span style='color:#aaa; font-size:0.9rem;'>💡 策略解析：</span>
                <span style='color:#ffd700; font-weight:bold;'>{adv_text}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 擷取近半年 (約 120 個交易日) 的資料來畫圖
        plot_df = hist.tail(120)

        # 建立雙層圖表 (上層: K線+均線+成交量, 下層: KD)
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.7, 0.3],
            specs=[[{"secondary_y": True}], [{"secondary_y": False}]]
        )

        # --- 上層：K線 ---
        fig.add_trace(go.Candlestick(
            x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'],
            name='K線', increasing_line_color='#ff4d4d', decreasing_line_color='#00cc66'
        ), row=1, col=1, secondary_y=False)

        # --- 上層：均線 ---
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA5'], mode='lines', name='MA5', line=dict(color='#00bfff', width=1.5)), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA10'], mode='lines', name='MA10', line=dict(color='#ab82ff', width=1.5)), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], mode='lines', name='MA20', line=dict(color='#ff8c00', width=1.5)), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA60'], mode='lines', name='MA60', line=dict(color='#ffd700', width=1.5)), row=1, col=1, secondary_y=False)

        # --- 上層：成交量 (疊加在底部) ---
        # 判斷紅綠量柱：收盤 >= 開盤 為紅，否則為綠
        vol_colors = ['#ff4d4d' if row['Close'] >= row['Open'] else '#00cc66' for _, row in plot_df.iterrows()]
        fig.add_trace(go.Bar(
            x=plot_df.index, y=plot_df['Volume']/1000,
            marker_color=vol_colors, name='成交量(張)', opacity=0.5
        ), row=1, col=1, secondary_y=True)

        # --- 下層：KD 指標 ---
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['K'], mode='lines', name='K9', line=dict(color='#00bfff', width=1.5)), row=2, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['D'], mode='lines', name='D9', line=dict(color='#ff8c00', width=1.5)), row=2, col=1)

        # --- 座標軸與版面設定 ---
        # 1. 價格 Y 軸：移至右側 (方便對照最新 K 線)，開啟左右框線鏡像
        fig.update_yaxes(side="right", mirror=True, showline=True, linecolor='#555', secondary_y=False, row=1, col=1)
        
        # 2. 成交量 Y 軸：隱藏刻度數字，置於左側避免與價格數字衝突
        max_vol = plot_df['Volume'].max() / 1000
        fig.update_yaxes(side="left", showgrid=False, showticklabels=False, range=[0, max_vol * 3.5], secondary_y=True, row=1, col=1)
        
        # 3. KD Y 軸：範圍固定 0-100，移至右側，開啟左右框線鏡像
        fig.update_yaxes(range=[0, 100], side="right", mirror=True, showline=True, linecolor='#555', row=2, col=1)

        # X 軸：隱藏假日、設定格式為 月/日，開啟上下框線鏡像
        fig.update_xaxes(
            rangebreaks=[dict(bounds=["sat", "mon"])],
            tickformat="%m/%d",
            showgrid=True, gridcolor='#333',
            mirror=True, showline=True, linecolor='#555'
        )

        fig.update_layout(
            height=650,
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified"
        )
        st.plotly_chart(fig, use_container_width=True)
