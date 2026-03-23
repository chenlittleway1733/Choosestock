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
import datetime
import os
import math

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
if 'ai_error' not in st.session_state:
    st.session_state.ai_error = None
if 'api_key' not in st.session_state:
    st.session_state.api_key = ""
if 'ai_fetched_eps' not in st.session_state:
    st.session_state.ai_fetched_eps = {}
if 'show_pk' not in st.session_state:
    st.session_state.show_pk = False
if 'ai_industry_result' not in st.session_state:
    st.session_state.ai_industry_result = None

def change_stock(stock_code):
    st.session_state.selected_stock = stock_code
    if "quick_select" in st.session_state:
        st.session_state.quick_select = "-- 快速切換標的 --"
    st.session_state.show_pk = False
    st.session_state.ai_industry_result = None

# --- 🛠️ 核心防護：絕對安全的浮點數轉換 (消滅 NaN 引發的 ValueError) ---
def s_float(val, default=None):
    try:
        if val is None: return default
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except:
        return default

# --- AI 解析與連線函數 ---
def get_ai_analysis_final(topic, api_key, model_name="gemini-2.5-flash"):
    if not api_key: return "ERROR: 未輸入金鑰", []
    api_key = api_key.strip()
    
    headers = {"Content-Type": "application/json"}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    system_prompt = """你是一位精通台股產業鏈的專業分析師。請針對議題推薦 3 檔「潛力權值股」與 3 檔「中小型飆股」。
    必須嚴格回傳 JSON 格式：
    {
      "reasoning": "產業趨勢簡析...",
      "stocks": [
        {"id": "4位數代號", "name": "中文名稱", "type": "潛力", "why": "原因"}
      ]
    }
    確保代號為純數字。直接輸出 JSON 字串，不要有 ```json 標籤。"""

    payload = {
        "contents": [{"parts": [{"text": f"請深度分析台股議題：{topic}"}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "tools": [{"google_search": {}}],
        "generationConfig": {"responseMimeType": "application/json"}
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            res_json = response.json()
            content = res_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            clean_json = re.sub(r'```json\n?|```', '', content).strip()
            
            start_idx = clean_json.find('{')
            end_idx = clean_json.rfind('}')
            if start_idx != -1 and end_idx != -1:
                clean_json = clean_json[start_idx:end_idx+1]
                
            grounding = res_json.get('candidates', [{}])[0].get('groundingMetadata', {})
            links = [a.get('web', {}).get('uri') for a in grounding.get('groundingAttributions', []) if a.get('web', {}).get('uri')]
            return json.loads(clean_json), list(set(links))
        return f"API 錯誤: {response.status_code}", []
    except Exception as e:
        return f"連線異常: {str(e)}", []

def get_eps_from_ai(stock_name, stock_id, api_key):
    if not api_key: return None
    api_key = api_key.strip()
    url = f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=){api_key}"
    system_prompt = "你是一個精準的財經數據提取機器人。請上網搜尋國內外法人針對該公司「明年」或「今年」所預估的 EPS。『嚴格只回傳一個最合理的數字』（例如：30.5）。不要解釋、不要有其他文字。若查無資料，請回傳 0。"
    payload = {
        "contents": [{"parts": [{"text": f"請搜尋台股 {stock_name} ({stock_id}) 最新的法人預估 EPS"}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "tools": [{"google_search": {}}]
    }
    try:
        res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=15)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            return s_float(text)
    except: pass
    return None

@st.cache_data(ttl=86400)
def get_peers_from_ai(stock_name, stock_id, api_key):
    if not api_key: return []
    api_key = api_key.strip()
    url = f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=){api_key}"
    system_prompt = "請列出與目標公司核心業務最直接競爭的 3~5 家台股上市櫃公司代號。必須是純數字 JSON 陣列格式：[\"2383\", \"3044\"]。絕對不要輸出其他文字。"
    payload = {
        "contents": [{"parts": [{"text": f"請尋找 {stock_name} ({stock_id}) 的同業競爭對手"}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]}
    }
    try:
        res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=15)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            clean_text = re.sub(r'```json\n?|```', '', text).strip()
            peers = json.loads(clean_text)
            if isinstance(peers, list): return [str(p) for p in peers][:4] 
    except: pass
    return []

def get_ai_industry_analysis(stock_name, stock_id, api_key, context_data, model_name="gemini-2.5-flash"):
    if not api_key: return "ERROR: 未輸入金鑰"
    api_key = api_key.strip()
    url = f"[https://generativelanguage.googleapis.com/v1beta/models/](https://generativelanguage.googleapis.com/v1beta/models/){model_name}:generateContent?key={api_key}"
    system_prompt = """你是一位精通台股的資深產業分析師與操盤手。請針對目標公司的最新動態、財報與法說會提供分析。包含產業前景、競爭優勢與具體買賣點策略。請用 Markdown 格式與 Emoji。不要輸出 HTML。"""
    prompt_text = f"請分析台股 {stock_name} ({stock_id})。關鍵數據：\n{context_data}"
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "tools": [{"google_search": {}}]
    }
    try:
        res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=90)
        if res.status_code == 200:
            content = res.json().get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            return re.sub(r'```markdown\n?|```', '', content).strip()
        elif res.status_code == 429:
            return "⏳ API 呼叫太頻繁，請稍後再試，或切換至 Flash 模型。"
        return f"AI 分析連線失敗"
    except Exception as e:
        if "timeout" in str(e).lower(): return "⏳ API 連線逾時，請重試。"
        return f"連線異常: {str(e)}"

# --- 🌍 動態判定今日/明日 (精準時間控制) ---
@st.cache_data(ttl=900) 
def get_global_market_trend():
    try:
        # 轉換為台灣時間 (UTC+8)
        tw_time = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
        h = tw_time.hour
        
        # 精準時間判定與文案顯示
        if 14 <= h < 22:
            target_day = "明日"
            time_status = "<span style='color:gray; font-size:0.9rem;'>(美股尚未開盤，此為昨夜收盤參考)</span>"
        elif h >= 22:
            target_day = "明日"
            time_status = "<span style='color:#00bfff; font-size:0.9rem;'>(美股 / 夜盤交易中)</span>"
        else: # 0 ~ 13 (過了零點到下午兩點前)
            target_day = "今日"
            time_status = "<span style='color:#00cc66; font-size:0.9rem;'>(美股 / 夜盤最新收盤)</span>"

        tickers = yf.Tickers('^SOX TSM NQ=F')
        
        def get_pct(ticker_obj):
            try:
                hist = ticker_obj.history(period='5d')
                if len(hist) >= 2:
                    c = float(hist['Close'].iloc[-1])
                    p = float(hist['Close'].iloc[-2])
                    if not math.isnan(c) and not math.isnan(p) and p != 0:
                        return (c - p) / p * 100
            except: pass
            return 0.0

        sox_pct = get_pct(tickers.tickers['^SOX'])
        tsm_pct = get_pct(tickers.tickers['TSM'])
        nq_pct = get_pct(tickers.tickers['NQ=F'])
        
        score = sox_pct * 0.5 + tsm_pct * 0.3 + nq_pct * 0.2
        
        if score > 1.0:
            trend, color = f"🔥 極度樂觀 ({target_day}台股開盤強勢)", "#ff4d4d"
        elif score > 0.1:
            trend, color = f"📈 偏多看待 (有利{target_day}台股表現)", "#ff4d4d"
        elif score > -0.8:
            trend, color = f"↔️ 震盪整理 ({target_day}台股可能平盤震盪)", "#FFD700"
        else:
            trend, color = f"❄️ 悲觀警戒 ({target_day}台股面臨回檔壓力)", "#00cc66"
            
        return {
            "sox": sox_pct, "tsm": tsm_pct, "nq": nq_pct,
            "trend": trend, "color": color, 
            "target_day": target_day, "time_status": time_status
        }
    except:
        return None

# --- 數據獲取引擎 ---
@st.cache_data(ttl=43200)
def get_monthly_revenue(stock_id):
    try:
        today = datetime.date.today()
        start_str = f"{today.year - 2}-{today.month:02d}-01"
        url = f"[https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMonthRevenue&data_id=](https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMonthRevenue&data_id=){stock_id}&start_date={start_str}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        data = res.json()
        if data.get('status') == 200 and data.get('data'):
            df = pd.DataFrame(data['data'])
            df['date'] = pd.to_datetime(df['date'])
            df = df[df['date'] < pd.to_datetime(f"{today.year}-{today.month:02d}-01")].sort_values('date').reset_index(drop=True)
            df['revenue'] = pd.to_numeric(df['revenue'], errors='coerce')
            df['YoY'] = df['revenue'].pct_change(periods=12) * 100
            df['Month'] = df['date'].dt.strftime('%Y-%m')
            df['Revenue'] = df['revenue'] / 100000000 
            final_df = df.dropna(subset=['YoY']).tail(12).copy()
            if not final_df.empty:
                final_df['Revenue'] = final_df['Revenue'].round(2)
                final_df['YoY'] = final_df['YoY'].round(2)
                return final_df[['Month', 'Revenue', 'YoY']].reset_index(drop=True)
    except: pass
    return None

@st.cache_data(ttl=43200)
def get_pe_pb_data(stock_id):
    try:
        today = datetime.date.today()
        start_str = f"{today.year - 5}-{today.month:02d}-01"
        url = f"[https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPER&data_id=](https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPER&data_id=){stock_id}&start_date={start_str}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data.get('status') == 200 and data.get('data'): 
                df = pd.DataFrame(data['data'])
                df['date'] = pd.to_datetime(df['date'])
                df['PER'] = pd.to_numeric(df['PER'], errors='coerce')
                df['PBR'] = pd.to_numeric(df.get('PBR'), errors='coerce') 
                return df[df['PER'] > 0].dropna(subset=['date', 'PER']).reset_index(drop=True)
    except: pass
    return None

def get_fallback_info(stock_id):
    info = {}
    try:
        url = f"[https://tw.stock.yahoo.com/quote/](https://tw.stock.yahoo.com/quote/){stock_id}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        text = res.text
        
        # 🚀 強力模糊掃描法：找到關鍵字後，跳過所有層級的 HTML 標籤，直接抓取純數字
        def fuzzy_ext(keyword, is_pct=False):
            idx = text.find(keyword)
            if idx != -1:
                chunk = text[idx:idx+200]
                match = re.search(r'>(?:\s*|&nbsp;)*([-0-9]{1,3}(?:\.[0-9]+)?)\s*%?\s*<', chunk)
                if match:
                    try:
                        val = float(match.group(1).replace(',', ''))
                        return val / 100.0 if is_pct else val
                    except: pass
            return None

        info['trailingPE'] = fuzzy_ext('本益比')
        info['priceToBook'] = fuzzy_ext('股價淨值比')
        info['trailingEps'] = fuzzy_ext('EPS')
        info['grossMargins'] = fuzzy_ext('毛利率', True) or fuzzy_ext('營業毛利率', True)
        info['operatingMargins'] = fuzzy_ext('營業利益率', True) or fuzzy_ext('營益率', True)
        info['returnOnEquity'] = fuzzy_ext('ROE', True) or fuzzy_ext('權益報酬率', True)
        sec_match = re.search(r'href="/class-quote\?category=([^"]+)"', text)
        if sec_match: info['sector'] = urllib.parse.unquote(sec_match.group(1))
    except: pass
    return info

@st.cache_data(ttl=3600)
def get_stock_data(stock_id):
    stock_id = str(stock_id).strip()
    hist = None
    info_data = {}
    
    for ext in [".TW", ".TWO"]:
        try:
            ticker = yf.Ticker(f"{stock_id}{ext}")
            temp_hist = ticker.history(period="5y")
            if not temp_hist.empty:
                hist = temp_hist
                try: info_data = ticker.info
                except: info_data = {}
                break
        except: continue
            
    if hist is None or hist.empty:
        try:
            today = datetime.date.today()
            start_str = f"{today.year - 5}-{today.month:02d}-{today.day:02d}"
            url = f"[https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id=](https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id=){stock_id}&start_date={start_str}"
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            data = res.json()
            if data.get('status') == 200 and data.get('data'):
                df = pd.DataFrame(data['data'])
                df['Date'] = pd.to_datetime(df['date'])
                df.rename(columns={'open':'Open','max':'High','min':'Low','close':'Close','Trading_Volume':'Volume'}, inplace=True)
                df.set_index('Date', inplace=True)
                hist = df[['Open','High','Low','Close','Volume']]
        except: pass

    if hist is not None and not hist.empty:
        if not info_data.get('returnOnEquity'):
            fallback = get_fallback_info(stock_id)
            info_data.update(fallback)
        return hist, info_data
    return None, None

@st.cache_data(ttl=86400) 
def get_chinese_name(stock_id):
    try:
        url = f"[https://tw.stock.yahoo.com/quote/](https://tw.stock.yahoo.com/quote/){stock_id}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        match = re.search(r'<title>(.*?)\(', res.text)
        if match: return match.group(1).strip()
    except: pass
    return None

@st.cache_data(ttl=1800)
def get_stock_news(query):
    try:
        encoded_q = urllib.parse.quote(f"{query} 股票")
        url = f"[https://news.google.com/rss/search?q=](https://news.google.com/rss/search?q=){encoded_q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        res = requests.get(url, timeout=5)
        root = ET.fromstring(res.text)
        news = []
        for item in root.findall('.//item')[:6]:
            t = item.find('title').text
            news.append({"title": t, "link": item.find('link').text, "sentiment": "🟢" if any(x in t for x in ["漲","成長","買超"]) else ("🔴" if any(x in t for x in ["跌","賣超","警訊"]) else "⚪")})
        return news
    except: return []

@st.cache_data(ttl=86400)
def translate_to_zh(text):
    if not text or text == '暫無簡介。': return text
    try:
        url = "[https://translate.googleapis.com/translate_a/single](https://translate.googleapis.com/translate_a/single)"
        params = {"client": "gtx", "sl": "en", "tl": "zh-TW", "dt": "t", "q": text}
        res = requests.get(url, params=params, timeout=5)
        return "".join([item[0] for item in res.json()[0]])
    except: return text + "\n\n(⚠️ 翻譯服務暫時忙碌中)"

# ==========================================
# 側邊欄：功能選單與策略漏斗
# ==========================================
with st.sidebar:
    st.markdown("### 🔍 個股查詢")
    stock_input = st.text_input("輸入台股代號", value=st.session_state.selected_stock)
    
    options = ["-- 快速切換標的 --"]
    categories = {}
    current_cat = "未分類"
    categories[current_cat] = []
    if os.path.exists("stocklist.txt"):
        try:
            with open("stocklist.txt", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    if "," in line:
                        p = line.split(",")
                        if len(p) >= 2:
                            options.append(f"　🔸 {p[0].strip()} {p[1].strip()}")
                            categories[current_cat].append((p[0].strip(), p[1].strip()))
                    else:
                        current_cat = line
                        options.append(f"🏷️ {line}")
                        categories[current_cat] = []
        except: pass
            
    selected_quick = st.selectbox("⚡ 快速選股名單", options, key="quick_select")
    if selected_quick != "-- 快速切換標的 --":
        if not selected_quick.startswith("🏷️"):
            q_code = selected_quick.replace("　🔸 ", "").split(" ")[0].strip()
            if q_code != st.session_state.selected_stock:
                st.session_state.selected_stock = q_code; st.rerun()
        else:
            st.session_state.quick_select = "-- 快速切換標的 --"; st.rerun()

    if stock_input != st.session_state.selected_stock:
        st.session_state.selected_stock = stock_input; st.rerun()

    st.markdown("---")
    st.markdown("### 🎯 策略漏斗掃描器")
    if st.button("🔍 掃描同族群潛力股", use_container_width=True):
        st.session_state.run_screener = True
        
    if st.session_state.get('run_screener'):
        target_cat = None; target_stocks = []
        for cat, stocks in categories.items():
            for code, name in stocks:
                if code == st.session_state.selected_stock: target_cat = cat; target_stocks = stocks; break
        if target_cat and target_stocks:
            with st.spinner(f"掃描 {target_cat} 財報中..."):
                results = []
                pbar = st.progress(0)
                for i, (c, n) in enumerate(target_stocks):
                    _, inf = get_stock_data(c)
                    if inf:
                        pe = s_float(inf.get('trailingPE'))
                        roe = s_float(inf.get('returnOnEquity'))
                        eg = s_float(inf.get('earningsGrowth'))
                        if eg is None:
                            df_rv = get_monthly_revenue(c)
                            if df_rv is not None and not df_rv.empty: eg = s_float(df_rv['YoY'].iloc[-1]) / 100.0
                        
                        sys_peg = s_float(inf.get('pegRatio'))
                        peg_is_neg = (eg is not None and eg <= 0)
                        if sys_peg is None and pe and eg and eg > 0: sys_peg = pe / (eg * 100)
                        
                        p_sort = sys_peg if sys_peg is not None and not peg_is_neg else 999
                        p_str = "分母為負" if peg_is_neg else (f"{sys_peg:.2f}" if sys_peg is not None else "N/A")
                        results.append({'code':c,'name':n,'roe':roe,'peg_sort':p_sort,'roe_str':f"{roe*100:.1f}%" if roe else "N/A",'peg_str':p_str})
                    time.sleep(0.5); pbar.progress((i+1)/len(target_stocks))
                pbar.empty(); results.sort(key=lambda x: (x['peg_sort'], -x['roe'] if x['roe'] else 0))
                st.markdown("<div style='background:#1e1e1e; padding:10px; border-radius:5px; border-left:4px solid #00bfff;'><b>🌟 掃描結果</b></div>", unsafe_allow_html=True)
                for res in results:
                    icon = "🔥" if res['peg_sort'] < 1.5 and res['roe'] and res['roe'] > 0.15 else "🔸"
                    st.button(f"{icon} {res['name']} ({res['code']})\nPEG: {res['peg_str']} | ROE: {res['roe_str']}", key=f"s_{res['code']}", on_click=change_stock, args=(res['code'],), use_container_width=True)

    st.markdown("---")
    st.session_state.api_key = st.text_input("🔑 Gemini API Key", type="password", value=st.session_state.api_key)
    if st.button("🔄 重新整理快取", use_container_width=True):
        st.cache_data.clear(); st.rerun()

# ==========================================
# 主畫面開始
# ==========================================
st.markdown("## 📈 台股聯網 AI 投資戰情室")

curr_id = st.session_state.selected_stock
if curr_id:
    with st.spinner('同步數據中...'):
        hist, info = get_stock_data(curr_id)
        if info is None: info = {}
        c_name = get_chinese_name(curr_id) or info.get('shortName', curr_id)

    if hist is not None and not hist.empty:
        st.markdown(f"### 🏢 {c_name} ({curr_id})")
        st.markdown(f"**🏷️ 產業分類：** {SECTOR_MAP.get(info.get('sector', '未知'), info.get('sector', '未知'))} / {info.get('industry', '未知')}")
        with st.expander("📖 查看公司詳細營業項目簡介 (自動英翻中)"):
            st.write(translate_to_zh(info.get('longBusinessSummary', '暫無簡介。')))

        # --- ⚡ 即時報價 ---
        st.markdown("#### ⚡ 即時報價與交易資訊")
        today_data = hist.iloc[-1]
        prev_data = hist.iloc[-2] if len(hist) > 1 else today_data
        curr_p = s_float(today_data.get('Close'), 0)
        prev_close = s_float(info.get('previousClose'), s_float(prev_data.get('Close'), 0))
        change = curr_p - prev_close if prev_close else 0
        change_pct = (change / prev_close) * 100 if prev_close else 0
        
        quote_html = f"""
        <div style='display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; background: #1e1e1e; padding: 15px; border-radius: 8px; border: 1px solid #333;'>
            <div style='text-align:center;'><span style='color:#aaa;'>成交</span><br><b style='font-size:1.5rem; color:{'#ff4d4d' if change > 0 else '#00cc66' if change < 0 else '#fff'};'>{curr_p:,.2f}</b></div>
            <div style='text-align:center;'><span style='color:#aaa;'>昨收</span><br><b style='font-size:1.5rem; color:#fff;'>{prev_close:,.2f}</b></div>
            <div style='text-align:center;'><span style='color:#aaa;'>漲跌幅</span><br><b style='font-size:1.5rem; color:{'#ff4d4d' if change > 0 else '#00cc66' if change < 0 else '#fff'};'>{'▲' if change > 0 else '▼' if change < 0 else ''} {abs(change_pct):.2f}%</b></div>
        </div>
        """
        st.markdown(quote_html, unsafe_allow_html=True)

        # --- 🌍 國際連動與動態時間趨勢推估 ---
        st.markdown("<br>", unsafe_allow_html=True)
        trend_data = get_global_market_trend()
        if trend_data:
            target_day_text = trend_data.get('target_day', '明日')
            time_status_text = trend_data.get('time_status', '')
            st.markdown(f"#### 🌍 國際連動與{target_day_text}趨勢推估 {time_status_text}", unsafe_allow_html=True)
            
            def c_color(v): return "#ff4d4d" if v > 0 else "#00cc66" if v < 0 else "#fff"
            trend_html = f"""
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {trend_data['color']}; margin-bottom: 20px; border-top:1px solid #333; border-right:1px solid #333; border-bottom:1px solid #333;'>
                <div style='font-size:1.15rem; font-weight:bold; color:{trend_data['color']}; margin-bottom:10px;'>{trend_data['trend']}</div>
                <div style='display:flex; justify-content:space-between; flex-wrap:wrap; gap:10px;'>
                    <div style='background:#2c2c2c; padding:8px 15px; border-radius:5px;'><span style='color:#aaa; font-size:0.9rem;'>費城半導體 (^SOX)</span><br><b style='font-size:1.1rem; color:{c_color(trend_data["sox"])};'>{trend_data["sox"]:+.2f}%</b></div>
                    <div style='background:#2c2c2c; padding:8px 15px; border-radius:5px;'><span style='color:#aaa; font-size:0.9rem;'>台積電 ADR (TSM)</span><br><b style='font-size:1.1rem; color:{c_color(trend_data["tsm"])};'>{trend_data["tsm"]:+.2f}%</b></div>
                    <div style='background:#2c2c2c; padding:8px 15px; border-radius:5px;'><span style='color:#aaa; font-size:0.9rem;'>納斯達克期貨 (NQ=F)</span><br><b style='font-size:1.1rem; color:{c_color(trend_data["nq"])};'>{trend_data["nq"]:+.2f}%</b></div>
                </div>
            </div>
            """
            st.markdown(trend_html, unsafe_allow_html=True)

        # --- 💼 財務基本面與獲利基準微調 ---
        st.markdown("#### 💼 財務基本面與獲利基準微調")
        df_rev_bk = get_monthly_revenue(curr_id)
        df_per_bk = get_pe_pb_data(curr_id)
        
        pe_ratio = s_float(info.get('trailingPE'))
        if (pe_ratio is None or pe_ratio > 1000) and df_per_bk is not None and not df_per_bk.empty:
            if (pd.Timestamp.today() - df_per_bk.iloc[-1]['date']).days < 30: pe_ratio = s_float(df_per_bk['PER'].iloc[-1])
            
        pb_ratio = s_float(info.get('priceToBook'))
        if (pb_ratio is None or pb_ratio > 500) and df_per_bk is not None and not df_per_bk.empty and 'PBR' in df_per_bk.columns:
            pb_ratio = s_float(df_per_bk['PBR'].iloc[-1])

        roe = s_float(info.get('returnOnEquity'))
        gm = s_float(info.get('grossMargins'))
        om = s_float(info.get('operatingMargins'))
        
        rev_growth = s_float(info.get('revenueGrowth'))
        if rev_growth is None and df_rev_bk is not None and not df_rev_bk.empty:
            rev_growth = s_float(df_rev_bk['YoY'].iloc[-1]) / 100.0
            
        earn_growth = s_float(info.get('earningsGrowth'))
        if earn_growth is None and rev_growth is not None: earn_growth = rev_growth 
        
        calc_earn_growth = earn_growth if earn_growth is not None and -1 <= earn_growth <= 5 else None
        peg_is_negative = (earn_growth is not None and earn_growth <= 0)
            
        t_eps = s_float(info.get('trailingEps'))
        if t_eps is not None and (t_eps > 500 or t_eps < -500): t_eps = None 
        if t_eps is None and pe_ratio is not None and pe_ratio > 0 and curr_p > 0: t_eps = curr_p / pe_ratio 
            
        sys_f_eps = s_float(info.get('forwardEps'))
        if sys_f_eps is not None and (sys_f_eps > 500 or sys_f_eps < -500): sys_f_eps = None
        if sys_f_eps is None and t_eps is not None and calc_earn_growth is not None: sys_f_eps = t_eps * (1 + calc_earn_growth) 
            
        sys_forward_pe = s_float(info.get('forwardPE'))
        if sys_forward_pe is None and sys_f_eps is not None and sys_f_eps > 0: sys_forward_pe = curr_p / sys_f_eps
            
        sys_peg_ratio = s_float(info.get('pegRatio'))
        if sys_peg_ratio is None and pe_ratio is not None and calc_earn_growth is not None and calc_earn_growth > 0:
            sys_peg_ratio = pe_ratio / (calc_earn_growth * 100)
        if peg_is_negative: sys_peg_ratio = -999

        col_eps1, col_eps2, col_eps3 = st.columns([1.2, 1.5, 1])
        with col_eps1: use_custom_eps = st.toggle("切換為「自訂 / 法人共識預估 EPS」", value=False)
        with col_eps3:
            if st.button("🤖 AI 自動上網尋找法人 EPS", disabled=not st.session_state.api_key):
                val = get_eps_from_ai(c_name, curr_id, st.session_state.api_key)
                if val: st.session_state.ai_fetched_eps[curr_id] = val; st.rerun()
        with col_eps2:
            default_eps = st.session_state.ai_fetched_eps.get(curr_id, sys_f_eps if sys_f_eps else (t_eps if t_eps else 1.0))
            custom_eps = st.number_input("輸入國內法人共識 EPS", value=s_float(default_eps, 1.0), step=0.5, disabled=not use_custom_eps)

        # ==========================================
        # 🚀 終極除錯區：絕對安全的預先字串排版，完全根除 ValueError
        # ==========================================
        if use_custom_eps:
            active_f_eps = custom_eps
            forward_pe = curr_p / active_f_eps if active_f_eps > 0 else None
            if t_eps and t_eps > 0 and pe_ratio:
                cg = (active_f_eps - t_eps) / t_eps
                peg_ratio = pe_ratio / (cg * 100) if cg > 0 else -999
                eg_str = f"{cg * 100:.2f}%"
                eg_color = "#ff4d4d" if cg > 0 else "#00cc66"
            else:
                peg_ratio = None
                eg_str = "N/A"
                eg_color = "gray"
            eps_source_text = f"自訂法人共識 ({active_f_eps:.2f}元)"
        else:
            active_f_eps = sys_f_eps
            forward_pe = sys_forward_pe
            peg_ratio = sys_peg_ratio
            eg_str = f"{earn_growth * 100:.2f}%" if earn_growth is not None else "N/A"
            eg_color = "#ff4d4d" if earn_growth and earn_growth > 0 else ("#00cc66" if earn_growth and earn_growth < 0 else "#fff")
            eps_source_text = f"海外系統或反推 ({sys_f_eps:.2f}元)" if sys_f_eps is not None else "系統預估 (無資料)"

        pe_str = f"{pe_ratio:.1f}x" if pe_ratio is not None else "N/A"
        t_eps_str = f"{t_eps:.2f}" if t_eps is not None else "N/A"
        active_f_eps_str = f"{active_f_eps:.2f}" if active_f_eps is not None else "N/A"
        f_eps_display = f"{t_eps_str} / <span style='color:#00bfff;'>{active_f_eps_str}</span>" if use_custom_eps else f"{t_eps_str} / {active_f_eps_str}"
            
        rg_str = to_pct(rev_growth)
        rg_color = "#ff4d4d" if rev_growth and rev_growth > 0 else ("#00cc66" if rev_growth and rev_growth < 0 else "#fff")
        gm_str = to_pct(gross_margin)
        om_str = to_pct(op_margin)
        roe_str = to_pct(roe)
        roe_eval = " <span style='color:#00cc66; font-size:0.8rem; margin-left:5px;' title='大於15%視為資金運用效率極佳'>⭐ 優質</span>" if roe is not None and roe >= 0.15 else ""

        fund_html = f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 20px;'>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>歷史本益比 (P/E)</div><div style='font-size:1.3rem; font-weight:bold; color:#fff;'>{pe_str}</div></div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>EPS (目前 / 預估)</div><div style='font-size:1.3rem; font-weight:bold; color:#FFD700;'>{f_eps_display}</div></div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>營收年增率 (YoY)</div><div style='font-size:1.3rem; font-weight:bold; color:{rg_color};'>{rg_str}</div></div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>預估獲利成長 (YoY)</div><div style='font-size:1.3rem; font-weight:bold; color:{eg_color};'>{eg_str}</div></div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>毛利率 / 營益率</div><div style='font-size:1.3rem; font-weight:bold; color:#fff;'>{gm_str} / {om_str}</div></div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>ROE (權益報酬率)</div><div style='font-size:1.3rem; font-weight:bold; color:#00bfff;'>{roe_str}{roe_eval}</div></div>
        </div>
        """
        st.markdown(fund_html, unsafe_allow_html=True)

        if pe_ratio is None: pe_color, pe_text = "gray", "數據不足"
        elif pe_ratio > 25: pe_color, pe_text = "#ff4d4d", "高成長溢價"
        elif pe_ratio < 15: pe_color, pe_text = "#00cc66", "相對便宜"
        else: pe_color, pe_text = "#FFD700", "合理區間"

        if pb_ratio is None: pb_color, pb_text = "gray", "數據不足"
        elif pb_ratio > 3: pb_color, pb_text = "#ff4d4d", "偏高溢價"
        elif pb_ratio < 1.5: pb_color, pb_text = "#00cc66", "具資產保護"
        else: pb_color, pb_text = "#FFD700", "合理區間"

        if peg_ratio == -999: peg_color, peg_text, peg_str_val = "gray", "分母為負，無意義", "N/A"
        elif peg_ratio is None: peg_color, peg_text, peg_str_val = "gray", "衰退或無數據", "N/A"
        else: 
            peg_str_val = f"{peg_ratio:.2f}"
            if peg_ratio > 2: peg_color, peg_text = "#ff4d4d", "透支未來成長"
            elif peg_ratio <= 1: peg_color, peg_text = "#00cc66", "低估 (成長性支撐)"
            else: peg_color, peg_text = "#FFD700", "合理區間"

        if forward_pe is None: fpe_color, fpe_text, fpe_str_val = "gray", "數據不足", "N/A"
        else:
            fpe_str_val = f"{forward_pe:.1f}x"
            if forward_pe > 25: fpe_color, fpe_text = "#ff4d4d", "高成長期望"
            elif forward_pe < 15: fpe_color, fpe_text = "#00cc66", "相對便宜"
            else: fpe_color, fpe_text = "#FFD700", "合理區間"

        pb_str_val = f"{pb_ratio:.2f}x" if pb_ratio is not None else "N/A"

        val_html = f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-bottom:20px;'>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {pe_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>📊 歷史本益比 (Trailing P/E)</div><div style='background:{pe_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{pe_text}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:10px;'>{pe_str}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {fpe_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🚀 前瞻本益比 (Forward P/E)</div><div style='background:{fpe_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{fpe_text}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:5px;'>{fpe_str_val}</div>
                <div style='color:#ffd700; font-size:0.85rem; font-weight:bold;'>基準：{eps_source_text}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {peg_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>📈 本益成長比 (PEG)</div><div style='background:{peg_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{peg_text}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:10px;'>{peg_str_val}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {pb_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🏦 股價淨值比 (P/B Ratio)</div><div style='background:{pb_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{pb_text}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:10px;'>{pb_str_val}</div>
            </div>
        </div>
        """
        st.markdown(val_html, unsafe_allow_html=True)
        st.markdown("---")

        # 【6. 產業前景與 AI 報告】
        if st.button("🤖 啟動 AI 深度報告 (含一鍵複製)", use_container_width=True):
            if st.session_state.api_key:
                ctx = f"現價:{curr_p}, P/E:{pe_ratio}, ROE:{to_pct(roe)}, 毛利:{to_pct(gross_margin)}, 營收YoY:{to_pct(rev_growth)}, 預估EPS:{active_f_eps}"
                st.session_state.ai_industry_result = get_ai_industry_analysis(c_name, curr_id, st.session_state.api_key, ctx, st.session_state.get('selected_model', 'gemini-2.5-flash'))
        if st.session_state.ai_industry_result:
            with st.container(border=True):
                st.markdown("### 🤖 AI 產業透視與實戰策略")
                st.markdown(st.session_state.ai_industry_result)
                st.markdown("---")
                with st.expander("📋 點擊展開【純文字版完整報告】 (附一鍵複製按鈕)"):
                    st.code(st.session_state.ai_industry_result, language="markdown")

        # 🚀 【9. 必備神兵：回歸最真實階梯狀的本益比河流圖 (P/E River Chart)】
        if df_per_bk is not None and not df_per_bk.empty:
            st.markdown("### 🌊 近五年本益比河流圖 (P/E River)")
            st.markdown("<small style='color:gray;'>*實戰價值：以最真實未平滑的財報數據繪製。一眼看穿目前股價是落入「被錯殺的低估冷門區」還是「過熱的瘋狂高估區」。*</small>", unsafe_allow_html=True)
            
            h_reset = hist.copy().reset_index()
            if h_reset['Date'].dt.tz is not None: h_reset['Date'] = h_reset['Date'].dt.tz_localize(None)
            h_reset['Date_only'] = h_reset['Date'].dt.date
            
            d_per = df_per_bk.drop_duplicates(subset=['date'], keep='last').copy()
            d_per['date_only'] = d_per['date'].dt.date
            h_reset = h_reset.drop_duplicates(subset=['Date_only'], keep='last')

            merged = pd.merge(h_reset, d_per, left_on='Date_only', right_on='date_only', how='inner').sort_values('Date_only')

            if not merged.empty and len(merged) > 60: 
                merged['EPS_calc'] = merged['Close'] / merged['PER']
                
                pe_quantiles = merged['PER'].quantile([0.1, 0.25, 0.5, 0.75, 0.9]).values

                fig_river = go.Figure()

                b1 = merged['EPS_calc'] * pe_quantiles[0]
                b2 = merged['EPS_calc'] * pe_quantiles[1]
                b3 = merged['EPS_calc'] * pe_quantiles[2]
                b4 = merged['EPS_calc'] * pe_quantiles[3]
                b5 = merged['EPS_calc'] * pe_quantiles[4]

                fig_river.add_trace(go.Scatter(x=merged['Date'], y=b1, mode='lines', line=dict(color='#00cc66', width=1), name=f'悲觀區 ({pe_quantiles[0]:.1f}x)'))
                fig_river.add_trace(go.Scatter(x=merged['Date'], y=b2, mode='lines', fill='tonexty', fillcolor='rgba(0, 204, 102, 0.2)', line=dict(color='#00cc66', width=1), name=f'低估區 ({pe_quantiles[1]:.1f}x)'))
                fig_river.add_trace(go.Scatter(x=merged['Date'], y=b3, mode='lines', fill='tonexty', fillcolor='rgba(255, 215, 0, 0.2)', line=dict(color='#FFD700', width=1), name=f'合理區 ({pe_quantiles[2]:.1f}x)'))
                fig_river.add_trace(go.Scatter(x=merged['Date'], y=b4, mode='lines', fill='tonexty', fillcolor='rgba(255, 140, 0, 0.2)', line=dict(color='#ff8c00', width=1), name=f'高估區 ({pe_quantiles[3]:.1f}x)'))
                fig_river.add_trace(go.Scatter(x=merged['Date'], y=b5, mode='lines', fill='tonexty', fillcolor='rgba(255, 77, 77, 0.2)', line=dict(color='#ff4d4d', width=1), name=f'瘋狂區 ({pe_quantiles[4]:.1f}x)'))

                fig_river.add_trace(go.Scatter(x=merged['Date'], y=merged['Close'], mode='lines', line=dict(color='#0033cc', width=3), name='實際股價'))

                current_pe = merged['PER'].iloc[-1]
                current_price = merged['Close'].iloc[-1]
                
                if current_price <= b2.iloc[-1]:
                    pe_status, status_color = "🔥 處於歷史低估區間！(潛在買點)", "#00cc66"
                elif current_price >= b5.iloc[-1]:
                    pe_status, status_color = "🚨 突破歷史瘋狂區間！(極度高估)", "#ff4d4d"
                elif current_price >= b4.iloc[-1]:
                    pe_status, status_color = "⚠️ 處於歷史高估區間！(留意風險)", "#ff8c00"
                else:
                    pe_status, status_color = "⚖️ 處於歷史合理區間", "#FFD700"

                fig_river.update_layout(
                    height=450,
                    margin=dict(l=10, r=10, t=50, b=10),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                    hovermode="x unified"
                )
                fig_river.update_yaxes(title_text="股價 (元)", showgrid=True, gridcolor='#e0e0e0')

                st.markdown(f"<div style='background:#f8f9fa; border-left:4px solid {status_color}; padding:10px; border-radius:5px; margin-bottom:10px; color:#333;'>目前位階推估：<b><span style='color:{status_color};'>{pe_status}</span></b> (最新本益比約 {current_pe:.1f}x)</div>", unsafe_allow_html=True)
                st.plotly_chart(fig_river, use_container_width=True)
        st.markdown("---")

        # 【10. 專業技術線圖】
        st.markdown("### 🤖 專業技術線圖與量化型態分析 (近半年)")
        plot_df = hist.tail(120).copy()
        
        plot_df['MA5'] = plot_df['Close'].rolling(5).mean()
        plot_df['MA20'] = plot_df['Close'].rolling(20).mean()
        plot_df['MA60'] = plot_df['Close'].rolling(60).mean()
        
        fig_k = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        fig_k.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name='K線'), row=1, col=1)
        fig_k.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name='成交量'), row=2, col=1)
        fig_k.update_layout(height=600, xaxis_rangeslider_visible=False, margin=dict(l=10,r=10,t=10,b=10), template="plotly_dark")
        st.plotly_chart(fig_k, use_container_width=True)
    else:
        st.error(f"找不到代號 {curr_id} 的資料。")
