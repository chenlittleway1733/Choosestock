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

# --- 🛠️ 核心防護：安全浮點數轉換 ---
def s_float(val, default=None):
    try:
        return float(val)
    except:
        return default

# --- AI 解析與連線函數 ---
def get_ai_analysis_final(topic, api_key, model_name="gemini-2.5-flash"):
    if not api_key: return "ERROR: 未輸入金鑰", []
    api_key = api_key.strip()
    
    model = model_name
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
    protocol = "https://"
    api_host = "generativelanguage.googleapis.com"
    url = f"{protocol}{api_host}/v1beta/models/{model}:generateContent?key={api_key}"
    
    payload_search = {
        "contents": [{"parts": [{"text": f"請深度分析台股議題：{topic}"}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "tools": [{"google_search": {}}],
        "generationConfig": {"responseMimeType": "application/json"}
    }

    try:
        response = requests.post(url, headers=headers, json=payload_search, timeout=20)
        if response.status_code == 200: 
            return parse_ai_response(response.json())
        elif response.status_code == 429:
            return "⏳ **API 呼叫太頻繁 (達到免費額度上限)！**\n\nGoogle 免費版 API (特別是 Pro 模型) 有每分鐘呼叫 2 次的限制。\n👉 **解決方法：** 請等待約 1 分鐘後再試，或在左側選單切換為「Gemini 2.5 Flash」模型。", []
        else:
            err_msg = response.json().get('error', {}).get('message', response.text)
            return f"⚠️ API 連線失敗: {err_msg}", []
    except Exception as e:
        return f"⚠️ 連線異常: {str(e)}", []

def parse_ai_response(res_json):
    try:
        content = res_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        clean_json = re.sub(r'```json\n?|```', '', content).strip()
        grounding = res_json.get('candidates', [{}])[0].get('groundingMetadata', {})
        links = [a.get('web', {}).get('uri') for a in grounding.get('groundingAttributions', []) if a.get('web', {}).get('uri')]
        
        start_idx = clean_json.find('{')
        end_idx = clean_json.rfind('}')
        if start_idx != -1 and end_idx != -1:
            clean_json = clean_json[start_idx:end_idx+1]
            
        return json.loads(clean_chunk), list(set(links))
    except Exception as e:
        # 修正：避免 parse 失敗導致 crash
        return {"reasoning": "解析失敗", "stocks": []}, []

def get_eps_from_ai(stock_name, stock_id, api_key):
    if not api_key: return None
    api_key = api_key.strip()
    model = "gemini-2.5-flash"
    protocol = "https://"
    api_host = "generativelanguage.googleapis.com"
    url = f"{protocol}{api_host}/v1beta/models/{model}:generateContent?key={api_key}"
    
    system_prompt = "你是一個精準的財經數據提取機器人。請上網搜尋國內外法人或投顧，針對該公司「明年」或「今年」所預估的 EPS（每股盈餘）。請綜合最新資訊，『嚴格只回傳一個最合理的數字』（例如：30.5 或 15.2）。不要加上任何單位、不要解釋、不要有其他文字。若真的查無資料，請回傳 0。"
    payload = {
        "contents": [{"parts": [{"text": f"請搜尋台股 {stock_name} ({stock_id}) 最新的法人預估 EPS"}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "tools": [{"google_search": {}}],
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
    model = "gemini-2.5-flash"
    protocol = "https://"
    api_host = "generativelanguage.googleapis.com"
    url = f"{protocol}{api_host}/v1beta/models/{model}:generateContent?key={api_key}"
    
    system_prompt = """你是一位精準的台股產業鏈分析師。
    請列出與目標公司「核心業務最直接競爭、屬於同族群」的 3 到 5 家「台股上市櫃公司」股票代號。
    【重要規定】：
    1. 必須是競爭對手或同族群。
    2. 請嚴格只回傳一個 JSON 陣列格式，包含純數字代號字串，例如：["2383", "3044", "6274", "6153"]。
    3. 絕對不要輸出任何其他文字、不要加上 markdown 標記。"""
    
    payload = {
        "contents": [{"parts": [{"text": f"請尋找 {stock_name} ({stock_id}) 的台股同業競爭對手"}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
    }
    try:
        res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=15)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            clean_text = re.sub(r'```json\n?|```', '', text).strip()
            peers = json.loads(clean_text)
            if isinstance(peers, list):
                return [str(p) for p in peers][:4] 
    except: pass
    return []

def get_ai_industry_analysis(stock_name, stock_id, api_key, context_data, model_name="gemini-2.5-flash"):
    if not api_key: return "ERROR: 未輸入金鑰"
    api_key = api_key.strip()
    
    system_prompt = """你是一位精通台股的資深產業分析師與操盤手。
    請上網搜尋目標公司的最新動態、財報與法說會資訊，並「強烈參考我提供給你的最新盤面與財務估值數據」，提供以下深度分析：
    1. 產業前景與趨勢判斷 (近期利多/利空、未來展望)
    2. 公司競爭優勢 (護城河、市占率、核心技術)
    3. 具體的買賣點建議與操作策略 (請結合我提供的基本面、本益比、目標價潛在空間與技術型態，給出具體進出場評估或價位區間參考)
    
    【重要排版要求】：
    - 標題與重點請使用 Emoji 點綴，增加易讀性。
    - 請一律使用專業優美的 Markdown 格式排版 (適當運用 ### 小標題、**粗體**、* 條列式重點)。
    - 絕對不要輸出 HTML 標籤，直接輸出 Markdown 內容即可。"""

    headers = {"Content-Type": "application/json"}
    protocol = "https://"
    api_host = "generativelanguage.googleapis.com"
    url = f"{protocol}{api_host}/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    prompt_text = f"請深度分析台股 {stock_name} ({stock_id}) 的產業前景、競爭優勢及買賣點策略。\n\n【系統已算出的最新關鍵數據，請務必納入買賣點評估考量】：\n{context_data}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "tools": [{"google_search": {}}]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=90)
        if response.status_code == 200: 
            res_json = response.json()
            content = res_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            content = re.sub(r'```markdown\n?|```', '', content).strip()
            return content
        elif response.status_code == 429:
             return "### ⏳ API 呼叫太頻繁 (達到免費額度上限)！\n\nGoogle 免費版 API 的限制較嚴格（尤其是 **Pro 模型每分鐘僅能呼叫 2 次**）。\n\n👉 **解決方法：**\n1. 請等待約 **30 ~ 60 秒**後再點擊一次。\n2. 或者在左側選單切換為速度更快、額度更高的「**Gemini 2.5 Flash**」大腦！\n3. 或者往下捲動，點擊展開右方的「📋 打包提示詞」，直接複製貼到付費版的 Gemini 中提問！"
        else:
            err_msg = response.json().get('error', {}).get('message', response.text)
            return f"⚠️ API 連線失敗: {err_msg}"
    except Exception as e:
        if "timeout" in str(e).lower():
            return "### ⏳ API 連線逾時 (Timeout)！\n\nAI (特別是 Pro 深度模型) 正在進行非常複雜的運算，超過了系統的等待上限。\n👉 **解決方法：** 請再次點擊按鈕重試，或者先切換為速度極快的「Gemini 2.5 Flash」模型進行初步分析。"
        return f"⚠️ 連線異常: {str(e)}"

@st.cache_data(ttl=43200)
def get_monthly_revenue(stock_id):
    try:
        today = datetime.date.today()
        start_year = today.year - 2
        start_str = f"{start_year}-{today.month:02d}-01"
        
        protocol = "https://"
        host_name = "api.finmindtrade.com"
        path = "/api/v4/data"
        params = f"?dataset=TaiwanStockMonthRevenue&data_id={stock_id}&start_date={start_str}"
        url = f"{protocol}{host_name}{path}{params}"
        
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()

        if data.get('status') != 200 or not data.get('data'): return None

        df = pd.DataFrame(data['data'])
        df['date'] = pd.to_datetime(df['date'])
        
        current_month_start = pd.to_datetime(f"{today.year}-{today.month:02d}-01")
        df = df[df['date'] < current_month_start]

        df = df.sort_values('date').reset_index(drop=True)

        df['revenue'] = pd.to_numeric(df['revenue'], errors='coerce')
        df['YoY'] = df['revenue'].pct_change(periods=12) * 100
        
        df['Month'] = df['date'].dt.strftime('%Y-%m')
        df['Revenue'] = df['revenue'] / 100000000 

        final_df = df.dropna(subset=['YoY']).tail(12).copy()
        if final_df.empty: return None

        final_df['Revenue'] = final_df['Revenue'].round(2)
        final_df['YoY'] = final_df['YoY'].round(2)
        return final_df[['Month', 'Revenue', 'YoY']].reset_index(drop=True)
    except Exception as e: return None

@st.cache_data(ttl=43200)
def get_pe_pb_data(stock_id):
    try:
        today = datetime.date.today()
        start_year = today.year - 5
        start_str = f"{start_year}-{today.month:02d}-01"

        protocol = "https://"
        host_name = "api.finmindtrade.com"
        path = "/api/v4/data"
        params = f"?dataset=TaiwanStockPER&data_id={stock_id}&start_date={start_str}"
        url = f"{protocol}{host_name}{path}{params}"

        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=10)
        
        if res.status_code != 200:
            return None
            
        data = res.json()

        if data.get('status') != 200 or not data.get('data'): 
            return pd.DataFrame()

        df = pd.DataFrame(data['data'])
        df['date'] = pd.to_datetime(df['date'])
        df['PER'] = pd.to_numeric(df['PER'], errors='coerce')
        df['PBR'] = pd.to_numeric(df.get('PBR'), errors='coerce') 
        df = df[df['PER'] > 0] 
        
        return df[['date', 'PER', 'PBR']].dropna(subset=['date', 'PER']).reset_index(drop=True)
    except Exception as e: 
        return None

# 🛡️ 終極修復：結合您的「早上版」穩定邏輯 + 模糊掃描引擎
def get_fallback_info(stock_id):
    info = {}
    try:
        protocol = "https://"
        host_name = "tw.stock.yahoo.com"
        url = f"{protocol}{host_name}/quote/{stock_id}"

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(url, headers=headers, timeout=5)
        text = res.text

        # 🚀 模糊掃描法：不管廣告再多、標籤再深，只要找到關鍵字，就掃描後方的第一個數字
        def fuzzy_extract(html, keyword, is_pct=False):
            # 先嘗試早上版的精準模式
            pattern_exact = rf'{keyword}</span><span[^>]*>([-0-9.,]+)%?</span>'
            m1 = re.search(pattern_exact, html)
            if m1:
                try:
                    val = float(m1.group(1).replace(',', ''))
                    return val / 100.0 if is_pct else val
                except: pass
            
            # 若失敗，啟動「標籤無視」模式：掃描關鍵字後方 150 字元內出現的第一組數字
            # 這能處理台積電這種佈局複雜、標籤層級深的頁面
            idx = html.find(keyword)
            if idx != -1:
                chunk = html[idx:idx+200]
                # 排除年份（4位數）、排除指數。專門抓帶有小數點或一到三位數的純財報數值
                # 關鍵：必須避開 2024, 2025 這種大數字
                match = re.search(r'>(?:\s*|&nbsp;)*([-0-9]{1,3}(?:\.[0-9]+)?)\s*%?\s*<', chunk)
                if match:
                    try:
                        val = float(match.group(1).replace(',', ''))
                        return val / 100.0 if is_pct else val
                    except: pass
            return None

        info['trailingPE'] = fuzzy_extract(text, '本益比')
        info['priceToBook'] = fuzzy_extract(text, '股價淨值比')
        info['trailingEps'] = fuzzy_extract(text, 'EPS')

        # 世芯/信驊等 KY 與上櫃股別名相容
        info['grossMargins'] = fuzzy_extract(text, '毛利率', True) or fuzzy_extract(text, '營業毛利率', True)
        info['operatingMargins'] = fuzzy_extract(text, '營業利益率', True) or fuzzy_extract(text, '營益率', True)
        info['returnOnEquity'] = fuzzy_extract(text, 'ROE', True) or fuzzy_extract(text, '權益報酬率', True)

        sec_match = re.search(r'href="/class-quote\?category=([^"]+)"', text)
        if sec_match:
            info['sector'] = urllib.parse.unquote(sec_match.group(1))
            info['industry'] = info['sector']
    except:
        pass
    return info

@st.cache_data(ttl=3600)
def get_stock_data(stock_id):
    stock_id = str(stock_id).strip()
    hist = None
    info_data = {}

    # 🚀 修復：將 Try 包在迴圈內，確保 .TW 失敗時絕對會換 .TWO 繼續找！
    for ext in [".TW", ".TWO"]:
        try:
            ticker = yf.Ticker(f"{stock_id}{ext}")
            temp_hist = ticker.history(period="5y") 
            if not temp_hist.empty:
                hist = temp_hist
                try:
                    info_data = ticker.info
                    if not isinstance(info_data, dict):
                        info_data = {}
                except: pass
                break 
        except:
            continue
            
    # 🚀 歷史股價二次備援：如果 Yahoo 完全擋掉(伺服器限流)，改用 FinMind 拉取 K 線數據
    if hist is None or hist.empty:
        try:
            url = f"[https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id=](https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id=){stock_id}&start_date={(datetime.date.today()-datetime.timedelta(days=1825)).isoformat()}"
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            data = res.json()
            if data.get('status') == 200 and data.get('data'):
                df = pd.DataFrame(data['data'])
                df['Date'] = pd.to_datetime(df['date'])
                df.rename(columns={'open': 'Open', 'max': 'High', 'min': 'Low', 'close': 'Close', 'Trading_Volume': 'Volume'}, inplace=True)
                df.set_index('Date', inplace=True)
                hist = df[['Open', 'High', 'Low', 'Close', 'Volume']]
        except: pass

    if hist is not None and not hist.empty:
        # 如果 Yahoo 原始 info 漏抓 (像台積電常漏 ROE)，啟動強化的模糊爬蟲
        if not info_data.get('trailingPE') or not info_data.get('returnOnEquity'):
            fallback = get_fallback_info(stock_id)
            info_data.update(fallback)
        return hist, info_data
        
    return None, None

@st.cache_data(ttl=86400) 
def get_chinese_name(stock_id):
    try:
        protocol = "https://"
        host_name = "tw.stock.yahoo.com"
        path = "/quote/"
        url = f"{protocol}{host_name}{path}{stock_id}"
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
        protocol = "https://"
        host_name = "news.google.com"
        path = f"/rss/search?q={encoded_q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        url = f"{protocol}{host_name}{path}"
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
        protocol = "https://"
        host_name = "translate.googleapis.com"
        path = "/translate_a/single"
        translate_url = f"{protocol}{host_name}{path}"
        params = {"client": "gtx", "sl": "en", "tl": "zh-TW", "dt": "t", "q": text}
        res = requests.get(translate_url, params=params, timeout=5)
        translated_text = "".join([item[0] for item in res.json()[0]])
        return translated_text
    except Exception:
        return text + "\n\n(⚠️ 翻譯服務暫時忙碌中，以上為原文顯示)"

# ==========================================
# 側邊欄：所有功能選單
# ==========================================
with st.sidebar:
    st.markdown("### 🔍 個股查詢")
    stock_input = st.text_input("輸入台股代號", value=st.session_state.selected_stock)
    
    if stock_input != st.session_state.selected_stock:
        st.session_state.selected_stock = stock_input
        if "quick_select" in st.session_state:
            st.session_state.quick_select = "-- 快速切換標的 --"
        st.session_state.show_pk = False 
        st.session_state.ai_industry_result = None 
        st.rerun()

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
                        parts = line.split(",")
                        if len(parts) >= 2:
                            code, name = parts[0].strip(), parts[1].strip()
                            options.append(f"　🔸 {code} {name}")
                            categories[current_cat].append((code, name))
                    else:
                        current_cat = line
                        options.append(f"🏷️ {line}")
                        categories[current_cat] = []
        except: pass
            
    if len(options) > 1:
        if "quick_select" not in st.session_state:
            st.session_state.quick_select = "-- 快速切換標的 --"
        selected_quick = st.selectbox("⚡ 快速選股名單", options, key="quick_select")
        if selected_quick != "-- 快速切換標的 --":
            if selected_quick.startswith("🏷️"):
                st.session_state.quick_select = "-- 快速切換標的 --"
                st.rerun()
            else:
                clean_str = selected_quick.replace("　🔸 ", "").strip()
                quick_code = clean_str.split(" ")[0].strip()
                if quick_code != st.session_state.selected_stock:
                    st.session_state.selected_stock = quick_code
                    st.session_state.show_pk = False
                    st.session_state.ai_industry_result = None
                    st.rerun()

    st.markdown("---")
    st.markdown("### 🎯 策略漏斗掃描器")
    st.caption("尋找目前標的所屬族群中的「高 ROE + 低 PEG」潛力股。")
    if st.button("🔍 掃描同族群潛力股", use_container_width=True):
        st.session_state.run_screener = True
        
    if st.session_state.get('run_screener'):
        target_cat = None
        target_stocks = []
        for cat, stocks in categories.items():
            for code, name in stocks:
                if code == st.session_state.selected_stock:
                    target_cat = cat
                    target_stocks = stocks
                    break
            if target_cat: break
            
        if target_cat and target_stocks:
            with st.spinner(f"正在掃描 {target_cat} 族群財報..."):
                results = []
                progress_bar = st.progress(0)
                for i, (c, n) in enumerate(target_stocks):
                    _, info = get_stock_data(c)
                    if info:
                        # 使用 FinMind 備援本益比以利漏斗排序
                        df_per_bk = get_pe_pb_data(c)
                        pe = s_float(df_per_bk['PER'].iloc[-1]) if df_per_bk is not None and not df_per_bk.empty else s_float(info.get('trailingPE'))
                        roe = s_float(info.get('returnOnEquity'))
                        eg = s_float(info.get('earningsGrowth'))
                        if eg is None:
                            df_rev_bk = get_monthly_revenue(c)
                            eg = (s_float(df_rev_bk['YoY'].iloc[-1]) / 100.0) if df_rev_bk is not None and not df_rev_bk.empty else None
                        
                        sys_peg = s_float(info.get('pegRatio'))
                        peg_is_negative = (eg is not None and eg <= 0)
                        if (sys_peg is None or pd.isna(sys_peg)) and pe is not None and eg is not None and eg > 0:
                            sys_peg = pe / (eg * 100)
                        
                        peg_for_sort = sys_peg if sys_peg is not None and not pd.isna(sys_peg) and not peg_is_negative else 999
                        peg_str = "分母為負" if peg_is_negative else (f"{sys_peg:.2f}" if sys_peg is not None and not pd.isna(sys_peg) else "N/A")
                        
                        results.append({'code': c, 'name': n, 'roe': roe if roe is not None else -999, 'peg_for_sort': peg_for_sort, 'roe_str': f"{roe*100:.1f}%" if roe is not None else "N/A", 'peg_str': peg_str})
                    time.sleep(0.8)
                    progress_bar.progress((i + 1) / len(target_stocks))
                progress_bar.empty()
                results.sort(key=lambda x: (x['peg_for_sort'], -x['roe']))
                st.markdown(f"<div style='background:#1e1e1e; padding:10px; border-radius:5px; border-left:4px solid #00bfff;'><b>🌟 掃描結果排序</b></div>", unsafe_allow_html=True)
                for res in results:
                    is_good = res['peg_for_sort'] < 1.5 and res['roe'] > 0.15
                    icon = "🔥" if is_good else "🔸"
                    btn_label = f"{icon} {res['name']} ({res['code']})\nPEG: {res['peg_str']} | ROE: {res['roe_str']}"
                    st.button(btn_label, key=f"scr_{res['code']}", on_click=change_stock, args=(res['code'],), use_container_width=True)
        else:
            st.warning("⚠️ 股票不在快速選股清單中，請先選擇！")

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
            st.rerun()
    st.markdown("---")
    if st.button("🔄 重新整理系統快取", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 主畫面開始
# ==========================================
st.markdown("## 📈 台股聯網 AI 投資戰情室")

if st.session_state.topic_results == "LOADING":
    with st.spinner(f"🤖 AI 正在連線推演「{topic_q}」..."):
        model_to_use = st.session_state.get('selected_model', 'gemini-2.5-flash')
        data, links = get_ai_analysis_final(topic_q, st.session_state.api_key, model_to_use)
        if isinstance(data, dict):
            st.session_state.topic_results = {"data": data, "links": links, "topic": topic_q}
            st.session_state.show_whale = False
        else:
            st.error(f"AI 解析失敗。"); st.session_state.topic_results = None

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
        with st.expander("🔗 參考來源"):
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
            summary_zh = translate_to_zh(info.get('longBusinessSummary', '暫無簡介。'))
            st.write(summary_zh)

        st.markdown("#### ⚡ 即時報價與交易資訊")
        today_data = hist.iloc[-1]
        prev_data = hist.iloc[-2] if len(hist) > 1 else today_data
        curr_p = s_float(today_data.get('Close'), 0)
        prev_close = s_float(info.get('previousClose'), s_float(prev_data.get('Close'), 0))
        change = curr_p - prev_close if prev_close else 0
        change_pct = (change / prev_close) * 100 if prev_close else 0
        
        quote_html = f"""
        <style>
        .q-container {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 30px; background: #1e1e1e; padding: 15px 20px; border-radius: 8px; font-family: sans-serif; margin-bottom: 20px; border: 1px solid #333; }}
        .q-item {{ display: flex; justify-content: space-between; border-bottom: 1px solid #333; padding-bottom: 4px; }}
        .q-label {{ color: #aaa; font-size: 1rem; }}
        .q-val {{ font-weight: bold; font-size: 1.1rem; color:#fff; }}
        </style>
        <div class="q-container">
            <div class="q-item"><span class="q-label">成交</span><span class="q-val" style="color: {'#ff4d4d' if change > 0 else '#00cc66' if change < 0 else '#fff'};">{curr_p:,.2f}</span></div>
            <div class="q-item"><span class="q-label">昨收</span><span class="q-val">{prev_close:,.2f}</span></div>
            <div class="q-item"><span class="q-label">漲跌幅</span><span class="q-val" style="color: {'#ff4d4d' if change > 0 else '#00cc66' if change < 0 else '#fff'};">{change_pct:.2f}%</span></div>
            <div class="q-item"><span class="q-label">最高</span><span class="q-val">{s_float(today_data.get('High'), 0):,.2f}</span></div>
            <div class="q-item"><span class="q-label">最低</span><span class="q-val">{s_float(today_data.get('Low'), 0):,.2f}</span></div>
            <div class="q-item"><span class="q-label">總量 (張)</span><span class="q-val" style="color:#ffd700;">{int(s_float(today_data.get('Volume'), 0)//1000):,}</span></div>
        </div>
        """
        st.markdown(quote_html, unsafe_allow_html=True)

        st.markdown("#### 💼 財務基本面與獲利基準微調")
        df_rev_bk = get_monthly_revenue(curr_id)
        df_per_bk = get_pe_pb_data(curr_id)
        
        pe_ratio = s_float(info.get('trailingPE'))
        if (pe_ratio is None or pe_ratio > 1000) and df_per_bk is not None and not df_per_bk.empty:
            pe_ratio = s_float(df_per_bk['PER'].iloc[-1])
        
        roe = s_float(info.get('returnOnEquity'))
        gross_margin = s_float(info.get('grossMargins'))
        op_margin = s_float(info.get('operatingMargins'))
        rev_growth = s_float(df_rev_bk['YoY'].iloc[-1]) / 100.0 if df_rev_bk is not None and not df_rev_bk.empty else s_float(info.get('revenueGrowth'))
        earn_growth = s_float(info.get('earningsGrowth')) or rev_growth
        
        # 🚀 強制數學還原 EPS
        t_eps = s_float(info.get('trailingEps'))
        if (t_eps is None or t_eps > 500) and pe_ratio and pe_ratio > 0: t_eps = curr_p / pe_ratio
            
        sys_f_eps = s_float(info.get('forwardEps')) or (t_eps * (1 + earn_growth) if t_eps and earn_growth else None)
        sys_forward_pe = curr_p / sys_f_eps if sys_f_eps and sys_f_eps > 0 else None
        
        sys_peg = s_float(info.get('pegRatio'))
        peg_is_negative = (earn_growth is not None and earn_growth <= 0)
        if (sys_peg is None or pd.isna(sys_peg)) and pe_ratio and earn_growth and earn_growth > 0:
            sys_peg = pe_ratio / (earn_growth * 100)
            
        st.markdown("##### ⚙️ 獲利預估基準設定")
        col1, col2, col3 = st.columns([1, 1.5, 1])
        with col1: use_custom = st.toggle("切換自訂 EPS", False)
        with col3:
            if st.button("🤖 AI 尋找 EPS", disabled=not st.session_state.api_key):
                val = get_eps_from_ai(c_name, curr_id, st.session_state.api_key)
                if val: st.session_state.ai_fetched_eps[curr_id] = val; st.rerun()
        with col2: 
            active_f_eps = st.number_input("法人共識 EPS (元)", value=s_float(st.session_state.ai_fetched_eps.get(curr_id, sys_f_eps), 1.0), disabled=not use_custom)

        if use_custom:
            peg_ratio = pe_ratio / (((active_f_eps / t_eps) - 1) * 100) if t_eps and t_eps > 0 and active_f_eps > t_eps else -999
            fpe = curr_p / active_f_eps if active_f_eps > 0 else None
        else:
            peg_ratio = -999 if peg_is_negative else sys_peg
            fpe = sys_forward_pe

        def to_p(v): return f"{v * 100:.2f}%" if v is not None else "N/A"
        pe_eval = ("#ff4d4d", "高成長溢價") if pe_ratio and pe_ratio > 25 else ("#00cc66", "相對便宜") if pe_ratio and pe_ratio < 15 else ("#FFD700", "合理區間") if pe_ratio else ("gray", "數據不足")
        peg_eval = ("gray", "分母為負，無意義") if peg_ratio == -999 else (("#ff4d4d", "偏高") if peg_ratio > 2 else ("#00cc66", "低估") if peg_ratio <= 1 else ("#FFD700", "合理"))

        fund_html = f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 20px;'>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>歷史本益比 (P/E)</div>
                <div style='font-size:1.3rem; font-weight:bold; color:#fff;'>{pe_ratio:.1f}x if pe_ratio else 'N/A'}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>EPS (目前 / 預估)</div>
                <div style='font-size:1.3rem; font-weight:bold; color:#FFD700;'>{t_eps:.2f if t_eps else 'N/A'} / {active_f_eps:.2f if active_f_eps else 'N/A'}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>營收年增率 (YoY)</div>
                <div style='font-size:1.3rem; font-weight:bold; color:{'#ff4d4d' if rev_growth and rev_growth > 0 else '#00cc66'};'>{to_p(rev_growth)}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>毛利率 / 營益率</div>
                <div style='font-size:1.3rem; font-weight:bold; color:#fff;'>{to_p(gross_margin)} / {to_p(op_margin)}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem;'>ROE (權益報酬率)</div>
                <div style='font-size:1.3rem; font-weight:bold; color:#00bfff;'>{to_p(roe)}</div>
            </div>
        </div>
        """
        st.markdown(fund_html, unsafe_allow_html=True)

        val_html = f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-bottom:20px;'>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {pe_eval[0]};'>
                <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>📊 歷史本益比: {pe_ratio:.1f if pe_ratio else 'N/A'}x</div>
                <div style='color:{pe_eval[0]}; font-size:0.85rem;'>{pe_eval[1]}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {peg_eval[0]};'>
                <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>📈 PEG: {peg_ratio:.2f if peg_ratio != -999 else 'N/A'}</div>
                <div style='color:{peg_eval[0]}; font-size:0.85rem;'>{peg_eval[1]}</div>
            </div>
        </div>
        """
        st.markdown(val_html, unsafe_allow_html=True)
        st.markdown("---")

        # 【6. 產業與 AI 報告】
        if st.button("🤖 啟動 AI 深度報告 (含一鍵複製)", use_container_width=True):
            if st.session_state.api_key:
                ctx = f"現價:{curr_p}, P/E:{pe_ratio}, ROE:{to_p(roe)}, 毛利:{to_p(gross_margin)}, 營收YoY:{to_p(rev_growth)}, 預估EPS:{active_f_eps}"
                st.session_state.ai_industry_result = get_ai_industry_analysis(c_name, curr_id, st.session_state.api_key, ctx, st.session_state.get('selected_model', 'gemini-2.5-flash'))
        
        if st.session_state.ai_industry_result:
            with st.container(border=True):
                st.markdown(st.session_state.ai_industry_result)
                st.markdown("---")
                st.markdown("<small style='color:gray;'>📋 點擊下方區塊右上角可一鍵複製</small>", unsafe_allow_html=True)
                st.code(st.session_state.ai_industry_result, language="markdown")

        # 【9. 本益比河流圖】
        if df_per_bk is not None and not df_per_bk.empty:
            st.markdown("### 🌊 5年本益比河流圖 (P/E River)")
            h_reset = hist.copy().reset_index(); h_reset['Date_only'] = h_reset['Date'].dt.date
            d_per = df_per_bk.drop_duplicates(subset=['date']).copy(); d_per['date_only'] = d_per['date'].dt.date
            merged = pd.merge(h_reset.drop_duplicates(subset=['Date_only']), d_per, left_on='Date_only', right_on='date_only', how='inner').sort_values('Date')
            
            if not merged.empty:
                merged['EPS_calc'] = merged['Close'] / merged['PER']
                merged['EPS_smooth'] = merged['EPS_calc'].rolling(60, min_periods=1).mean()
                q = merged['PER'].quantile([0.1, 0.25, 0.5, 0.75, 0.9]).values
                fig_r = go.Figure()
                colors = ['rgba(0,204,102,0.2)','rgba(255,215,0,0.2)','rgba(255,140,0,0.2)','rgba(255,77,77,0.2)']
                labels = ['低估','合理','高估','瘋狂']
                for i in range(4):
                    fig_r.add_trace(go.Scatter(x=merged['Date'], y=merged['EPS_smooth']*q[i+1], fill='tonexty' if i>0 else None, fillcolor=colors[i], line=dict(width=0), name=labels[i]))
                fig_r.add_trace(go.Scatter(x=merged['Date'], y=merged['Close'], mode='lines', line=dict(color='#0033cc', width=3), name='實際股價'))
                fig_r.update_layout(height=450, margin=dict(l=10,r=10,t=10,b=10), legend=dict(orientation="h", y=1.1), hovermode="x unified")
                st.plotly_chart(fig_r, use_container_width=True)

        # 【10. 技術 K 線】
        st.markdown("### 🤖 專業技術分析")
        plot_df = hist.tail(120).copy()
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name='K線'), row=1, col=1)
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name='成交量'), row=2, col=1)
        fig.update_layout(height=600, xaxis_rangeslider_visible=False, margin=dict(l=10,r=10,t=10,b=10), legend=dict(orientation="h", y=1.05))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error(f"找不到代號 {curr_id} 的資料。")
