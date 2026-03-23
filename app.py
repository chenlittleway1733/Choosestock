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
            
        return json.loads(clean_json), list(set(links))
    except Exception as e:
        return f"JSON 解析失敗。", []

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
        
        df['Month'] = df['date'].dt.strftime('%Y/%m')
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
        # 🚀 同時抓取準確的股價淨值比 (PBR)
        df['PBR'] = pd.to_numeric(df.get('PBR'), errors='coerce') 
        df = df[df['PER'] > 0] 
        
        return df[['date', 'PER', 'PBR']].dropna(subset=['date', 'PER']).reset_index(drop=True)
    except Exception as e: 
        return None

# 🚀 終極重構：捨棄脆弱的 HTML，僅抓取有防護的財務比率 (%)，防範 2026 年份誤判
def get_fallback_info(stock_id):
    info = {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    domain = "tw.stock.yahoo.com"
    
    # 專門抓取財務比率專屬頁面 (利用嚴格正則表達式，且只抓 %)
    try:
        url2 = f"https://{domain}/quote/{stock_id}/financial-ratio"
        res_ratio = requests.get(url2, headers=headers, timeout=5)
        if res_ratio.status_code == 200:
            # 將 HTML 標籤徹底清除為純文字
            clean_text2 = re.sub(r'<[^>]+>', ' ', res_ratio.text)
            
            def ext_pct(labels):
                for label in labels:
                    # 嚴格規則：找到關鍵字後，只抓緊接在後面的「數字 + %」，確保不會抓到年份
                    m = re.search(rf'{label}(?:.|\n){{1,50}}?([-0-9.,]+)\s*%', clean_text2)
                    if m:
                        try:
                            val = float(m.group(1).replace(',', ''))
                            # 邏輯檢查：利潤率與 ROE 應在合理範圍 (-500% ~ 500%)
                            if -500 <= val <= 500:
                                return val / 100.0
                        except: pass
                return None
                
            # 加入多重別名，專治 KY 股財報命名
            info['grossMargins'] = ext_pct(['毛利率', '營業毛利率'])
            info['operatingMargins'] = ext_pct(['營業利益率', '營益率'])
            info['returnOnEquity'] = ext_pct(['ROE', '權益報酬率', '股東權益報酬率'])
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
                try:
                    info_data = ticker.info
                    if not isinstance(info_data, dict):
                        info_data = {}
                except:
                    pass
                break
        except:
            continue
            
    if hist is not None and not hist.empty:
        # 直接補上穩定的備援，只抓 ROE 與毛利
        if not info_data.get('returnOnEquity'):
            fallback = get_fallback_info(stock_id)
            for k, v in fallback.items():
                if v is not None:
                    info_data[k] = v
                    
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
                    if not line:
                        continue
                    
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
        except Exception as e:
            pass
            
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
                status_text = st.empty()
                
                for i, (c, n) in enumerate(target_stocks):
                    status_text.text(f"⏳ 深度解析中: {n} ({c})...")
                    _, info = get_stock_data(c)
                    
                    if info:
                        # 在掃描器中也套用無敵代理運算機制
                        df_per_bk = get_pe_pb_data(c)
                        df_rev_bk = get_monthly_revenue(c)
                        
                        fm_pe = s_float(df_per_bk['PER'].iloc[-1]) if df_per_bk is not None and not df_per_bk.empty else None
                        pe = fm_pe if fm_pe and fm_pe > 0 else s_float(info.get('trailingPE'))
                        if pe is not None and (pe < 0 or pe > 1000): pe = None
                        
                        roe = s_float(info.get('returnOnEquity'))
                        
                        rev_g = s_float(df_rev_bk['YoY'].iloc[-1]) / 100.0 if df_rev_bk is not None and not df_rev_bk.empty else None
                        eg = s_float(info.get('earningsGrowth'))
                        if eg is None and rev_g is not None: eg = rev_g
                            
                        sys_peg = s_float(info.get('pegRatio'))
                        peg = sys_peg if sys_peg is not None else (pe / (eg * 100) if pe and eg and eg > 0 else None)
                        
                        results.append({
                            'code': c,
                            'name': n,
                            'roe': roe if roe is not None else -999,
                            'peg': peg if peg is not None else 999,
                            'roe_str': f"{roe*100:.1f}%" if roe is not None else "N/A",
                            'peg_str': f"{peg:.2f}" if peg is not None else "N/A"
                        })
                    
                    time.sleep(0.8)
                    progress_bar.progress((i + 1) / len(target_stocks))
                        
                status_text.empty()
                progress_bar.empty()
                
                results.sort(key=lambda x: (x['peg'], -x['roe']))
                
                st.markdown(f"<div style='background:#1e1e1e; padding:10px; border-radius:5px; border-left:4px solid #00bfff;'><b>🌟 掃描結果排序</b></div>", unsafe_allow_html=True)
                st.markdown("<small style='color:gray;'>*點擊下方按鈕可直接切換標的*</small>", unsafe_allow_html=True)
                
                for res in results:
                    is_good = res['peg'] < 1.5 and res['roe'] > 0.15
                    icon = "🔥" if is_good else "🔸"
                    btn_label = f"{icon} {res['name']} ({res['code']})\nPEG: {res['peg_str']} | ROE: {res['roe_str']}"
                    st.button(btn_label, key=f"scr_{res['code']}", on_click=change_stock, args=(res['code'],), use_container_width=True)
        else:
            st.warning("⚠️ 目前的股票不在快速選股分類名單中，請先從上方下拉選單挑選！")

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
    
    ai_model_option = st.radio(
        "選擇 AI 推演大腦", 
        ["Gemini 2.5 Flash (快速 / 省額度)", "Gemini 2.5 Pro (深度推演 / 耗額度)"],
        help="Pro 模型邏輯更深層，但免費版 API 每分鐘僅能呼叫 2 次，請斟酌使用以免耗盡額度。"
    )
    
    st.session_state.api_key = st.text_input("🔑 Gemini API Key", type="password", value=st.session_state.api_key, help="貼入您從 Google AI Studio 複製的金鑰。")
    
    if st.button("AI 實時推演分析", type="primary", use_container_width=True):
        if topic_q:
            if not st.session_state.api_key:
                st.warning("請先輸入您的 API Key。")
            else:
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
        
        c_name = get_chinese_name(curr_id)
        if not c_name:
            c_name = info.get('shortName', curr_id)

    if hist is not None and not hist.empty:
        st.markdown(f"### 🏢 {c_name} ({curr_id})")
        sector = SECTOR_MAP.get(info.get('sector', '未知'), info.get('sector', '未知'))
        st.markdown(f"**🏷️ 產業分類：** {sector} / {info.get('industry', '未知')}")
        with st.expander("📖 查看公司詳細營業項目簡介 (自動英翻中)"):
            summary_en = info.get('longBusinessSummary', '暫無簡介。')
            if summary_en != '暫無簡介。':
                with st.spinner("背景翻譯中..."):
                    summary_zh = translate_to_zh(summary_en)
                st.write(summary_zh)
            else:
                st.write(summary_en)

        st.markdown("#### ⚡ 即時報價與交易資訊")
        today_data = hist.iloc[-1]
        prev_data = hist.iloc[-2] if len(hist) > 1 else today_data
        
        curr_p = s_float(today_data.get('Close'), 0)
        open_p = s_float(today_data.get('Open'), 0)
        high_p = s_float(today_data.get('High'), 0)
        low_p = s_float(today_data.get('Low'), 0)
        vol_shares = s_float(today_data.get('Volume'), 0)
        
        vol_lots = int(vol_shares // 1000) 
        prev_vol_lots = int(s_float(prev_data.get('Volume'), 0) // 1000) if len(hist) > 1 else 0
        
        prev_close = s_float(info.get('previousClose'), s_float(prev_data.get('Close'), 0))
        change = curr_p - prev_close if prev_close else 0
        change_pct = (change / prev_close) * 100 if prev_close else 0
        amp = ((high_p - low_p) / prev_close) * 100 if prev_close else 0
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

        st.markdown("#### 💼 財務基本面與獲利基準微調")
        
        # 🚀 終極數據還原與代理計算核心
        df_rev_backup = get_monthly_revenue(curr_id)
        df_per_backup = get_pe_pb_data(curr_id)

        # 優先相信公開資料庫 (FinMind) 的精準本益比與淨值比
        finmind_pe = s_float(df_per_backup['PER'].iloc[-1]) if df_per_backup is not None and not df_per_backup.empty else None
        finmind_pb = s_float(df_per_backup['PBR'].iloc[-1]) if df_per_backup is not None and not df_per_backup.empty and 'PBR' in df_per_backup.columns else None

        pe_ratio = finmind_pe if finmind_pe and finmind_pe > 0 else s_float(info.get('trailingPE'))
        pb_ratio = finmind_pb if finmind_pb and finmind_pb > 0 else s_float(info.get('priceToBook'))

        # 嚴密排除 HTML 爬蟲抓到的年份或不合理資料
        if pe_ratio is not None and (pe_ratio < 0 or pe_ratio > 1000): pe_ratio = None
        if pb_ratio is not None and (pb_ratio < 0 or pb_ratio > 500): pb_ratio = None
            
        roe = s_float(info.get('returnOnEquity'))
        gross_margin = s_float(info.get('grossMargins'))
        op_margin = s_float(info.get('operatingMargins'))
        
        rev_growth = s_float(df_rev_backup['YoY'].iloc[-1]) / 100.0 if df_rev_backup is not None and not df_rev_backup.empty else s_float(info.get('revenueGrowth'))
            
        earn_growth = s_float(info.get('earningsGrowth'))
        if earn_growth is None and rev_growth is not None:
            earn_growth = rev_growth # 用營收成長率代理獲利成長率
            
        t_eps = s_float(info.get('trailingEps'))
        if t_eps is not None and (t_eps > 500 or t_eps < -500): 
            t_eps = None # 消滅 2026 年份 Bug
            
        if t_eps is None and pe_ratio is not None and pe_ratio > 0 and curr_p > 0:
            t_eps = curr_p / pe_ratio # 直接用現價與 P/E 反推出 100% 正確的 EPS
            
        sys_f_eps = s_float(info.get('forwardEps'))
        if sys_f_eps is not None and (sys_f_eps > 500 or sys_f_eps < -500): 
            sys_f_eps = None
            
        if sys_f_eps is None and t_eps is not None and earn_growth is not None:
            sys_f_eps = t_eps * (1 + earn_growth) # 用當前 EPS 乘上成長率反推預估 EPS
            
        sys_forward_pe = s_float(info.get('forwardPE'))
        if sys_forward_pe is None and sys_f_eps is not None and sys_f_eps > 0:
            sys_forward_pe = curr_p / sys_f_eps
            
        sys_peg_ratio = s_float(info.get('pegRatio'))
        if sys_peg_ratio is None and pe_ratio is not None and earn_growth is not None and earn_growth > 0:
            sys_peg_ratio = pe_ratio / (earn_growth * 100)

        st.markdown("##### ⚙️ 獲利預估基準設定 (將同步更新下方數據)")
        col_eps1, col_eps2, col_eps3 = st.columns([1.2, 1.5, 1])
        with col_eps1:
            use_custom_eps = st.toggle("切換為「自訂 / 法人共識預估 EPS」", value=False)
        with col_eps3:
            if st.button("🤖 AI 自動上網尋找法人 EPS", disabled=not st.session_state.api_key, help="需在左側選單輸入 API Key"):
                with st.spinner("AI 爬文中..."):
                    fetched_val = get_eps_from_ai(c_name, curr_id, st.session_state.api_key)
                    if fetched_val is not None and fetched_val > 0:
                        st.session_state.ai_fetched_eps[curr_id] = fetched_val
                        st.success(f"抓取成功！AI 推估值約為 {fetched_val} 元")
                        st.rerun()
                    else:
                        st.error("AI 暫時找不到具體數據，請手動輸入。")
                        
        with col_eps2:
            default_eps_val = st.session_state.ai_fetched_eps.get(curr_id)
            if default_eps_val is None:
                default_eps_val = sys_f_eps if sys_f_eps is not None else (t_eps if t_eps is not None else 1.0)
            custom_eps = st.number_input("輸入國內法人共識 EPS (元)", value=s_float(default_eps_val, 1.0), step=0.5, disabled=not use_custom_eps)

        if use_custom_eps:
            active_f_eps = custom_eps
            forward_pe = curr_p / active_f_eps if active_f_eps > 0 else None
            if t_eps is not None and t_eps > 0 and pe_ratio is not None:
                custom_growth = (active_f_eps - t_eps) / t_eps
                peg_ratio = pe_ratio / (custom_growth * 100) if custom_growth > 0 else None
                eg_str = f"{custom_growth * 100:.2f}%"
                eg_color = "#ff4d4d" if custom_growth > 0 else ("#00cc66" if custom_growth < 0 else "#fff")
                eg_label = "預估獲利成長 (YoY)"
            else:
                peg_ratio = None
                eg_str = "N/A"
                eg_color = "gray"
                eg_label = "預估獲利成長 (YoY)"
            eps_source_text = f"自訂法人共識 ({active_f_eps:.2f}元)"
        else:
            active_f_eps = sys_f_eps
            forward_pe = sys_forward_pe
            peg_ratio = sys_peg_ratio
            eg_str = f"{earn_growth * 100:.2f}%" if earn_growth is not None else "N/A"
            eg_color = "#ff4d4d" if earn_growth is not None and earn_growth > 0 else ("#00cc66" if earn_growth is not None and earn_growth < 0 else "#fff")
            eg_label = "獲利年增率 (YoY)"
            eps_source_text = f"海外系統或反推 ({sys_f_eps:.2f}元)" if sys_f_eps is not None else "系統預估 (無資料)"

        def to_pct(val): return f"{val * 100:.2f}%" if val is not None else "N/A"

        pe_str = f"{pe_ratio:.1f}x" if pe_ratio is not None else "N/A"
        roe_str = to_pct(roe)
        gm_str = to_pct(gross_margin)
        om_str = to_pct(op_margin)
        rg_str = to_pct(rev_growth)
        t_eps_str = f"{t_eps:.2f}" if t_eps is not None else "N/A"
        f_eps_str = f"{active_f_eps:.2f}" if active_f_eps is not None else "N/A"
        f_eps_display = f"{t_eps_str} / <span style='color:#00bfff;'>{f_eps_str}</span>" if use_custom_eps else f"{t_eps_str} / {f_eps_str}"
        roe_eval = " <span style='color:#00cc66; font-size:0.8rem; margin-left:5px;' title='大於15%視為資金運用效率極佳'>⭐ 優質</span>" if roe is not None and roe >= 0.15 else ""
        rg_color = "#ff4d4d" if rev_growth is not None and rev_growth > 0 else ("#00cc66" if rev_growth is not None and rev_growth < 0 else "#fff")

        fund_html = f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 20px;'>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>歷史本益比 (P/E)</div>
                <div style='font-size:1.3rem; font-weight:bold; color:#fff;'>{pe_str}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>EPS (目前 / 預估)</div>
                <div style='font-size:1.3rem; font-weight:bold; color:#FFD700;'>{f_eps_display}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>營收年增率 (YoY)</div>
                <div style='font-size:1.3rem; font-weight:bold; color:{rg_color};'>{rg_str}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>{eg_label}</div>
                <div style='font-size:1.3rem; font-weight:bold; color:{eg_color};'>{eg_str}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>毛利率 / 營益率</div>
                <div style='font-size:1.3rem; font-weight:bold; color:#fff;'>{gm_str} / {om_str}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;' title='長期維持在 15% 以上通常被視為優質企業'>ROE (股東權益報酬率)</div>
                <div style='font-size:1.3rem; font-weight:bold; color:#00bfff;'>{roe_str}{roe_eval}</div>
            </div>
        </div>
        """
        st.markdown(fund_html, unsafe_allow_html=True)

        pe_color, pe_eval = ("#ff4d4d", "偏高 / 高成長溢價") if pe_ratio and pe_ratio > 25 else ("#00cc66", "相對便宜") if pe_ratio and pe_ratio < 15 else ("#FFD700", "合理區間") if pe_ratio else ("gray", "數據不足")
        pb_str = f"{pb_ratio:.2f}x" if pb_ratio is not None else "N/A"
        pb_color, pb_eval = ("#ff4d4d", "偏高溢價") if pb_ratio and pb_ratio > 3 else ("#00cc66", "具資產保護") if pb_ratio and pb_ratio < 1.5 else ("#FFD700", "合理區間") if pb_ratio else ("gray", "數據不足")
        peg_str = f"{peg_ratio:.2f}" if peg_ratio is not None else "N/A"
        peg_color, peg_eval = ("#ff4d4d", "透支未來成長") if peg_ratio and peg_ratio > 2 else ("#00cc66", "低估 (成長性支撐)") if peg_ratio and peg_ratio <= 1 else ("#FFD700", "合理區間") if peg_ratio else ("gray", "衰退或無數據")
        fpe_str = f"{forward_pe:.1f}x" if forward_pe is not None else "N/A"
        fpe_color, fpe_eval = ("#ff4d4d", "偏高 / 成長期望高") if forward_pe and forward_pe > 25 else ("#00cc66", "相對便宜") if forward_pe and forward_pe < 15 else ("#FFD700", "合理區間") if forward_pe else ("gray", "數據不足")

        val_html = f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-bottom:20px;'>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {pe_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>📊 歷史本益比 (Trailing P/E)</div>
                    <div style='background:{pe_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{pe_eval}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:10px;'>{pe_str}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {fpe_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🚀 前瞻本益比 (Forward P/E)</div>
                    <div style='background:{fpe_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{fpe_eval}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:5px;'>{fpe_str}</div>
                <div style='color:#ffd700; font-size:0.85rem; font-weight:bold;'>基準：{eps_source_text}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {peg_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>📈 本益成長比 (PEG)</div>
                    <div style='background:{peg_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{peg_eval}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:10px;'>{peg_str}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {pb_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🏦 股價淨值比 (P/B Ratio)</div>
                    <div style='background:{pb_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{pb_eval}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:10px;'>{pb_str}</div>
            </div>
        </div>
        """
        st.markdown(val_html, unsafe_allow_html=True)
        st.markdown("---")

        # 【4. 產業橫向對比 PK 表格】
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

        # 【5. 月營收與 YoY 圖表】
        df_rev = df_rev_backup
        if df_rev is not None and not df_rev.empty:
            st.markdown("#### 📊 近一年月營收與成長動能趨勢 (真實數據)")
            st.markdown("<small style='color:gray;'>*數據來源：自動抓取最新公告之每月營收與年增率 (YoY)*</small>", unsafe_allow_html=True)

            fig_rev = make_subplots(specs=[[{"secondary_y": True}]])
            fig_rev.add_trace(go.Bar(x=df_rev['Month'], y=df_rev['Revenue'], name="單月營收 (億)", marker_color='#3498db', opacity=0.8, hovertemplate="營收: %{y} 億<extra></extra>"), secondary_y=False)
            fig_rev.add_trace(go.Scatter(x=df_rev['Month'], y=df_rev['YoY'], name="YoY (%)", mode='lines+markers', line=dict(color='#ff4d4d', width=3), marker=dict(size=8, symbol='circle'), hovertemplate="YoY: %{y}%<extra></extra>"), secondary_y=True)
            
            fig_rev.update_layout(
                height=400, hovermode="x unified", 
                margin=dict(l=10, r=10, t=50, b=10), 
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
            )
            fig_rev.update_yaxes(title_text="營收金額 (億)", secondary_y=False, showgrid=False)
            fig_rev.update_yaxes(title_text="年增率 YoY (%)", secondary_y=True, showgrid=True, gridcolor='#e0e0e0', zeroline=True, zerolinewidth=1, zerolinecolor='#ccc')
            fig_rev.update_xaxes(type='category')
            
            st.plotly_chart(fig_rev, use_container_width=True)
            st.markdown("---")
        else:
            st.warning("⚠️ 目前暫時無法連線至公開庫取得月營收數據。")

        # 【6. 產業前景與競爭優勢評估】
        st.markdown("#### 🌟 產業前景與競爭優勢評估", unsafe_allow_html=True)
        st.markdown("<small style='color:gray;'>*註：下方為客觀數據推導。您可點擊 AI 按鈕進行聯網深度檢索與買賣點分析。*</small>", unsafe_allow_html=True)

        hi_val = s_float(info.get('targetHighPrice'))
        me_val = s_float(info.get('targetMeanPrice'))
        lo_val = s_float(info.get('targetLowPrice'))
        hi_str = f"{hi_val:.1f}" if hi_val else "無資料"
        me_str = f"{me_val:.1f}" if me_val else "無資料"
        lo_str = f"{lo_val:.1f}" if lo_val else "無資料"
        
        context_str = f"""
        【即時盤面與估值】
        - 最新收盤價: {curr_p} 元
        - 歷史本益比 (Trailing P/E): {pe_str}
        - 前瞻本益比 (Forward P/E): {fpe_str}
        - 股價淨值比 (P/B): {pb_str}
        - 本益成長比 (PEG): {peg_str}
        
        【財務基本面動能】
        - 預估 EPS: {active_f_eps} 元
        - 營收年增率 (YoY): {rg_str}
        - 毛利率: {gm_str}
        - 營業利益率: {om_str}
        - 股東權益報酬率 (ROE): {roe_str}
        
        【法人預估目標價】
        - 最高目標價: {hi_str}
        - 平均目標價: {me_str}
        - 最低保底價: {lo_str}
        """

        current_model = "gemini-2.5-pro" if "Pro" in ai_model_option else "gemini-2.5-flash"
        
        full_prompt_for_copy = f"""你是一位精通台股的資深產業分析師與操盤手。
請上網搜尋目標公司的最新動態、財報與法說會資訊，並「強烈參考我提供給你的最新盤面與財務估值數據」，提供以下深度分析：
1. 產業前景與趨勢判斷 (近期利多/利空、未來展望)
2. 公司競爭優勢 (護城河、市占率、核心技術)
3. 具體的買賣點建議與操作策略 (請結合我提供的基本面、本益比、目標價潛在空間與技術型態，給出具體進出場評估或價位區間參考)

請深度分析台股 {c_name} ({curr_id}) 的產業前景、競爭優勢及買賣點策略。

【系統已算出的最新關鍵數據，請務必納入買賣點評估考量】：\n{context_str}"""

        col_ai1, col_ai2 = st.columns([1.2, 1])
        with col_ai1:
            if st.button("🤖 啟動 AI 深度產業與操作分析 (聯網推演)", help="將結合畫面上算出的財報與目標價數據，提供深度的買賣點建議"):
                if not st.session_state.api_key:
                    st.warning("請先於左側選單輸入您的 API Key。")
                else:
                    with st.spinner(f"AI ({current_model}) 正在深度檢索最新產業動態並結合盤面數據計算買賣點..."):
                        st.session_state.ai_industry_result = get_ai_industry_analysis(c_name, curr_id, st.session_state.api_key, context_str, current_model)
        
        with col_ai2:
            with st.expander("📋 若 API 額度耗盡？點此複製【打包提示詞】手動發問"):
                st.markdown("<small style='color:gray;'>*點擊下方黑框右上角的 📋 複製圖示，直接貼至付費版 Gemini Advanced 或是 ChatGPT 對話框，即可獲得同等專業的分析！*</small>", unsafe_allow_html=True)
                st.code(full_prompt_for_copy, language="text")
        
        if st.session_state.ai_industry_result:
            st.markdown("<br>", unsafe_allow_html=True)
            with st.container(border=True):
                col1, col2 = st.columns([0.7, 0.3])
                with col1:
                    st.markdown("### 🤖 AI 產業透視與實戰策略")
                with col2:
                    st.markdown("<div style='text-align:right; margin-top:20px;'><small style='color:#00bfff;'>💡 往下捲動有【一鍵複製區塊】</small></div>", unsafe_allow_html=True)
                
                st.markdown(st.session_state.ai_industry_result)
                
                st.markdown("---")
                st.markdown("##### 📋 【純文字複製區】")
                st.markdown("<small style='color:gray;'>*將游標移至下方黑框內，點擊右上角的「📋」圖示，即可將報告全文複製，貼至 Gemini Advanced 進行二次深度驗證。*</small>", unsafe_allow_html=True)
                st.code(st.session_state.ai_industry_result, language="markdown")
                    
            st.markdown("<br>", unsafe_allow_html=True)

        hot_industries = ['Semiconductor', 'Software', 'Hardware', 'Electronic', 'IT Services', 'Communication', 'Technology']
        is_hot = any(hot in sector for hot in hot_industries) or any(hot in info.get('industry', '未知') for hot in hot_industries)
        
        if is_hot:
            trend_icon, trend_title, trend_desc, trend_color = "🚀", "長線成長大趨勢", f"所屬板塊 ({info.get('industry', '未知')}) 涵蓋高階運算、AI 應用或資料中心等剛性需求，具備長期市場成長潛力。", "#ff4d4d"
        else:
            trend_icon, trend_title, trend_desc, trend_color = "🏭", "穩定或景氣循環產業", f"所屬板塊 ({info.get('industry', '未知')}) 發展相對成熟，需特別留意整體景氣波動或公司的特殊利基點。", "#FFD700"

        if gross_margin is None:
            moat_icon, moat_title, moat_desc, moat_color = "❓", "數據不足", "缺乏毛利率數據無法精確評估。", "gray"
        elif gross_margin >= 0.40:
            moat_icon, moat_title, moat_desc, moat_color = "🏰", "極寬廣 (強大護城河)", f"毛利率高達 {gross_margin*100:.1f}%！顯示公司具備極高的技術門檻、專利佈局或客戶轉換成本，對手極難搶奪市佔率。", "#ff4d4d"
        elif gross_margin >= 0.20:
            moat_icon, moat_title, moat_desc, moat_color = "🛡️", "中等壁壘", f"毛利率 {gross_margin*100:.1f}%。具備一定的技術領先或營運規模，存在競爭壁壘。", "#FFD700"
        else:
            moat_icon, moat_title, moat_desc, moat_color = "⚔️", "競爭激烈 (低護城河)", f"毛利率僅 {gross_margin*100:.1f}%。產品同質性偏高，容易落入價格戰，無法輕易阻擋對手跨入。", "#00cc66"

        if op_margin is None:
            pos_icon, pos_title, pos_desc, pos_color = "❓", "數據不足", "缺乏營益率數據無法精確評估。", "gray"
        elif op_margin >= 0.15:
            pos_icon, pos_title, pos_desc, pos_color = "👑", "核心主導者 (具定價權)", f"營益率高達 {op_margin*100:.1f}%。在產業鏈中掌握關鍵零組件、設備或 IP 設計，景氣波動時具備高度抗跌能力與話語權。", "#ff4d4d"
        elif op_margin >= 0.05:
            pos_icon, pos_title, pos_desc, pos_color = "⚙️", "關鍵供應商", f"營益率 {op_margin*100:.1f}%。在整體供應鏈中扮演不可或缺的一環，營運與定價能力相對穩健。", "#FFD700"
        else:
            pos_icon, pos_title, pos_desc, pos_color = "📦", "弱勢地位 (低階代工/組裝)", f"營益率僅 {op_margin*100:.1f}%。毛利微薄且被成本擠壓，在供應鏈中缺乏定價權，極易受原物料上漲與終端砍單衝擊。", "#00cc66"

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

        # 🚀 【9. 必備神兵：本益比河流圖 (P/E River Chart)】
        st.markdown("### 🌊 必備神兵：近五年本益比河流圖 (P/E River)")
        st.markdown("<small style='color:gray;'>*實戰價值：透過歷史估值區間，一眼看穿目前股價是落入「被錯殺的低估冷門區」還是「過熱的瘋狂高估區」。*</small>", unsafe_allow_html=True)
        
        with st.spinner("抓取近五年每日歷史本益比數據中..."):
            df_per = df_per_backup
            
        if df_per is None:
            st.warning("⚠️ 目前公開資料庫 (FinMind) 連線忙碌或遭遇免費 API 呼叫限制，導致無法抓取資料，請稍候重整網頁再試。")
        elif df_per.empty:
            st.info("💡 該股票近期獲利為負或缺乏有效的本益比數據，系統無法為其繪製河流圖。")
        else:
            hist_reset = hist.copy().reset_index()
            if hist_reset['Date'].dt.tz is not None:
                hist_reset['Date'] = hist_reset['Date'].dt.tz_localize(None)

            hist_reset['Date_only'] = hist_reset['Date'].dt.date
            df_per['date_only'] = df_per['date'].dt.date

            merged = pd.merge(hist_reset, df_per, left_on='Date_only', right_on='date_only', how='inner')

            if not merged.empty and len(merged) > 60: 
                merged['EPS_calc'] = merged['Close'] / merged['PER']
                merged['EPS_smoothed'] = merged['EPS_calc'].rolling(window=60, min_periods=1).mean()

                pe_quantiles = merged['PER'].quantile([0.1, 0.25, 0.5, 0.75, 0.9]).values

                fig_river = go.Figure()

                b1 = merged['EPS_smoothed'] * pe_quantiles[0]
                b2 = merged['EPS_smoothed'] * pe_quantiles[1]
                b3 = merged['EPS_smoothed'] * pe_quantiles[2]
                b4 = merged['EPS_smoothed'] * pe_quantiles[3]
                b5 = merged['EPS_smoothed'] * pe_quantiles[4]

                fig_river.add_trace(go.Scatter(x=merged['Date'], y=b1, mode='lines', line=dict(color='#00cc66', width=1), name=f'悲觀區 ({pe_quantiles[0]:.1f}x)'))
                fig_river.add_trace(go.Scatter(x=merged['Date'], y=b2, mode='lines', fill='tonexty', fillcolor='rgba(0, 204, 102, 0.2)', line=dict(color='#00cc66', width=1), name=f'低估區 ({pe_quantiles[1]:.1f}x)'))
                fig_river.add_trace(go.Scatter(x=merged['Date'], y=b3, mode='lines', fill='tonexty', fillcolor='rgba(255, 215, 0, 0.2)', line=dict(color='#FFD700', width=1), name=f'合理區 ({pe_quantiles[2]:.1f}x)'))
                fig_river.add_trace(go.Scatter(x=merged['Date'], y=b4, mode='lines', fill='tonexty', fillcolor='rgba(255, 140, 0, 0.2)', line=dict(color='#ff8c00', width=1), name=f'高估區 ({pe_quantiles[3]:.1f}x)'))
                fig_river.add_trace(go.Scatter(x=merged['Date'], y=b5, mode='lines', fill='tonexty', fillcolor='rgba(255, 77, 77, 0.2)', line=dict(color='#ff4d4d', width=1), name=f'瘋狂區 ({pe_quantiles[4]:.1f}x)'))

                fig_river.add_trace(go.Scatter(x=merged['Date'], y=merged['Close'], mode='lines', line=dict(color='#0033cc', width=3), name='實際股價'))

                current_pe = merged['PER'].iloc[-1]
                
                rerating_warn = ""
                if current_pe >= pe_quantiles[4] * 0.95:
                     rerating_warn = "<br><br><span style='color:#ff8c00; font-size:0.95rem;'>⚠️ <b>系統智能偵測：可能發生「估值重評 (Re-rating)」</b><br>此股票目前本益比已突破或逼近五年歷史極高點（如設備廠轉型 AI 供應鏈）。此時歷史河流圖的參考價值降低，請務必配合「未來 EPS 爆發力」與「右方 AI 深度推演」來評估其實際價值，切勿單看歷史估值放空！</span>"
                
                if current_pe <= pe_quantiles[1]:
                    pe_status, status_color = "🔥 處於歷史低估區間！(潛在買點)", "#00cc66"
                elif current_pe >= pe_quantiles[3]:
                    pe_status, status_color = "⚠️ 處於歷史高估區間！(留意風險)", "#ff4d4d"
                else:
                    pe_status, status_color = "⚖️ 處於歷史合理區間", "#FFD700"

                fig_river.update_layout(
                    height=450,
                    margin=dict(l=10, r=10, t=50, b=10),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                    hovermode="x unified"
                )
                fig_river.update_yaxes(title_text="股價 (元)", showgrid=True, gridcolor='#e0e0e0')

                st.markdown(f"<div style='background:#f8f9fa; border-left:4px solid {status_color}; padding:10px; border-radius:5px; margin-bottom:10px; color:#333;'>目前位階推估：<b><span style='color:{status_color};'>{pe_status}</span></b> (最新本益比約 {current_pe:.1f}x){rerating_warn}</div>", unsafe_allow_html=True)
                st.plotly_chart(fig_river, use_container_width=True)
            else:
                st.info("💡 該股票資料筆數不足以計算有效的本益比通道。")
        st.markdown("---")

        # 【10. 專業技術線圖與量化型態分析】
        st.markdown("### 🤖 專業技術線圖與量化型態分析 (近半年)")
        
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col not in hist.columns:
                hist[col] = 0.0

        hist['MA5'] = hist['Close'].rolling(5).mean()
        hist['MA10'] = hist['Close'].rolling(10).mean()
        hist['MA20'] = hist['Close'].rolling(20).mean()
        hist['MA60'] = hist['Close'].rolling(60).mean()
        hist['MA120'] = hist['Close'].rolling(120).mean()
        hist['Vol_MA20'] = hist['Volume'].rolling(20).mean()

        h9, l9 = hist['High'].rolling(9).max(), hist['Low'].rolling(9).min()
        
        h9_l9_diff = h9 - l9
        h9_l9_diff[h9_l9_diff == 0] = 1e-9 
        rsv = (hist['Close'] - l9) / h9_l9_diff * 100
        
        K, D = [50], [50]
        for v in rsv.fillna(50):
            K.append(K[-1]*(2/3) + v*(1/3))
            D.append(D[-1]*(2/3) + K[-1]*(1/3))
        hist['K'], hist['D'] = K[1:], D[1:]

        last_close = hist['Close'].iloc[-1]
        ma5_last = hist['MA5'].iloc[-1]
        ma20_last = hist['MA20'].iloc[-1]
        ma60_last = hist['MA60'].iloc[-1]
        ma120_last = hist['MA120'].iloc[-1] if not pd.isna(hist['MA120'].iloc[-1]) else ma60_last
        k_last = hist['K'].iloc[-1]
        d_last = hist['D'].iloc[-1]
        
        recent_20 = hist.tail(20)
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

        plot_df = hist.tail(120)

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3], specs=[[{"secondary_y": True}], [{"secondary_y": False}]])
        fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name='K線', increasing_line_color='#ff4d4d', decreasing_line_color='#00cc66'), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA5'], mode='lines', name='MA5(周線)', line=dict(color='#00bfff', width=1.5)), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA10'], mode='lines', name='MA10(雙周)', line=dict(color='#ab82ff', width=1.5)), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], mode='lines', name='MA20(月線)', line=dict(color='#ff8c00', width=1.5)), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA60'], mode='lines', name='MA60(季線)', line=dict(color='#ffd700', width=1.5)), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA120'], mode='lines', name='MA120(半年線)', line=dict(color='#ff69b4', width=1.5)), row=1, col=1, secondary_y=False)
        
        vol_colors = ['#ff4d4d' if getattr(row, 'Close', 0) >= getattr(row, 'Open', 0) else '#00cc66' for _, row in plot_df.iterrows()]
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume']/1000, marker_color=vol_colors, name='成交量(張)', opacity=0.5), row=1, col=1, secondary_y=True)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['K'], mode='lines', name='K9', line=dict(color='#00bfff', width=1.5)), row=2, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['D'], mode='lines', name='D9', line=dict(color='#ff8c00', width=1.5)), row=2, col=1)

        fig.update_yaxes(side="right", mirror=True, showline=True, linecolor='#ccc', secondary_y=False, row=1, col=1)
        max_vol = plot_df['Volume'].max() / 1000 if not plot_df['Volume'].empty else 100
        fig.update_yaxes(side="left", showgrid=False, showticklabels=False, range=[0, max_vol * 3.5], secondary_y=True, row=1, col=1)
        fig.update_yaxes(range=[0, 100], dtick=10, side="right", mirror=True, showline=True, linecolor='#ccc', row=2, col=1)
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], tickformat="%m/%d", showgrid=True, gridcolor='#e0e0e0', mirror=True, showline=True, linecolor='#ccc')
        
        fig.update_layout(
            height=650, 
            xaxis_rangeslider_visible=False, 
            margin=dict(l=10, r=10, t=50, b=10), 
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0), 
            hovermode="x unified"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error(f"找不到代號 {curr_id} 的資料，請確認代號是否正確。")
