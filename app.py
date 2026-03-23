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

# --- 🛠️ 核心防護：絕對安全的浮點數轉換 ---
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

# --- 🌍 動態判定今日/明日 ---
@st.cache_data(ttl=900) 
def get_global_market_trend():
    try:
        tw_time = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
        h = tw_time.hour
        
        if 14 <= h < 22:
            target_day = "明日"
            time_status = "<span style='color:gray; font-size:0.9rem;'>(美股現貨尚未開盤，此為昨夜收盤參考)</span>"
        elif h >= 22 or h < 5:
            target_day = "明日" if h >= 22 else "今日"
            time_status = "<span style='color:#00bfff; font-size:0.9rem;'>(美股現貨與台股夜盤 交易中)</span>"
        else:
            target_day = "今日"
            time_status = "<span style='color:#00cc66; font-size:0.9rem;'>(美股與夜盤已收盤，為最新結算數據)</span>"

        tickers = yf.Tickers('^SOX TSM NQ=F EWT')
        
        def get_price_and_pct(ticker_obj):
            try:
                hist = ticker_obj.history(period='5d')
                if len(hist) >= 2:
                    c = float(hist['Close'].iloc[-1])
                    p = float(hist['Close'].iloc[-2])
                    if not math.isnan(c) and not math.isnan(p) and p != 0:
                        return c, (c - p) / p * 100
            except: pass
            return 0.0, 0.0

        sox_price, sox_pct = get_price_and_pct(tickers.tickers['^SOX'])
        tsm_price, tsm_pct = get_price_and_pct(tickers.tickers['TSM'])
        nq_price, nq_pct = get_price_and_pct(tickers.tickers['NQ=F'])
        ewt_price, ewt_pct = get_price_and_pct(tickers.tickers['EWT'])
        
        score = sox_pct * 0.3 + tsm_pct * 0.3 + nq_pct * 0.1 + ewt_pct * 0.3
        
        if score > 1.0:
            trend, color = f"🔥 極度樂觀 ({target_day}台股開盤強勢)", "#ff4d4d"
        elif score > 0.1:
            trend, color = f"📈 偏多看待 (有利{target_day}台股表現)", "#ff4d4d"
        elif score > -0.8:
            trend, color = f"↔️ 震盪整理 ({target_day}台股可能平盤震盪)", "#FFD700"
        else:
            trend, color = f"❄️ 悲觀警戒 ({target_day}台股面臨回檔壓力)", "#00cc66"
            
        return {
            "sox_p": sox_price, "sox": sox_pct, 
            "tsm_p": tsm_price, "tsm": tsm_pct, 
            "nq_p": nq_price, "nq": nq_pct, 
            "ewt_p": ewt_price, "ewt": ewt_pct,
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
                        if (sys_peg is None or pd.isna(sys_peg)) and pe and eg and eg > 0: sys_peg = pe / (eg * 100)
                        
                        p_sort = sys_peg if sys_peg is not None and not pd.isna(sys_peg) and not peg_is_neg else 999
                        p_str = "分母為負" if peg_is_neg else (f"{sys_peg:.2f}" if sys_peg is not None and not pd.isna(sys_peg) else "N/A")
                        
                        roe_str_local = f"{roe*100:.1f}%" if roe is not None and not pd.isna(roe) else "N/A"
                        
                        results.append({'code':c,'name':n,'roe':roe,'peg_sort':p_sort,'roe_str':roe_str_local,'peg_str':p_str})
                    time.sleep(0.5); pbar.progress((i+1)/len(target_stocks))
                pbar.empty(); results.sort(key=lambda x: (x['peg_sort'], -x['roe'] if x['roe'] else 0))
                st.markdown("<div style='background:#1e1e1e; padding:10px; border-radius:5px; border-left:4px solid #00bfff;'><b>🌟 掃描結果</b></div>", unsafe_allow_html=True)
                for res in results:
                    icon = "🔥" if res['peg_sort'] < 1.5 and res['roe'] and res['roe'] > 0.15 else "🔸"
                    st.button(f"{icon} {res['name']} ({res['code']})\nPEG: {res['peg_str']} | ROE: {res['roe_str']}", key=f"s_{res['code']}", on_click=change_stock, args=(res['code'],), use_container_width=True)

    # 🚀 滿血回歸：籌碼追蹤、AI推演、同業PK 全部還原！
    st.markdown("---")
    st.markdown("### 🐳 籌碼集中度追蹤")
    if st.button("🔍 掃描籌碼增持名單", use_container_width=True):
        st.session_state.show_whale = True
        st.session_state.topic_results = None
        st.session_state.show_pk = False
        st.session_state.ai_industry_result = None
        st.rerun()
        
    st.markdown("---")
    st.markdown("### 🧠 AI 聯網議題選股")
    topic_q = st.text_input("輸入議題 (如: 代理人AI、矽光子)")
    ai_model_option = st.radio("選擇 AI 推演大腦", ["Gemini 2.5 Flash (快速 / 省額度)", "Gemini 2.5 Pro (深度推演 / 耗額度)"])
    st.session_state.api_key = st.text_input("🔑 Gemini API Key", type="password", value=st.session_state.api_key)
    
    if st.button("AI 實時推演分析", type="primary", use_container_width=True):
        if topic_q and st.session_state.api_key:
            st.session_state.selected_model = "gemini-2.5-pro" if "Pro" in ai_model_option else "gemini-2.5-flash"
            st.session_state.topic_results = "LOADING"
            st.session_state.ai_industry_result = None
            st.rerun()
            
    st.markdown("---")
    st.markdown("### ⚔️ 產業同業 PK")
    if st.button("🤖 尋找同業競爭對手並 PK", use_container_width=True):
        if not st.session_state.api_key:
            st.warning("請先輸入您的 API Key。")
        else:
            st.session_state.show_pk = True 
            st.rerun()

    st.markdown("---")
    if st.button("🔄 重新整理快取", use_container_width=True):
        st.cache_data.clear(); st.rerun()

# ==========================================
# 主畫面開始
# ==========================================
st.markdown("## 📈 台股聯網 AI 投資戰情室")

# 🚀 處理 AI 議題結果顯示區塊
if st.session_state.topic_results == "LOADING":
    with st.spinner(f"🤖 AI 正在連線推演「{topic_q}」..."):
        model_to_use = st.session_state.get('selected_model', 'gemini-2.5-flash')
        data, links = get_ai_analysis_final(topic_q, st.session_state.api_key, model_to_use)
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

if st.session_state.show_whale:
    st.markdown("### 🐳 近兩周大戶持股比例顯著增加標的")
    whales = [("2317", "鴻海"), ("2382", "廣達"), ("1519", "華城"), ("6669", "緯穎"), ("3324", "雙鴻")]
    cols = st.columns(5)
    for idx, (code, name) in enumerate(whales):
        with cols[idx]: st.button(f"{name}\n({code})", on_click=change_stock, args=(code,), key=f"w_{code}", use_container_width=True)
    st.markdown("---")

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
                    <div style='background:#2c2c2c; padding:8px 15px; border-radius:5px;'><span style='color:#aaa; font-size:0.9rem;'>費城半導體 (^SOX)</span><br><b style='font-size:1.1rem; color:#fff;'>{trend_data["sox_p"]:,.2f}</b> <span style='font-size:1rem; color:{c_color(trend_data["sox"])};'>({trend_data["sox"]:+.2f}%)</span></div>
                    <div style='background:#2c2c2c; padding:8px 15px; border-radius:5px;'><span style='color:#aaa; font-size:0.9rem;'>台積電 ADR (TSM)</span><br><b style='font-size:1.1rem; color:#fff;'>{trend_data["tsm_p"]:,.2f}</b> <span style='font-size:1rem; color:{c_color(trend_data["tsm"])};'>({trend_data["tsm"]:+.2f}%)</span></div>
                    <div style='background:#2c2c2c; padding:8px 15px; border-radius:5px;'><span style='color:#aaa; font-size:0.9rem;'>納斯達克期貨 (NQ=F)</span><br><b style='font-size:1.1rem; color:#fff;'>{trend_data["nq_p"]:,.2f}</b> <span style='font-size:1rem; color:{c_color(trend_data["nq"])};'>({trend_data["nq"]:+.2f}%)</span></div>
                    <div style='background:#2c2c2c; padding:8px 15px; border-radius:5px;'><span style='color:#aaa; font-size:0.9rem;'>台股 ETF (EWT)</span><br><b style='font-size:1.1rem; color:#fff;'>{trend_data["ewt_p"]:,.2f}</b> <span style='font-size:1rem; color:{c_color(trend_data["ewt"])};'>({trend_data["ewt"]:+.2f}%)</span></div>
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
        gross_margin = s_float(info.get('grossMargins'))
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
        if (sys_peg_ratio is None or pd.isna(sys_peg_ratio)) and pe_ratio is not None and calc_earn_growth is not None and calc_earn_growth > 0:
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
        # 🚀 絕對安全的本地格式化工具：保證在此刻定義，絕不引發 NameError
        # ==========================================
        def safe_pct(val):
            return f"{val * 100:.2f}%" if val is not None and not pd.isna(val) else "N/A"

        if use_custom_eps:
            active_f_eps = custom_eps
            forward_pe = curr_p / active_f_eps if active_f_eps > 0 else None
            if t_eps and t_eps > 0 and pe_ratio:
                cg = (active_f_eps - t_eps) / t_eps
                peg_ratio = pe_ratio / (cg * 100) if cg > 0 else -999
                eg_str = safe_pct(cg)
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
            eg_str = safe_pct(earn_growth)
            eg_color = "#ff4d4d" if earn_growth and earn_growth > 0 else ("#00cc66" if earn_growth and earn_growth < 0 else "#fff")
            eps_source_text = f"海外系統或反推 ({sys_f_eps:.2f}元)" if sys_f_eps is not None else "系統預估 (無資料)"

        pe_str = f"{pe_ratio:.1f}x" if pe_ratio is not None else "N/A"
        t_eps_str = f"{t_eps:.2f}" if t_eps is not None else "N/A"
        active_f_eps_str = f"{active_f_eps:.2f}" if active_f_eps is not None else "N/A"
        f_eps_display = f"{t_eps_str} / <span style='color:#00bfff;'>{active_f_eps_str}</span>" if use_custom_eps else f"{t_eps_str} / {active_f_eps_str}"
            
        rg_str = safe_pct(rev_growth)
        rg_color = "#ff4d4d" if rev_growth and rev_growth > 0 else ("#00cc66" if rev_growth and rev_growth < 0 else "#fff")
        gm_str = safe_pct(gross_margin)
        om_str = safe_pct(op_margin)
        roe_str = safe_pct(roe)
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

        # 🚀 產業 PK 與比較 (側邊欄觸發)
        if st.session_state.show_pk:
            st.markdown("#### ⚔️ 產業橫向對比 (同業估值與利潤率 PK)")
            st.markdown("<small style='color:gray;'>*註：透過 AI 動態檢索業務相近的競爭對手，並抓取最新財報數據進行橫向比較。*</small>", unsafe_allow_html=True)

            with st.spinner("AI 正在深度檢索產業鏈與競爭對手，並同步抓取最新財報數據..."):
                peers = get_peers_from_ai(c_name, curr_id, st.session_state.api_key)
                if peers:
                    compare_list = [curr_id] + [p for p in peers if p != curr_id]
                    compare_data = []
                    for code in compare_list:
                        _, p_info = get_stock_data(code)
                        p_name = get_chinese_name(code) or code
                        if p_info:
                            pe_val = s_float(p_info.get("trailingPE"))
                            pe_fmt = f"{pe_val:.2f}x" if pe_val is not None else "N/A"
                            
                            gm_val = s_float(p_info.get('grossMargins'))
                            gm_fmt = f"{gm_val * 100:.2f}%" if gm_val is not None else "N/A"
                            
                            om_val = s_float(p_info.get('operatingMargins'))
                            om_fmt = f"{om_val * 100:.2f}%" if om_val is not None else "N/A"
                            
                            roe_val = s_float(p_info.get('returnOnEquity'))
                            roe_fmt = f"{roe_val * 100:.2f}%" if roe_val is not None else "N/A"
                            
                            prev_close_val = s_float(p_info.get("previousClose"))
                            prev_close_fmt = f"{prev_close_val:.2f}" if prev_close_val is not None else "N/A"
                            
                            t_eps_p = s_float(p_info.get('trailingEps'))
                            f_eps_p = s_float(p_info.get('forwardEps'))
                            t_eps_p_str = f"{t_eps_p:.2f}" if t_eps_p is not None else "N/A"
                            f_eps_p_str = f"{f_eps_p:.2f}" if f_eps_p is not None else "N/A"
                            eps_display = f"{t_eps_p_str} / <span style='color:#00bfff;'>{f_eps_p_str}</span>"
                            
                            if prev_close_val is not None and f_eps_p is not None and f_eps_p > 0:
                                fpe_val = prev_close_val / f_eps_p
                                fpe_fmt = f"<b style='color:#FFD700;'>{fpe_val:.1f}x</b>"
                            else:
                                fpe_fmt = "<span style='color:gray;'>N/A</span>"

                            target_mean_p = s_float(p_info.get('targetMeanPrice'))
                            if target_mean_p is not None and prev_close_val is not None and prev_close_val > 0:
                                upside = ((target_mean_p - prev_close_val) / prev_close_val) * 100
                                if upside >= 25:
                                    upside_fmt = f"<span style='color:#ff4d4d; font-weight:bold;'>+{upside:.1f}%</span>"
                                elif upside > 0:
                                    upside_fmt = f"<span style='color:#00cc66;'>+{upside:.1f}%</span>"
                                else:
                                    upside_fmt = f"<span style='color:#aaa;'>{upside:.1f}%</span>"
                                target_display = f"{target_mean_p:.1f} ({upside_fmt})"
                            else:
                                target_display = "<span style='color:gray;'>無資料</span>"
                            
                            compare_data.append({
                                "代號": f"{p_name} ({code})",
                                "股價": prev_close_fmt,
                                "前瞻 P/E": fpe_fmt,
                                "預估 EPS": eps_display,
                                "目標價": target_display,
                                "毛利率": gm_fmt,
                                "營益率": om_fmt,
                                "ROE": roe_fmt
                            })
                    
                    if compare_data:
                        table_html = "<table style='width:100%; text-align:center; border-collapse: collapse; margin-top: 10px; font-size: 1.05rem; color: #e0e0e0;'>"
                        table_html += "<tr style='background-color:#333; color:#fff; border-bottom: 2px solid #555;'><th style='padding:12px;'>公司名稱</th><th>最新收盤價</th><th>前瞻 P/E</th><th>預估 EPS (今/明)</th><th>目標價 (潛在空間)</th><th>毛利率</th><th>營益率</th><th>ROE</th></tr>"
                        for d in compare_data:
                            row_bg = "#2c3e50" if str(curr_id) in d['代號'] else "#1e1e1e" 
                            table_html += f"<tr style='background-color:{row_bg}; border-bottom:1px solid #444;'>"
                            table_html += f"<td style='padding:12px; color:#ffffff;'><b>{d['代號']}</b></td>"
                            table_html += f"<td>{d['股價']}</td>"
                            table_html += f"<td>{d['前瞻 P/E']}</td>"
                            table_html += f"<td>{d['預估 EPS']}</td>"
                            table_html += f"<td>{d['目標價']}</td>"
                            table_html += f"<td>{d['毛利率']}</td>"
                            table_html += f"<td>{d['營益率']}</td>"
                            table_html += f"<td style='color:#00bfff;'><b>{d['ROE']}</b></td>"
                            table_html += "</tr>"
                        table_html += "</table>"
                        st.markdown(table_html, unsafe_allow_html=True)
                else:
                    st.error("AI 暫時找不到明確的同業數據，或請檢查您的 API Key 額度。")
            st.markdown("---")

        # 【6. 產業前景與 AI 報告】
        if st.button("🤖 啟動 AI 深度報告 (含一鍵複製)", use_container_width=True):
            if st.session_state.api_key:
                ctx = f"現價:{curr_p}, P/E:{pe_ratio}, ROE:{safe_pct(roe)}, 毛利:{safe_pct(gross_margin)}, 營收YoY:{safe_pct(rev_growth)}, 預估EPS:{active_f_eps}"
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
        plot_df['MA10'] = plot_df['Close'].rolling(10).mean()
        plot_df['MA20'] = plot_df['Close'].rolling(20).mean()
        plot_df['MA60'] = plot_df['Close'].rolling(60).mean()
        plot_df['MA120'] = plot_df['Close'].rolling(120).mean()
        plot_df['Vol_MA20'] = plot_df['Volume'].rolling(20).mean()
        
        # 🚀 KD 指標計算邏輯
        h9, l9 = plot_df['High'].rolling(9).max(), plot_df['Low'].rolling(9).min()
        h9_l9_diff = h9 - l9
        h9_l9_diff[h9_l9_diff == 0] = 1e-9 
        rsv = (plot_df['Close'] - l9) / h9_l9_diff * 100
        
        K, D = [50], [50]
        for v in rsv.fillna(50):
            K.append(K[-1]*(2/3) + v*(1/3))
            D.append(D[-1]*(2/3) + K[-1]*(1/3))
        plot_df['K'], plot_df['D'] = K[1:], D[1:]
        
        last_close = plot_df['Close'].iloc[-1]
        ma5_last = plot_df['MA5'].iloc[-1]
        ma20_last = plot_df['MA20'].iloc[-1]
        ma60_last = plot_df['MA60'].iloc[-1]
        k_last = plot_df['K'].iloc[-1]
        d_last = plot_df['D'].iloc[-1]
        
        recent_20 = plot_df.tail(20)
        recent_high = recent_20['High'].max()
        recent_low = recent_20['Low'].min()
        max_vol_idx = recent_20['Volume'].idxmax()
        max_vol_day = recent_20.loc[max_vol_idx]
        
        is_high_vol = max_vol_day['Volume'] > (max_vol_day['Vol_MA20'] * 2)
        is_at_high = max_vol_day['High'] >= (recent_high * 0.95)
        is_dropping = last_close < max_vol_day['Low']
        high_vol_warning = is_high_vol and is_at_high and is_dropping
        
        support_price = max(recent_low, ma60_last) if last_close > ma60_last else recent_low
        resist_price = recent_high if last_close > ma20_last else min(recent_high, ma20_last)

        if last_close < ma60_last:
            trend_status, trend_color = "⚠️ 跌破季線 (趨勢轉弱)", "#00cc66"
        elif last_close > ma20_last and ma5_last > ma20_last:
            trend_status, trend_color = "📈 多頭強勢 (站上月線)", "#ff4d4d"
        elif last_close < ma20_last and ma5_last < ma20_last:
            trend_status, trend_color = "📉 空頭弱勢 (跌破月線)", "#00cc66"
        else:
            trend_status, trend_color = "↔️ 區間震盪 (方向未明)", "#ffd700"
            
        if high_vol_warning:
            adv_text = "🚨 【量價警訊】高檔爆出天量且跌破低點，主力疑似出貨，切勿盲目接刀！"
            buy_rec, sell_rec = "強烈觀望", f"反彈至 {max_vol_day['High']:.2f} 逃命"
        elif last_close < ma60_last:
            adv_text = "📉 【趨勢轉弱】股價已跌破季線(生命線)，長線大趨勢走弱，應耐心等待底部確立。"
            buy_rec, sell_rec = "等待站回季線", f"{ma60_last:.2f} (季線壓力)"
        elif k_last < 25 and k_last > d_last:
            adv_text = "📈 【技術反彈】KD 低檔黃金交叉且長線均線有守，可嘗試逢低少量佈局。"
            buy_rec, sell_rec = f"現價~{support_price:.2f} 附近", f"{resist_price:.2f} (上檔壓力)"
        elif k_last > 80 and k_last < d_last:
            adv_text = "⚠️ 【動能轉弱】KD 高檔死亡交叉，建議適度獲利了結保住利潤。"
            buy_rec, sell_rec = "暫時觀望", f"現價~{resist_price:.2f} 附近"
        elif last_close > ma20_last:
            adv_text = "🔥 【多方格局】量價配合良好，拉回月線(20MA)有守可伺機介入。"
            buy_rec, sell_rec = f"{ma20_last:.2f} (月線支撐)", f"{resist_price:.2f} (近期前高)"
        else:
            adv_text = "❄️ 【空方格局】短線均線反壓，反彈至均線壓力區可考慮減碼。"
            buy_rec, sell_rec = "等待技術面打底", f"{ma20_last:.2f} (月線壓力)"

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
        
        fig_k = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        fig_k.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name='K線'), row=1, col=1)
        fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA5'], mode='lines', name='MA5', line=dict(color='#00bfff', width=1.5)), row=1, col=1)
        fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA10'], mode='lines', name='MA10', line=dict(color='#ab82ff', width=1.5)), row=1, col=1)
        fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], mode='lines', name='MA20', line=dict(color='#ff8c00', width=1.5)), row=1, col=1)
        fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA60'], mode='lines', name='MA60', line=dict(color='#ffd700', width=1.5)), row=1, col=1)
        fig_k.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name='成交量'), row=2, col=1)
        fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df['K'], mode='lines', name='K9', line=dict(color='#00bfff', width=1.5)), row=2, col=1)
        fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df['D'], mode='lines', name='D9', line=dict(color='#ff8c00', width=1.5)), row=2, col=1)
        fig_k.update_layout(height=600, xaxis_rangeslider_visible=False, margin=dict(l=10,r=10,t=10,b=10), template="plotly_dark", hovermode="x unified")
        st.plotly_chart(fig_k, use_container_width=True)
    else:
        st.error(f"找不到代號 {curr_id} 的資料。")
