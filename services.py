"""
外部資料與模型服務層：
yfinance、Fugle、FinMind、Yahoo、Gemini 等 API 存取都集中在這裡。
由原始 app(1).py 拆分而來，已全面升級為最新的 google-genai 官方 SDK。
"""
import datetime
import email.utils
import io
import json
import math
import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# 新增 Google 官方 GenAI SDK 引入
from google import genai
from google.genai import types

from ai_services.financial_filler import postprocess_financial_ai_payload
# 從 utils 引入需要的工具
from utils import (
    build_monthly_revenue_growth_frame,
    expected_latest_revenue_month,
    format_field_source_priority_for_prompt,
    normalize_revenue_month,
    s_float,
    log_data_health,
    log_exception,
)
try:
    from industry_taxonomy import INDUSTRY_TAXONOMY
except Exception:
    INDUSTRY_TAXONOMY = {}


def _google_search_tool():
    """Gemini Google Search tool：優先使用官方 typed config，舊版 SDK 才退回 dict。"""
    try:
        return types.Tool(google_search=types.GoogleSearch())
    except Exception:
        return {"google_search": {}}

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
            log_data_health("Fugle", True, res.status_code)
            data = res.json().get('data', [])
            if data:
                df = pd.DataFrame(data)
                df['Date'] = pd.to_datetime(df['date'])
                df.set_index('Date', inplace=True)
                df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
                return df[['Open', 'High', 'Low', 'Close', 'Volume']].sort_index()
            else:
                log_data_health("Fugle", False, res.status_code)
    except Exception as e:
        log_exception("Fugle", f"fetch_fugle_kline:{stock_id}:{timeframe}", e)
        log_data_health("Fugle", False, f"ERR:{str(e)[:120]}")

    return pd.DataFrame()

# ==========================================
# 3.1 ETF 持股曝險追蹤（系統抓取，不使用 AI）
# ==========================================
def _normalize_etf_code(code):
    """ETF 代號標準化：支援 00987A / 00987a / 0050。"""
    if code is None:
        return ""
    return str(code).strip().upper().replace(".TW", "")


def _normalize_etf_holders(rows, default_source="系統抓取"):
    """將不同來源抓到的 ETF 持股資料統一欄位，並去重。"""
    normalized = []
    seen = set()
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        code = _normalize_etf_code(r.get("etf_code") or r.get("code") or r.get("id"))
        name = str(r.get("etf_name") or r.get("name") or "").strip()
        if not code:
            continue

        weight = r.get("weight")
        try:
            if isinstance(weight, str):
                weight = weight.replace("%", "").replace(",", "").strip()
            weight = float(weight) if weight not in (None, "", "null") else None
            # AI 偶爾會回傳 0.0685，畫面統一顯示為 6.85
            if weight is not None and 0 < abs(weight) <= 1:
                weight = weight * 100
        except Exception:
            weight = None

        shares = r.get("shares") or r.get("holding_shares") or r.get("持有股數")
        data_date = str(r.get("data_date") or r.get("date") or r.get("資料日期") or "").strip()
        source = str(r.get("source") or default_source).strip()
        data_type = str(r.get("data_type") or default_source).strip()
        note = str(r.get("note") or r.get("備註") or "").strip()

        key = code
        if key in seen:
            continue
        seen.add(key)
        normalized.append({
            "etf_code": code,
            "etf_name": name,
            "weight": weight,
            "shares": shares,
            "data_date": data_date,
            "source": source,
            "data_type": data_type,
            "note": note,
        })

    normalized.sort(key=lambda x: (x.get("weight") is None, -(x.get("weight") or 0)))
    return normalized


def _extract_etf_holders_from_text(raw_text, source_name):
    """
    從 Yahoo / FindBillion 等頁面的 HTML 或嵌入 JSON 文字中，盡量抽取 ETF 代號、名稱、持股比例。
    注意：這是備援式解析，網站改版時仍可能失效，因此 UI 會明確標示資料來源與限制。
    """
    if not raw_text:
        return []

    text = re.sub(r"\\u002F", "/", raw_text)
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"&quot;|&#34;", '"', text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    rows = []

    # 先抓常見格式：ETF中文名稱 00987A ... 6.85%
    # 名稱長度設寬一點，避免抓到整段敘述；後面再清洗。
    pattern = re.compile(r"([\u4e00-\u9fffA-Za-z0-9\-＋+（）()·\.]{2,32})\s*(00\d{2,3}[A-Z]?)\s{0,20}(.{0,120}?)(\d{1,2}(?:\.\d{1,4})?)\s*%", re.I)
    for m in pattern.finditer(text):
        name = m.group(1).strip(" ：:-｜|,，。")
        code = _normalize_etf_code(m.group(2))
        weight = m.group(4)
        if not code or not name:
            continue
        if any(bad in name for bad in ["http", "Yahoo", "FindBillion", "資料", "持有"]):
            # 若名稱被抓太長，取最後一段可能的 ETF 名稱
            name = re.split(r"[：:｜|，,。\s]", name)[-1].strip()
        rows.append({
            "etf_code": code,
            "etf_name": name,
            "weight": weight,
            "source": source_name,
            "data_type": "系統抓取",
        })

    # 另外抓 JSON 常見 key-value 格式，例如 symbol/name/weight 分散在附近。
    code_pat = re.compile(r'"(?:symbol|code|etfCode|stockNo|id)"\s*:\s*"?(00\d{2,3}[A-Z]?)"?', re.I)
    for m in code_pat.finditer(text):
        start = max(0, m.start() - 250)
        end = min(len(text), m.end() + 350)
        block = text[start:end]
        code = _normalize_etf_code(m.group(1))
        name_match = re.search(r'"(?:name|etfName|stockName|shortName)"\s*:\s*"([^"{}]{2,40})"', block, re.I)
        weight_match = re.search(r'"(?:weight|holdingRatio|ratio|percent|shareholding)"\s*:\s*"?(-?\d+(?:\.\d+)?)"?', block, re.I)
        rows.append({
            "etf_code": code,
            "etf_name": name_match.group(1).strip() if name_match else "",
            "weight": weight_match.group(1) if weight_match else None,
            "source": source_name,
            "data_type": "系統抓取",
        })

    return _normalize_etf_holders(rows, default_source="系統抓取")





# ==========================================
# 3.2 ETF 成分股快取反查（v4：MoneyDJ/Pocket/TWSE；一般查詢不使用 AI / 不用 Google）
# ==========================================
ETF_CACHE_DIR = ".etf_cache"
ETF_MASTER_CACHE_FILE = os.path.join(ETF_CACHE_DIR, "etf_master_list.json")
ETF_HOLDINGS_CACHE_FILE = os.path.join(ETF_CACHE_DIR, "etf_holdings_cache.json")
ETF_CACHE_VERSION = "v8.0-regex-fallback-holdings-cache"
ETF_SEED_CUTOFF_DATE = "2026-05-14"

# 這是「保底種子清單」：避免 TWSE / 外部清單抓不到時漏掉主動式 ETF。
# 新 ETF 仍會盡量由 discover_etf_master_list() 從公開頁面補進來。
ETF_SEED_LIST = [
    ("0050", "元大台灣50"), ("0051", "元大中型100"), ("0052", "富邦科技"),
    ("0053", "元大電子"), ("0056", "元大高股息"), ("0057", "富邦摩台"),
    ("006208", "富邦台50"), ("00690", "兆豐藍籌30"), ("00692", "富邦公司治理"),
    ("00701", "國泰股利精選30"), ("00713", "元大台灣高息低波"), ("00728", "第一金工業30"),
    ("00730", "富邦臺灣優質高息"), ("00733", "富邦臺灣中小"), ("00735", "國泰臺韓科技"),
    ("00736", "國泰新興市場"), ("00850", "元大臺灣ESG永續"), ("00878", "國泰永續高股息"),
    ("00881", "國泰台灣5G+"), ("00891", "中信關鍵半導體"), ("00892", "富邦台灣半導體"),
    ("00900", "富邦特選高股息30"), ("00904", "新光臺灣半導體30"), ("00905", "FT臺灣Smart"),
    ("00907", "永豐優息存股"), ("00912", "中信臺灣智慧50"), ("00913", "兆豐台灣晶圓製造"),
    ("00915", "凱基優選高股息30"), ("00919", "群益台灣精選高息"), ("00922", "國泰台灣領袖50"),
    ("00923", "群益台ESG低碳50"), ("00927", "群益半導體收益"), ("00929", "復華台灣科技優息"),
    ("00932", "兆豐永續高息等權"), ("00934", "中信成長高股息"), ("00939", "統一台灣高息動能"),
    ("00940", "元大台灣價值高息"), ("00944", "野村趨勢動能高息"), ("00946", "群益科技高息成長"),
    ("00952", "凱基台灣AI50"), ("00980A", "主動野村臺灣優選"), ("00981A", "主動統一台股增長"),
    ("00982A", "主動群益台灣強棒"), ("00983A", "主動中信ARK創新"), ("00984A", "主動安聯台灣高息"),
    ("00985A", "主動野村台灣50"), ("00986A", "主動群益科技創新"), ("00987A", "主動台新優勢成長"),
    ("00988A", "主動統一台股優"), ("00989A", "主動復華未來50"), ("00990A", "主動野村全球航運"),
    ("00400A", "主動國泰動能高息"), ("00403A", "主動統一台灣科技"),
]


def _today_str():
    return datetime.date.today().strftime("%Y-%m-%d")


def _ensure_etf_cache_dir():
    os.makedirs(ETF_CACHE_DIR, exist_ok=True)


def _read_json_file(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json_file(path, data):
    _ensure_etf_cache_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _flatten_columns(df):
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ["_".join([str(x) for x in c if str(x) != "nan"]).strip() for c in df.columns]
    else:
        df.columns = [str(c).strip() for c in df.columns]
    return df


def _clean_percent_to_float(v):
    if v is None:
        return None
    try:
        s = str(v).strip().replace("％", "%").replace("%", "").replace(",", "")
        if s in ["", "--", "-", "N/A", "nan", "None"]:
            return None
        x = float(s)
        # 有些來源用 0.0968 表示 9.68%，統一轉為百分比數字。
        if 0 < abs(x) <= 1:
            x *= 100
        return x
    except Exception:
        return None

def _normalize_tw_name(name):
    """把股票/ETF 名稱做最小清洗，方便由名稱反查代號。"""
    s = str(name or "").strip()
    s = re.sub(r"\([^)]*\)|（[^）]*）", "", s)
    s = re.sub(r"\s+", "", s)
    s = s.replace("臺", "台")
    return s


@st.cache_data(ttl=86400, show_spinner=False)
def _load_local_stock_name_code_map():
    """
    建立『股票名稱 → 股票代號』對照。
    MoneyDJ / Pocket 的 ETF 成分股表有時只有股票名稱、沒有 2330 這種代號；
    若不做名稱反查，快取就會是 0 筆或漏掉 00981A → 台積電。
    """
    mapping = {
        "台積電": "2330", "聯發科": "2454", "鴻海": "2317", "台達電": "2308",
        "廣達": "2382", "緯穎": "6669", "奇鋐": "3017", "雙鴻": "3324",
        "金像電": "2368", "台光電": "2383", "台燿": "6274", "欣興": "3037",
        "南電": "8046", "日月光投控": "3711", "聯電": "2303", "中華電": "2412",
        "富邦金": "2881", "國泰金": "2882", "兆豐金": "2886", "中信金": "2891",
        "元大金": "2885", "玉山金": "2884", "第一金": "2892", "華南金": "2880",
        "統一": "1216", "長榮": "2603", "陽明": "2609", "萬海": "2615",
        "大立光": "3008", "世芯-KY": "3661", "創意": "3443", "智原": "3035",
    }

    # 從你的 stocklist.txt 補充更多自選/產業鏈股票名稱。
    for path in ["stocklist.txt", os.path.join(os.getcwd(), "stocklist.txt")]:
        try:
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or "," not in line:
                        continue
                    parts = [x.strip() for x in line.split(",")]
                    if len(parts) >= 2 and re.fullmatch(r"\d{4}", parts[0]):
                        mapping[_normalize_tw_name(parts[1])] = parts[0]
        except Exception:
            pass

    return {_normalize_tw_name(k): str(v) for k, v in mapping.items() if k and v}


def _infer_stock_name_from_row(vals, stock_code=""):
    """從表格列中猜測成分股名稱。"""
    candidates = []
    for v in vals:
        s = str(v or "").strip()
        if not s or s.lower() in ["nan", "none"]:
            continue
        if any(bad in s for bad in ["投資比例", "持股比例", "持有股數", "股票代號", "證券代號", "合計", "小計", "ETF"]):
            continue
        if stock_code and stock_code in s:
            # 台積電(2330.TW) 這種格式，先取代號前的名稱。
            m = re.search(r"([\u4e00-\u9fffA-Za-z0-9\-＋+·]{2,30})\s*[\(（]?" + re.escape(stock_code), s)
            if m:
                return m.group(1).strip()
            continue
        if re.search(r"[\u4e00-\u9fff]", s):
            # 避免拿到整段很長的說明。
            s = re.split(r"[\s　,，|｜]", s)[0].strip()
            if 1 < len(s) <= 30:
                candidates.append(s)
    return candidates[0] if candidates else ""


def _extract_stock_code_from_row(row_text, vals, stock_name=""):
    """優先從文字抓 4 碼代號；抓不到時，用名稱對照表反查。"""
    m_code = re.search(r"(?<!\d)(\d{4})(?:\.TW|\s|$|\)|）|　|,|，|/)", row_text)
    if m_code:
        return m_code.group(1)

    name_map = _load_local_stock_name_code_map()
    possible_names = []
    if stock_name:
        possible_names.append(stock_name)
    for v in vals:
        sv = str(v or "").strip()
        if re.search(r"[\u4e00-\u9fff]", sv):
            possible_names.append(sv)

    for nm in possible_names:
        key = _normalize_tw_name(nm)
        if key in name_map:
            return name_map[key]
        # 有時儲存格包含「台積電 普通股」或「台積電(2330)」這類字串。
        for k, code in name_map.items():
            if k and k in key:
                return code
    return ""


def _extract_data_date_from_text(text):
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text))
    patterns = [
        r"(?:資料日期|資料時間|更新日期|更新時間|持股日期|成分股日期|基準日|截至|日期)[:：\s]*(\d{4}[/-]\d{1,2}[/-]\d{1,2})",
        r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})\s*(?:資料|更新|持股|成分股|基準日)",
        r"(\d{3}[/-]\d{1,2}[/-]\d{1,2})",  # 民國年格式，先原樣保留
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).replace("/", "-")
    return ""


def _request_html(url, timeout=15):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/",
    }
    res = requests.get(url, headers=headers, timeout=timeout)
    res.raise_for_status()
    # MoneyDJ 有時編碼不是 UTF-8，交給 requests 判斷。
    if not res.encoding or res.encoding.lower() == "iso-8859-1":
        res.encoding = res.apparent_encoding or "utf-8"
    return res.text


def discover_etf_master_list(force=False):
    """
    建立 ETF 主清單：
    1) 先讀快取；
    2) 盡量從公開資料源補 ETF 代號；
    3) 失敗時至少使用 ETF_SEED_LIST，避免 00981A 這類主動式 ETF 漏掉。
    """
    cached = _read_json_file(ETF_MASTER_CACHE_FILE, {})
    if (not force) and cached.get("updated_date") == _today_str() and cached.get("items"):
        return cached.get("items", [])

    items = {code.upper(): {"etf_code": code.upper(), "etf_name": name, "source": "seed"} for code, name in ETF_SEED_LIST}

    # 嘗試從 TWSE OpenAPI / 公開列表補充。不同時期 endpoint 可能調整；失敗不阻斷主流程。
    candidate_urls = [
        "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX",
        "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
        "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
    ]
    for url in candidate_urls:
        try:
            data = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"}).json()
            if not isinstance(data, list):
                continue
            for row in data:
                if not isinstance(row, dict):
                    continue
                txt = " ".join([str(v) for v in row.values()])
                # 台股 ETF 常見代號：00xxx / 00xxxA / 004xxA / 006xxL 等
                m = re.search(r"\b(00\d{2,4}[A-Z]?)\b", txt, re.I)
                if not m:
                    continue
                code = m.group(1).upper()
                if not code.startswith("00"):
                    continue
                # 嘗試從欄位名稱找中文名稱
                name = ""
                for k, v in row.items():
                    ks = str(k)
                    if any(x in ks for x in ["名稱", "股票名稱", "有價證券名稱", "基金"]):
                        name = str(v).strip()
                        break
                if not name:
                    name = items.get(code, {}).get("etf_name", "")
                items[code] = {"etf_code": code, "etf_name": name, "source": "TWSE/OpenAPI"}
        except Exception:
            continue

    result = sorted(items.values(), key=lambda x: x.get("etf_code", ""))
    _write_json_file(ETF_MASTER_CACHE_FILE, {
        "version": ETF_CACHE_VERSION,
        "updated_date": _today_str(),
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "seed_cutoff_date": ETF_SEED_CUTOFF_DATE,
        "count": len(result),
        "source_counts": {src: sum(1 for x in result if x.get("source") == src) for src in sorted(set(x.get("source", "未知") for x in result))},
        "note": f"內建種子清單包含 {ETF_SEED_CUTOFF_DATE} 前已知上市 ETF；可按鈕重新從 TWSE/OpenAPI 補抓新上市或漏收 ETF。",
        "items": result,
    })
    return result


def _parse_holdings_text_regex_fallback(html, etf_code, etf_name, source, source_url, data_date=""):
    """
    v8：MoneyDJ / CMoney / Pocket 有些頁面雖然文字裡有成分股，
    但 pandas.read_html 在 Streamlit Cloud 可能因 lxml/bs4 或表格格式失敗，
    因此再用純文字 regex 補抓。
    常見格式：台積電(2330.TW) 9.68 11,657,000.00
    或：2330 台積電 9.23%
    """
    if not html:
        return []
    text = str(html)
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&quot;|&#34;", '"', text)
    text = re.sub(r"\s+", " ", text)

    rows = []
    # MoneyDJ：台積電(2330.TW) 9.68 11,657,000.00
    pat_name_code = re.compile(
        r"([\u4e00-\u9fffA-Za-z0-9\-＋+＊*·]{1,32})\s*[\(（]\s*(\d{4})\.TW\s*[\)）]\s*[,，\s]*(-?\d{1,3}(?:\.\d{1,4})?)\s*%?\s*[,，\s]*([0-9,]+(?:\.\d+)?)?",
        re.I
    )
    for m in pat_name_code.finditer(text):
        stock_name = m.group(1).strip()
        stock_code = m.group(2).strip()
        weight = _clean_percent_to_float(m.group(3))
        shares = (m.group(4) or "").strip() or None
        if not stock_name or not stock_code:
            continue
        rows.append({
            "etf_code": etf_code.upper(),
            "etf_name": etf_name,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "weight": weight,
            "shares": shares,
            "data_date": data_date,
            "source": source,
            "source_url": source_url,
            "data_type": "系統抓取",
            "fetched_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "parse_method": "regex_name_code",
        })

    # CMoney / Pocket 常見：2330 台積電 9.23%
    pat_code_name = re.compile(
        r"(?<!\d)(\d{4})(?!\d)\s+([\u4e00-\u9fffA-Za-z0-9\-＋+＊*·]{1,32})\s+(-?\d{1,3}(?:\.\d{1,4})?)\s*%",
        re.I
    )
    for m in pat_code_name.finditer(text):
        stock_code = m.group(1).strip()
        stock_name = m.group(2).strip()
        weight = _clean_percent_to_float(m.group(3))
        if not stock_name or not stock_code:
            continue
        rows.append({
            "etf_code": etf_code.upper(),
            "etf_name": etf_name,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "weight": weight,
            "shares": None,
            "data_date": data_date,
            "source": source,
            "source_url": source_url,
            "data_type": "系統抓取",
            "fetched_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "parse_method": "regex_code_name",
        })

    return rows


def _dedup_holding_rows(rows):
    dedup = {}
    for r in rows or []:
        stock_key = str(r.get("stock_code") or "").strip()
        if not stock_key:
            stock_key = _normalize_tw_name(r.get("stock_name", ""))
        key = (str(r.get("etf_code", "")).upper(), stock_key)
        if not key[0] or not stock_key:
            continue
        old = dedup.get(key)
        if old is None or (old.get("weight") is None and r.get("weight") is not None):
            dedup[key] = r
    return list(dedup.values())


def _parse_holdings_tables_from_html(html, etf_code, etf_name, source, source_url):
    """
    解析 MoneyDJ / Pocket / 其他 HTML 表格。
    v8 重點：
    - pandas.read_html 失敗時不直接放棄，改用 regex 從 HTML 純文字補抓。
    - 不再假設表格一定有 4 碼股票代號；有名稱也保留。
    """
    rows = []
    data_date = _extract_data_date_from_text(html)
    try:
        tables = pd.read_html(io.StringIO(html))
    except Exception:
        tables = []

    name_code_map = _load_local_stock_name_code_map()

    for df in tables:
        if df is None or df.empty:
            continue
        df = _flatten_columns(df)
        df = df.fillna("")
        full_text = " ".join(df.astype(str).head(120).values.ravel().tolist())
        col_text = " ".join([str(c) for c in df.columns])
        table_text = full_text + " " + col_text

        # MoneyDJ 有時欄名很簡短；只要表格像成分股/持股表，就嘗試解析。
        looks_like_holding_table = any(k in table_text for k in [
            "投資比例", "持股", "權重", "比例", "成分股", "股票代號", "證券代號", "持有股數", "名稱"
        ])
        has_known_stock_name = any(k in table_text for k in list(name_code_map.keys())[:80])
        if not looks_like_holding_table and not has_known_stock_name:
            continue

        for _, r in df.iterrows():
            vals = [str(v).strip() for v in list(r.values) if str(v).strip() not in ["", "nan", "None"]]
            if not vals:
                continue
            row_text = " ".join(vals)
            if any(x in row_text for x in ["投資區域", "產業", "資產配置", "合計", "小計", "現金", "期貨", "基金淨資產"]):
                continue

            # 先猜名稱，再由名稱/文字找代號。
            stock_name = _infer_stock_name_from_row(vals)
            stock_code = _extract_stock_code_from_row(row_text, vals, stock_name)

            # v7：不要強制要求 ETF 成分股列一定有股票代號。
            # 因為 MoneyDJ / Pocket 有時只提供「台積電」這種成分股名稱；
            # 個股頁目前已經知道 curr_id 與 c_name，所以反查時可直接用名稱比對。
            if not stock_code and not stock_name:
                continue
            if stock_code and stock_code == str(etf_code)[:4]:
                # 避免把 ETF 自己誤判為成分股。
                continue
            if not stock_name:
                stock_name = _infer_stock_name_from_row(vals, stock_code)

            weight = None
            # 優先從欄名含比例/權重/持股的欄位取。
            for c in df.columns:
                if any(k in str(c) for k in ["投資比例", "持股比例", "權重", "比例", "%"]):
                    weight = _clean_percent_to_float(r.get(c))
                    if weight is not None:
                        break
            # 再從整列抓百分比。
            if weight is None:
                m_w = re.search(r"(-?\d{1,3}(?:\.\d{1,4})?)\s*%", row_text)
                if m_w:
                    weight = _clean_percent_to_float(m_w.group(1))
            # 最後退一步：若該列有多個數字，常見最後一個小數是比例。
            if weight is None:
                nums = re.findall(r"(?<!\d)(\d{1,3}(?:\.\d{1,4})?)(?!\d)", row_text.replace(",", ""))
                for num in reversed(nums):
                    try:
                        x = float(num)
                        if 0 <= x <= 100 and num != stock_code:
                            weight = x
                            break
                    except Exception:
                        pass

            shares = None
            for c in df.columns:
                if any(k in str(c) for k in ["持有股數", "股數", "持股"]):
                    shares = str(r.get(c)).strip()
                    break

            rows.append({
                "etf_code": etf_code.upper(),
                "etf_name": etf_name,
                "stock_code": stock_code,
                "stock_name": stock_name,
                "weight": weight,
                "shares": shares,
                "data_date": data_date,
                "source": source,
                "source_url": source_url,
                "data_type": "系統抓取",
                "fetched_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

    # v8：表格解析後，再用 regex 補抓；若 read_html 失敗，也可靠 regex 建立快取。
    rows.extend(_parse_holdings_text_regex_fallback(html, etf_code, etf_name, source, source_url, data_date=data_date))
    return _dedup_holding_rows(rows)

def fetch_moneydj_etf_holdings(etf_code, etf_name=""):
    url = f"https://www.moneydj.com/etf/x/basic/basic0007.xdjhtm?etfid={str(etf_code).lower()}.tw"
    html = _request_html(url)
    return _parse_holdings_tables_from_html(html, etf_code, etf_name, "MoneyDJ", url)


def fetch_pocket_etf_holdings(etf_code, etf_name=""):
    url = f"https://www.pocket.tw/etf/tw/{str(etf_code).upper()}/fundholding/"
    html = _request_html(url)
    return _parse_holdings_tables_from_html(html, etf_code, etf_name, "Pocket", url)


def fetch_cmoney_etf_holdings(etf_code, etf_name=""):
    url = f"https://www.cmoney.tw/etf/tw/{str(etf_code).upper()}/fundholding"
    html = _request_html(url)
    return _parse_holdings_tables_from_html(html, etf_code, etf_name, "CMoney", url)






def update_etf_master_list_cache(force=True):
    """
    更新 ETF 主清單快取：
    - 不使用 AI、不用 Google 搜尋；
    - 以內建種子清單為底，再嘗試從 TWSE/OpenAPI 補進新上市或漏收 ETF；
    - 只更新 ETF 清單，不會抓每檔 ETF 的成分股。
    """
    discover_etf_master_list(force=force)
    return _read_json_file(ETF_MASTER_CACHE_FILE, {})


def get_etf_master_cache_status():
    master = _read_json_file(ETF_MASTER_CACHE_FILE, {})
    items = master.get("items", []) if isinstance(master.get("items"), list) else []
    active_count = 0
    for x in items:
        code = str(x.get("etf_code", "")).upper()
        name = str(x.get("etf_name", ""))
        if code.endswith("A") or "主動" in name:
            active_count += 1
    return {
        "cache_version": master.get("version", "尚未建立"),
        "updated_date": master.get("updated_date", "尚未更新"),
        "updated_at": master.get("updated_at", "尚未更新"),
        "is_today": master.get("updated_date") == _today_str(),
        "count": master.get("count", len(items)),
        "active_count": active_count,
        "seed_cutoff_date": master.get("seed_cutoff_date", ETF_SEED_CUTOFF_DATE),
        "source_counts": master.get("source_counts", {}),
        "note": master.get("note", f"內建種子清單包含 {ETF_SEED_CUTOFF_DATE} 前已知上市 ETF。"),
    }





AI_FINANCIAL_FIELD_LABELS = {
    "current_price": "目前股價",
    "pe": "歷史本益比 P/E",
    "trailing_eps": "近四季 EPS（legacy）",
    "forward_eps": "法人預估 EPS（legacy）",
    "latest_month_eps": "最新單月 / 自結 EPS",
    "latest_quarter_eps": "最新單季 EPS",
    "previous_quarter_eps": "前一季 EPS",
    "last_two_quarter_eps": "近二季 EPS 合計",
    "ttm_eps": "近四季 TTM EPS",
    "fiscal_year_eps": "最近完整年度 EPS",
    "forward_eps_system": "系統預估 Forward EPS",
    "forward_eps_ai": "AI 抓取/推估 Forward EPS",
    "forward_eps_consensus": "法人共識 Forward EPS",
    "forward_eps_fy1": "FY1 Forward EPS（下一個完整年度）",
    "forward_eps_fy2": "FY2 Forward EPS（第二個預估年度）",
    "forward_eps_fy3": "FY3 Forward EPS（第三個預估年度/長期情境）",
    "forward_eps_fy1_year": "FY1 EPS 年份",
    "forward_eps_fy2_year": "FY2 EPS 年份",
    "forward_eps_fy3_year": "FY3 EPS 年份",
    "forward_eps_fy_source_note": "Forward EPS 年期來源備註",
    "forward_eps_fy_basis": "Forward EPS 年期基準/可靠度",
    "pb": "股價淨值比 P/B",
    "gross_margin": "毛利率",
    "operating_margin": "營益率",
    "roe": "ROE",
    "yoy": "營收/獲利成長率 YoY/CAGR",
    "target_price": "目標價",
    "target_price_high": "目標價高標",
    "target_price_avg": "目標價均值",
    "target_price_low": "目標價低標",
    "target_price_analyst_count": "目標價分析師人數",
    "target_price_rationale": "目標價理由",
    "debt_to_equity": "負債權益比 D/E",
    "mom": "最新單月營收 MoM",
    "dividend_yield": "預估現金殖利率",
    "data_period": "資料期間",
    "free_cash_flow": "自由現金流",
    "current_ratio": "流動比率",
    "shares_outstanding": "總發行股數/股本",
}

def _normalize_ai_source_metadata(parsed):
    """
    將 AI 回傳的來源欄位統一整理到 _ai_source_trace。
    支援新格式 _sources / field_sources，也相容 source_urls 這類舊式總表。
    """
    if not isinstance(parsed, dict):
        return parsed

    raw_sources = parsed.get("_sources") or parsed.get("field_sources") or parsed.get("sources") or {}
    global_urls = parsed.get("source_urls") or parsed.get("reference_urls") or []
    if isinstance(global_urls, str):
        global_urls = [global_urls]

    trace = {}
    for key, label in AI_FINANCIAL_FIELD_LABELS.items():
        meta = raw_sources.get(key) if isinstance(raw_sources, dict) else None
        if isinstance(meta, dict):
            source = str(meta.get("source") or meta.get("publisher") or meta.get("title") or "AI聯網搜尋").strip()
            published_date = str(meta.get("published_date") or meta.get("date") or meta.get("data_date") or meta.get("period") or parsed.get("data_period") or "").strip()
            source_url = str(meta.get("source_url") or meta.get("url") or meta.get("link") or "").strip()
            note = str(meta.get("note") or meta.get("quote") or meta.get("description") or "").strip()
        elif isinstance(meta, str) and meta.strip():
            source = meta.strip()
            published_date = str(parsed.get("data_period") or "").strip()
            source_url = ""
            note = ""
        else:
            source = "AI聯網搜尋" if parsed.get(key) not in (None, "", "null") else ""
            published_date = str(parsed.get("data_period") or "").strip() if source else ""
            source_url = ""
            note = ""

        trace[key] = {
            "field": key,
            "label": label,
            "value": parsed.get(key),
            "source": source,
            "published_date": published_date,
            "source_url": source_url,
            "note": note,
        }

    if global_urls:
        parsed["source_urls"] = [str(u).strip() for u in global_urls if str(u).strip()]

    parsed["_ai_source_trace"] = trace
    parsed["source_summary"] = "已要求 AI 逐欄回傳來源、發布日期與網址；若單欄來源缺漏，請以原始回報與 source_urls 交叉檢查。"
    return parsed


def get_financials_from_ai(
    stock_name,
    stock_id,
    api_key,
    model_name="gemini-3.1-pro-preview",
    missing_fields=None,
    programmatic_snapshot=None,
):
    """
    AI 財報校對與補齊.
    v7 修正重點：
    1) 僅允許 Gemini 3.1 Pro Preview 付費版 + Google Search。
    2) 不自動降級到 2.5 Pro / 2.5 Flash / 離線保底，避免不準資料進入估值模型。
    3) 尖峰時段採用「同模型 Pro Only Retry」：立即重試、等待 3 秒、等待 8 秒。
    4) 全部失敗時只回傳 error 與 attempts，不產生 AI 財報數據。
    """
    if not api_key:
        return {"error": "未提供 API Key"}

    try:
        client = genai.Client(api_key=api_key.strip())
    except Exception as e:
        return {"error": f"GenAI Client 初始化失敗：{str(e)}"}

    current_year = datetime.date.today().year
    target_year = current_year if datetime.date.today().month < 9 else current_year + 1
    valid_taxon_codes_text = ", ".join(sorted(INDUSTRY_TAXONOMY.keys())) if INDUSTRY_TAXONOMY else "GENERAL"
    source_priority_prompt = format_field_source_priority_for_prompt(max_rows=24)

    missing_fields = [str(field).strip() for field in (missing_fields or []) if str(field).strip()]
    programmatic_snapshot = programmatic_snapshot if isinstance(programmatic_snapshot, dict) else {}
    protected_programmatic_snapshot = {
        str(key): value
        for key, value in programmatic_snapshot.items()
        if value not in (None, "", "null")
    }
    fill_scope_text = ", ".join(missing_fields) if missing_fields else "其他尚未取得的財報與估值欄位"
    programmatic_snapshot_text = json.dumps(protected_programmatic_snapshot, ensure_ascii=False, sort_keys=True)

    system_prompt = f"""你是一個精準的財經數據提取機器人。請上網搜尋該台股公司「最新」、「最即時」的財報與市場數據，絕對不要使用過期的舊資料，提取以下指標：
    系統已先用程式抓取可取得的法人資料。既有程式值如下：{programmatic_snapshot_text}。
    本次優先補齊欄位：{fill_scope_text}。
    你可以回傳完整 JSON 供交叉校對，但不得要求覆蓋既有程式值；正式合併時只採用你對缺值欄位的補齊結果。
    0. 「目前股價 (current_price)」：抓取查詢當下或最近交易日成交/收盤價，僅供交叉校對；正式採用仍以系統行情為準。
    1. 「歷史本益比 (P/E)」
    2. 「最新單月 / 自結 EPS (latest_month_eps)」：若公司因注意股、重大訊息或新聞公告最近月份自結獲利，請填該單月 EPS，例如 2026年4月單月 EPS 13.95；沒有明確單月 EPS 請填 null。
    2-0. 「最新單季 EPS (latest_quarter_eps)」：最新已公告季度 EPS，例如 2026Q1 EPS。
    2-1. 「前一季 EPS (previous_quarter_eps)」與「近二季 EPS 合計 (last_two_quarter_eps)」：用於 Run-rate EPS 動能估值。last_two_quarter_eps=最新單季 EPS + 前一季 EPS；若只能查到其中一季，缺值請填 null。
    3. 「近四季 EPS 合計 (ttm_eps / trailing_eps)」：用於歷史 P/E。
    4. 「最近完整年度 EPS (fiscal_year_eps)」：最近完整會計年度 EPS。
    5. 「法人預估 {target_year} 年度 EPS (forward_eps_ai / forward_eps_consensus)」：若有多家法人共識請填 forward_eps_consensus；若只有 AI 從單一新聞/券商抓取或推估，請填 forward_eps_ai。
    5-1. 「Forward EPS 年期分層」：請抓取「預估年度 EPS 序列」。FY1=一年預估 EPS，FY2=第二年預估 EPS，FY3=第三年預估 EPS；不是查詢日後 1/2/3 年的滾動 EPS。請務必回傳對應年度，例如 FY1=2026E、FY2=2027E、FY3=2028E；若查不到年度請填 null。
        - forward_eps_fy1：一年預估 EPS，例如 2026E 或 2027E，需搭配 forward_eps_fy1_year。
        - forward_eps_fy2：第二年預估 EPS，例如 FY1=2026E 時，FY2 通常為 2027E。
        - forward_eps_fy3：第三年預估 EPS，或長期情境 EPS；若非法人共識，請在 forward_eps_fy_source_note 標示。
        - forward_eps_fy_basis：請填「法人共識年度預估 / 單一券商預估 / 新聞引用預估 / AI依成長率推估 / 查無明確資料」之一。
        若年度不明確或只是 AI 自行推算，請填 null 或明確標示「AI推估，非法人共識」。
    6. 「股價淨值比 (P/B)」
    7. 「毛利率」
    8. 「營益率」
    9. 「ROE(股東權益報酬率)」
    10. 「最新公告月份單月營收 YoY (yoy)」；若查不到單月 YoY 才可用未來 1~3 年獲利 CAGR，且必須在來源備註標明口徑。
    11. 「國內外法人最新預估目標價」：同時回傳 target_price（主要/代表目標價）、target_price_avg（平均）、target_price_low（最低）、target_price_high（最高）。
    12. 「負債權益比 (Debt-to-Equity Ratio)」
    13. 「最新單月營收月增率(MoM)」
    14. 「預估現金殖利率 (Dividend Yield)」(例如：擬配發現金股利2元，最新股價900元，殖利率應為 0.0022)
    15. 「最新資料所屬年月或具體日期 (Data Period)」(請務必標示出你查到這些最新數據的具體發布日期或所屬時間，例如：2024年4月或2024/05/15)
    16. 「目標價統計分析師人數 (Target Price Analyst Count)」
    17. 「目標價核心理由摘要 (Target Price Rationale)」
    18. 「最新自由現金流 (Free Cash Flow)」
    19. 「最新流動比率 (Current Ratio)」
    20. 「總發行股數或股本大小 (Shares Outstanding / Capital)」
    21. 「industry_classification」：請判斷公司主要營收來源、主要產品、產業鏈位置，並輸出建議產業分類。這是給系統輔助判斷用，不會直接覆蓋正式 stock_mapping.py。
        industry_classification 必須包含：
        - suggested_primary_taxon：只能從下列代碼選一個，若不確定填 GENERAL。代碼包括 {valid_taxon_codes_text}。
        - suggested_display_name：中文分類名稱。
        - suggested_themes：題材標籤陣列，例如 ["FOPLP", "玻璃基板", "先進封裝設備"]。
        - confidence：high / medium / low。
        - reason：簡短說明分類依據，請以公司實際產品與營收來源為主，不要只看市場題材。
        - evidence：找到的產品、營收、法說、官網或新聞依據摘要。
        - needs_manual_review：一律填 true，除非分類已非常明確且與公司本業完全一致。
    EPS 欄位請務必拆欄，不可把「最新單季 EPS」、「近四季 TTM EPS」、「完整年度 EPS」、「Forward EPS」混在同一欄：
    - latest_month_eps：最新單月 / 自結 EPS，例如注意股公告或公司自結的 4 月 EPS；只可填單月值，不可填季度或年化值。
    - latest_quarter_eps：最新已公告季度 EPS。
    - previous_quarter_eps：前一季 EPS。
    - last_two_quarter_eps：近二季 EPS 合計，用於 Run-rate EPS；不可取代 TTM EPS 或 FY1/FY2。
    - ttm_eps：近四季 EPS 合計。
    - fiscal_year_eps：最近完整年度 EPS。
    - forward_eps_ai：AI 從最新新聞/券商報告抓取或推估的 {target_year} EPS。
    - forward_eps_consensus：多家法人共識 EPS；若無明確共識請填 null。
    - forward_eps_fy1：FY1 EPS，通常是市場接下來 6～12 個月最常用的年度 EPS。
    - forward_eps_fy2：FY2 EPS，市場先行半年到一年、法人樂觀估值常使用的明年 EPS。
    - forward_eps_fy3：FY3 EPS 或長期情境 EPS，只能作高風險先行情境，不可作一般買點。
    - forward_eps_fy1_year / forward_eps_fy2_year / forward_eps_fy3_year：上述 EPS 對應年度，例如 2026、2027、2028。
    - forward_eps_fy_source_note：簡述 EPS 年期資料來源與可靠度，例如「券商共識」、「單一券商」、「AI依成長率推估」。
    - trailing_eps 與 forward_eps 為向下相容 legacy 欄位，trailing_eps 可同 ttm_eps，forward_eps 可同 forward_eps_consensus 或 forward_eps_ai。

    欄位來源優先表：
    {source_priority_prompt}
    若搜尋結果與欄位來源優先表衝突，請優先依照優先表判斷；若採用較低順位來源，必須在 _sources.<field>.note 說明原因。尤其注意：
    - 最新單月 / 自結 EPS 若存在，必須填 latest_month_eps，並在 _sources.latest_month_eps.note 寫明月份與是否為自結；不得塞入 latest_quarter_eps。
    - 月營收 YoY / MoM 必須以公告月份的單月資料為準，不可用 yfinance revenueGrowth 或累計 YoY 覆蓋。
    - Forward EPS 必須拆 FY1 / FY2 / FY3 與來源可靠度；FY2/FY3 不可冒充 FY1。
    - D/E 必須說明是倍數或百分比，系統會統一標準化成倍數。

    必須嚴格回傳包含上述財務欄位的 JSON 格式。百分比請轉換為小數（例如 25.5% 寫成 0.255，衰退5%寫成 -0.05），數值請直接輸出數字。若查無資料，該欄位請填 null。
    請務必搜尋近期各大券商對該公司的最新目標價。

    重要：除了上述財務與分類欄位，請額外回傳「_sources」物件，逐欄標示每個數值的來源。
    _sources 內每個欄位必須包含：
    - source：來源名稱，例如 Yahoo股市、Goodinfo、公開資訊觀測站、券商報告、公司法說會、MoneyDJ、鉅亨網等。
    - published_date：該資料發布日期、法說日期、報導日期或財報所屬期間。
    - source_url：可查證網址；若搜尋工具無法提供網址，請填空字串。
    - note：簡短說明該欄位採用邏輯，例如「近四季合計」、「2026法人均值」、「最新月營收」。
    若某欄位查無資料，數值填 null，_sources 該欄位也要保留，但 source 與 source_url 可填空字串。

    注意：本函式只負責財報與估值校對，不要查詢 ETF 持股；ETF 持股由獨立按鈕 get_etf_holders_from_ai() 執行。
    JSON 格式範例：
    {{"pe": 15.2, "latest_month_eps": 0.42, "latest_quarter_eps": 1.35, "previous_quarter_eps": 1.10, "last_two_quarter_eps": 2.45, "ttm_eps": 5.4, "fiscal_year_eps": 4.9, "forward_eps_system": null, "forward_eps_ai": 6.0, "forward_eps_consensus": 6.2, "forward_eps_fy1": 6.2, "forward_eps_fy2": 7.4, "forward_eps_fy3": 8.6, "forward_eps_fy1_year": 2026, "forward_eps_fy2_year": 2027, "forward_eps_fy3_year": 2028, "forward_eps_fy_source_note": "券商共識 FY1/FY2，FY3 為高成長情境", "trailing_eps": 5.4, "forward_eps": 6.2, "pb": 2.1, "gross_margin": 0.255, "operating_margin": 0.123, "roe": 0.15, "yoy": 0.35, "target_price": 1050.0, "target_price_high": 1200.0, "target_price_avg": 1050.0, "target_price_low": 900.0, "target_price_analyst_count": 18, "target_price_rationale": "AI 伺服器需求強、毛利率改善但評價偏高", "debt_to_equity": 0.45, "mom": 0.015, "dividend_yield": 0.032, "data_period": "2026/05/15", "free_cash_flow": 1500000000, "current_ratio": 1.85, "shares_outstanding": 2500000000, "industry_classification": {{"suggested_primary_taxon": "AI_SERVER_ODM", "suggested_display_name": "AI 伺服器 ODM / 組裝", "suggested_themes": ["AI伺服器", "資料中心"], "confidence": "medium", "reason": "主要成長動能來自 AI 伺服器，但仍需確認營收比重。", "evidence": "近期法說與新聞提及 AI 伺服器出貨動能。", "needs_manual_review": true}}, "_sources": {{"pe": {{"source": "Yahoo股市", "published_date": "2026/05/31", "source_url": "https://example.com", "note": "最新可得本益比"}}, "latest_month_eps": {{"source": "公司自結公告", "published_date": "2026/05/10", "source_url": "https://example.com", "note": "2026年4月單月 EPS"}}, "ttm_eps": {{"source": "最新財報/公開資訊觀測站", "published_date": "2026Q1", "source_url": "https://example.com", "note": "近四季 EPS 合計"}}, "last_two_quarter_eps": {{"source": "最新財報/公開資訊觀測站", "published_date": "2026Q1", "source_url": "https://example.com", "note": "近二季 EPS 合計，用於 Run-rate 動能估值"}}, "forward_eps_consensus": {{"source": "券商/法人預估彙整", "published_date": "2026/05/20", "source_url": "https://example.com", "note": "{target_year} 年度 EPS 共識預估"}}, "target_price_avg": {{"source": "券商目標價彙整", "published_date": "2026/05/20", "source_url": "https://example.com", "note": "最新法人目標價均值"}}}}, "source_urls": ["https://example.com"]}}
    絕對不要輸出 markdown 標記或其他文字。"""

    prompt_text = f"請啟用搜尋引擎，【務必尋找最新日期】查詢台股 {stock_name} ({stock_id}) 現價、TTM EPS、FY1/FY2/FY3 法人預測 EPS、毛利率、營益率、最新公告月份單月營收 YoY，以及法人目標價的代表值/平均/最低/最高。程式已取得資料：{programmatic_snapshot_text}；請優先補齊：{fill_scope_text}。請務必確認並標示 EPS 年度、資料發布日期與逐欄來源！不要查詢 ETF 持股，ETF 持股由獨立功能處理。"

    def _make_config(search_enabled=True):
        kwargs = {
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
        }
        if search_enabled:
            kwargs["tools"] = [_google_search_tool()]
        return types.GenerateContentConfig(**kwargs)

    def _is_non_retryable_error(err_text):
        """授權/權限/模型不存在這類錯誤，短時間重試通常無效。"""
        t = str(err_text).lower()
        fatal_keywords = [
            "api key not valid", "invalid api key", "api_key_invalid",
            "permission_denied", "permission denied", "unauthenticated",
            "401", "403", "not found", "model not found",
            "billing", "quota exceeded"
        ]
        return any(k in t for k in fatal_keywords)

    # Pro Only：只用付費版高階模型 + Google Search；不降級。
    candidate_model = "gemini-3.1-pro-preview"
    retry_delays = [0, 3, 8]
    attempts = []
    response = None
    text = None
    used_model = candidate_model
    used_search = True
    fallback_reason = ""
    last_error = None

    for idx, delay_sec in enumerate(retry_delays, start=1):
        if delay_sec > 0:
            time.sleep(delay_sec)

        try:
            response = client.models.generate_content(
                model=candidate_model,
                contents=prompt_text,
                config=_make_config(search_enabled=True)
            )
            text = response.text
            log_data_health("Gemini", True, 200)
            attempts.append({
                "attempt": idx,
                "model": candidate_model,
                "search_enabled": True,
                "delay_before_retry_sec": delay_sec,
                "ok": True,
                "reason": "Pro Only 同模型聯網重試成功" if idx > 1 else "Pro Only 付費版高階模型聯網成功"
            })
            break
        except Exception as e:
            err_msg = str(e)
            last_error = err_msg
            log_data_health("Gemini", False, f"ERR:{candidate_model}:search:try{idx}")
            attempts.append({
                "attempt": idx,
                "model": candidate_model,
                "search_enabled": True,
                "delay_before_retry_sec": delay_sec,
                "ok": False,
                "error": err_msg[:500],
                "reason": "Pro Only 付費版高階模型聯網失敗；不降級，只重試同模型"
            })
            if _is_non_retryable_error(err_msg):
                break

    if response is None or text is None:
        return {
            "error": (
                "Gemini 3.1 Pro Preview（付費版）聯網財報校對失敗。"
                f"系統已用同一付費模型重試 {len(attempts)} 次，仍未成功；"
                "已禁止降級到 2.5 Pro / 2.5 Flash / 離線保底，以避免不準數據進入極限高空價。"
                "請稍後再試，或檢查 API 權限、配額與模型可用狀態。"
            ),
            "last_error": str(last_error)[:500] if last_error else None,
            "attempts": attempts
        }

    if not text:
        return {
            "error": "Gemini 3.1 Pro Preview（付費版）回傳內容為空；系統不降級，請稍後重試。",
            "attempts": attempts
        }

    marker_match = re.search(r"\[TARGET_PRICE:\s*([^,\]]+)\s*,\s*([^,\]]+)\s*,\s*([^\]]+)\]", text)
    marker_data = {}
    if marker_match:
        marker_data = {
            "target_price_high": s_float(marker_match.group(1).replace("無", "")),
            "target_price_avg": s_float(marker_match.group(2).replace("無", "")),
            "target_price_low": s_float(marker_match.group(3).replace("無", "")),
        }

    s_idx = text.find('{')
    e_idx = text.rfind('}')
    if s_idx != -1 and e_idx != -1:
        clean_text = text[s_idx:e_idx+1]
        try:
            parsed = json.loads(clean_text)
            if isinstance(parsed, dict):
                parsed = postprocess_financial_ai_payload(
                    parsed,
                    marker_data=marker_data,
                    stock_id=stock_id,
                    stock_name=stock_name,
                    target_year=target_year,
                    used_model=used_model,
                    used_search=used_search,
                    fallback_reason=fallback_reason,
                    attempts=attempts,
                    prompt_text=prompt_text,
                    system_prompt=system_prompt,
                )
            return parsed
        except json.JSONDecodeError:
            return {
                "error": "AI 回傳的格式不正確，無法解析 JSON 資料。系統不降級，請稍後重試。",
                "raw_text_preview": text[:500],
                "attempts": attempts
            }
    else:
        return {
            "error": "AI 回傳的格式不正確，無法萃取 JSON 資料。系統不降級，請稍後重試。",
            "raw_text_preview": text[:500],
            "attempts": attempts
        }

@st.cache_data(ttl=86400)
def get_peers_from_ai(stock_name, stock_id, api_key):
    if not api_key: return []
    try:
        client = genai.Client(api_key=api_key.strip())
        system_prompt = "請列出與目標公司核心業務最直接競爭的 3~5 家台股上市櫃公司代號。必須是純數字 JSON 陣列格式：[\"2383\", \"3044\"]。絕對不要輸出其他文字。"
        
        response = client.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=f"請尋找 {stock_name} ({stock_id}) 的同業競爭對手",
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=[_google_search_tool()]
            )
        )
        log_data_health("Gemini", True, 200)
        clean_text = re.sub(r'```json\n?|```', '', response.text).strip()
        peers = json.loads(clean_text)
        if isinstance(peers, list): return [str(p) for p in peers][:4] 
    except Exception as e: 
        log_data_health("Gemini", False, str(e))
    return []

def get_ai_industry_analysis(stock_name, stock_id, api_key, context_data, model_name="gemini-3.1-pro-preview"):
    if not api_key: return "ERROR: 未輸入金鑰"
    try:
        client = genai.Client(api_key=api_key.strip())
        system_prompt = "你是一位精通台股的資深產業分析師與操盤手。請針對目標公司的最新動態提供深度分析，包含產業前景、競爭優勢、系統風險及買賣點策略。請用 Markdown 格式與 Emoji。不要輸出 HTML。"
        
        used_model = "gemini-3.1-pro-preview"
        try:
            response = client.models.generate_content(
                model=used_model,
                contents=f"請深度分析台股 {stock_name} ({stock_id})。關鍵數據：\n{context_data}",
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=[_google_search_tool()]
                )
            )
            log_data_health("Gemini", True, 200)
            ans = re.sub(r'```markdown\n?|```', '', response.text).strip()
            return ans
        except Exception as e:
            log_data_health("Gemini", False, f"ERR:{used_model}:search")
            return f"⚠️ Gemini 3.1 Pro Preview（付費版）聯網分析失敗；系統已禁止降級到 2.5 系列，以避免不準資料。細節: {str(e)}"
    except Exception as e: 
        return f"連線異常: {str(e)}"

def _parse_revenue_number(value):
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "null", "--", "-"}:
        return None
    text = text.replace(",", "").replace("，", "")
    text = re.sub(r"[^0-9.\-]", "", text)
    return s_float(text)


def _flatten_table_columns(df):
    out = df.copy()
    cols = []
    for col in out.columns:
        if isinstance(col, tuple):
            parts = [str(x).strip() for x in col if str(x).strip() and not str(x).startswith("Unnamed")]
            cols.append(" ".join(parts) if parts else str(col[-1]).strip())
        else:
            cols.append(str(col).strip())
    out.columns = cols
    return out


def _find_col(columns, include, exclude=None):
    exclude = exclude or []
    for col in columns:
        name = str(col)
        if all(token in name for token in include) and not any(token in name for token in exclude):
            return col
    return None


def _roc_yyyymm_to_month(value):
    text = re.sub(r"\D", "", str(value or ""))
    if not text:
        return ""
    if len(text) == 6 and text.startswith("20"):
        year = int(text[:4])
        month = int(text[4:6])
    elif len(text) >= 5:
        year = int(text[:-2]) + 1911
        month = int(text[-2:])
    else:
        return ""
    if month < 1 or month > 12:
        return ""
    return f"{year:04d}/{month:02d}"


def _roc_date_to_iso(value):
    text = re.sub(r"\D", "", str(value or ""))
    if not text:
        return ""
    if len(text) == 8 and text.startswith("20"):
        year = int(text[:4])
        month = int(text[4:6])
        day = int(text[6:8])
    elif len(text) >= 7:
        year = int(text[:-4]) + 1911
        month = int(text[-4:-2])
        day = int(text[-2:])
    else:
        return ""
    if month < 1 or month > 12 or day < 1 or day > 31:
        return ""
    return f"{year:04d}/{month:02d}/{day:02d}"


def parse_mops_monthly_revenue_csv(csv_text, stock_id, market_label="", source_url=""):
    """Parse MOPS OpenData monthly revenue CSV for one stock.

    t187ap05_* values are in thousand NTD. Returned monthly_revenue is NTD.
    """
    if not csv_text or not stock_id:
        return pd.DataFrame()
    try:
        table = pd.read_csv(io.StringIO(csv_text), dtype=str)
    except Exception:
        return pd.DataFrame()
    if table.empty:
        return pd.DataFrame()

    table = table.copy()
    table.columns = [str(c).strip().lstrip("\ufeff") for c in table.columns]
    cols = list(table.columns)
    code_col = _find_col(cols, ["公司代號"])
    name_col = _find_col(cols, ["公司名稱"])
    period_col = _find_col(cols, ["資料年月"])
    announce_col = _find_col(cols, ["出表日期"])
    current_col = _find_col(cols, ["當月營收"], exclude=["累計", "去年", "上月"])
    prev_col = _find_col(cols, ["上月營收"], exclude=["累計"])
    last_year_col = _find_col(cols, ["去年當月營收"], exclude=["累計"])
    mom_col = _find_col(cols, ["上月比較增減"], exclude=["累計"])
    yoy_col = _find_col(cols, ["去年同月增減"], exclude=["累計"])
    if not code_col or not period_col or not current_col:
        return pd.DataFrame()

    matched = table[table[code_col].astype(str).str.strip() == str(stock_id)]
    if matched.empty:
        return pd.DataFrame()

    row = matched.iloc[0]
    revenue_month = _roc_yyyymm_to_month(row.get(period_col))
    if not revenue_month:
        return pd.DataFrame()
    period = pd.Period(revenue_month.replace("/", "-"), freq="M")
    current = _parse_revenue_number(row.get(current_col))
    prev_month = _parse_revenue_number(row.get(prev_col)) if prev_col else None
    last_year = _parse_revenue_number(row.get(last_year_col)) if last_year_col else None
    mom_pct = _parse_revenue_number(row.get(mom_col)) if mom_col else None
    yoy_pct = _parse_revenue_number(row.get(yoy_col)) if yoy_col else None
    if current is None:
        return pd.DataFrame()

    rows = [{"date": period.to_timestamp(), "revenue": current * 1000}]
    if prev_month is not None:
        rows.append({"date": (period - 1).to_timestamp(), "revenue": prev_month * 1000})
    if last_year is not None:
        rows.append({"date": (period - 12).to_timestamp(), "revenue": last_year * 1000})

    growth_df = build_monthly_revenue_growth_frame(pd.DataFrame(rows), "date", "revenue")
    latest = growth_df[growth_df["revenue_month"] == revenue_month].copy()
    if latest.empty:
        return pd.DataFrame()
    if pd.isna(latest.iloc[0].get("monthly_revenue_mom")) and mom_pct is not None:
        latest.loc[:, "monthly_revenue_mom"] = mom_pct
        latest.loc[:, "MoM"] = mom_pct
    if pd.isna(latest.iloc[0].get("monthly_revenue_yoy")) and yoy_pct is not None:
        latest.loc[:, "monthly_revenue_yoy"] = yoy_pct
        latest.loc[:, "YoY"] = yoy_pct

    announce_date = _roc_date_to_iso(row.get(announce_col)) if announce_col else ""
    source_name = f"MOPS 開放資料月營收({market_label})" if market_label else "MOPS 開放資料月營收"
    latest.loc[:, "stock_id"] = str(stock_id)
    latest.loc[:, "stock_name"] = str(row.get(name_col, "")).strip() if name_col else ""
    latest.loc[:, "revenue_source"] = source_name
    latest.loc[:, "source_rule"] = "MOPS OpenData monthly revenue; same-month YoY/MoM"
    latest.loc[:, "announce_date"] = announce_date
    latest.loc[:, "announce_month"] = announce_date[:7] if announce_date else ""
    latest.loc[:, "source_url"] = source_url
    return latest.reset_index(drop=True)


class _SimpleHtmlTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self._table = None
        self._row = None
        self._cell = None
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
            self._in_cell = True

    def handle_data(self, data):
        if self._in_cell and self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"td", "th"} and self._in_cell and self._row is not None:
            text = " ".join("".join(self._cell or []).split())
            self._row.append(text)
            self._cell = None
            self._in_cell = False
        elif tag == "tr" and self._table is not None and self._row:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def _read_html_tables_with_fallback(html):
    try:
        return pd.read_html(io.StringIO(html))
    except Exception:
        parser = _SimpleHtmlTableParser()
        try:
            parser.feed(html)
        except Exception:
            return []
        tables = []
        for rows in parser.tables:
            if not rows:
                continue
            width = max(len(row) for row in rows)
            padded = [row + [""] * (width - len(row)) for row in rows]
            header = padded[0]
            body = padded[1:] if len(padded) > 1 else []
            if body:
                tables.append(pd.DataFrame(body, columns=header))
        return tables


def parse_mops_monthly_revenue_html(html, stock_id, revenue_month):
    """Parse one MOPS monthly revenue page for a single stock.

    MOPS monthly revenue values are in thousand NTD. Returned monthly_revenue is NTD.
    """
    if not html or not stock_id:
        return pd.DataFrame()
    tables = _read_html_tables_with_fallback(html)
    if not tables:
        return pd.DataFrame()

    period = pd.Period(str(revenue_month).replace("/", "-"), freq="M")
    for raw_table in tables:
        table = _flatten_table_columns(raw_table)
        cols = list(table.columns)
        code_col = _find_col(cols, ["代號"]) or _find_col(cols, ["公司", "代號"])
        name_col = _find_col(cols, ["公司", "名稱"]) or _find_col(cols, ["名稱"])
        current_col = _find_col(cols, ["當月營收"], exclude=["累計", "去年", "上月"])
        prev_col = _find_col(cols, ["上月營收"], exclude=["累計"])
        last_year_col = _find_col(cols, ["去年當月營收"], exclude=["累計"])
        mom_col = _find_col(cols, ["上月", "增減"], exclude=["累計"])
        yoy_col = _find_col(cols, ["去年同月", "增減"], exclude=["累計"])

        for _, row in table.iterrows():
            cells = [str(x).strip() for x in row.tolist()]
            code_text = str(row.get(code_col, "")).strip() if code_col else ""
            if code_text != str(stock_id) and str(stock_id) not in cells[:3]:
                continue

            def by_col_or_pos(col, pos):
                if col is not None:
                    return row.get(col)
                return row.iloc[pos] if len(row) > pos else None

            current = _parse_revenue_number(by_col_or_pos(current_col, 2))
            prev_month = _parse_revenue_number(by_col_or_pos(prev_col, 3))
            last_year = _parse_revenue_number(by_col_or_pos(last_year_col, 4))
            mom_pct = _parse_revenue_number(by_col_or_pos(mom_col, 5))
            yoy_pct = _parse_revenue_number(by_col_or_pos(yoy_col, 6))
            if current is None:
                continue

            rows = [{"date": period.to_timestamp(), "revenue": current * 1000}]
            if prev_month is not None:
                rows.append({"date": (period - 1).to_timestamp(), "revenue": prev_month * 1000})
            if last_year is not None:
                rows.append({"date": (period - 12).to_timestamp(), "revenue": last_year * 1000})

            growth_df = build_monthly_revenue_growth_frame(pd.DataFrame(rows), "date", "revenue")
            latest = growth_df[growth_df["revenue_month"] == f"{period.year:04d}/{period.month:02d}"].copy()
            if latest.empty:
                continue
            if pd.isna(latest.iloc[0].get("monthly_revenue_mom")) and mom_pct is not None:
                latest.loc[:, "monthly_revenue_mom"] = mom_pct
                latest.loc[:, "MoM"] = mom_pct
            if pd.isna(latest.iloc[0].get("monthly_revenue_yoy")) and yoy_pct is not None:
                latest.loc[:, "monthly_revenue_yoy"] = yoy_pct
                latest.loc[:, "YoY"] = yoy_pct

            company_name = str(row.get(name_col, "")).strip() if name_col else ""
            latest.loc[:, "stock_id"] = str(stock_id)
            latest.loc[:, "stock_name"] = company_name
            latest.loc[:, "revenue_source"] = "MOPS 公開資訊觀測站月營收"
            latest.loc[:, "source_rule"] = "MOPS monthly revenue; same-month YoY/MoM"
            latest.loc[:, "announce_date"] = ""
            latest.loc[:, "announce_month"] = ""
            latest.loc[:, "source_url"] = ""
            return latest.reset_index(drop=True)
    return pd.DataFrame()


def _mops_revenue_month_candidates(today=None, max_back_months=6):
    expected = expected_latest_revenue_month(today)
    base = pd.Period(str(expected).replace("/", "-"), freq="M")
    return [base - i for i in range(max_back_months)]


def get_mops_monthly_revenue(
    stock_id,
    today=None,
    max_back_months=2,
    request_timeout=(0.8, 1.8),
    allow_legacy_fallback=False,
):
    """Fetch official MOPS revenue with a bounded fast path.

    Streamlit Cloud may block or throttle MOPS. The primary request path only
    checks the three OpenData markets with short connect/read timeouts. The old
    month-by-month HTML crawl is opt-in because its worst case could block the
    whole page for several minutes.
    """
    opendata_markets = [
        ("L", "上市"),
        ("O", "上櫃"),
        ("R", "興櫃"),
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    for suffix, market_label in opendata_markets:
        url = f"https://mopsfin.twse.com.tw/opendata/t187ap05_{suffix}.csv"
        try:
            res = requests.get(url, headers=headers, timeout=request_timeout)
            ok = res.status_code == 200
            log_data_health("MOPS OpenData", ok, res.status_code)
            if not ok:
                continue
            raw = res.content
            for encoding in ("utf-8-sig", "big5"):
                try:
                    text = raw.decode(encoding, errors="ignore")
                    break
                except Exception:
                    text = res.text
            parsed = parse_mops_monthly_revenue_csv(text, stock_id, market_label, url)
            if parsed is not None and not parsed.empty:
                return parsed
        except Exception as e:
            log_exception("MOPS", f"get_mops_monthly_revenue_opendata:{stock_id}:{suffix}", e)
            log_data_health("MOPS OpenData", False, f"ERR:{str(e)[:120]}")

    if not allow_legacy_fallback:
        return pd.DataFrame()

    markets = [
        ("sii", "上市"),
        ("otc", "上櫃"),
        ("rotc", "興櫃"),
    ]
    for period in _mops_revenue_month_candidates(today=today, max_back_months=max_back_months):
        roc_year = period.year - 1911
        month = period.month
        revenue_month = f"{period.year:04d}/{period.month:02d}"
        for market_key, market_label in markets:
            url = f"https://mops.twse.com.tw/nas/t21/{market_key}/t21sc03_{roc_year}_{month}_0.html"
            try:
                res = requests.get(url, headers=headers, timeout=request_timeout)
                ok = res.status_code == 200
                log_data_health("MOPS", ok, res.status_code)
                if not ok:
                    continue
                raw = res.content
                try:
                    text = raw.decode("big5", errors="ignore")
                except Exception:
                    text = res.text
                parsed = parse_mops_monthly_revenue_html(text, stock_id, revenue_month)
                if parsed is not None and not parsed.empty:
                    parsed.loc[:, "revenue_source"] = f"MOPS 公開資訊觀測站月營收({market_label})"
                    parsed.loc[:, "source_url"] = url
                    return parsed
            except Exception as e:
                log_exception("MOPS", f"get_mops_monthly_revenue:{stock_id}:{market_key}:{revenue_month}", e)
                log_data_health("MOPS", False, f"ERR:{str(e)[:120]}")
    return pd.DataFrame()


def merge_mops_latest_revenue(history_df, mops_df):
    """Use MOPS latest row as official source while preserving historical rows."""
    if mops_df is None or getattr(mops_df, "empty", True):
        return history_df
    if history_df is None or getattr(history_df, "empty", True):
        return mops_df.copy()

    hist = history_df.copy()
    mops = mops_df.copy()
    month_col = "Month" if "Month" in hist.columns else "revenue_month"
    mops_month = str(mops["Month"].iloc[-1] if "Month" in mops.columns else mops["revenue_month"].iloc[-1])
    all_cols = list(dict.fromkeys(list(hist.columns) + list(mops.columns)))
    for col in all_cols:
        if col not in hist.columns:
            hist[col] = None
        if col not in mops.columns:
            mops[col] = None
    hist = hist[all_cols]
    mops = mops[all_cols]
    if month_col in hist.columns:
        hist = hist[hist[month_col].astype(str).map(normalize_revenue_month) != normalize_revenue_month(mops_month)]
    hist_nonempty = hist.dropna(axis=1, how="all")
    mops_latest = mops.tail(1).dropna(axis=1, how="all")
    merged = pd.concat([hist_nonempty, mops_latest], ignore_index=True, sort=False)
    if "Month" in merged.columns:
        merged["_sort_month"] = merged["Month"].astype(str).map(normalize_revenue_month)
        merged = merged.sort_values("_sort_month").drop(columns=["_sort_month"]).reset_index(drop=True)
    return merged


@st.cache_data(ttl=43200, show_spinner="正在快速取得月營收（逾時將自動跳過）…")
def get_monthly_revenue(stock_id, fm_key=""):
    """取得月營收資料，並明確保留「實際公告月份」。

    重要原則：
    - Month / actual_revenue_month 一律來自資料來源回傳的月份，不使用查詢當月推定。
    - UI 顯示時應使用 actual_revenue_month，避免 6/1 查詢時誤標成 5 月營收。
    - 保留舊欄位 Month/Revenue/YoY/MoM，確保既有評分與圖表相容。
    """

    def _standardize_revenue_df(df, source="", source_url="", source_date=None, source_rule=""):
        if df is None or df.empty:
            return df
        out = df.copy()
        fetch_date = source_date or datetime.date.today().isoformat()
        if "Month" in out.columns:
            out["actual_revenue_month"] = out["Month"].astype(str).map(normalize_revenue_month)
            out["revenue_month"] = out["actual_revenue_month"]
        if "Revenue" in out.columns:
            out["monthly_revenue"] = out["Revenue"]
        if "YoY" in out.columns:
            out["monthly_yoy"] = out["YoY"]
            if "monthly_revenue_yoy" not in out.columns:
                out["monthly_revenue_yoy"] = out["YoY"]
        if "MoM" in out.columns:
            out["monthly_mom"] = out["MoM"]
            if "monthly_revenue_mom" not in out.columns:
                out["monthly_revenue_mom"] = out["MoM"]
        out["revenue_source"] = source
        out["source_url"] = source_url
        out["source_date"] = fetch_date
        if source_rule:
            out["source_rule"] = source_rule
        elif "source_rule" not in out.columns:
            out["source_rule"] = "monthly revenue only; not yfinance revenueGrowth"

        # FinMind/Yahoo do not expose an official announcement date in these endpoints.
        # Keep that explicit so the UI does not mistake fetch date for announce date.
        for col in ("announce_date", "announce_month"):
            if col not in out.columns:
                out[col] = "來源未提供"
            else:
                cleaned = out[col].fillna("").astype(str).str.strip()
                cleaned = cleaned.mask(cleaned.str.lower().isin(["", "nan", "none", "nat", "null"]), "來源未提供")
                out[col] = cleaned
        if "revenue_month" not in out.columns:
            out["revenue_month"] = ""
        out["revenue_month"] = out["revenue_month"].astype(str).map(normalize_revenue_month)
        return out

    # Fast-first order: Yahoo -> FinMind -> bounded MOPS fallback.  The former
    # MOPS-first order could issue up to 21 sequential 10-second requests.
    try:
        y_url = f"https://tw.stock.yahoo.com/quote/{stock_id}/revenue"
        y_res = requests.get(y_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=(1.5, 4.0))
        log_data_health("Yahoo", y_res.status_code == 200, y_res.status_code)
        if y_res.status_code == 200:
            json_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', y_res.text)
            if json_match:
                raw_json = json.loads(json_match.group(1))
                def find_rev_list(node):
                    if isinstance(node, dict):
                        if 'yearMonth' in node and 'revenue' in node and 'monthOverMonth' in node:
                            return [node]
                        res = []
                        for k, v in node.items():
                            ext = find_rev_list(v)
                            if ext: res.extend(ext)
                        return res
                    elif isinstance(node, list):
                        res = []
                        for item in node:
                            ext = find_rev_list(item)
                            if ext: res.extend(ext)
                        return res
                    return []

                rev_list = find_rev_list(raw_json)
                valid_revs = [r for r in rev_list if isinstance(r.get('yearMonth'), str) and re.match(r'\d{4}/\d{2}', r.get('yearMonth'))]

                if valid_revs:
                    def get_raw(field):
                        val = field
                        if isinstance(val, dict): return val.get('raw', 0)
                        return float(val) if val is not None else 0

                    rows = []
                    for item in valid_revs:
                        mon = item.get('yearMonth')
                        rev_raw = get_raw(item.get('revenue'))
                        if mon and rev_raw:
                            rows.append({
                                "date": f"{mon.replace('/', '-')}-01",
                                "revenue": rev_raw,
                                "_source_yoy": get_raw(item.get('yearOverYear')),
                                "_source_mom": get_raw(item.get('monthOverMonth')),
                            })

                    growth_df = build_monthly_revenue_growth_frame(pd.DataFrame(rows), "date", "revenue")
                    if not growth_df.empty:
                        final_df = growth_df.dropna(subset=["YoY"]).tail(12).copy()
                        if final_df.empty:
                            latest = growth_df.iloc[-1].copy()
                            matching = pd.DataFrame(rows)
                            latest_row = matching.sort_values("date").iloc[-1] if not matching.empty else {}
                            latest["YoY"] = s_float(latest_row.get("_source_yoy")) * 100 if s_float(latest_row.get("_source_yoy")) is not None else None
                            latest["MoM"] = s_float(latest_row.get("_source_mom")) * 100 if s_float(latest_row.get("_source_mom")) is not None else None
                            latest["monthly_revenue_yoy"] = latest["YoY"]
                            latest["monthly_revenue_mom"] = latest["MoM"]
                            final_df = pd.DataFrame([latest])
                        if not final_df.empty:
                            final_df['Revenue'] = pd.to_numeric(final_df['Revenue'], errors='coerce').round(2)
                            final_df['YoY'] = pd.to_numeric(final_df['YoY'], errors='coerce').round(2)
                            final_df['MoM'] = pd.to_numeric(final_df['MoM'], errors='coerce').round(2)
                            final_df = final_df[['Month', 'Revenue', 'YoY', 'MoM', 'monthly_revenue', 'monthly_revenue_yoy', 'monthly_revenue_mom', 'source_rule']].reset_index(drop=True)
                            yahoo_df = _standardize_revenue_df(
                                final_df,
                                source="Yahoo 股市月營收",
                                source_url=y_url,
                                source_rule="Yahoo monthly revenue yearMonth; same-month YoY/MoM; not yfinance revenueGrowth",
                            )
                            return yahoo_df
    except Exception as e:
        log_exception("Yahoo", f"get_monthly_revenue:yahoo:{stock_id}", e)

    try:
        today = datetime.date.today()
        start_str = f"{today.year - 2}-{today.month:02d}-01"
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMonthRevenue&data_id={stock_id}&start_date={start_str}"
        if fm_key: url += f"&token={fm_key}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=(1.5, 4.0))
        ok = (res.status_code == 200)
        status_val = res.status_code
        data = res.json()
        ok = ok and data.get('status') == 200
        log_data_health("FinMind", ok, status_val)
        if data.get('status') == 200 and data.get('data'):
            df = pd.DataFrame(data['data'])
            df['date'] = pd.to_datetime(df['date'])
            # 只排除查詢當月；實際最新月份仍以 FinMind 回傳的 date 為準，不自行套用 current_date。
            current_month_start = pd.to_datetime(f"{today.year}-{today.month:02d}-01")
            df = df[df['date'] < current_month_start].sort_values('date').reset_index(drop=True)
            df['revenue'] = pd.to_numeric(df['revenue'], errors='coerce')
            growth_df = build_monthly_revenue_growth_frame(df, "date", "revenue")
            final_df = growth_df.dropna(subset=['YoY']).tail(12).copy()
            if not final_df.empty:
                final_df['Revenue'] = final_df['Revenue'].round(2)
                final_df['YoY'] = final_df['YoY'].round(2)
                final_df['MoM'] = final_df['MoM'].round(2)
                final_df = final_df[['Month', 'Revenue', 'YoY', 'MoM', 'monthly_revenue', 'monthly_revenue_yoy', 'monthly_revenue_mom', 'source_rule']].reset_index(drop=True)
                finmind_df = _standardize_revenue_df(
                    final_df,
                    source="FinMind TaiwanStockMonthRevenue",
                    source_url=url.split('&token=')[0],
                    source_rule="FinMind TaiwanStockMonthRevenue; same-month YoY/MoM; not yfinance revenueGrowth",
                )
                return finmind_df
    except Exception as e:
        log_exception("FinMind", f"get_monthly_revenue:finmind:{stock_id}", e)
        log_data_health("FinMind", False, f"ERR:{str(e)[:120]}")
    mops_df = get_mops_monthly_revenue(
        stock_id,
        max_back_months=2,
        request_timeout=(0.8, 1.8),
        allow_legacy_fallback=False,
    )
    if mops_df is not None and not mops_df.empty:
        return mops_df
    return None

@st.cache_data(ttl=43200, show_spinner="正在取得 P/E、P/B 歷史資料（逾時將自動跳過）…")
def get_pe_pb_data(stock_id, fm_key=""):
    try:
        today = datetime.date.today()
        start_str = f"{today.year - 5}-{today.month:02d}-01"
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPER&data_id={stock_id}&start_date={start_str}"
        if fm_key: url += f"&token={fm_key}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=(1.5, 4.0))
        if res.status_code == 200:
            data = res.json()
            if data.get('status') == 200 and data.get('data'): 
                df = pd.DataFrame(data['data'])
                df['date'] = pd.to_datetime(df['date'])
                df['PER'] = pd.to_numeric(df['PER'], errors='coerce')
                df['PBR'] = pd.to_numeric(df.get('PBR'), errors='coerce') 
                return df[df['PER'] > 0].dropna(subset=['date', 'PER']).reset_index(drop=True)
    except Exception as e:
        log_exception("FinMind", f"get_pe_pb_data:{stock_id}", e)
        log_data_health("FinMind", False, f"ERR:{str(e)[:120]}")
    return None

@st.cache_data(ttl=43200, show_spinner="正在取得財務健康資料（逾時將自動跳過）…")
def get_finmind_financial_health(stock_id, fm_key=""):
    try:
        today = datetime.date.today()
        start_str = f"{today.year - 2}-01-01" 
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockFinancialStatements&data_id={stock_id}&start_date={start_str}"
        if fm_key: url += f"&token={fm_key}"
        res = requests.get(url, timeout=(1.5, 5.0))
        data = res.json()
        if data.get('status') == 200 and data.get('data'):
            df = pd.DataFrame(data['data'])
            if df.empty: return {}
            
            df['date'] = pd.to_datetime(df['date'])
            dates = sorted(df['date'].unique())
            latest_date = dates[-1]
            prev_date = dates[-5] if len(dates) >= 5 else (dates[0] if len(dates)>1 else latest_date)
            
            df_latest = df[df['date'] == latest_date]
            df_prev = df[df['date'] == prev_date]
            
            vals_l = dict(zip(df_latest['type'].astype(str).str.strip(), df_latest['value']))
            vals_p = dict(zip(df_prev['type'].astype(str).str.strip(), df_prev['value']))
            
            def get_val(v_dict, *keys):
                for k in keys:
                    for v_key in v_dict.keys():
                        if k in v_key:
                            try: return float(str(v_dict[v_key]).replace(',', '').replace('%', ''))
                            except Exception as e:
                                log_exception("FinMind", f"get_finmind_financial_health:get_val:{stock_id}", e)
                return 0.0
                
            rev_l = get_val(vals_l, '營業收入', '淨收益', '收益')
            gp_l = get_val(vals_l, '營業毛利', '毛利')
            op_l = get_val(vals_l, '營業利益')
            ni_l = get_val(vals_l, '本期淨利', '淨利')
            ta_l = get_val(vals_l, '資產總計', '資產總額', '資產')
            tl_l = get_val(vals_l, '負債總')
            eq_l = get_val(vals_l, '權益總')
            ca_l = get_val(vals_l, '流動資產')
            cl_l = get_val(vals_l, '流動負債')
            ltd_l = get_val(vals_l, '非流動負債', '長期借款')
            cfo_l = get_val(vals_l, '營業活動之淨現金流入', '營業活動之現金流量', '營業活動之淨現金')
            if cfo_l == 0: cfo_l = op_l 
            shares_l = get_val(vals_l, '普通股股本', '股本')
            
            rev_p = get_val(vals_p, '營業收入', '淨收益', '收益')
            gp_p = get_val(vals_p, '營業毛利', '毛利')
            ni_p = get_val(vals_p, '本期淨利', '淨利')
            ta_p = get_val(vals_p, '資產總計', '資產總額', '資產')
            ca_p = get_val(vals_p, '流動資產')
            cl_p = get_val(vals_p, '流動負債')
            ltd_p = get_val(vals_p, '非流動負債', '長期借款')
            shares_p = get_val(vals_p, '普通股股本', '股本')
            
            if ta_l <= 0 or ta_p <= 0: return {}

            res_dict = {}
            if rev_l > 0:
                res_dict['grossMargins'] = gp_l / rev_l
                res_dict['operatingMargins'] = op_l / rev_l
            if eq_l > 0: res_dict['debtToEquity'] = tl_l / eq_l
                
            f_score = 0
            if ta_l > 0 and ta_p > 0:
                roa_l, roa_p = ni_l / ta_l, ni_p / ta_p
                if roa_l > 0: f_score += 1                 
                if cfo_l > 0: f_score += 1                 
                if roa_l > roa_p: f_score += 1             
                if cfo_l > ni_l: f_score += 1              
                if (ltd_l / ta_l) < (ltd_p / ta_p): f_score += 1  
                cr_l = (ca_l / cl_l) if cl_l > 0 else 0
                cr_p = (ca_p / cl_p) if cl_p > 0 else 0
                if cr_l > cr_p: f_score += 1               
                if shares_l <= shares_p and shares_l > 0: f_score += 1 
                gm_l = (gp_l / rev_l) if rev_l > 0 else 0
                gm_p = (gp_p / rev_p) if rev_p > 0 else 0
                if gm_l > gm_p: f_score += 1               
                at_l = rev_l / ta_l
                at_p = rev_p / ta_p
                if at_l > at_p: f_score += 1               
                
            res_dict['f_score'] = f_score
            res_dict['cfo_l'] = cfo_l
            return res_dict
    except Exception as e:
        log_exception("FinMind", f"get_finmind_financial_health:{stock_id}", e)
        log_data_health("FinMind", False, f"ERR:{str(e)[:120]}")
    return {}

@st.cache_data(ttl=1800)
def get_stock_news(stock_id):
    news_data = []
    
    try:
        query = f"{stock_id} 台股 (財報 OR 法說會 OR 營收 OR 盈餘 OR EPS)"
        encoded_query = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            import email.utils
            root = ET.fromstring(res.text)
            for item in root.findall('.//item')[:5]:
                title = item.find('title').text if item.find('title') is not None else ""
                link = item.find('link').text if item.find('link') is not None else ""
                source = item.find('source').text if item.find('source') is not None else "Google News"
                pubDate = item.find('pubDate').text if item.find('pubDate') is not None else ""
                
                timestamp = 0
                if pubDate:
                    try:
                        parsed_date = email.utils.parsedate_tz(pubDate)
                        if parsed_date:
                            timestamp = int(email.utils.mktime_tz(parsed_date))
                    except Exception as e:
                        log_exception("Yahoo", f"get_stock_news:parse_pubdate:{stock_id}", e)
                    
                news_data.append({
                    "title": title,
                    "publisher": source,
                    "link": link,
                    "timestamp": timestamp
                })
    except Exception as e:
        log_exception("Yahoo", f"get_stock_news:rss:{stock_id}", e)

    if not news_data:
        for ext in [".TW", ".TWO"]:
            try:
                ticker = yf.Ticker(f"{stock_id}{ext}")
                news = ticker.news
                if news:
                    for n in news:
                        title = n.get("title", "")
                        if any(kw in title for kw in ["財報", "法說", "營收", "EPS", "盈餘", "季報", "年報", "獲利"]):
                            news_data.append({
                                "title": title,
                                "publisher": n.get("publisher", ""),
                                "link": n.get("link", ""),
                                "timestamp": n.get("providerPublishTime", 0)
                            })
                    break 
            except Exception as e:
                log_exception("Yahoo", f"get_stock_news:yfinance:{stock_id}{ext}", e)
            
    if news_data:
        news_data.sort(key=lambda x: x["timestamp"], reverse=True)
        return news_data[:5]
    return []

def get_fallback_info(stock_id):
    info = {}
    for ext in [".TW", ".TWO"]:
        try:
            tk = yf.Ticker(f"{stock_id}{ext}")
            fi = tk.fast_info
            if 'last_price' in fi:
                info['realtime_price'] = fi['last_price']
                info['realtime_prev_close'] = fi.get('previous_close')
                info['realtime_open'] = fi.get('open')
                info['realtime_high'] = fi.get('day_high')
                info['realtime_low'] = fi.get('day_low')
                info['realtime_volume'] = fi.get('last_volume')
                break
        except Exception as e:
            log_exception("Yahoo", f"get_fallback_info:fast_info:{stock_id}{ext}", e)
        
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        text = res.text
        
        json_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', text)
        if json_match:
            data = json.loads(json_match.group(1))
            keys_to_find = ['peRatio', 'trailingPE', 'pbRatio', 'priceToBook', 'eps', 'trailingEps', 'dividendYield', 'targetHighPrice', 'targetMeanPrice', 'targetLowPrice', 'numberOfAnalystOpinions', 'grossMargins', 'operatingMargins', 'returnOnEquity']
            found_data = {}
            
            def find_keys(node):
                if isinstance(node, dict):
                    for k, v in node.items():
                        if k in keys_to_find:
                            if isinstance(v, dict) and 'raw' in v:
                                found_data[k] = v['raw']
                            elif isinstance(v, (int, float)):
                                found_data[k] = v
                        find_keys(v)
                elif isinstance(node, list):
                    for item in node:
                        find_keys(item)
                        
            find_keys(data)
            
            info['trailingPE'] = found_data.get('peRatio') or found_data.get('trailingPE')
            info['priceToBook'] = found_data.get('pbRatio') or found_data.get('priceToBook')
            info['trailingEps'] = found_data.get('eps') or found_data.get('trailingEps')
            info['dividendYield'] = found_data.get('dividendYield')
            info['targetHighPrice'] = found_data.get('targetHighPrice')
            info['targetMeanPrice'] = found_data.get('targetMeanPrice')
            info['targetLowPrice'] = found_data.get('targetLowPrice')
            info['numberOfAnalystOpinions'] = found_data.get('numberOfAnalystOpinions')
            info['grossMargins'] = found_data.get('grossMargins')
            info['operatingMargins'] = found_data.get('operatingMargins')
            info['returnOnEquity'] = found_data.get('returnOnEquity')
            
        sec_match = re.search(r'href="/class-quote\?category=([^"&]+)', text)
        if sec_match: info['sector'] = urllib.parse.unquote(sec_match.group(1))
    except Exception as e:
        log_exception("Yahoo", f"get_fallback_info:page_parse:{stock_id}", e)
    return info

@st.cache_data(ttl=30)
def get_realtime_data(stock_id):
    rt_data = {}
    try:
        session = requests.Session()
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        session.get("https://mis.twse.com.tw/stock/index.jsp", headers=headers, timeout=5)
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{stock_id}.tw|otc_{stock_id}.tw"
        res = session.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            msg_array = data.get('msgArray', [])
            if msg_array:
                info = msg_array[0]
                def p_f(v): return float(v) if v != '-' and v is not None else None
                rt_price = p_f(info.get('z'))
                if rt_price is None: rt_price = p_f(info.get('y'))
                if rt_price is not None:
                    rt_data['realtime_price'] = rt_price
                    rt_data['realtime_prev_close'] = p_f(info.get('y'))
                    rt_data['realtime_open'] = p_f(info.get('o')) or rt_price
                    rt_data['realtime_high'] = p_f(info.get('h')) or rt_price
                    rt_data['realtime_low'] = p_f(info.get('l')) or rt_price
                    rt_data['realtime_volume'] = p_f(info.get('v'))
                    return rt_data
    except Exception as e:
        log_exception("TWSE", f"get_realtime_data:mis:{stock_id}", e)

    for ext in [".TW", ".TWO"]:
        try:
            tk = yf.Ticker(f"{stock_id}{ext}")
            fi = tk.fast_info
            if 'last_price' in fi:
                rt_data['realtime_price'] = fi['last_price']
                rt_data['realtime_prev_close'] = fi.get('previous_close')
                rt_data['realtime_open'] = fi.get('open')
                rt_data['realtime_high'] = fi.get('day_high')
                rt_data['realtime_low'] = fi.get('day_low')
                rt_data['realtime_volume'] = fi.get('last_volume')
                return rt_data
        except Exception as e:
            log_exception("Yahoo", f"get_realtime_data:yfinance:{stock_id}{ext}", e)
            continue
        
    return rt_data

def inject_realtime_data(hist, stock_id, timeframe="D"):
    if hist is None or hist.empty: return hist, None
    
    tw_time = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    if tw_time.hour < 9: target_date = (tw_time - datetime.timedelta(days=1)).date()
    else: target_date = tw_time.date()
    
    if hist.index.tz is not None:
        hist = hist[hist.index.date <= target_date]
    else:
        hist = hist[hist.index.date <= target_date]
        
    if hist.empty: return hist, None

    rt_data = get_realtime_data(stock_id)
    rt_price = rt_data.get('realtime_price')
    rt_prev = rt_data.get('realtime_prev_close')
    
    if rt_price is not None and rt_price > 0:
        rt_open = rt_data.get('realtime_open') or rt_price
        rt_high = rt_data.get('realtime_high') or rt_price
        rt_low = rt_data.get('realtime_low') or rt_price
        rt_vol = rt_data.get('realtime_volume') or 0
        
        last_date = hist.index[-1].date()
        if timeframe == "D":
            if last_date < target_date:
                new_idx = pd.to_datetime(target_date)
                if hist.index.tz is not None: new_idx = new_idx.tz_localize(hist.index.tz)
                new_row = pd.DataFrame({
                    'Open': [rt_open], 'High': [rt_high], 'Low': [rt_low], 
                    'Close': [rt_price], 'Volume': [rt_vol]
                }, index=pd.Index([new_idx], name='Date'))
                hist = pd.concat([hist, new_row])
            elif last_date == target_date:
                hist.loc[hist.index[-1], 'Close'] = rt_price
                hist.loc[hist.index[-1], 'Open'] = rt_open
                hist.loc[hist.index[-1], 'High'] = max(hist.loc[hist.index[-1], 'High'], rt_high)
                hist.loc[hist.index[-1], 'Low'] = min(hist.loc[hist.index[-1], 'Low'], rt_low)
                if rt_vol > 0: hist.loc[hist.index[-1], 'Volume'] = rt_vol
        elif timeframe in ["W", "M"]:
            hist.loc[hist.index[-1], 'Close'] = rt_price
            if rt_high > hist.loc[hist.index[-1], 'High']: hist.loc[hist.index[-1], 'High'] = rt_high
            if rt_low < hist.loc[hist.index[-1], 'Low']: hist.loc[hist.index[-1], 'Low'] = rt_low
            
    hist.index.name = 'Date'
    return hist, rt_prev


def reconcile_price_history_with_reference(
    primary_hist,
    reference_hist,
    *,
    stock_id="",
    primary_source="主股價來源",
    reference_source="FinMind",
    divergence_threshold=0.35,
):
    """Flag material price-source divergence without replacing the primary market price."""
    if primary_hist is None or getattr(primary_hist, "empty", True):
        return primary_hist, None
    if reference_hist is None or getattr(reference_hist, "empty", True):
        return primary_hist, None
    try:
        primary_close = float(primary_hist["Close"].dropna().iloc[-1])
        reference_close = float(reference_hist["Close"].dropna().iloc[-1])
    except Exception:
        return primary_hist, None
    if primary_close <= 0 or reference_close <= 0:
        return primary_hist, None

    divergence = abs(primary_close - reference_close) / reference_close
    if divergence <= divergence_threshold:
        return primary_hist, None

    code_text = f"{stock_id} " if stock_id else ""
    note = (
        f"{code_text}股價來源交叉檢查：{primary_source} 最新收盤 {primary_close:.2f} "
        f"與 {reference_source} {reference_close:.2f} 差距 {divergence*100:.1f}%，"
        f"請確認是否為不同市場、延遲資料、還原價或來源錯置；系統不自動覆蓋現價。"
    )
    return primary_hist, note


def _analyst_table_value(table, row_key, column_names):
    """Read one numeric value from a yfinance analyst table without depending on column casing."""
    if not isinstance(table, pd.DataFrame) or table.empty:
        return None

    normalized_rows = {str(label).strip().lower(): label for label in table.index}
    normalized_columns = {str(label).strip().lower(): label for label in table.columns}
    actual_row = normalized_rows.get(str(row_key).strip().lower())
    if actual_row is None:
        return None

    for column_name in column_names:
        actual_column = normalized_columns.get(str(column_name).strip().lower())
        if actual_column is None:
            continue
        value = s_float(table.at[actual_row, actual_column])
        if value is not None and math.isfinite(value):
            return value
    return None


def _infer_analyst_fy1_year(base_info=None, today=None):
    """Infer the calendar label for yfinance's 0y estimate row."""
    base_info = base_info if isinstance(base_info, dict) else {}
    today = today or datetime.date.today()
    if isinstance(today, datetime.datetime):
        today = today.date()
    current_year = int(today.year)
    last_fiscal_year = None
    raw_last_fiscal_end = base_info.get("lastFiscalYearEnd")

    try:
        if isinstance(raw_last_fiscal_end, (datetime.date, datetime.datetime, pd.Timestamp)):
            last_fiscal_year = int(raw_last_fiscal_end.year)
        else:
            timestamp = s_float(raw_last_fiscal_end)
            if timestamp is not None and timestamp > 0:
                last_fiscal_year = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc).year
    except Exception:
        last_fiscal_year = None

    if last_fiscal_year is None:
        return current_year
    return max(current_year, last_fiscal_year + 1)


def extract_yfinance_analyst_snapshot(ticker, base_info=None, today=None):
    """Normalize analyst targets and annual EPS estimates into stable info keys.

    Dedicated yfinance analyst endpoints are preferred. ``Ticker.info`` is
    retained only as a fallback for target-price fields and analyst count.
    FY1/FY2/FY3 are never inferred from the year-less ``forwardEps`` field.
    """
    base_info = base_info if isinstance(base_info, dict) else {}
    snapshot = {}

    try:
        raw_targets = getattr(ticker, "analyst_price_targets")
    except Exception:
        raw_targets = None
    if isinstance(raw_targets, pd.Series):
        raw_targets = raw_targets.to_dict()
    if not isinstance(raw_targets, dict):
        raw_targets = {}

    target_specs = [
        ("targetHighPrice", ("high",)),
        ("targetMeanPrice", ("mean", "median")),
        ("targetLowPrice", ("low",)),
    ]
    target_sources = []
    for output_key, dedicated_keys in target_specs:
        value = None
        source = ""
        for dedicated_key in dedicated_keys:
            value = s_float(raw_targets.get(dedicated_key))
            if value is not None and value > 0:
                source = "Yahoo Finance / yfinance analyst_price_targets"
                break
            value = None
        if value is None:
            fallback_value = s_float(base_info.get(output_key))
            if fallback_value is not None and fallback_value > 0:
                value = fallback_value
                source = "Yahoo Finance / yfinance Ticker.info"
        if value is not None:
            snapshot[output_key] = value
            snapshot[f"{output_key}Source"] = source
            target_sources.append(source)

    analyst_count = s_float(base_info.get("numberOfAnalystOpinions"))
    if analyst_count is not None and 0 < analyst_count <= 100:
        snapshot["numberOfAnalystOpinions"] = int(round(analyst_count))
        snapshot["numberOfAnalystOpinionsSource"] = "Yahoo Finance / yfinance Ticker.info"

    if target_sources:
        distinct_sources = list(dict.fromkeys(target_sources))
        snapshot["targetPriceSource"] = " + ".join(distinct_sources)

    try:
        earnings_estimate = getattr(ticker, "earnings_estimate")
    except Exception:
        earnings_estimate = None
    try:
        eps_trend = getattr(ticker, "eps_trend")
    except Exception:
        eps_trend = None

    fy1_year = _infer_analyst_fy1_year(base_info, today=today)
    for tier, row_key in ((1, "0y"), (2, "+1y"), (3, "+2y")):
        eps_value = _analyst_table_value(earnings_estimate, row_key, ("avg", "average"))
        source = ""
        if eps_value is not None:
            source = f"Yahoo Finance / yfinance earnings_estimate ({row_key})"
        else:
            eps_value = _analyst_table_value(eps_trend, row_key, ("current",))
            if eps_value is not None:
                source = f"Yahoo Finance / yfinance eps_trend ({row_key})"
        if eps_value is None or abs(eps_value) > 10000:
            continue

        prefix = f"forwardEpsFY{tier}"
        snapshot[prefix] = eps_value
        snapshot[f"{prefix}Year"] = fy1_year + tier - 1
        snapshot[f"{prefix}Source"] = source
        analyst_count_for_tier = _analyst_table_value(
            earnings_estimate,
            row_key,
            ("numberOfAnalysts", "numberofanalysts", "analystCount"),
        )
        if analyst_count_for_tier is not None and analyst_count_for_tier > 0:
            snapshot[f"{prefix}AnalystCount"] = int(round(analyst_count_for_tier))

    if any(snapshot.get(f"forwardEpsFY{tier}") is not None for tier in (1, 2, 3)):
        snapshot["forwardEpsFYBasis"] = "Yahoo Finance 法人年度 EPS 預估（程式抓取）"

    return snapshot


@st.cache_data(ttl=3600)
def fetch_finmind_price_history(stock_id, fm_key="", days=1825):
    """Fetch TaiwanStockPrice history from FinMind as price fallback / cross-check."""
    try:
        start_str = f"{(datetime.date.today() - datetime.timedelta(days=days)).isoformat()}"
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id={stock_id}&start_date={start_str}"
        if fm_key:
            url += f"&token={fm_key}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        log_data_health("FinMind", res.status_code == 200, res.status_code)
        data = res.json()
        if data.get('status') == 200 and data.get('data'):
            df = pd.DataFrame(data['data'])
            df['Date'] = pd.to_datetime(df['date'])
            df.rename(columns={'open':'Open','max':'High','min':'Low','close':'Close','Trading_Volume':'Volume'}, inplace=True)
            df.set_index('Date', inplace=True)
            out = df[['Open','High','Low','Close','Volume']].dropna()
            if out is not None and not out.empty:
                out.index.name = 'Date'
                return out
    except Exception as e:
        log_exception("FinMind", f"fetch_finmind_price_history:{stock_id}", e)
        log_data_health("FinMind", False, f"ERR:{str(e)[:120]}")
    return None


@st.cache_data(ttl=3600)
def _get_base_stock_data(stock_id, fugle_key="", fm_key=""):
    hist = None
    info_data = {}
    price_source = None
    info_source = None
    fallback_notes = []

    if fugle_key:
        hist = fetch_fugle_kline(stock_id, fugle_key, "D")
        if hist is not None and not hist.empty:
            price_source = "Fugle API"
    
    for ext in [".TW", ".TWO"]:
        try:
            ticker = yf.Ticker(f"{stock_id}{ext}")
            if hist is None or hist.empty:
                temp_hist = ticker.history(period="5y")
                if not temp_hist.empty:
                    hist = temp_hist
                    price_source = "Yahoo Finance (yfinance)"
            try:
                info_data = ticker.info
                if info_data:
                    info_source = "Yahoo Finance (yfinance)"
            except Exception as e:
                log_exception("Yahoo", f"_get_base_stock_data:ticker_info:{stock_id}{ext}", e)
            try:
                analyst_snapshot = extract_yfinance_analyst_snapshot(ticker, base_info=info_data)
                if analyst_snapshot:
                    info_data.update(analyst_snapshot)
            except Exception as e:
                log_exception("Yahoo", f"_get_base_stock_data:analyst_snapshot:{stock_id}{ext}", e)
            if info_data or (hist is not None and not hist.empty): break
        except Exception as e:
            log_exception("Yahoo", f"_get_base_stock_data:yfinance:{stock_id}{ext}", e)
            continue
            
    if hist is None or hist.empty:
        for ext in [".TW", ".TWO"]:
            try:
                url = f"https://query1.finance.yahoo.com/v7/finance/download/{stock_id}{ext}?range=5y&interval=1d&events=history"
                res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                log_data_health("Yahoo", res.status_code == 200, res.status_code)
                if res.status_code == 200:
                    df = pd.read_csv(io.StringIO(res.text))
                    df['Date'] = pd.to_datetime(df['Date'])
                    df.set_index('Date', inplace=True)
                    hist = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
                    if not hist.empty:
                        price_source = "Yahoo Finance CSV fallback"
                        fallback_notes.append("主資料源失敗，已改用 Yahoo CSV 備援股價。")
                        break
            except Exception as e:
                log_exception("Yahoo", f"_get_base_stock_data:csv_fallback:{stock_id}{ext}", e)

    if hist is None or hist.empty:
        finmind_hist = fetch_finmind_price_history(stock_id, fm_key)
        if finmind_hist is not None and not finmind_hist.empty:
            hist = finmind_hist
            price_source = "FinMind fallback"
            fallback_notes.append("Yahoo 來源失敗，已改用 FinMind 備援股價。")

    if hist is not None and not hist.empty and price_source not in {"FinMind fallback", "Fugle API"}:
        finmind_hist = fetch_finmind_price_history(stock_id, fm_key)
        hist_checked, price_note = reconcile_price_history_with_reference(
            hist,
            finmind_hist,
            stock_id=stock_id,
            primary_source=price_source or "Yahoo/yfinance",
            reference_source="FinMind",
            divergence_threshold=0.35,
        )
        if price_note:
            fallback_notes.append(price_note)

    if hist is not None and not hist.empty:
        hist.index.name = 'Date'
        fallback = get_fallback_info(stock_id)
        filled_from_fallback = 0
        target_fields_from_page_fallback = []
        for k, v in fallback.items():
            if v is not None:
                if k not in info_data or not info_data[k] or str(info_data[k]).lower() == 'nan':
                    info_data[k] = v
                    filled_from_fallback += 1
                    if k in {"targetHighPrice", "targetMeanPrice", "targetLowPrice"}:
                        info_data[f"{k}Source"] = "Yahoo 股市頁面解析備援"
                        target_fields_from_page_fallback.append(k)
                    elif k == "numberOfAnalystOpinions":
                        info_data["numberOfAnalystOpinionsSource"] = "Yahoo 股市頁面解析備援"
        if target_fields_from_page_fallback:
            existing_target_source = str(info_data.get("targetPriceSource") or "").strip()
            fallback_target_source = "Yahoo 股市頁面解析備援"
            info_data["targetPriceSource"] = (
                f"{existing_target_source} + {fallback_target_source}"
                if existing_target_source and fallback_target_source not in existing_target_source
                else (existing_target_source or fallback_target_source)
            )
        if filled_from_fallback > 0:
            if info_source is None:
                info_source = "Yahoo 頁面解析備援"
            fallback_notes.append(f"已由頁面解析補齊 {filled_from_fallback} 個財務欄位。")

    info_data['__price_source'] = price_source or "未知來源"
    info_data['__info_source'] = info_source or "未知來源"
    info_data['__fallback_notes'] = fallback_notes                    
    return hist, info_data

def get_stock_data(stock_id, fugle_key="", fm_key=""):
    hist, info_data = _get_base_stock_data(stock_id, fugle_key, fm_key)
    if hist is not None and not hist.empty:
        hist = hist.copy()
        info_data = info_data.copy()
        hist, rt_prev = inject_realtime_data(hist, stock_id, "D")
        if rt_prev is not None: info_data['previousClose'] = rt_prev
        finmind_hist = fetch_finmind_price_history(stock_id, fm_key)
        hist_checked, price_note = reconcile_price_history_with_reference(
            hist,
            finmind_hist,
            stock_id=stock_id,
            primary_source="即時/主股價來源",
            reference_source="FinMind",
            divergence_threshold=0.35,
        )
        if price_note:
            notes = list(info_data.get('__fallback_notes') or [])
            notes.append(price_note)
            info_data['__fallback_notes'] = notes
    return hist, info_data

@st.cache_data(ttl=900)
def _get_base_chart_data(stock_id, timeframe, fugle_key=""):
    tf_map = {"日線": "D", "週線": "W", "月線": "M", "60分線": "60"}
    if fugle_key:
        tf = tf_map.get(timeframe, "D")
        df = fetch_fugle_kline(stock_id, fugle_key, tf)
        if not df.empty:
            df.index.name = 'Date'
            return df

    interval_map = {"日線": {"period": "1y", "interval": "1d"}, "週線": {"period": "2y", "interval": "1wk"}, "月線": {"period": "5y", "interval": "1mo"}, "60分線": {"period": "1mo", "interval": "60m"}}
    params = interval_map.get(timeframe, {"period": "1y", "interval": "1d"})
    for ext in [".TW", ".TWO"]:
        try:
            ticker = yf.Ticker(f"{stock_id}{ext}")
            df = ticker.history(period=params["period"], interval=params["interval"])
            if not df.empty:
                if df.index.tz is not None: df.index = df.index.tz_localize(None)
                df.index.name = 'Date'
                return df
        except Exception as e:
            log_exception("Yahoo", f"get_price_history:yfinance:{stock_id}{ext}:{timeframe}", e)
            continue
        
    if timeframe == "日線":
        hist, _ = _get_base_stock_data(stock_id, fugle_key, "")
        if hist is not None and not hist.empty: return hist

    return pd.DataFrame()

def get_chart_data(stock_id, timeframe, fugle_key=""):
    df = _get_base_chart_data(stock_id, timeframe, fugle_key)
    if not df.empty:
        df = df.copy()
        if timeframe == "日線": df, _ = inject_realtime_data(df, stock_id, "D")
        elif timeframe == "週線": df, _ = inject_realtime_data(df, stock_id, "W")
        elif timeframe == "月線": df, _ = inject_realtime_data(df, stock_id, "M")
    return df

@st.cache_data(ttl=43200)
def get_inst_data(stock_id, fm_key=""):
    try:
        today = datetime.date.today()
        start_str = (today - datetime.timedelta(days=180)).strftime("%Y-%m-%d")
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={stock_id}&start_date={start_str}"
        if fm_key: url += f"&token={fm_key}" 
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data.get('status') == 200 and data.get('data'):
                df = pd.DataFrame(data['data'])
                if df.empty: return pd.DataFrame()
                df['date'] = pd.to_datetime(df['date'])
                
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
                f_cols = [c for c in pivot_df.columns if '外資' in str(c) or 'Foreign' in str(c)]
                t_cols = [c for c in pivot_df.columns if '投信' in str(c) or 'Trust' in str(c)]
                d_cols = [c for c in pivot_df.columns if '自營商' in str(c) or 'Dealer' in str(c)]
                res_df['Foreign'] = pivot_df[f_cols].sum(axis=1) if f_cols else 0
                res_df['Trust'] = pivot_df[t_cols].sum(axis=1) if t_cols else 0
                res_df['Dealer'] = pivot_df[d_cols].sum(axis=1) if d_cols else 0
                return res_df / 1000 
    except Exception as e:
        log_exception("FinMind", f"get_chip_data:{stock_id}", e)
        log_data_health("FinMind", False, f"ERR:{str(e)[:120]}")
    return pd.DataFrame()


def _safe_ratio(numerator, denominator):
    numerator = s_float(numerator)
    denominator = s_float(denominator)
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _margin_period_change(df, balance_col, trading_days):
    if df is None or df.empty or balance_col not in df.columns:
        return None, None
    if len(df) < trading_days + 1:
        return None, None
    latest = s_float(df[balance_col].iloc[-1])
    if latest is None:
        return None, None
    idx = max(0, len(df) - 1 - trading_days)
    base = s_float(df[balance_col].iloc[idx])
    if base is None:
        return None, None
    change = latest - base
    change_pct = change / base if base > 0 else None
    return change, change_pct


def build_margin_credit_summary(df, shares_outstanding=None):
    """Build a margin/short-sale risk summary from FinMind credit-trading rows."""
    try:
        if df is None or getattr(df, "empty", True):
            return {"available": False, "message": "未取得融資融券資料"}

        data = df.copy()
        if "date" in data.columns:
            data["date"] = pd.to_datetime(data["date"], errors="coerce")
            data = data.sort_values("date")

        numeric_cols = [
            "MarginPurchaseBuy",
            "MarginPurchaseCashRepayment",
            "MarginPurchaseLimit",
            "MarginPurchaseSell",
            "MarginPurchaseTodayBalance",
            "MarginPurchaseYesterdayBalance",
            "OffsetLoanAndShort",
            "ShortSaleBuy",
            "ShortSaleCashRepayment",
            "ShortSaleLimit",
            "ShortSaleSell",
            "ShortSaleTodayBalance",
            "ShortSaleYesterdayBalance",
        ]
        for col in numeric_cols:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce")

        latest = data.iloc[-1]
        margin_balance = s_float(latest.get("MarginPurchaseTodayBalance"))
        margin_yesterday = s_float(latest.get("MarginPurchaseYesterdayBalance"))
        margin_limit = s_float(latest.get("MarginPurchaseLimit"))
        short_balance = s_float(latest.get("ShortSaleTodayBalance"))
        short_limit = s_float(latest.get("ShortSaleLimit"))
        margin_buy = s_float(latest.get("MarginPurchaseBuy"))
        margin_sell = s_float(latest.get("MarginPurchaseSell"))
        margin_repay = s_float(latest.get("MarginPurchaseCashRepayment"))
        short_sell = s_float(latest.get("ShortSaleSell"))
        short_buy = s_float(latest.get("ShortSaleBuy"))
        offset_loan_short = s_float(latest.get("OffsetLoanAndShort"))

        if margin_yesterday is not None and margin_balance is not None:
            margin_change_1d = margin_balance - margin_yesterday
        else:
            margin_change_1d, _ = _margin_period_change(data.tail(2), "MarginPurchaseTodayBalance", 1)

        margin_change_5d, margin_change_5d_pct = _margin_period_change(data, "MarginPurchaseTodayBalance", 5)
        margin_change_20d, margin_change_20d_pct = _margin_period_change(data, "MarginPurchaseTodayBalance", 20)

        shares_lots = None
        shares = s_float(shares_outstanding)
        if shares is not None and shares > 0:
            shares_lots = shares / 1000.0

        margin_usage_ratio = _safe_ratio(margin_balance, margin_limit)
        margin_to_shares_ratio = _safe_ratio(margin_balance, shares_lots)
        short_margin_ratio = _safe_ratio(short_balance, margin_balance)
        short_usage_ratio = _safe_ratio(short_balance, short_limit)

        risk_score = 0
        if margin_usage_ratio is not None:
            if margin_usage_ratio >= 0.80:
                risk_score += 3
            elif margin_usage_ratio >= 0.60:
                risk_score += 2
            elif margin_usage_ratio >= 0.40:
                risk_score += 1
        if margin_to_shares_ratio is not None:
            if margin_to_shares_ratio >= 0.10:
                risk_score += 3
            elif margin_to_shares_ratio >= 0.05:
                risk_score += 2
            elif margin_to_shares_ratio >= 0.03:
                risk_score += 1
        if margin_change_5d_pct is not None:
            if margin_change_5d_pct >= 0.30:
                risk_score += 2
            elif margin_change_5d_pct >= 0.15:
                risk_score += 1
            elif margin_change_5d_pct <= -0.15:
                risk_score -= 1
        if margin_change_20d_pct is not None:
            if margin_change_20d_pct >= 0.50:
                risk_score += 1
            elif margin_change_20d_pct <= -0.25:
                risk_score -= 1

        if margin_balance is None:
            risk_label, risk_color, risk_note = "資料不足", "gray", "融資餘額缺值，無法判讀信用風險。"
        elif risk_score >= 5:
            risk_label, risk_color, risk_note = "過熱", "#ff4d4d", "融資水位或增速偏高，籌碼槓桿壓力大，追價需保守。"
        elif risk_score >= 3:
            risk_label, risk_color, risk_note = "偏熱", "#ff8c00", "融資籌碼已有升溫跡象，需搭配法人與成交量確認。"
        elif risk_score >= 1:
            risk_label, risk_color, risk_note = "正常", "#FFD700", "融資水位尚在可觀察區間，仍需追蹤是否連續增加。"
        else:
            risk_label, risk_color, risk_note = "低", "#00cc66", "融資籌碼壓力低或正在降溫，短線槓桿風險相對較小。"

        def fmt_lots(value):
            value = s_float(value)
            return "NULL" if value is None else f"{value:,.0f} 張"

        def fmt_pct(value):
            value = s_float(value)
            return "NULL" if value is None else f"{value:.2%}"

        report = pd.DataFrame([
            {"項目": "最新日期", "數值": str(latest.get("date", ""))[:10], "判讀": "FinMind 個股融資融券資料"},
            {"項目": "融資餘額", "數值": fmt_lots(margin_balance), "判讀": f"較昨日 {fmt_lots(margin_change_1d)}"},
            {"項目": "融資使用率", "數值": fmt_pct(margin_usage_ratio), "判讀": "融資今日餘額 / 融資限額"},
            {"項目": "融資占股本", "數值": fmt_pct(margin_to_shares_ratio), "判讀": "融資今日餘額 / 發行股數張數"},
            {"項目": "5日融資變化", "數值": fmt_lots(margin_change_5d), "判讀": fmt_pct(margin_change_5d_pct)},
            {"項目": "20日融資變化", "數值": fmt_lots(margin_change_20d), "判讀": fmt_pct(margin_change_20d_pct)},
            {"項目": "融券餘額", "數值": fmt_lots(short_balance), "判讀": f"券資比 {fmt_pct(short_margin_ratio)}"},
            {"項目": "信用風險", "數值": risk_label, "判讀": risk_note},
        ])

        return {
            "available": True,
            "source": "FinMind TaiwanStockMarginPurchaseShortSale",
            "latest_date": str(latest.get("date", ""))[:10],
            "margin_balance": margin_balance,
            "margin_yesterday_balance": margin_yesterday,
            "margin_change_1d": margin_change_1d,
            "margin_change_5d": margin_change_5d,
            "margin_change_5d_pct": margin_change_5d_pct,
            "margin_change_20d": margin_change_20d,
            "margin_change_20d_pct": margin_change_20d_pct,
            "margin_limit": margin_limit,
            "margin_usage_ratio": margin_usage_ratio,
            "margin_to_shares_ratio": margin_to_shares_ratio,
            "margin_buy": margin_buy,
            "margin_sell": margin_sell,
            "margin_repay": margin_repay,
            "short_balance": short_balance,
            "short_limit": short_limit,
            "short_margin_ratio": short_margin_ratio,
            "short_usage_ratio": short_usage_ratio,
            "short_sell": short_sell,
            "short_buy": short_buy,
            "offset_loan_short": offset_loan_short,
            "shares_lots": shares_lots,
            "risk_score": risk_score,
            "risk_label": risk_label,
            "risk_color": risk_color,
            "risk_note": risk_note,
            "report": report,
        }
    except Exception as e:
        log_exception("FinMind", "build_margin_credit_summary", e)
        return {"available": False, "message": f"融資融券資料整理失敗：{str(e)[:80]}"}


@st.cache_data(ttl=43200)
def get_margin_credit_data(stock_id, fm_key=""):
    """Fetch individual margin purchase / short sale balance from FinMind."""
    try:
        today = datetime.date.today()
        start_str = (today - datetime.timedelta(days=180)).strftime("%Y-%m-%d")
        url = (
            "https://api.finmindtrade.com/api/v4/data"
            f"?dataset=TaiwanStockMarginPurchaseShortSale&data_id={stock_id}&start_date={start_str}"
        )
        if fm_key:
            url += f"&token={fm_key}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        log_data_health("FinMind", res.status_code == 200, res.status_code)
        if res.status_code == 200:
            data = res.json()
            if data.get("status") == 200 and data.get("data"):
                df = pd.DataFrame(data["data"])
                if df.empty:
                    return pd.DataFrame()
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"], errors="coerce")
                    df = df.sort_values("date")
                return df
    except Exception as e:
        log_exception("FinMind", f"get_margin_credit_data:{stock_id}", e)
        log_data_health("FinMind", False, f"ERR:{str(e)[:120]}")
    return pd.DataFrame()


@st.cache_data(ttl=60)
def validate_api_keys(f_key, m_key):
    f_res, m_res = None, None
    if f_key:
        clean_f = re.sub(r'\s+', '', f_key)
        try:
            r1 = requests.get("https://api.fugle.tw/marketdata/v1.0/stock/historical/candles/2330?timeframe=D", headers={"X-API-KEY": clean_f}, timeout=15)
            f_res = (r1.status_code == 200)
        except Exception as e:
            log_exception("Fugle", "validate_api_keys:fugle", e)
            f_res = False
    if m_key:
        clean_m = re.sub(r'\s+', '', m_key)
        try:
            r2 = requests.get(f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id=2330&start_date=2024-01-01&end_date=2024-01-02&token={clean_m}", timeout=15)
            m_res = (r2.status_code == 200 and r2.json().get('status') == 200)
        except Exception as e:
            log_exception("FinMind", "validate_api_keys:finmind", e)
            m_res = False
    return f_res, m_res

@st.cache_data(ttl=86400) 
def get_chinese_name(stock_id):
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        match = re.search(r'<title>(.*?)(?:\(| \()', res.text)
        if match: return match.group(1).strip()
    except Exception as e:
        log_exception("Yahoo", f"get_chinese_name:{stock_id}", e)
    return None

@st.cache_data(ttl=86400)
def translate_to_zh(text):
    if not text or text == '暫無簡介。': return text
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": "en", "tl": "zh-TW", "dt": "t", "q": text}
        res = requests.get(url, params=params, timeout=5)
        return "".join([item[0] for item in res.json()[0]])
    except Exception as e:
        log_exception("GoogleTranslate", "translate_to_zh", e)
        return text + "\n\n(⚠️ 翻譯服務暫時忙碌中)"

# ==========================================
# 3.3 ETF 持股快取 v9 覆寫：避免外部站連線失敗時慢掃；新增 Yahoo ETF 持股頁反查
# ==========================================
ETF_CACHE_VERSION = "v9.0-fast-fail-yahoo-etf-holding-fallback"

# 預設只快速掃描台股/主動式與常見科技 ETF，避免 53 檔 x 3 來源造成 Streamlit 卡住。
ETF_PRIORITY_CODES = [
    "00981A", "00987A", "00988A", "00403A", "00400A",
    "00980A", "00982A", "00984A", "00985A", "00986A", "00989A",
    "0050", "0052", "006208", "00952", "00922", "00923", "00904", "00881",
]


def _request_html_quick(url, timeout=(1.2, 3.0)):
    """短逾時抓取，避免 Streamlit Cloud 對 MoneyDJ/Pocket/CMoney 連線失敗時卡很久。"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "close",
    }
    res = requests.get(url, headers=headers, timeout=timeout)
    res.raise_for_status()
    if not res.encoding or str(res.encoding).lower() == "iso-8859-1":
        res.encoding = res.apparent_encoding or "utf-8"
    return res.text


def _parse_yahoo_etf_holding_html(html, etf_code, etf_name=""):
    """解析 Yahoo ETF 的 holding 頁：/quote/00981A.TW/holding。"""
    url = f"https://tw.stock.yahoo.com/quote/{str(etf_code).upper()}.TW/holding"
    data_date = _extract_data_date_from_text(html)
    rows = []

    # 先沿用 v8 的表格/文字解析。
    try:
        rows.extend(_parse_holdings_tables_from_html(html, etf_code, etf_name, "Yahoo ETF持股頁", url))
    except Exception:
        pass

    try:
        rows.extend(_parse_holdings_text_regex_fallback(html, etf_code, etf_name, "Yahoo ETF持股頁", url, data_date=data_date))
    except Exception:
        pass

    # Yahoo 常把資料塞在 JSON/Next data，補抓常見 key 組合。
    text = str(html or "")
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"&quot;|&#34;", '"', text)
    text = re.sub(r"&amp;", "&", text)
    text_plain = re.sub(r"<[^>]+>", " ", text)
    text_plain = re.sub(r"\s+", " ", text_plain)

    # JSON 區塊：symbol/name/weight 可能順序不同，所以用附近 block 判讀。
    for m in re.finditer(r'(?<!\d)(\d{4})(?:\.TW)?(?!\d)', text_plain):
        stock_code = m.group(1)
        block = text_plain[max(0, m.start()-220): min(len(text_plain), m.end()+260)]
        # 抓附近中文名
        nm = ""
        before = block[:block.find(stock_code)] if stock_code in block else block
        after = block[block.find(stock_code)+len(stock_code):] if stock_code in block else block
        name_candidates = re.findall(r"[\u4e00-\u9fffA-Za-z0-9\-＋+＊*·]{2,24}", before[-80:] + " " + after[:80])
        for cand in name_candidates:
            if cand not in ["持股比例", "持有股數", "資料日期", "Yahoo", "Finance"] and not re.fullmatch(r"\d+", cand):
                nm = cand
                break
        # 抓附近百分比
        wm = re.search(r"(-?\d{1,3}(?:\.\d{1,4})?)\s*%", block)
        weight = _clean_percent_to_float(wm.group(1)) if wm else None
        if stock_code and (nm or weight is not None):
            rows.append({
                "etf_code": str(etf_code).upper(),
                "etf_name": etf_name,
                "stock_code": stock_code,
                "stock_name": nm,
                "weight": weight,
                "shares": None,
                "data_date": data_date,
                "source": "Yahoo ETF持股頁",
                "source_url": url,
                "data_type": "系統抓取",
                "fetched_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "parse_method": "yahoo_nearby_regex",
            })

    return _dedup_holding_rows(rows)


def fetch_yahoo_etf_holdings(etf_code, etf_name=""):
    url = f"https://tw.stock.yahoo.com/quote/{str(etf_code).upper()}.TW/holding"
    html = _request_html_quick(url)
    return _parse_yahoo_etf_holding_html(html, etf_code, etf_name)


def _probe_source_health():
    """先探測來源是否可連線；不可連線就整批跳過，避免每檔 ETF 都 timeout。"""
    tests = {
        "MoneyDJ": "https://www.moneydj.com/etf/x/basic/basic0007.xdjhtm?etfid=0050.tw",
        "Pocket": "https://www.pocket.tw/etf/tw/0050/fundholding/",
        "CMoney": "https://www.cmoney.tw/etf/tw/0050/fundholding",
        "Yahoo ETF持股頁": "https://tw.stock.yahoo.com/quote/0050.TW/holding",
    }
    health = {}
    for name, url in tests.items():
        try:
            html = _request_html_quick(url, timeout=(1.0, 2.2))
            health[name] = bool(html and len(html) > 500)
        except Exception as e:
            health[name] = False
    return health


def _get_priority_master_items(master):
    """把主動式與常用台股科技 ETF 放前面，且預設只掃這批，避免更新太慢。"""
    by_code = {str(x.get("etf_code", "")).upper(): x for x in master if x.get("etf_code")}
    items = []
    for code in ETF_PRIORITY_CODES:
        if code in by_code:
            items.append(by_code[code])
        else:
            seed_name = next((n for c, n in ETF_SEED_LIST if c.upper() == code), "")
            items.append({"etf_code": code, "etf_name": seed_name, "source": "priority_seed"})
    # 去重
    seen, out = set(), []
    for x in items:
        c = str(x.get("etf_code", "")).upper()
        if c and c not in seen:
            seen.add(c)
            out.append(x)
    return out


def update_etf_holdings_cache(force=False, max_etfs=None, scan_all=False):
    """
    v9：快速更新 ETF → 成分股快取。
    - 先探測來源，MoneyDJ/Pocket/CMoney 無法連線就整批跳過，不再 53 檔逐一 timeout。
    - 預設只掃重點/主動式 ETF，避免 Streamlit Cloud 按鈕卡 1 分鐘以上。
    - 新增 Yahoo ETF 持股頁作為可連線的 ETF→成分股來源，用來補 00981A 這類 Yahoo 個股頁漏列問題。
    """
    cached = _read_json_file(ETF_HOLDINGS_CACHE_FILE, {})
    if (not force) and cached.get("updated_date") == _today_str() and cached.get("holdings"):
        return cached

    master_all = discover_etf_master_list(force=force)
    if scan_all:
        master = master_all
    else:
        master = _get_priority_master_items(master_all)
    if max_etfs:
        master = master[:int(max_etfs)]

    source_health = _probe_source_health()
    holdings = []
    errors = []

    for item in master:
        code = str(item.get("etf_code", "")).upper()
        name = item.get("etf_name", "")
        if not code:
            continue
        rows = []

        if source_health.get("MoneyDJ"):
            try:
                rows = fetch_moneydj_etf_holdings(code, name)
            except Exception as e:
                errors.append({"etf_code": code, "source": "MoneyDJ", "error": str(e)[:180]})
        else:
            errors.append({"etf_code": code, "source": "MoneyDJ", "error": "來源探測失敗，已跳過整批 MoneyDJ，避免逐檔 timeout"})

        if not rows and source_health.get("Yahoo ETF持股頁"):
            try:
                rows = fetch_yahoo_etf_holdings(code, name)
            except Exception as e:
                errors.append({"etf_code": code, "source": "Yahoo ETF持股頁", "error": str(e)[:180]})

        if not rows and source_health.get("Pocket"):
            try:
                rows = fetch_pocket_etf_holdings(code, name)
            except Exception as e:
                errors.append({"etf_code": code, "source": "Pocket", "error": str(e)[:180]})
        elif not source_health.get("Pocket"):
            errors.append({"etf_code": code, "source": "Pocket", "error": "來源探測失敗，已跳過整批 Pocket"})

        if not rows and source_health.get("CMoney"):
            try:
                rows = fetch_cmoney_etf_holdings(code, name)
            except Exception as e:
                errors.append({"etf_code": code, "source": "CMoney", "error": str(e)[:180]})
        elif not source_health.get("CMoney"):
            errors.append({"etf_code": code, "source": "CMoney", "error": "來源探測失敗，已跳過整批 CMoney"})

        holdings.extend(rows)
        time.sleep(0.05)

    cache = {
        "version": ETF_CACHE_VERSION,
        "updated_date": _today_str(),
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "master_count": len(master),
        "master_total_count": len(master_all),
        "scan_mode": "all" if scan_all else "priority_fast",
        "source_health": source_health,
        "holdings_count": len(holdings),
        "holdings": _dedup_holding_rows(holdings),
        "errors_sample": errors[:80],
        "note": "v9 預設快速掃描重點/主動式 ETF；MoneyDJ/Pocket/CMoney 若探測失敗會整批跳過，避免按鈕卡住。",
    }
    cache["holdings_count"] = len(cache["holdings"])
    _write_json_file(ETF_HOLDINGS_CACHE_FILE, cache)
    return cache


def load_etf_holdings_cache(auto_update=True):
    cache = _read_json_file(ETF_HOLDINGS_CACHE_FILE, {})
    # v9：自動更新只在快取不存在時做快速更新；若今天已建立但 0 筆，不在每次頁面載入重跑，避免變慢。
    if auto_update and (not cache or cache.get("updated_date") != _today_str()):
        cache = update_etf_holdings_cache(force=False)
    return cache


def get_etf_cache_status():
    cache = _read_json_file(ETF_HOLDINGS_CACHE_FILE, {})
    master = _read_json_file(ETF_MASTER_CACHE_FILE, {})
    return {
        "cache_version": cache.get("version", "尚未建立"),
        "updated_date": cache.get("updated_date", "尚未更新"),
        "updated_at": cache.get("updated_at", "尚未更新"),
        "is_today": cache.get("updated_date") == _today_str(),
        "master_count": cache.get("master_count", master.get("count", 0)),
        "master_total_count": cache.get("master_total_count", master.get("count", 0)),
        "scan_mode": cache.get("scan_mode", "尚未建立"),
        "source_health": cache.get("source_health", {}),
        "holdings_count": cache.get("holdings_count", len(cache.get("holdings", [])) if isinstance(cache.get("holdings"), list) else 0),
        "errors_count": len(cache.get("errors_sample", [])) if isinstance(cache.get("errors_sample"), list) else 0,
    }


def _scan_priority_etfs_for_stock(stock_id, stock_name=""):
    """快取沒有命中時，快速直接檢查重點 ETF 的 Yahoo ETF 持股頁，避免 00981A 漏掉。"""
    stock_id = str(stock_id).strip()
    target_name_key = _normalize_tw_name(stock_name or "")
    if not target_name_key:
        try:
            target_name_key = _normalize_tw_name(get_chinese_name(stock_id) or "")
        except Exception:
            target_name_key = ""

    master = discover_etf_master_list(force=False)
    candidates = _get_priority_master_items(master)
    out = []
    for item in candidates:
        code = str(item.get("etf_code", "")).upper()
        name = item.get("etf_name", "")
        try:
            rows = fetch_yahoo_etf_holdings(code, name)
        except Exception:
            continue
        for r in rows:
            row_code = str(r.get("stock_code", "")).strip()
            row_name_key = _normalize_tw_name(r.get("stock_name", ""))
            if row_code == stock_id or (target_name_key and row_name_key and target_name_key == row_name_key):
                out.append({
                    "etf_code": _normalize_etf_code(r.get("etf_code")),
                    "etf_name": r.get("etf_name", name),
                    "weight": r.get("weight"),
                    "shares": r.get("shares"),
                    "data_date": r.get("data_date") or "來源未揭露",
                    "source": r.get("source") or "Yahoo ETF持股頁",
                    "source_url": r.get("source_url", ""),
                    "data_type": "ETF持股頁快速反查",
                    "note": "快取未命中時，直接檢查重點 ETF 的持股頁；不是 Yahoo 個股頁結果",
                })
    return _normalize_etf_holders(out, default_source="ETF持股頁快速反查")




# ==========================================
# 3.4 ETF 持股查詢 v10：一般頁面只顯示 Yahoo 主要/前十大；完整 ETF 另用 AI 按鈕查
# ==========================================
ETF_SYSTEM_NOTE_V10 = "Yahoo 個股 ETF 頁多為主要/前十大或公開頁面可解析清單，不代表完整 ETF 持股名單。"

@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_etf_holders(stock_id, stock_name=None, force_refresh=False):
    """
    v10：一般個股頁只做快速查詢，不再更新/掃描 ETF 成分股快取。
    - 不使用 AI。
    - 不掃 MoneyDJ / Pocket / CMoney，避免 Streamlit Cloud 卡住。
    - 主要使用 Yahoo 個股 ETF 頁，必要時 FindBillion 補漏。
    - 回傳的 data_type 固定標示為「主要/前十大快速查詢」。
    """
    stock_id = str(stock_id).strip()
    if not stock_id:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    }
    sources = [
        ("Yahoo股市", f"https://tw.stock.yahoo.com/quote/{stock_id}.TW/etf"),
        ("FindBillion", f"https://www.findbillion.com/twstock/{stock_id}/etf"),
    ]
    best_rows = []
    for source_name, url in sources:
        try:
            res = requests.get(url, headers=headers, timeout=(1.5, 4.0))
            if res.status_code != 200:
                continue
            rows = _extract_etf_holders_from_text(res.text, source_name)
            for rr in rows:
                rr["data_date"] = rr.get("data_date") or "來源未揭露"
                rr["data_type"] = "主要/前十大快速查詢"
                rr["note"] = ETF_SYSTEM_NOTE_V10
            if rows and (not best_rows or len(rows) > len(best_rows)):
                best_rows = rows
        except Exception:
            continue
    return _normalize_etf_holders(best_rows, default_source="主要/前十大快速查詢")[:20]


def get_etf_holders_from_ai(stock_id, stock_name, api_key, model_name="gemini-3.1-pro-preview"):
    """
    獨立 AI ETF 持股查詢：只在使用者按下「AI 查完整 ETF 持有狀況」時執行。
    不併入 get_financials_from_ai()，避免財報校對工作量過大。
    """
    if not api_key:
        return {"error": "未提供 API Key"}
    try:
        client = genai.Client(api_key=api_key.strip())
    except Exception as e:
        return {"error": f"GenAI Client 初始化失敗：{str(e)}"}

    system_prompt = """你是一位台股 ETF 持股查詢助理。請查詢指定台股被哪些 ETF 持有。
重點規則：
1. 不要只依賴 Yahoo 個股 ETF 頁，因為該頁可能只列主要或前十大 ETF。
2. 優先查投信官網/PCF/投資組合明細，其次 MoneyDJ、Pocket、CMoney、WantGoo、Yahoo ETF 持股頁。
3. 請特別檢查主動式 ETF：00981A、00987A、00988A、00400A、00403A、00980A、00982A、00984A、00985A、00986A、00989A、00990A。
4. 請回傳 JSON，不要輸出 markdown 或解釋文字。
5. weight 請用百分比數字，例如 9.68% 寫成 9.68；若查無比例請填 null。
6. data_date 請填資料日期；若來源未揭露請填 null。
格式：
{"etf_holders_ai":[{"etf_code":"00981A","etf_name":"主動統一台股增長","weight":9.68,"data_date":"2026/05/13","source":"MoneyDJ","note":"資料來源說明"}],"summary":"簡短說明資料完整性與限制"}
"""
    prompt_text = f"請查詢台股 {stock_name} ({stock_id}) 被哪些 ETF 持有，尤其確認主動式 ETF 是否持有。請回傳 ETF 代號、名稱、持股比例、資料日期、資料來源。"
    attempts = []
    try:
        response = client.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=prompt_text,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=[_google_search_tool()],
                response_mime_type="application/json",
            ),
        )
        text = response.text or ""
        attempts.append({"model": "gemini-3.1-pro-preview", "ok": True})
    except Exception as e:
        return {"error": f"AI ETF 持股查詢失敗：{str(e)}", "attempts": attempts}

    s_idx = text.find('{')
    e_idx = text.rfind('}')
    if s_idx == -1 or e_idx == -1:
        return {"error": "AI 回傳格式無法解析 JSON", "raw_text_preview": text[:500], "attempts": attempts}
    try:
        parsed = json.loads(text[s_idx:e_idx+1])
    except Exception as e:
        return {"error": f"AI ETF JSON 解析失敗：{str(e)}", "raw_text_preview": text[:500], "attempts": attempts}

    rows = _normalize_etf_holders(parsed.get("etf_holders_ai") or [], default_source="AI補查ETF")
    for row in rows:
        row["data_type"] = "AI完整ETF補查"
        row["note"] = row.get("note") or "AI 聯網補查，請以投信公告、PCF 或 ETF 官方持股明細為準。"
        if not row.get("data_date"):
            row["data_date"] = "來源未揭露"
    return {
        "etf_holders_ai": rows,
        "summary": parsed.get("summary", "AI 已完成 ETF 持股補查。"),
        "model_used": "Gemini 3.1 Pro Preview (付費版)",
        "ai_search_enabled": True,
        "query_payload": json.dumps({"stock": f"{stock_name} ({stock_id})", "prompt": prompt_text, "task": "獨立 AI ETF 持股查詢"}, ensure_ascii=False, indent=2),
        "attempts": attempts,
    }
