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

# ==========================================
# 0. 網頁基本設定
# ==========================================
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

# ==========================================
# 1. 全局安全轉換與排版函數
# ==========================================
def s_float(val, default=None):
    try:
        if val is None: return default
        v = float(val)
        if math.isnan(v) or math.isinf(v): return default
        return v
    except:
        return default

def to_pct(val):
    try:
        if val is None or pd.isna(val): return "N/A"
        return f"{val * 100:.2f}%"
    except:
        return "N/A"

def to_val_str(v, fmt="pct"):
    if v is None or pd.isna(v): return "N/A"
    if fmt == "pct": return f"{v * 100:.2f}%"
    if fmt == "x": return f"{v:.1f}x"
    return f"{v:.2f}"

def build_cmp_str(orig, ai_val, fmt="pct", suffix="AI捉取"):
    s = to_val_str(orig, fmt)
    if ai_val is not None and not pd.isna(ai_val):
        s += f"<br><span style='color:#FFD700; font-size:0.85rem;'>({to_val_str(float(ai_val), fmt)}, {suffix})</span>"
    return s

def build_cmp_dual_str(o1, o2, a1, a2, fmt1="num", fmt2="num", suffix="AI捉取"):
    s1 = to_val_str(o1, fmt1)
    s2 = to_val_str(o2, fmt2)
    s = f"{s1} / <span style='color:#00bfff;'>{s2}</span>" if (fmt1=="num" and fmt2=="num") else f"{s1} / {s2}"
    if (a1 is not None and not pd.isna(a1)) or (a2 is not None and not pd.isna(a2)):
        sa1 = to_val_str(float(a1) if a1 is not None else None, fmt1)
        sa2 = to_val_str(float(a2) if a2 is not None else None, fmt2)
        s += f"<br><span style='color:#FFD700; font-size:0.85rem;'>({sa1} / {sa2}, {suffix})</span>"
    return s

# --- 🌟 動態自選股讀寫引擎 ---
def get_watchlist():
    watchlist = []
    if os.path.exists("stocklist.txt"):
        try:
            with open("stocklist.txt", "r", encoding="utf-8") as f:
                for line in f:
                    if "," in line:
                        watchlist.append(line.split(",")[0].strip())
        except: pass
    return watchlist

def toggle_watchlist(code, name):
    lines = []
    if os.path.exists("stocklist.txt"):
        try:
            with open("stocklist.txt", "r", encoding="utf-8") as f:
                lines = f.readlines()
        except: pass
    
    new_lines = []
    is_removed = False
    for line in lines:
        if "," in line and line.split(",")[0].strip() == str(code):
            is_removed = True
            continue
        new_lines.append(line)
        
    if not is_removed:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] = new_lines[-1] + "\n"
        new_lines.append(f"{code},{name}\n")
        
    with open("stocklist.txt", "w", encoding="utf-8") as f:
        f.writelines(new_lines)

# ==========================================
# 2. Session State 初始化 & 狀態管理
# ==========================================
if 'selected_stock' not in st.session_state: st.session_state.selected_stock = "2330"
if 'topic_results' not in st.session_state: st.session_state.topic_results = None
if 'show_whale' not in st.session_state: st.session_state.show_whale = False
if 'api_key' not in st.session_state: st.session_state.api_key = ""
if 'fugle_key' not in st.session_state: st.session_state.fugle_key = "" 
if 'ai_fetched_financials' not in st.session_state: st.session_state.ai_fetched_financials = {}
if 'show_pk' not in st.session_state: st.session_state.show_pk = False
if 'ai_industry_result' not in st.session_state: st.session_state.ai_industry_result = None
if 'run_screener' not in st.session_state: st.session_state.run_screener = False
if 'quick_select' not in st.session_state: st.session_state.quick_select = "-- 快速切換標的 --"
if 'stock_input_widget' not in st.session_state: st.session_state.stock_input_widget = "2330"

def reset_all_states_on_stock_change(stock_code):
    st.session_state.selected_stock = stock_code
    st.session_state.quick_select = "-- 快速切換標的 --"
    st.session_state.show_pk = False
    st.session_state.ai_industry_result = None
    st.session_state.run_screener = False

def on_stock_input_change():
    new_stock = st.session_state.stock_input_widget
    if new_stock != st.session_state.selected_stock:
        reset_all_states_on_stock_change(new_stock)

def on_quick_select_change():
    selected = st.session_state.quick_select
    if selected != "-- 快速切換標的 --":
        if not selected.startswith("🏷️"):
            q_code = selected.replace("　🔸 ", "").split(" ")[0].strip()
            if q_code != st.session_state.selected_stock:
                reset_all_states_on_stock_change(q_code)
        st.session_state.quick_select = "-- 快速切換標的 --"

# ==========================================
# 3. 外部 API 與模型模組
# ==========================================
def fetch_fugle_kline(stock_id, api_key, timeframe="D"):
    if not api_key: return pd.DataFrame()
    today = datetime.date.today()
    if timeframe in ["60", "30", "15"]: from_date = (today - datetime.timedelta(days=60)).strftime("%Y-%m-%d")
    else: from_date = (today - datetime.timedelta(days=365*5)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/historical/candles/{stock_id}?timeframe={timeframe}&from={from_date}&to={to_date}"
    headers = {"X-API-KEY": api_key.strip()}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json().get('data', [])
            if data:
                df = pd.DataFrame(data)
                df['Date'] = pd.to_datetime(df['date'])
                df.set_index('Date', inplace=True)
                df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
                return df[['Open', 'High', 'Low', 'Close', 'Volume']].sort_index()
    except: pass
    return pd.DataFrame()

def get_financials_from_ai(stock_name, stock_id, api_key):
    if not api_key: return None
    api_key = api_key.strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    current_year = datetime.date.today().year
    target_year = current_year if datetime.date.today().month < 9 else current_year + 1
    
    system_prompt = f"""你是一個精準的財經數據提取機器人。請上網搜尋該台股公司最新財報與市場數據，提取以下指標：
    1. 「歷史本益比 (P/E)」
    2. 「近四季或最新年度 EPS (Trailing EPS)」
    3. 「法人預估 {target_year} 年度 EPS (Forward EPS)」(請優先找 {target_year} 年的預測值)
    4. 「股價淨值比 (P/B)」
    5. 「毛利率」
    6. 「營益率」
    7. 「ROE(股東權益報酬率)」(非常重要，請務必搜尋)
    8. 「最新單月或累計營收年增率(YoY)」
    9. 「國內外法人最新預估目標價 (Target Price)」(請找近期外資或投信給出的目標價平均或最新值)
    10. 「負債權益比 (Debt-to-Equity Ratio)」(請務必搜尋，評估財務槓桿)

    必須嚴格回傳包含上述 10 個欄位的 JSON 格式。百分比請轉換為小數（例如 25.5% 寫成 0.255，衰退5%寫成 -0.05），數值請直接輸出數字。若查無資料，該欄位請填 null。
    格式範例：
    {{"pe": 15.2, "trailing_eps": 5.4, "forward_eps": 6.2, "pb": 2.1, "gross_margin": 0.255, "operating_margin": 0.123, "roe": 0.15, "yoy": 0.082, "target_price": 1050.0, "debt_to_equity": 0.45}}
    絕對不要輸出 markdown 標記或其他文字。"""
    
    payload = {
        "contents": [{"parts": [{"text": f"請啟動搜尋引擎，查詢台股 {stock_name} ({stock_id}) 最新財報新聞 (務必找出: 毛利率、營益率、ROE 股東權益報酬率、負債權益比) 以及 {target_year} 法人預測 EPS 與 最新目標價"}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "tools": [{"google_search": {}}]
    }
    try:
        res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=20)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            clean_text = re.sub(r'```json\n?|```', '', text).strip()
            return json.loads(clean_text)
    except: pass
    return None

@st.cache_data(ttl=86400)
def get_peers_from_ai(stock_name, stock_id, api_key):
    if not api_key: return []
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key.strip()}"
    payload = {"contents": [{"parts": [{"text": f"請尋找 {stock_name} ({stock_id}) 的同業競爭對手"}]}], "systemInstruction": {"parts": [{"text": "請列出與目標公司核心業務最直接競爭的 3~5 家台股上市櫃公司代號。必須是純數字 JSON 陣列格式：[\"2383\", \"3044\"]。絕對不要輸出其他文字。"}]}}
    try:
        res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=15)
        if res.status_code == 200:
            clean_text = re.sub(r'```json\n?|```', '', res.json()['candidates'][0]['content']['parts'][0]['text']).strip()
            peers = json.loads(clean_text)
            if isinstance(peers, list): return [str(p) for p in peers][:4] 
    except: pass
    return []

def get_ai_industry_analysis(stock_name, stock_id, api_key, context_data, model_name="gemini-2.5-flash"):
    if not api_key: return "ERROR: 未輸入金鑰"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key.strip()}"
    system_prompt = """你是一位精通台股的資深產業分析師與操盤手。請針對目標公司的最新動態、財報與法說會提供分析。必須包含：1. 產業前景、2. 競爭優勢、3. 總體經濟與地緣政治系統風險評估(如中東局勢、通膨、關稅對該公司的近期影響)、4. 具體買賣點策略。請用 Markdown 格式與 Emoji。不要輸出 HTML。"""
    payload = {"contents": [{"parts": [{"text": f"請深度分析台股 {stock_name} ({stock_id})。關鍵數據：\n{context_data}"}]}], "systemInstruction": {"parts": [{"text": system_prompt}]}, "tools": [{"google_search": {}}]}
    try:
        res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=90)
        fallback_msg = ""
        if res.status_code == 404 and model_name != "gemini-2.5-flash":
            fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key.strip()}"
            res = requests.post(fallback_url, headers={"Content-Type": "application/json"}, json=payload, timeout=90)
            fallback_msg = f"> 💡 **系統提示**：您指定的 `{model_name}` 尚未開放或輸入錯誤，系統已自動降級使用 `Gemini 2.5 Flash` 為您完成分析。\n\n---\n\n"
        if res.status_code == 200: 
            ans = re.sub(r'```markdown\n?|```', '', res.json().get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')).strip()
            return fallback_msg + ans
        elif res.status_code == 429: return "⏳ API 呼叫太頻繁，請稍候再試或切換回 Flash 模型。"
        else: return f"⚠️ API 連線失敗 (狀態碼: {res.status_code})"
    except Exception as e: return f"連線異常: {str(e)}"

def get_ai_analysis_final(topic, api_key, model_name="gemini-2.5-flash"):
    if not api_key: return "ERROR: 未輸入金鑰", []
    api_key = api_key.strip()
    headers = {"Content-Type": "application/json"}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    system_prompt = """你是一位精通台股產業鏈的專業分析師。請針對議題推薦 3 檔「潛力權值股」與 3 檔「中小型飆股」。必須嚴格回傳 JSON 格式：{"reasoning": "...", "stocks": [{"id": "4位數代號", "name": "中文名稱", "type": "潛力", "why": "原因"}]}。確保代號為純數字。"""
    payload = {"contents": [{"parts": [{"text": f"請深度分析台股議題：{topic}"}]}], "systemInstruction": {"parts": [{"text": system_prompt}]}, "tools": [{"google_search": {}}], "generationConfig": {"responseMimeType": "application/json"}}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 404 and model_name != "gemini-2.5-flash":
            fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            response = requests.post(fallback_url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            res_json = response.json()
            content = res_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            clean_json = re.sub(r'```json\n?|```', '', content).strip()
            s_idx = clean_json.find('{')
            e_idx = clean_json.rfind('}')
            if s_idx != -1 and e_idx != -1: clean_json = clean_json[s_idx:e_idx+1]
            grounding = res_json.get('candidates', [{}])[0].get('groundingMetadata', {})
            links = [a.get('web', {}).get('uri') for a in grounding.get('groundingAttributions', []) if a.get('web', {}).get('uri')]
            return json.loads(clean_json), list(set(links))
        else: return f"API 錯誤 ({response.status_code})", []
    except Exception as e: return f"連線異常: {str(e)}", []

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
                    if not math.isnan(c) and not math.isnan(p) and p != 0: return c, (c - p) / p * 100
            except: pass
            return 0.0, 0.0

        sox_price, sox_pct = get_price_and_pct(tickers.tickers['^SOX'])
        tsm_price, tsm_pct = get_price_and_pct(tickers.tickers['TSM'])
        nq_price, nq_pct = get_price_and_pct(tickers.tickers['NQ=F'])
        ewt_price, ewt_pct = get_price_and_pct(tickers.tickers['EWT'])
        score = sox_pct * 0.3 + tsm_pct * 0.3 + nq_pct * 0.1 + ewt_pct * 0.3
        
        if score > 1.0: trend, color = f"🔥 極度樂觀 ({target_day}台股開盤強勢)", "#ff4d4d"
        elif score > 0.1: trend, color = f"📈 偏多看待 (有利{target_day}台股表現)", "#ff4d4d"
        elif score > -0.8: trend, color = f"↔️ 震盪整理 ({target_day}台股可能平盤震盪)", "#FFD700"
        else: trend, color = f"❄️ 悲觀警戒 ({target_day}台股面臨回檔壓力)", "#00cc66"
            
        return {"sox_p": sox_price, "sox": sox_pct, "tsm_p": tsm_price, "tsm": tsm_pct, "nq_p": nq_price, "nq": nq_pct, "ewt_p": ewt_price, "ewt": ewt_pct, "trend": trend, "color": color, "target_day": target_day, "time_status": time_status}
    except: return None

# --- 數據獲取引擎 ---
@st.cache_data(ttl=43200)
def get_monthly_revenue(stock_id):
    try:
        today = datetime.date.today()
        start_str = f"{today.year - 2}-{today.month:02d}-01"
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMonthRevenue&data_id={stock_id}&start_date={start_str}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        data = res.json()
        if data.get('status') == 200 and data.get('data'):
            df = pd.DataFrame(data['data'])
            df['date'] = pd.to_datetime(df['date'])
            current_month_start = pd.to_datetime(f"{today.year}-{today.month:02d}-01")
            df = df[df['date'] < current_month_start].sort_values('date').reset_index(drop=True)
            df['revenue'] = pd.to_numeric(df['revenue'], errors='coerce')
            
            if 'revenue_year_on_year_growth' in df.columns: df['YoY'] = pd.to_numeric(df['revenue_year_on_year_growth'], errors='coerce')
            else: df['YoY'] = df['revenue'].pct_change(periods=12) * 100
                
            df['Month'] = df['date'].dt.strftime('%Y/%m')
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
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPER&data_id={stock_id}&start_date={start_str}"
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
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=5)
        text = res.text
        def fuzzy_ext(keyword, is_pct=False):
            idx = text.find(keyword)
            if idx != -1:
                chunk = text[idx:idx+300]
                matches = re.findall(r'>\s*([+-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(%)?\s*<', chunk)
                if matches:
                    try:
                        val = float(matches[0][0].replace(',', ''))
                        if is_pct or matches[0][1] == '%': return val / 100.0
                        return val
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
def get_stock_data(stock_id, fugle_key=""):
    stock_id = str(stock_id).strip()
    hist = None
    info_data = {}
    
    if fugle_key:
        hist = fetch_fugle_kline(stock_id, fugle_key, "D")
    
    for ext in [".TW", ".TWO"]:
        try:
            ticker = yf.Ticker(f"{stock_id}{ext}")
            if hist is None or hist.empty:
                temp_hist = ticker.history(period="5y")
                if not temp_hist.empty:
                    hist = temp_hist
            try: info_data = ticker.info
            except: pass
            if info_data: break
        except: continue
            
    if hist is None or hist.empty:
        try:
            start_str = f"{(datetime.date.today() - datetime.timedelta(days=1825)).isoformat()}"
            url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id={stock_id}&start_date={start_str}"
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
        fallback = get_fallback_info(stock_id)
        for k, v in fallback.items():
            if v is not None:
                if k not in info_data or info_data[k] is None or str(info_data[k]).lower() == 'nan':
                    info_data[k] = v
        return hist, info_data
    return None, None

@st.cache_data(ttl=900)
def get_chart_data(stock_id, timeframe, fugle_key=""):
    stock_id = str(stock_id).strip()
    tf_map = {"日線": "D", "週線": "W", "月線": "M", "60分線": "60"}
    
    if fugle_key:
        tf = tf_map.get(timeframe, "D")
        df = fetch_fugle_kline(stock_id, fugle_key, tf)
        if not df.empty: return df

    interval_map = {"日線": {"period": "1y", "interval": "1d"}, "週線": {"period": "2y", "interval": "1wk"}, "月線": {"period": "5y", "interval": "1mo"}, "60分線": {"period": "1mo", "interval": "60m"}}
    params = interval_map.get(timeframe, {"period": "1y", "interval": "1d"})
    for ext in [".TW", ".TWO"]:
        try:
            ticker = yf.Ticker(f"{stock_id}{ext}")
            df = ticker.history(period=params["period"], interval=params["interval"])
            if not df.empty:
                if df.index.tz is not None: df.index = df.index.tz_localize(None)
                return df
        except: continue
    return pd.DataFrame()

# 🌟 極度容錯版：取得法人買賣超資料
@st.cache_data(ttl=43200)
def get_inst_data(stock_id):
    try:
        today = datetime.date.today()
        start_str = (today - datetime.timedelta(days=180)).strftime("%Y-%m-%d")
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={stock_id}&start_date={start_str}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        data = res.json()
        
        # 確認 API 有正常回傳，且 data 裡面真的有東西
        if data.get('status') == 200 and data.get('data'):
            df = pd.DataFrame(data['data'])
            if df.empty: return pd.DataFrame()
            
            df['date'] = pd.to_datetime(df['date'])
            
            # 🚀 暴力防呆：處理各種可能的欄位缺失狀況
            if 'buy_sell' not in df.columns:
                if 'buy' not in df.columns: df['buy'] = 0
                if 'sell' not in df.columns: df['sell'] = 0
                df['buy'] = pd.to_numeric(df['buy'], errors='coerce').fillna(0)
                df['sell'] = pd.to_numeric(df['sell'], errors='coerce').fillna(0)
                df['buy_sell'] = df['buy'] - df['sell']
            else:
                df['buy_sell'] = pd.to_numeric(df['buy_sell'], errors='coerce').fillna(0)
            
            pivot_df = df.pivot_table(index='date', columns='name', values='buy_sell', aggfunc='sum').fillna(0)
            res_df = pd.DataFrame(index=pivot_df.index)
            
            # 模糊比對欄位名稱，避免中英文變更
            f_cols = [c for c in pivot_df.columns if '外資' in str(c) or 'Foreign' in str(c)]
            t_cols = [c for c in pivot_df.columns if '投信' in str(c) or 'Trust' in str(c)]
            d_cols = [c for c in pivot_df.columns if '自營商' in str(c) or 'Dealer' in str(c)]
            
            res_df['Foreign'] = pivot_df[f_cols].sum(axis=1) if f_cols else 0
            res_df['Trust'] = pivot_df[t_cols].sum(axis=1) if t_cols else 0
            res_df['Dealer'] = pivot_df[d_cols].sum(axis=1) if d_cols else 0
            return res_df / 1000 # 轉換為張數
    except: pass
    
    return pd.DataFrame() # 只要出錯一律安靜回傳空表

@st.cache_data(ttl=86400) 
def get_chinese_name(stock_id):
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        match = re.search(r'<title>(.*?)(?:\(| \()', res.text)
        if match: return match.group(1).strip()
    except: pass
    return None

@st.cache_data(ttl=86400)
def translate_to_zh(text):
    if not text or text == '暫無簡介。': return text
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": "en", "tl": "zh-TW", "dt": "t", "q": text}
        res = requests.get(url, params=params, timeout=5)
        return "".join([item[0] for item in res.json()[0]])
    except: return text + "\n\n(⚠️ 翻譯服務暫時忙碌中)"

# ==========================================
# 4. 側邊欄：功能選單與策略漏斗
# ==========================================
with st.sidebar:
    st.markdown("### 🔍 個股查詢")
    st.text_input("輸入台股代號", value=st.session_state.selected_stock, key="stock_input_widget", on_change=on_stock_input_change)
    
    options = ["-- 快速切換標的 --"]
    categories = {}
    current_cat = "未分類"
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
            
    st.selectbox("⚡ 快速選股名單", options, key="quick_select", on_change=on_quick_select_change)

    st.markdown("---")
    st.markdown("### 🎯 策略漏斗掃描器")
    if st.button("🔍 掃描同族群潛力股", use_container_width=True): st.session_state.run_screener = True
        
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
                    _, inf = get_stock_data(c, st.session_state.fugle_key)
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
                        results.append({'code':c,'name':n,'roe':roe,'peg_sort':p_sort,'roe_str':to_pct(roe),'peg_str':p_str})
                    time.sleep(0.5); pbar.progress((i+1)/len(target_stocks))
                pbar.empty(); results.sort(key=lambda x: (x['peg_sort'], -x['roe'] if x['roe'] else 0))
                st.markdown("<div style='background:#1e1e1e; padding:10px; border-radius:5px; border-left:4px solid #00bfff;'><b>🌟 掃描結果</b></div>", unsafe_allow_html=True)
                for res in results:
                    icon = "🔥" if res['peg_sort'] < 1.5 and res['roe'] and res['roe'] > 0.15 else "🔸"
                    st.button(f"{icon} {res['name']} ({res['code']})\nPEG: {res['peg_str']} | ROE: {res['roe_str']}", key=f"s_{res['code']}", on_click=reset_all_states_on_stock_change, args=(res['code'],), use_container_width=True)

    st.markdown("---")
    st.markdown("### 🐳 籌碼集中度追蹤")
    if st.button("🔍 掃描籌碼增持名單", use_container_width=True):
        st.session_state.show_whale = True
        st.session_state.topic_results = None
        st.session_state.show_pk = False
        st.session_state.ai_industry_result = None
        st.session_state.run_screener = False
        st.rerun()
        
    st.markdown("---")
    st.markdown("### 🧠 AI 聯網議題選股")
    topic_q = st.text_input("輸入議題 (如: 代理人AI、矽光子)")
    
    ai_model_option = st.radio("選擇 AI 大腦", [
        "Gemini 2.5 Flash", 
        "Gemini 2.5 Pro",
        "Gemini 3 Flash Preview",
        "Gemini 3.1 Flash-Lite Preview",
        "Gemini 3.1 Pro Preview (付費版)"
    ])
    st.session_state.api_key = st.text_input("🔑 Gemini API Key", type="password", value=st.session_state.api_key)
    
    if st.button("AI 實時推演分析", type="primary", use_container_width=True):
        if topic_q and st.session_state.api_key:
            if "3.1 Pro" in ai_model_option: st.session_state.selected_model = "gemini-3.1-pro-preview"
            elif "3.1 Flash-Lite" in ai_model_option: st.session_state.selected_model = "gemini-3.1-flash-lite-preview"
            elif "3 Flash" in ai_model_option: st.session_state.selected_model = "gemini-3-flash-preview"
            elif "2.5 Pro" in ai_model_option: st.session_state.selected_model = "gemini-2.5-pro"
            else: st.session_state.selected_model = "gemini-2.5-flash"
                
            st.session_state.topic_results = "LOADING"
            st.session_state.ai_industry_result = None
            st.session_state.run_screener = False
            st.rerun()
            
    st.markdown("---")
    st.markdown("### ⚔️ 產業同業 PK")
    if st.button("🤖 尋找同業競爭對手並 PK", use_container_width=True):
        if not st.session_state.api_key: st.warning("請先輸入您的 API Key。")
        else: st.session_state.show_pk = True; st.rerun()

    st.markdown("---")
    st.markdown("### 📈 進階資料源設定")
    st.session_state.fugle_key = st.text_input("🔑 Fugle (富果) API Key (選填)", type="password", value=st.session_state.fugle_key, help="輸入後將優先使用 Fugle 抓取 100% 準確的高級 K 線與報價資料")
    
    st.markdown("---")
    if st.button("🔄 重新整理快取", use_container_width=True):
        st.cache_data.clear(); st.rerun()

# ==========================================
# 5. 主畫面開始
# ==========================================
st.markdown("## 📈 台股聯網 AI 投資戰情室")

if st.session_state.topic_results == "LOADING":
    with st.spinner(f"🤖 AI 正在連線推演「{topic_q}」..."):
        data, links = get_ai_analysis_final(topic_q, st.session_state.api_key, st.session_state.get('selected_model', 'gemini-2.5-flash'))
        if isinstance(data, dict):
            st.session_state.topic_results = {"data": data, "links": links, "topic": topic_q}
            st.session_state.show_whale = False
            st.rerun()
        else:
            st.error(f"AI 解析失敗。\n\n詳細原因：{data}"); st.session_state.topic_results = None

if isinstance(st.session_state.topic_results, dict):
    t = st.session_state.topic_results
    st.markdown(f"### 💡 議題動態推演：【{t['topic']}】")
    st.info(f"**AI 深度分析：**\n{t['data'].get('reasoning', '')}")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 🛡️ 潛力權值股")
        for s in [x for x in t['data'].get('stocks', []) if x['type'] == "潛力"]:
            st.button(f"{s['name']} ({s['id']})", on_click=reset_all_states_on_stock_change, args=(s['id'],), key=f"tp_{s['id']}", use_container_width=True)
            st.caption(f"理由：{s['why']}")
    with c2:
        st.markdown("#### 🚀 爆發概念股")
        for s in [x for x in t['data'].get('stocks', []) if x['type'] != "潛力"]:
            st.button(f"{s['name']} ({s['id']})", on_click=reset_all_states_on_stock_change, args=(s['id'],), key=f"ts_{s['id']}", use_container_width=True)
            st.caption(f"理由：{s['why']}")
    if t['links']:
        with st.expander("🔗 查看 AI 參考來源"):
            for link in t['links']: st.markdown(f"- [{link}]({link})")
    st.markdown("---")

if st.session_state.show_whale:
    st.markdown("### 🐳 近兩周大戶持股比例顯著增加標的")
    whales = [("2317", "鴻海"), ("2382", "廣達"), ("1519", "華城"), ("6669", "緯穎"), ("3324", "雙鴻")]
    cols = st.columns(5)
    for idx, (code, name) in enumerate(whales):
        with cols[idx]: st.button(f"{name}\n({code})", on_click=reset_all_states_on_stock_change, args=(code,), key=f"w_{code}", use_container_width=True)
    st.markdown("---")

curr_id = st.session_state.selected_stock
if curr_id:
    with st.spinner('同步數據中...'):
        hist, info = get_stock_data(curr_id, st.session_state.fugle_key)
        if info is None: info = {}
        c_name = get_chinese_name(curr_id) or info.get('shortName', curr_id)

    if hist is not None and not hist.empty:
        
        # 🌟 動態加入/移除自選股按鈕
        col_title, col_star = st.columns([0.85, 0.15])
        with col_title:
            st.markdown(f"### 🏢 {c_name} ({curr_id})")
        with col_star:
            in_watch = curr_id in get_watchlist()
            btn_label = "⭐ 移除自選" if in_watch else "☆ 加入自選"
            if st.button(btn_label, use_container_width=True):
                toggle_watchlist(curr_id, c_name)
                st.rerun()

        sector_disp = SECTOR_MAP.get(info.get('sector', '未知'), info.get('sector', '未知'))
        st.markdown(f"**🏷️ 產業分類：** {sector_disp} / {info.get('industry', '未知')}")
        with st.expander("📖 查看公司詳細營業項目簡介 (自動英翻中)"):
            st.write(translate_to_zh(info.get('longBusinessSummary', '暫無簡介。')))

        # ==========================================
        # ⚡ 即時報價
        # ==========================================
        st.markdown("#### ⚡ 即時報價與交易資訊")
        today_data = hist.iloc[-1]
        prev_data = hist.iloc[-2] if len(hist) > 1 else today_data
        
        curr_p = s_float(today_data.get('Close'), 0)
        open_p = s_float(today_data.get('Open'), 0)
        high_p = s_float(today_data.get('High'), 0)
        low_p = s_float(today_data.get('Low'), 0)
        vol_shares = s_float(today_data.get('Volume'), 0)
        
        vol_lots = int(vol_shares // 1000) if vol_shares else 0
        prev_vol_lots = int(s_float(prev_data.get('Volume'), 0) // 1000) if len(hist) > 1 else 0
        
        prev_close = s_float(info.get('previousClose'), s_float(prev_data.get('Close'), 0))
        change = curr_p - prev_close if prev_close else 0
        change_pct = (change / prev_close) * 100 if prev_close else 0
        amp = ((high_p - low_p) / prev_close) * 100 if prev_close and prev_close > 0 else 0
        avg_price = (high_p + low_p + curr_p) / 3 if curr_p else 0
        turnover_100m = (vol_shares * avg_price) / 100000000
        
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

        # ==========================================
        # 🌍 國際連動與動態時間趨勢推估
        # ==========================================
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

        # ==========================================
        # 💼 財務基本面與獲利基準微調
        # ==========================================
        col_fin_title, col_fin_btn = st.columns([0.6, 0.4])
        with col_fin_title:
            st.markdown("#### 💼 財務基本面與獲利基準微調")
        with col_fin_btn:
            if st.button("🪄 啟動 AI 全方位校對與補齊財報", disabled=not st.session_state.api_key, use_container_width=True, help="點此讓 AI 上網搜尋最新8大財報與估值指標，並與現有資料進行比對"):
                with st.spinner("AI 正在各大財經庫檢索全方位數據..."):
                    fetched_data = get_financials_from_ai(c_name, curr_id, st.session_state.api_key)
                    if fetched_data:
                        st.session_state.ai_fetched_financials[curr_id] = fetched_data
                        st.rerun()
                    else:
                        st.error("AI 暫時無法找到確切數據")
                        
        df_rev_bk = get_monthly_revenue(curr_id)
        df_per_bk = get_pe_pb_data(curr_id)
        
        # 取得系統原始數據
        pe_ratio = s_float(info.get('trailingPE'))
        if (pe_ratio is None or pe_ratio > 1000) and df_per_bk is not None and not df_per_bk.empty:
            if (pd.Timestamp.today() - df_per_bk.iloc[-1]['date']).days < 30: pe_ratio = s_float(df_per_bk['PER'].iloc[-1])
        pb_ratio = s_float(info.get('priceToBook'))
        if (pb_ratio is None or pb_ratio > 500) and df_per_bk is not None and not df_per_bk.empty and 'PBR' in df_per_bk.columns:
            pb_ratio = s_float(df_per_bk['PBR'].iloc[-1])
            
        roe = s_float(info.get('returnOnEquity'))
        
        # 🚀 負債權益比 (Yahoo 預設為百分位數如 50 代表 50%)
        sys_de = s_float(info.get('debtToEquity'))
        if sys_de is not None: sys_de = sys_de / 100.0  
        
        gross_margin = s_float(info.get('grossMargins'))
        op_margin = s_float(info.get('operatingMargins'))
        
        rev_growth = s_float(info.get('revenueGrowth'))
        if rev_growth is None and df_rev_bk is not None and not df_rev_bk.empty:
            rev_growth = s_float(df_rev_bk['YoY'].iloc[-1]) / 100.0
        earn_growth = s_float(info.get('earningsGrowth'))
        
        t_eps = s_float(info.get('trailingEps'))
        if t_eps is None and pe_ratio is not None and pe_ratio > 0 and curr_p > 0:
            t_eps = curr_p / pe_ratio
            
        sys_f_eps = s_float(info.get('forwardEps'))
        
        # 取出 AI 校對數據字典
        ai_fin = st.session_state.ai_fetched_financials.get(curr_id, {})
        ai_pe = s_float(ai_fin.get('pe'))
        ai_pb = s_float(ai_fin.get('pb'))
        ai_t_eps = s_float(ai_fin.get('trailing_eps'))
        ai_f_eps = s_float(ai_fin.get('forward_eps'))
        ai_yoy = s_float(ai_fin.get('yoy'))
        ai_gm = s_float(ai_fin.get('gross_margin'))
        ai_om = s_float(ai_fin.get('operating_margin'))
        ai_roe = s_float(ai_fin.get('roe'))
        ai_de = s_float(ai_fin.get('debt_to_equity'))
        ai_target_price = s_float(ai_fin.get('target_price'))
        
        # 決定有效數值 (Fallback to AI)
        eff_pe = pe_ratio if pe_ratio is not None else ai_pe
        eff_pb = pb_ratio if pb_ratio is not None else ai_pb
        eff_t_eps = t_eps if t_eps is not None else ai_t_eps
        eff_rg = rev_growth if rev_growth is not None else ai_yoy
        eff_eg = earn_growth if earn_growth is not None else ai_yoy
        eff_gm = gross_margin if gross_margin is not None else ai_gm
        eff_om = op_margin if op_margin is not None else ai_om
        eff_roe = roe if roe is not None else ai_roe
        eff_de = sys_de if sys_de is not None else ai_de
        
        # 🚀 智慧反推與有效 Forward EPS 決策
        ai_f_eps_calc = ai_f_eps
        if ai_f_eps_calc is None and eff_t_eps is not None and eff_eg is not None and -1 <= eff_eg <= 5:
            ai_f_eps_calc = eff_t_eps * (1 + eff_eg)
            
        sys_f_eps_calc = sys_f_eps
        if sys_f_eps_calc is None and t_eps is not None and earn_growth is not None and -1 <= earn_growth <= 5:
            sys_f_eps_calc = t_eps * (1 + earn_growth)

        # 🚀 乾淨的雙欄位配置
        col_eps1, col_eps2 = st.columns([1.2, 1.5])
        with col_eps1: 
            use_custom_eps = st.toggle("切換為「自訂 / 法人共識預估 EPS」", value=False)
        with col_eps2:
            default_eps = ai_f_eps_calc if ai_f_eps_calc is not None else (sys_f_eps_calc if sys_f_eps_calc is not None else 1.0)
            custom_eps = st.number_input("輸入國內法人共識 EPS", value=s_float(default_eps, 1.0), step=0.5, disabled=not use_custom_eps)

        if use_custom_eps:
            eff_f_eps = custom_eps
            eff_cg = (eff_f_eps - eff_t_eps) / eff_t_eps if eff_t_eps and eff_t_eps > 0 else None
            eff_forward_pe = curr_p / eff_f_eps if eff_f_eps > 0 else None
            eff_peg = eff_pe / (eff_cg * 100) if eff_pe and eff_cg and eff_cg > 0 else None
            
            eg_str_disp = f"{eff_cg * 100:.2f}%" if eff_cg is not None else "N/A"
            eg_color = "#ff4d4d" if eff_cg and eff_cg > 0 else ("#00cc66" if eff_cg and eff_cg < 0 else "gray")
            eps_source_text = f"自訂法人共識 ({eff_f_eps:.2f}元)"
            peg_str_disp = f"{eff_peg:.2f}" if eff_peg is not None else "N/A"
            fpe_str = f"{eff_forward_pe:.1f}x" if eff_forward_pe is not None else "N/A"
            
            pe_str = build_cmp_str(pe_ratio, ai_pe, 'x')
            f_eps_display = build_cmp_dual_str(t_eps, eff_f_eps, ai_t_eps, None, 'num', 'num', 'AI捉取')
        else:
            eff_f_eps = sys_f_eps_calc if sys_f_eps_calc is not None else ai_f_eps_calc
            eps_source_text = f"海外系統或反推 ({eff_f_eps:.2f}元)" if eff_f_eps is not None else "系統預估 (無資料)"
            f_eps_display = build_cmp_dual_str(t_eps, sys_f_eps_calc, ai_t_eps, ai_f_eps_calc, 'num', 'num', 'AI推/捉')
            
            sys_forward_pe = s_float(info.get('forwardPE'))
            if sys_forward_pe is None and eff_f_eps is not None and eff_f_eps > 0: sys_forward_pe = curr_p / eff_f_eps
            
            ai_fpe = curr_p / ai_f_eps_calc if ai_f_eps_calc and ai_f_eps_calc > 0 else None
            eff_forward_pe = sys_forward_pe if sys_forward_pe is not None else ai_fpe
            
            # 🚀 修復點：讓系統自己計算「真實隱含成長率」，不再被傳統資料庫誤導！
            if eff_f_eps is not None and t_eps is not None and t_eps > 0:
                real_cg = (eff_f_eps - t_eps) / t_eps
            else:
                real_cg = earn_growth
            
            orig_peg = pe_ratio / (real_cg * 100) if pe_ratio is not None and real_cg is not None and real_cg > 0 else None
            
            ai_cg = (ai_f_eps_calc - ai_t_eps) / ai_t_eps if ai_t_eps and ai_t_eps > 0 and ai_f_eps_calc else ai_yoy
            ai_peg = ai_pe / (ai_cg * 100) if ai_pe and ai_cg and ai_cg > 0 else None
            
            eff_peg = orig_peg if orig_peg is not None else ai_peg
            if real_cg is not None and real_cg <= 0: eff_peg = -999
            
            # 更新畫面顯示為真實的反推成長率
            eg_str_disp = build_cmp_str(real_cg, ai_yoy, 'pct', 'AI反推')
            eg_color = "#ff4d4d" if real_cg and real_cg > 0 else ("#00cc66" if real_cg and real_cg < 0 else "#fff")
            
            orig_peg_str = f"{orig_peg:.2f}" if orig_peg is not None else ("分母為負" if real_cg is not None and real_cg <= 0 else "N/A")
            peg_str_disp = f"{orig_peg_str}<br><span style='color:#FFD700; font-size:0.85rem;'>({ai_peg:.2f}, AI反推)</span>" if ai_peg is not None else orig_peg_str
            
            orig_fpe_str = f"{sys_forward_pe:.1f}x" if sys_forward_pe is not None else "N/A"
            fpe_str = f"{orig_fpe_str}<br><span style='color:#FFD700; font-size:0.85rem;'>({ai_fpe:.1f}x, AI反推)</span>" if ai_fpe is not None else orig_fpe_str
            
            pe_str = build_cmp_str(pe_ratio, ai_pe, 'x')

        rg_str = build_cmp_str(rev_growth, ai_yoy, 'pct')
        gm_om_str = build_cmp_dual_str(gross_margin, op_margin, ai_gm, ai_om, 'pct', 'pct', 'AI捉取')
        roe_str = build_cmp_str(roe, ai_roe, 'pct')
        de_str = build_cmp_str(sys_de, ai_de, 'pct')
        
        rg_color = "#ff4d4d" if eff_rg and eff_rg > 0 else ("#00cc66" if eff_rg and eff_rg < 0 else "#fff")
        roe_eval = " <span style='color:#00cc66; font-size:0.8rem; margin-left:5px;' title='大於15%視為資金運用效率極佳'>⭐ 優質</span>" if eff_roe is not None and eff_roe >= 0.15 else ""
        
        if eff_de is None:
            de_eval = ""
        elif eff_de < 0.5:
            de_eval = " <span style='color:#00cc66; font-size:0.8rem; margin-left:5px;' title='小於50%財務極度穩健'>⭐ 優質</span>"
        elif eff_de > 1.0:
            de_eval = " <span style='color:#ff4d4d; font-size:0.8rem; margin-left:5px;' title='大於100%視為高槓桿風險'>⚠️ 高槓桿</span>"
        else:
            de_eval = " <span style='color:#FFD700; font-size:0.8rem; margin-left:5px;' title='50%~100%為資本密集產業常見合理區間'>🆗 合理</span>"

        # 🚀 在畫面上加入第 7 格：負債權益比
        fund_html = f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 20px;'>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>歷史本益比 (P/E)</div><div style='font-size:1.3rem; font-weight:bold; color:#fff;'>{pe_str}</div></div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>EPS (目前 / 預估)</div><div style='font-size:1.3rem; font-weight:bold; color:#FFD700;'>{f_eps_display}</div></div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>營收年增率 (YoY)</div><div style='font-size:1.3rem; font-weight:bold; color:{rg_color};'>{rg_str}</div></div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>預估獲利成長 (YoY)</div><div style='font-size:1.3rem; font-weight:bold; color:{eg_color};'>{eg_str_disp}</div></div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>毛利率 / 營益率</div><div style='font-size:1.3rem; font-weight:bold; color:#fff;'>{gm_om_str}</div></div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>ROE (權益報酬率)</div><div style='font-size:1.3rem; font-weight:bold; color:#00bfff;'>{roe_str}{roe_eval}</div></div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>負債權益比 (D/E)</div><div style='font-size:1.3rem; font-weight:bold; color:#fff;'>{de_str}{de_eval}</div></div>
        </div>
        """
        st.markdown(fund_html, unsafe_allow_html=True)

        if eff_pe is None: pe_color, pe_text = "gray", "數據不足"
        elif eff_pe > 25: pe_color, pe_text = "#ff4d4d", "高成長溢價"
        elif eff_pe < 15: pe_color, pe_text = "#00cc66", "相對便宜"
        else: pe_color, pe_text = "#FFD700", "合理區間"

        if eff_pb is None: pb_color, pb_text = "gray", "數據不足"
        elif eff_pb > 3: pb_color, pb_text = "#ff4d4d", "偏高溢價"
        elif eff_pb < 1.5: pb_color, pb_text = "#00cc66", "具資產保護"
        else: pb_color, pb_text = "#FFD700", "合理區間"

        if eff_peg == -999: peg_color, peg_text = "gray", "分母為負，無意義"
        elif eff_peg is None: peg_color, peg_text = "gray", "衰退或無數據"
        else: 
            if eff_peg > 2: peg_color, peg_text = "#ff4d4d", "透支未來成長"
            elif eff_peg <= 1: peg_color, peg_text = "#00cc66", "低估 (成長性支撐)"
            else: peg_color, peg_text = "#FFD700", "合理區間"

        if eff_forward_pe is None: fpe_color, fpe_text = "gray", "數據不足"
        else:
            if eff_forward_pe > 25: fpe_color, fpe_text = "#ff4d4d", "高成長期望"
            elif eff_forward_pe < 15: fpe_color, fpe_text = "#00cc66", "相對便宜"
            else: fpe_color, fpe_text = "#FFD700", "合理區間"

        pb_str = build_cmp_str(pb_ratio, ai_pb, 'x')

        val_html = f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-bottom:20px;'>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {pe_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>📊 歷史本益比 (Trailing P/E)</div><div style='background:{pe_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{pe_text}</div>
                </div>
                <div style='font-size:1.6rem; font-weight:bold; color:#fff; margin-bottom:10px;'>{pe_str}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {fpe_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🚀 前瞻本益比 (Forward P/E)</div><div style='background:{fpe_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{fpe_text}</div>
                </div>
                <div style='font-size:1.6rem; font-weight:bold; color:#fff; margin-bottom:5px;'>{fpe_str}</div>
                <div style='color:#ffd700; font-size:0.85rem; font-weight:bold;'>基準：{eps_source_text}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {peg_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>📈 本益成長比 (PEG)</div><div style='background:{peg_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{peg_text}</div>
                </div>
                <div style='font-size:1.6rem; font-weight:bold; color:#fff; margin-bottom:10px;'>{peg_str_disp}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {pb_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🏦 股價淨值比 (P/B Ratio)</div><div style='background:{pb_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{pb_text}</div>
                </div>
                <div style='font-size:1.6rem; font-weight:bold; color:#fff; margin-bottom:10px;'>{pb_str}</div>
            </div>
        </div>
        """
        st.markdown(val_html, unsafe_allow_html=True)
        st.markdown("---")

        # ==========================================
        # 🚀 月營收圖表
        # ==========================================
        if df_rev_bk is not None and not df_rev_bk.empty:
            st.markdown("#### 📊 近一年月營收與成長動能趨勢 (真實數據)")
            st.markdown("<small style='color:gray;'>*數據來源：自動抓取最新公告之每月營收與年增率 (YoY)*</small>", unsafe_allow_html=True)

            fig_rev = make_subplots(specs=[[{"secondary_y": True}]])
            fig_rev.add_trace(go.Bar(x=df_rev_bk['Month'], y=df_rev_bk['Revenue'], name="單月營收 (億)", marker_color='#3498db', opacity=0.8, hovertemplate="營收: %{y} 億<extra></extra>"), secondary_y=False)
            fig_rev.add_trace(go.Scatter(x=df_rev_bk['Month'], y=df_rev_bk['YoY'], name="YoY (%)", mode='lines+markers', line=dict(color='#ff4d4d', width=3), marker=dict(size=8, symbol='circle'), hovertemplate="YoY: %{y}%<extra></extra>"), secondary_y=True)

            fig_rev.update_layout(
                height=400, template="plotly_dark", hovermode="x unified",
                margin=dict(l=10, r=10, t=50, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
            )
            fig_rev.update_yaxes(title_text="營收金額 (億)", secondary_y=False, showgrid=False)
            fig_rev.update_yaxes(title_text="年增率 YoY (%)", secondary_y=True, showgrid=True, gridcolor='#333', zeroline=True, zerolinewidth=1, zerolinecolor='#555')
            fig_rev.update_xaxes(type='category')

            st.plotly_chart(fig_rev, use_container_width=True)
            st.markdown("---")

        # ==========================================
        # 🚀 產業前景與競爭優勢評估 (Moat / Trend cards)
        # ==========================================
        st.markdown("#### 🌟 產業前景與競爭優勢評估", unsafe_allow_html=True)
        st.markdown("<small style='color:gray;'>*註：下方為客觀數據推導。您可點擊 AI 按鈕進行聯網深度檢索與買賣點分析。*</small>", unsafe_allow_html=True)

        hot_industries = ['Semiconductor', 'Software', 'Hardware', 'Electronic', 'IT Services', 'Communication', 'Technology']
        is_hot = any(hot in sector_disp for hot in hot_industries) or any(hot in info.get('industry', '未知') for hot in hot_industries)
        
        if is_hot:
            trend_icon, trend_title, trend_desc, trend_color = "🚀", "長線成長大趨勢", f"所屬板塊 ({info.get('industry', '未知')}) 涵蓋高階運算、AI 應用或資料中心等剛性需求，具備長期市場成長潛力。", "#ff4d4d"
        else:
            trend_icon, trend_title, trend_desc, trend_color = "🏭", "穩定或景氣循環產業", f"所屬板塊 ({info.get('industry', '未知')}) 發展相對成熟，需特別留意整體景氣波動或公司的特殊利基點。", "#FFD700"

        if eff_gm is None:
            moat_icon, moat_title, moat_desc, moat_color = "❓", "數據不足", "缺乏毛利率數據無法精確評估。", "gray"
        elif eff_gm >= 0.40:
            moat_icon, moat_title, moat_desc, moat_color = "🏰", "極寬廣 (強大護城河)", f"毛利率高達 {eff_gm*100:.1f}%！顯示公司具備極高的技術門檻、專利佈局或客戶轉換成本，對手極難搶奪市佔率。", "#ff4d4d"
        elif eff_gm >= 0.20:
            moat_icon, moat_title, moat_desc, moat_color = "🛡️", "中等壁壘", f"毛利率 {eff_gm*100:.1f}%。具備一定的技術領先或營運規模，存在競爭壁壘。", "#FFD700"
        else:
            moat_icon, moat_title, moat_desc, moat_color = "⚔️", "競爭激烈 (低護城河)", f"毛利率僅 {eff_gm*100:.1f}%。產品同質性偏高，容易落入價格戰，無法輕易阻擋對手跨入。", "#00cc66"

        if eff_om is None:
            pos_icon, pos_title, pos_desc, pos_color = "❓", "數據不足", "缺乏營益率數據無法精確評估。", "gray"
        elif eff_om >= 0.15:
            pos_icon, pos_title, pos_desc, pos_color = "👑", "核心主導者 (具定價權)", f"營益率高達 {eff_om*100:.1f}%。在產業鏈中掌握關鍵零組件、設備或 IP 設計，景氣波動時具備高度抗跌能力與話語權。", "#ff4d4d"
        elif eff_om >= 0.05:
            pos_icon, pos_title, pos_desc, pos_color = "⚙️", "關鍵供應商", f"營益率 {eff_om*100:.1f}%。在整體供應鏈中扮演不可或缺的一環，營運與定價能力相對穩健。", "#FFD700"
        else:
            pos_icon, pos_title, pos_desc, pos_color = "📦", "弱勢地位 (低階代工/組裝)", f"營益率僅 {eff_om*100:.1f}%。毛利微薄且被成本擠壓，在供應鏈中缺乏定價權，極易受原物料上漲與終端砍單衝擊。", "#00cc66"

        st.markdown(f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-top:10px;'>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {trend_color};'>
                <div style='font-size:1.1rem; font-weight:bold; color:#fff; margin-bottom:8px;'>{trend_icon} 市場趨勢</div>
                <div style='color:{trend_color}; font-weight:bold; margin-bottom:5px;'>{trend_title}</div>
                <div style='color:#aaa; font-size:0.9rem; line-height:1.5;'>{trend_desc}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {moat_color};'>
                <div style='font-size:1.1rem; font-weight:bold; color:#fff; margin-bottom:8px;'>{moat_icon} 護城河 (競爭壁壘)</div>
                <div style='color:{moat_color}; font-weight:bold; margin-bottom:5px;'>{moat_title}</div>
                <div style='color:#aaa; font-size:0.9rem; line-height:1.5;'>{moat_desc}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {pos_color};'>
                <div style='font-size:1.1rem; font-weight:bold; color:#fff; margin-bottom:8px;'>{pos_icon} 供應鏈地位</div>
                <div style='color:{pos_color}; font-weight:bold; margin-bottom:5px;'>{pos_title}</div>
                <div style='color:#aaa; font-size:0.9rem; line-height:1.5;'>{pos_desc}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("---")

        # ==========================================
        # 🚀 法人預估目標價 (系統原始數據 vs AI聯網捕捉)
        # ==========================================
        hi_val = s_float(info.get('targetHighPrice'))
        me_val = s_float(info.get('targetMeanPrice'))
        lo_val = s_float(info.get('targetLowPrice'))
        ai_target_price = s_float(st.session_state.ai_fetched_financials.get(curr_id, {}).get('target_price'))

        st.markdown(f"#### 🎯 法人預估目標價 (分析師統計：{info.get('numberOfAnalystOpinions', 0)} 位)")
        
        if hi_val is not None and me_val is not None and lo_val is not None:
            v1, v2, v3 = st.columns(3)
            v1.markdown(f"<div style='background:#ffebee;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人最高預期</small><br><b>{hi_val:.1f}</b></div>", unsafe_allow_html=True)
            upside = ((me_val / curr_p) - 1) * 100 if curr_p else 0
            v2.markdown(f"<div style='background:#fff3e0;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>平均預測</small><br><b>{me_val:.1f}</b><br><small>空間: {upside:+.1f}%</small></div>", unsafe_allow_html=True)
            v3.markdown(f"<div style='background:#e8f5e9;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人最低保底</small><br><b>{lo_val:.1f}</b></div>", unsafe_allow_html=True)
            if ai_target_price: st.info(f"🤖 **AI 最新聯網捕捉法人目標價：** {ai_target_price:.1f} 元")
            st.markdown("---")
            
        elif hi_val is not None:
             st.info(f"系統法人最高預期：**{hi_val:.1f}**")
             if ai_target_price: st.info(f"🤖 **AI 最新聯網捕捉法人目標價：** {ai_target_price:.1f} 元")
             st.markdown("---")
             
        elif ai_target_price:
             upside_ai = ((ai_target_price / curr_p) - 1) * 100 if curr_p else 0
             st.markdown(f"<div style='background:#fff3e0;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>🤖 AI 聯網捕捉最新目標價</small><br><b>{ai_target_price:.1f}</b><br><small>潛在空間: {upside_ai:+.1f}%</small></div>", unsafe_allow_html=True)
             st.markdown("---")
        else:
             st.markdown("<span style='color:gray;'>系統與 AI 目前皆無明確的法人目標價資料。</span>", unsafe_allow_html=True)
             st.markdown("---")

        # ==========================================
        # 🚀 籌碼面與股權結構分析
        # ==========================================
        st.markdown("#### 🐳 籌碼面與股權結構分析", unsafe_allow_html=True)
        insider_pct = s_float(info.get('heldPercentInsiders'))
        inst_pct = s_float(info.get('heldPercentInstitutions'))
        shares_out = s_float(info.get('sharesOutstanding'))
        share_capital = shares_out * 10 if shares_out is not None else None

        if share_capital is not None:
            if share_capital >= 10_000_000_000:
                cap_type, driver, cap_color, driver_desc = "大型權值股", "🌍 外資主導", "#4169E1", f"股本約 {share_capital/100000000:.0f} 億。籌碼龐大，走勢受外資資金影響大。"
            elif share_capital <= 3_000_000_000:
                cap_type, driver, cap_color, driver_desc = "中小型飆股", "🔥 投信/內資主力", "#ff8c00", f"股本約 {share_capital/100000000:.0f} 億。籌碼輕薄，易受投信作帳帶動。"
            else:
                cap_type, driver, cap_color, driver_desc = "中型中堅股", "🤝 土洋共議", "#9370DB", f"股本約 {share_capital/100000000:.0f} 億。出現土洋合作易有波段行情。"
        else:
            cap_type, driver, cap_color, driver_desc = "無資料", "未知", "gray", "無法獲取股本資料"

        inst_str = to_pct(inst_pct)
        inst_color, inst_eval = ("#ff4d4d", "高度集中 (留意結帳)") if inst_pct is not None and inst_pct > 0.40 else ("#FFD700", "穩定認可") if inst_pct is not None and inst_pct > 0.15 else ("#00bfff", "內資/散戶主導") if inst_pct is not None else ("gray", "數據不足")

        insider_str = to_pct(insider_pct)
        in_color, in_eval = ("#ff4d4d", "籌碼極度安定") if insider_pct is not None and insider_pct > 0.40 else ("#FFD700", "相對穩健") if insider_pct is not None and insider_pct > 0.20 else ("#00cc66", "籌碼較渙散 (警戒)") if insider_pct is not None else ("gray", "數據不足")

        chip_html = f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-top:10px;'>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {inst_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🏦 三大法人持股率</div>
                    <div style='background:{inst_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{inst_eval}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:5px;'>{inst_str}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {in_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🏢 內部人與大股東持股</div>
                    <div style='background:{in_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{in_eval}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:5px;'>{insider_str}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {cap_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🎯 控盤主力推估</div>
                    <div style='background:{cap_color}; color:#fff; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{cap_type}</div>
                </div>
                <div style='font-size:1.3rem; font-weight:bold; color:{cap_color}; margin-bottom:10px;'>{driver}</div>
                <div style='color:#aaa; font-size:0.85rem; line-height:1.5;'>{driver_desc}</div>
            </div>
        </div>
        """
        st.markdown(chip_html, unsafe_allow_html=True)
        st.markdown("---")

        # ==========================================
        # 🚀 AI 綜合產業報告與打包提示詞
        # ==========================================
        hi_str = f"{hi_val:.1f}" if hi_val else "無資料"
        me_str = f"{me_val:.1f}" if me_val else "無資料"
        lo_str = f"{lo_val:.1f}" if lo_val else "無資料"
        ai_tp_str = f"{ai_target_price:.1f}" if ai_target_price else "未捕捉到"

        def p_fmt(orig, ai_val, fmt="pct", suffix="AI捉取"):
            s = to_val_str(orig, fmt)
            if ai_val is not None and not pd.isna(ai_val):
                s += f" ({to_val_str(float(ai_val), fmt)}, {suffix})"
            return s
            
        def p_dual(o1, o2, a1, a2, suffix="AI捉取"):
            s = f"{to_val_str(o1, 'num')} / {to_val_str(o2, 'num')}"
            if (a1 is not None and not pd.isna(a1)) or (a2 is not None and not pd.isna(a2)):
                sa1 = to_val_str(float(a1) if a1 is not None else None, 'num')
                sa2 = to_val_str(float(a2) if a2 is not None else None, 'num')
                s += f" ({sa1} / {sa2}, {suffix})"
            return s

        ctx_pe = p_fmt(pe_ratio, ai_pe, 'x')
        ctx_pb = p_fmt(pb_ratio, ai_pb, 'x')
        ctx_rg = p_fmt(rev_growth, ai_yoy, 'pct')
        ctx_gm = p_fmt(gross_margin, ai_gm, 'pct')
        ctx_om = p_fmt(op_margin, ai_om, 'pct')
        ctx_roe = p_fmt(roe, ai_roe, 'pct')
        ctx_de = p_fmt(sys_de, ai_de, 'pct')
        
        # 確保隱藏提示詞中的 eg (成長率) 使用真實反推的值
        if use_custom_eps:
            ctx_fpe = f"{eff_forward_pe:.1f}x" if eff_forward_pe is not None else "N/A"
            ctx_peg = f"{eff_peg:.2f}" if eff_peg is not None else "N/A"
            ctx_eps = p_dual(t_eps, eff_f_eps, ai_t_eps, None, 'AI捉取')
            ctx_eg = f"{eff_cg * 100:.2f}%" if eff_cg is not None else "N/A"
        else:
            ctx_fpe = p_fmt(sys_forward_pe, ai_fpe, 'x', 'AI反推')
            orig_peg_num = orig_peg if orig_peg is not None else (-999 if real_cg is not None and real_cg <= 0 else None)
            if orig_peg_num == -999:
                ctx_peg = f"分母為負，無意義 ({ai_peg:.2f}, AI反推)" if ai_peg is not None else "分母為負，無意義"
            else:
                ctx_peg = p_fmt(orig_peg_num, ai_peg, 'num', 'AI反推')
            ctx_eps = p_dual(t_eps, sys_f_eps_calc, ai_t_eps, ai_f_eps_calc, 'AI推/捉')
            ctx_eg = p_fmt(real_cg, ai_yoy, 'pct', 'AI推算')

        context_str = f"""
        【即時盤面與估值 (原始數據 vs AI數據)】
        - 最新收盤價: {curr_p} 元
        - 歷史本益比 (Trailing P/E): {ctx_pe}
        - 前瞻本益比 (Forward P/E): {ctx_fpe}
        - 股價淨值比 (P/B): {ctx_pb}
        - 本益成長比 (PEG): {ctx_peg}

        【財務基本面動能 (原始數據 vs AI數據)】
        - EPS (目前 / 預估): {ctx_eps} 元
        - 營收年增率 (YoY): {ctx_rg}
        - 預估獲利成長 (YoY): {ctx_eg}
        - 毛利率: {ctx_gm}
        - 營業利益率: {ctx_om}
        - 股東權益報酬率 (ROE): {ctx_roe}
        - 負債權益比 (D/E Ratio): {ctx_de}

        【法人預估目標價】
        - 最高目標價: {hi_str}
        - 平均目標價: {me_str}
        - 最低保底價: {lo_str}
        - AI 聯網捕捉最新目標價: {ai_tp_str}
        """
        
        full_prompt_for_copy = f"""你是一位精通台股的資深產業分析師與操盤手。
請上網搜尋目標公司的最新動態、財報與法說會資訊，並「強烈參考我提供給你的最新盤面與財務估值數據」，提供以下深度分析：
1. 產業前景與趨勢判斷 (近期利多/利空、未來展望)
2. 公司競爭優勢 (護城河、市占率、核心技術)
3. 總體經濟與地緣政治系統性風險評估 (如中東局勢、通膨、關稅對該公司的近期影響)
4. 具體的買賣點建議與操作策略 (請結合我提供的基本面、本益比、目標價潛在空間與技術型態，給出具體進出場評估或價位區間參考)

請深度分析台股 {c_name} ({curr_id}) 的產業前景、競爭優勢、系統性風險及買賣點策略。

【系統已算出的最新關鍵數據，請務必納入買賣點評估考量】：\n{context_str}"""

        col_ai1, col_ai2 = st.columns([1.2, 1])
        with col_ai1:
            if st.button("🤖 啟動 AI 綜合產業與實戰操作分析", help="將結合畫面上算出的財報與目標價數據，提供深度的買賣點建議"):
                if not st.session_state.api_key: st.warning("請先於左側選單輸入您的 API Key。")
                else:
                    with st.spinner(f"AI ({st.session_state.get('selected_model', 'gemini-2.5-flash')}) 正在深度檢索最新產業動態並結合盤面數據計算買賣點..."):
                        st.session_state.ai_industry_result = get_ai_industry_analysis(c_name, curr_id, st.session_state.api_key, context_str, st.session_state.get('selected_model', 'gemini-2.5-flash'))
        
        with col_ai2:
            with st.expander("📋 若 API 額度耗盡？點此複製【打包提示詞】手動發問"):
                st.markdown("<small style='color:gray;'>*點擊下方黑框右上角的 📋 複製圖示，直接貼至付費版 Gemini Advanced 或是 ChatGPT 對話框，即可獲得同等專業的分析！*</small>", unsafe_allow_html=True)
                st.code(full_prompt_for_copy, language="text")
        
        if st.session_state.ai_industry_result:
            st.markdown("<br>", unsafe_allow_html=True)
            with st.container(border=True):
                col1, col2 = st.columns([0.7, 0.3])
                with col1: st.markdown("### 🤖 AI 綜合產業透視與實戰策略")
                with col2: st.markdown("<div style='text-align:right; margin-top:20px;'><small style='color:#00bfff;'>💡 往下捲動有【一鍵複製區塊】</small></div>", unsafe_allow_html=True)
                st.markdown(st.session_state.ai_industry_result)
                st.markdown("---")
                st.markdown("##### 📋 【純文字複製區】")
                st.markdown("<small style='color:gray;'>*將游標移至下方黑框內，點擊右上角的「📋」圖示，即可將報告全文複製，貼至 Gemini Advanced 進行二次深度驗證。*</small>", unsafe_allow_html=True)
                st.code(st.session_state.ai_industry_result, language="markdown")
            st.markdown("<br>", unsafe_allow_html=True)
            
        st.markdown("---")

        # 產業 PK
        if st.session_state.show_pk:
            st.markdown("#### ⚔️ 產業橫向對比 (同業估值與利潤率 PK)")
            st.markdown("<small style='color:gray;'>*註：透過 AI 動態檢索業務相近的競爭對手，並抓取最新財報數據進行橫向比較。*</small>", unsafe_allow_html=True)
            with st.spinner("AI 正在深度檢索產業鏈與競爭對手，並同步抓取最新財報數據..."):
                peers = get_peers_from_ai(c_name, curr_id, st.session_state.api_key)
                if peers:
                    compare_list = [curr_id] + [p for p in peers if p != curr_id]
                    compare_data = []
                    for code in compare_list:
                        _, p_info = get_stock_data(code, st.session_state.fugle_key)
                        p_name = get_chinese_name(code) or code
                        if p_info:
                            pe_val = s_float(p_info.get("trailingPE"))
                            pe_fmt = f"{pe_val:.2f}x" if pe_val is not None else "N/A"
                            gm_fmt = to_pct(s_float(p_info.get('grossMargins')))
                            om_fmt = to_pct(s_float(p_info.get('operatingMargins')))
                            roe_fmt = to_pct(s_float(p_info.get('returnOnEquity')))
                            prev_close_val = s_float(p_info.get("previousClose"))
                            prev_close_fmt = f"{prev_close_val:.2f}" if prev_close_val is not None else "N/A"
                            t_eps_p = s_float(p_info.get('trailingEps'))
                            f_eps_p = s_float(p_info.get('forwardEps'))
                            t_eps_p_str = f"{t_eps_p:.2f}" if t_eps_p is not None else "N/A"
                            f_eps_p_str = f"{f_eps_p:.2f}" if f_eps_p is not None else "N/A"
                            eps_display = f"{t_eps_p_str} / <span style='color:#00bfff;'>{f_eps_p_str}</span>"
                            if prev_close_val is not None and f_eps_p is not None and f_eps_p > 0: fpe_fmt = f"<b style='color:#FFD700;'>{prev_close_val / f_eps_p:.1f}x</b>"
                            else: fpe_fmt = "<span style='color:gray;'>N/A</span>"
                            target_mean_p = s_float(p_info.get('targetMeanPrice'))
                            if target_mean_p is not None and prev_close_val is not None and prev_close_val > 0:
                                upside = ((target_mean_p - prev_close_val) / prev_close_val) * 100
                                if upside >= 25: upside_fmt = f"<span style='color:#ff4d4d; font-weight:bold;'>+{upside:.1f}%</span>"
                                elif upside > 0: upside_fmt = f"<span style='color:#00cc66;'>+{upside:.1f}%</span>"
                                else: upside_fmt = f"<span style='color:#aaa;'>{upside:.1f}%</span>"
                                target_display = f"{target_mean_p:.1f} ({upside_fmt})"
                            else: target_display = "<span style='color:gray;'>無資料</span>"
                            compare_data.append({"代號": f"{p_name} ({code})", "股價": prev_close_fmt, "前瞻 P/E": fpe_fmt, "預估 EPS": eps_display, "目標價": target_display, "毛利率": gm_fmt, "營益率": om_fmt, "ROE": roe_fmt})
                    if compare_data:
                        table_html = "<table style='width:100%; text-align:center; border-collapse: collapse; margin-top: 10px; font-size: 1.05rem; color: #e0e0e0;'><tr style='background-color:#333; color:#fff; border-bottom: 2px solid #555;'><th style='padding:12px;'>公司名稱</th><th>最新收盤價</th><th>前瞻 P/E</th><th>預估 EPS (今/明)</th><th>目標價 (潛在空間)</th><th>毛利率</th><th>營益率</th><th>ROE</th></tr>"
                        for d in compare_data:
                            row_bg = "#2c3e50" if str(curr_id) in d['代號'] else "#1e1e1e" 
                            table_html += f"<tr style='background-color:{row_bg}; border-bottom:1px solid #444;'><td style='padding:12px; color:#ffffff;'><b>{d['代號']}</b></td><td>{d['股價']}</td><td>{d['前瞻 P/E']}</td><td>{d['預估 EPS']}</td><td>{d['目標價']}</td><td>{d['毛利率']}</td><td>{d['營益率']}</td><td style='color:#00bfff;'><b>{d['ROE']}</b></td></tr>"
                        table_html += "</table>"
                        st.markdown(table_html, unsafe_allow_html=True)
                else: st.error("AI 暫時找不到明確的同業數據，或請檢查您的 API Key 額度。")
            st.markdown("---")

        # 本益比河流圖
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
                
                if current_price <= b2.iloc[-1]: pe_status, status_color = "🔥 處於歷史低估區間！(潛在買點)", "#00cc66"
                elif current_price >= b5.iloc[-1]: pe_status, status_color = "🚨 突破歷史瘋狂區間！(極度高估)", "#ff4d4d"
                elif current_price >= b4.iloc[-1]: pe_status, status_color = "⚠️ 處於歷史高估區間！(留意風險)", "#ff8c00"
                else: pe_status, status_color = "⚖️ 處於歷史合理區間", "#FFD700"

                fig_river.update_layout(height=450, margin=dict(l=10, r=10, t=50, b=10), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0), hovermode="x unified")
                fig_river.update_yaxes(title_text="股價 (元)", showgrid=True, gridcolor='#e0e0e0')

                st.markdown(f"<div style='background:#f8f9fa; border-left:4px solid {status_color}; padding:10px; border-radius:5px; margin-bottom:10px; color:#333;'>目前位階推估：<b><span style='color:{status_color};'>{pe_status}</span></b> (最新本益比約 {current_pe:.1f}x)</div>", unsafe_allow_html=True)
                st.plotly_chart(fig_river, use_container_width=True)
        st.markdown("---")

        # 🚀 專業技術線圖與 KD 指標
        st.markdown("### 🤖 專業技術線圖與量化型態分析")
        
        chart_tf = st.radio("切換 K 線週期：", ["60分線", "日線", "週線", "月線"], index=1, horizontal=True)
        
        with st.spinner(f"載入 {chart_tf} 數據中..."):
            chart_df = get_chart_data(curr_id, chart_tf, st.session_state.fugle_key)
            
        if chart_df.empty: full_df = hist.copy() 
        else: full_df = chart_df.copy()

        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col not in full_df.columns: full_df[col] = 0.0
            
        full_df['MA5'] = full_df['Close'].rolling(5).mean()
        full_df['MA10'] = full_df['Close'].rolling(10).mean()
        full_df['MA20'] = full_df['Close'].rolling(20).mean()
        full_df['MA60'] = full_df['Close'].rolling(60).mean()
        full_df['Vol_MA20'] = full_df['Volume'].rolling(20).mean()
        
        h9, l9 = full_df['High'].rolling(9).max(), full_df['Low'].rolling(9).min()
        h9_l9_diff = h9 - l9
        h9_l9_diff[h9_l9_diff == 0] = 1e-9 
        rsv = (full_df['Close'] - l9) / h9_l9_diff * 100
        
        K, D = [50], [50]
        for v in rsv.fillna(50):
            K.append(K[-1]*(2/3) + v*(1/3))
            D.append(D[-1]*(2/3) + K[-1]*(1/3))
        full_df['K'], full_df['D'] = K[1:], D[1:]
        
        plot_df = full_df.tail(120).copy()
        
        # --- 🚀 完美容錯版：加入法人籌碼資料對齊 ---
        inst_df = get_inst_data(curr_id)
        if not inst_df.empty:
            # 建立暫存日期欄位來對齊，確保不會破壞原本 K 線的 intraday 時間軸
            temp_dates = pd.to_datetime(plot_df.index).normalize()
            inst_df.index = pd.to_datetime(inst_df.index).normalize()
            
            plot_df['Foreign'] = temp_dates.map(inst_df['Foreign']).fillna(0)
            plot_df['Trust'] = temp_dates.map(inst_df['Trust']).fillna(0)
            plot_df['Dealer'] = temp_dates.map(inst_df['Dealer']).fillna(0)
        else:
            # 若資料庫斷線或回傳空表，全部設為 0，並跳出黃色警示！
            plot_df['Foreign'] = 0; plot_df['Trust'] = 0; plot_df['Dealer'] = 0
            st.warning("⚠️ 系統無法獲取三大法人買賣超數據。 (原因：免費資料庫 FinMind 限制每小時 300 次請求，您可能已達上限，請稍後再試。下方籌碼圖暫時以 0 顯示。)")
            
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

        if last_close < ma60_last: trend_status, trend_color = "⚠️ 跌破長線支撐 (趨勢轉弱)", "#00cc66"
        elif last_close > ma20_last and ma5_last > ma20_last: trend_status, trend_color = "📈 多頭強勢 (站上短中均線)", "#ff4d4d"
        elif last_close < ma20_last and ma5_last < ma20_last: trend_status, trend_color = "📉 空頭弱勢 (跌破中線)", "#00cc66"
        else: trend_status, trend_color = "↔️ 區間震盪 (方向未明)", "#ffd700"
            
        if high_vol_warning: adv_text, buy_rec, sell_rec = "🚨 【量價警訊】高檔爆出天量且跌破低點，切勿盲目接刀！", "強烈觀望", f"反彈至 {max_vol_day['High']:.2f} 逃命"
        elif last_close < ma60_last: adv_text, buy_rec, sell_rec = "📉 【趨勢轉弱】跌破長期均線，應耐心等待底部確立。", "等待站回均線", f"{ma60_last:.2f} (長線壓力)"
        elif k_last < 25 and k_last > d_last: adv_text, buy_rec, sell_rec = "📈 【技術反彈】KD 低檔黃金交叉，可嘗試逢低少量佈局。", f"現價~{support_price:.2f} 附近", f"{resist_price:.2f} (上檔壓力)"
        elif k_last > 80 and k_last < d_last: adv_text, buy_rec, sell_rec = "⚠️ 【動能轉弱】KD 高檔死亡交叉，建議適度獲利了結保住利潤。", "暫時觀望", f"現價~{resist_price:.2f} 附近"
        elif last_close > ma20_last: adv_text, buy_rec, sell_rec = "🔥 【多方格局】量價配合良好，拉回中線(20MA)有守可伺機介入。", f"{ma20_last:.2f} (中線支撐)", f"{resist_price:.2f} (近期前高)"
        else: adv_text, buy_rec, sell_rec = "❄️ 【空方格局】短線均線反壓，反彈至均線壓力區可考慮減碼。", "等待技術面打底", f"{ma20_last:.2f} (中線壓力)"

        st.markdown(f"""
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; margin-bottom:20px;'>
            <h4 style='margin-top:0; color:#fff;'>🎯 演算法量化交易策略</h4>
            <div style='display:flex; justify-content:space-between; flex-wrap:wrap; gap:10px;'>
                <div style='flex:1; min-width:120px;'><div style='color:#aaa; font-size:0.9rem;'>目前趨勢</div><div style='font-size:1.1rem; font-weight:bold; color:{trend_color};'>{trend_status}</div></div>
                <div style='flex:1; min-width:120px;'><div style='color:#aaa; font-size:0.9rem;'>下檔支撐</div><div style='font-size:1.1rem; font-weight:bold; color:#00bfff;'>{support_price:.2f}</div></div>
                <div style='flex:1; min-width:120px;'><div style='color:#aaa; font-size:0.9rem;'>上檔壓力</div><div style='font-size:1.1rem; font-weight:bold; color:#ab82ff;'>{resist_price:.2f}</div></div>
                <div style='flex:1; min-width:120px;'><div style='color:#aaa; font-size:0.9rem;'>建議買點</div><div style='font-size:1.1rem; font-weight:bold; color:#ff4d4d;'>{buy_rec}</div></div>
                <div style='flex:1; min-width:120px;'><div style='color:#aaa; font-size:0.9rem;'>建議賣點</div><div style='font-size:1.1rem; font-weight:bold; color:#00cc66;'>{sell_rec}</div></div>
            </div>
            <div style='margin-top:15px; padding-top:10px; border-top:1px dashed #444;'><span style='color:#aaa; font-size:0.9rem;'>💡 策略解析：</span><span style='color:#ffd700; font-weight:bold;'>{adv_text}</span></div>
        </div>
        """, unsafe_allow_html=True)
        
        # 🌟 將圖表從 2 層改為 3 層
        fig_k = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.5, 0.25, 0.25], vertical_spacing=0.05, specs=[[{"secondary_y": True}], [{"secondary_y": False}], [{"secondary_y": False}]])
        
        fig_k.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name='K線', increasing_line_color='#ff4d4d', decreasing_line_color='#00cc66'), row=1, col=1, secondary_y=False)
        fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA5'], mode='lines', name='5MA', line=dict(color='#00bfff', width=1.5)), row=1, col=1, secondary_y=False)
        fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA10'], mode='lines', name='10MA', line=dict(color='#ab82ff', width=1.5)), row=1, col=1, secondary_y=False)
        fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], mode='lines', name='20MA', line=dict(color='#ff8c00', width=1.5)), row=1, col=1, secondary_y=False)
        fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA60'], mode='lines', name='60MA', line=dict(color='#ffd700', width=1.5)), row=1, col=1, secondary_y=False)
        
        vol_colors = ['#ff4d4d' if c >= o else '#00cc66' for c, o in zip(plot_df['Close'], plot_df['Open'])]
        fig_k.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume']/1000, marker_color=vol_colors, name='成交量(張)', opacity=0.5), row=1, col=1, secondary_y=True)
        
        # 🌟 第二層：三大法人買賣超 (紅買綠賣)
        f_colors = ['#ff4d4d' if v > 0 else '#00cc66' for v in plot_df['Foreign']]
        t_colors = ['#ff4d4d' if v > 0 else '#00cc66' for v in plot_df['Trust']]
        d_colors = ['#ff4d4d' if v > 0 else '#00cc66' for v in plot_df['Dealer']]
        fig_k.add_trace(go.Bar(x=plot_df.index, y=plot_df['Foreign'], name='外資', marker_color=f_colors, opacity=0.8), row=2, col=1)
        fig_k.add_trace(go.Bar(x=plot_df.index, y=plot_df['Trust'], name='投信', marker_color=t_colors, opacity=0.8), row=2, col=1)
        fig_k.add_trace(go.Bar(x=plot_df.index, y=plot_df['Dealer'], name='自營商', marker_color=d_colors, opacity=0.8), row=2, col=1)

        # 🌟 第三層：KD指標往下移
        fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df['K'], mode='lines', name='K9', line=dict(color='#00bfff', width=1.5)), row=3, col=1, secondary_y=False)
        fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df['D'], mode='lines', name='D9', line=dict(color='#ff8c00', width=1.5)), row=3, col=1, secondary_y=False)
        
        max_vol = plot_df['Volume'].max() / 1000 if not plot_df['Volume'].empty else 100
        fig_k.update_yaxes(side="left", showgrid=False, showticklabels=False, range=[0, max_vol * 3.5], secondary_y=True, row=1, col=1)
        fig_k.update_yaxes(side="right", mirror=True, showline=True, linecolor='#555', secondary_y=False, row=1, col=1)
        fig_k.update_yaxes(title_text="買賣超(張)", side="right", mirror=True, showline=True, linecolor='#555', row=2, col=1)
        fig_k.update_yaxes(range=[0, 100], dtick=20, side="right", mirror=True, showline=True, linecolor='#555', row=3, col=1)
        
        if chart_tf == "60分線":
            x_fmt = "%m/%d %H:%M"
            rb = [dict(bounds=["sat", "mon"]), dict(bounds=[13.5, 9], pattern="hour")]
        elif chart_tf == "月線":
            x_fmt = "%Y/%m"
            rb = [] 
        elif chart_tf == "週線":
            x_fmt = "%Y/%m/%d"
            rb = [] 
        else: 
            x_fmt = "%m/%d"
            rb = [dict(bounds=["sat", "mon"])] 

        fig_k.update_xaxes(rangebreaks=rb, tickformat=x_fmt, showgrid=True, gridcolor='#333', mirror=True, showline=True, linecolor='#555')
        
        fig_k.update_layout(height=750, xaxis_rangeslider_visible=False, margin=dict(l=10,r=10,t=10,b=10), template="plotly_dark", hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
        st.plotly_chart(fig_k, use_container_width=True)
    else:
        st.error(f"找不到代號 {curr_id} 的資料，請確認代號是否正確或重新整理。")
