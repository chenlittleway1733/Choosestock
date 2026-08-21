"""
共用常數、格式化工具、自選股與 Streamlit Session State 管理。
由原始 app(1).py 拆分而來。
"""
import os
import re
import math
import hashlib
import datetime
import json
import pandas as pd
import streamlit as st

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



def log_exception(source, context, exc=None):
    """
    集中記錄非致命例外：避免 except: pass 吃掉錯誤。
    - source：資料源或模組名稱，例如 Yahoo / Fugle / FinMind / Gemini / Utils
    - context：發生錯誤的函式或流程
    - exc：例外物件
    """
    src = str(source or "Unknown").strip()
    ctx = str(context or "unknown_context").strip()
    msg = str(exc)[:200] if exc is not None else "unknown error"
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    event = {"time": now_str, "source": src, "context": ctx, "error": msg}

    try:
        if "error_events" not in st.session_state:
            st.session_state.error_events = []
        st.session_state.error_events.append(event)
        st.session_state.error_events = st.session_state.error_events[-30:]
    except Exception:
        return event
    return event


def format_fy_year_label(year_value):
    """Display FY year labels consistently as 2026E / 年期未明."""
    try:
        if year_value is None:
            return "年期未明"
        text = str(year_value).strip()
        if text in ["", "None", "nan", "未標示"]:
            return "年期未明"
        return f"{text}E" if re.match(r"^\d{4}$", text) else text
    except Exception:
        return "年期未明"


def taipei_today():
    """Return Taiwan-market current date independent of server timezone."""
    tz = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz).date()


def build_forward_eps_calendar_notice(current_date=None, fy1_year=None, fy2_year=None, fy3_year=None):
    """Build FY year/month guidance without changing FY1/FY2/FY3 calculations."""
    try:
        if current_date is None:
            day = taipei_today()
        elif isinstance(current_date, datetime.datetime):
            day = current_date.date()
        elif isinstance(current_date, datetime.date):
            day = current_date
        else:
            day = datetime.datetime.strptime(str(current_date)[:10], "%Y-%m-%d").date()
    except Exception:
        day = taipei_today()

    month = int(day.month)
    fy_sequence_text = (
        f"FY1={format_fy_year_label(fy1_year)} / "
        f"FY2={format_fy_year_label(fy2_year)} / "
        f"FY3={format_fy_year_label(fy3_year)}"
    )

    if month >= 10:
        phase = "q4_fy2_primary_reference"
        ui_notice = "目前已進入 10 月後，FY1 接近落地，市場通常改以 FY2 作主要前瞻參考；FY1 仍需用來驗證本年度獲利是否達標。"
        prompt_notice = "10-12 月：FY1 接近落地，請以 FY2 作主要前瞻參考，但不得自動用 FY2 支撐買進；仍需檢查 FY2 法人共識、訂單/營收/毛利率證據與 FY1 落地狀況。"
    elif month >= 7:
        phase = "h2_fy2_reference"
        ui_notice = "目前已進入 7 月後，估值判讀應同步參考 FY2；FY1 計算方式不變，仍是年度主估值與落地檢查基準。"
        prompt_notice = "7-9 月：FY1 計算方式不變，但請同步參考 FY2 判斷市場是否提前定價；FY2 仍不可直接視為買點。"
    else:
        phase = "h1_fy1_primary"
        ui_notice = ""
        prompt_notice = "1-6 月：FY1 通常仍是主要年度估值參考；FY2/FY3 僅作遠期情境與市場先行定價檢查。"

    return {
        "date": day.isoformat(),
        "month": month,
        "phase": phase,
        "fy_sequence_text": fy_sequence_text,
        "ui_notice": ui_notice,
        "prompt_notice": f"目前台北時間月份={month}月；{fy_sequence_text}；{prompt_notice} FY1/FY2/FY3 EPS 計算方式不變。",
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
    except (TypeError, ValueError, OverflowError):
        return default

def to_pct(val):
    try:
        if val is None or pd.isna(val): return "N/A"
        return f"{val * 100:.2f}%"
    except (TypeError, ValueError, OverflowError):
        return "N/A"

def to_val_str(v, fmt="pct"):
    if v is None or pd.isna(v): return "N/A"
    if fmt == "pct": return f"{v * 100:.2f}%"
    if fmt == "x": return f"{v:.1f}x"
    return f"{v:.2f}"

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

def build_cmp_str(orig, ai_val, fmt="pct", suffix="AI推估", show_ai_missing=False, period=""):
    s = to_val_str(orig, fmt)
    if ai_val is not None and not pd.isna(ai_val):
        ai_text = to_val_str(float(ai_val), fmt)
    elif show_ai_missing:
        ai_text = "AI找不到數據"
    else:
        return s
    
    time_str = f", {period}" if period else ""
    s += f"<br><span style='color:#FFD700; font-size:0.85rem;'>({suffix}: {ai_text}{time_str})</span>"
    return s

def build_cmp_dual_str(o1, o2, a1, a2, fmt1="num", fmt2="num", suffix="AI推估", show_ai_missing=False, period=""):
    s1 = to_val_str(o1, fmt1)
    s2 = to_val_str(o2, fmt2)
    s = f"{s1} / <span style='color:#00bfff;'>{s2}</span>" if (fmt1=="num" and fmt2=="num") else f"{s1} / {s2}"
    has_ai = ((a1 is not None and not pd.isna(a1)) or (a2 is not None and not pd.isna(a2)))
    if not has_ai and not show_ai_missing:
        return s
    sa1 = to_val_str(float(a1) if a1 is not None and not pd.isna(a1) else None, fmt1)
    sa2 = to_val_str(float(a2) if a2 is not None and not pd.isna(a2) else None, fmt2)
    if sa1 == "N/A":
        sa1 = "AI找不到數據"
    if sa2 == "N/A":
        sa2 = "AI找不到數據"
        
    time_str = f", {period}" if period else ""
    s += f"<br><span style='color:#FFD700; font-size:0.85rem;'>({suffix}: {sa1} / {sa2}{time_str})</span>"
    return s

def clean_html(html_str):
    return re.sub(r'[\r\n\t]+', ' ', html_str).strip()



def format_quality_value(val, fmt="num"):
    """資料品質表專用格式化：避免 UI 端重複處理百分比/倍數/金額。"""
    if val is None:
        return "NULL"
    try:
        if pd.isna(val):
            return "NULL"
    except Exception:
        pass
    try:
        v = float(val)
        if fmt == "pct":
            return f"{v * 100:.2f}%"
        if fmt == "x":
            return f"{v:.2f}x"
        if fmt == "price":
            return f"{v:,.2f}"
        if fmt == "int":
            return f"{v:,.0f}"
        return f"{v:,.2f}"
    except Exception:
        text = str(val).strip()
        return text if text else "NULL"


def get_ai_field_source_meta(ai_fin, field_key):
    """取得 AI 單一財務欄位的來源資訊。相容 _ai_source_trace、_sources、field_sources。"""
    if not isinstance(ai_fin, dict) or not field_key:
        return {}
    trace = ai_fin.get("_ai_source_trace") or ai_fin.get("_sources") or ai_fin.get("field_sources") or {}
    if not isinstance(trace, dict):
        return {}
    meta = trace.get(field_key) or {}
    if isinstance(meta, str):
        return {"source": meta}
    return meta if isinstance(meta, dict) else {}

def format_ai_source_detail(ai_fin, field_key, fallback_period="", fallback_source="AI補齊"):
    """將 AI 來源名稱與日期壓成適合放進資料品質表的文字。"""
    meta = get_ai_field_source_meta(ai_fin, field_key)
    source = str(meta.get("source") or meta.get("publisher") or fallback_source or "AI補齊").strip()
    data_period = ai_fin.get("data_period", "") if isinstance(ai_fin, dict) else ""
    date = str(meta.get("published_date") or meta.get("date") or meta.get("data_date") or meta.get("period") or fallback_period or data_period or "").strip()
    note = str(meta.get("note") or "").strip()
    parts = [source]
    if date:
        parts.append(date)
    if note:
        parts.append(note[:40])
    return "｜".join([x for x in parts if x])

def get_ai_source_url(ai_fin, field_key):
    """取得 AI 單一欄位來源網址；若單欄未提供，回傳空字串。"""
    meta = get_ai_field_source_meta(ai_fin, field_key)
    return str(meta.get("source_url") or meta.get("url") or meta.get("link") or "").strip()

def build_ai_source_trace_report(ai_fin):
    """把 AI 回傳的逐欄來源整理成 DataFrame，供 UI 檢視。"""
    if not isinstance(ai_fin, dict):
        return pd.DataFrame()
    trace = ai_fin.get("_ai_source_trace") or ai_fin.get("_sources") or ai_fin.get("field_sources") or {}
    if not isinstance(trace, dict) or not trace:
        return pd.DataFrame()
    rows = []
    for key, meta in trace.items():
        if isinstance(meta, str):
            meta = {"source": meta}
        if not isinstance(meta, dict):
            continue
        rows.append({
            "欄位代碼": key,
            "欄位名稱": meta.get("label") or key,
            "AI值": format_quality_value(ai_fin.get(key), "num"),
            "來源": meta.get("source") or meta.get("publisher") or "—",
            "發布日/期間": meta.get("published_date") or meta.get("date") or meta.get("data_date") or meta.get("period") or ai_fin.get("data_period") or "—",
            "來源網址": meta.get("source_url") or meta.get("url") or meta.get("link") or "—",
            "備註": meta.get("note") or "—",
        })
    return pd.DataFrame(rows)


REVIEW_STATUS_LABELS = {
    "pending": "待審核",
    "accepted": "已採用AI候選值",
    "rejected": "已拒絕AI候選值",
    "kept_original": "保留系統原值",
    "needs_followup": "需追查",
    "ignored": "已忽略",
}

FINANCIAL_CANDIDATE_FIELD_LABELS = {
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
    "forward_eps_fy1": "FY1 Forward EPS",
    "forward_eps_fy2": "FY2 Forward EPS",
    "forward_eps_fy3": "FY3 Forward EPS",
    "forward_eps_fy1_year": "FY1 EPS 年份",
    "forward_eps_fy2_year": "FY2 EPS 年份",
    "forward_eps_fy3_year": "FY3 EPS 年份",
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
    "debt_to_equity": "負債權益比 D/E",
    "mom": "最新單月營收 MoM",
    "dividend_yield": "預估現金殖利率",
    "free_cash_flow": "自由現金流",
    "current_ratio": "流動比率",
    "shares_outstanding": "總發行股數/股本",
}

FINANCIAL_CANDIDATE_FIELD_UNITS = {
    "current_price": "NTD/share",
    "pe": "x",
    "pb": "x",
    "forward_pe": "x",
    "latest_month_eps": "NTD/share",
    "latest_quarter_eps": "NTD/share",
    "previous_quarter_eps": "NTD/share",
    "last_two_quarter_eps": "NTD/share",
    "trailing_eps": "NTD/share",
    "ttm_eps": "NTD/share",
    "fiscal_year_eps": "NTD/share",
    "forward_eps": "NTD/share",
    "forward_eps_system": "NTD/share",
    "forward_eps_ai": "NTD/share",
    "forward_eps_consensus": "NTD/share",
    "forward_eps_fy1": "NTD/share",
    "forward_eps_fy2": "NTD/share",
    "forward_eps_fy3": "NTD/share",
    "target_price": "NTD/share",
    "target_price_high": "NTD/share",
    "target_price_avg": "NTD/share",
    "target_price_low": "NTD/share",
    "target_price_analyst_count": "count",
    "gross_margin": "ratio_decimal",
    "operating_margin": "ratio_decimal",
    "roe": "ratio_decimal",
    "yoy": "ratio_decimal",
    "mom": "ratio_decimal",
    "dividend_yield": "ratio_decimal",
    "debt_to_equity": "x",
    "free_cash_flow": "NTD",
    "current_ratio": "x",
    "shares_outstanding": "shares",
}

FINANCIAL_CANDIDATE_PERIOD_TYPES = {
    "latest_month_eps": "single_month",
    "latest_quarter_eps": "single_quarter",
    "previous_quarter_eps": "single_quarter",
    "last_two_quarter_eps": "two_quarter_sum",
    "ttm_eps": "ttm",
    "trailing_eps": "ttm",
    "fiscal_year_eps": "annual",
    "forward_eps": "forward_year",
    "forward_eps_ai": "forward_year",
    "forward_eps_consensus": "forward_year",
    "forward_eps_fy1": "forward_year",
    "forward_eps_fy2": "forward_year",
    "forward_eps_fy3": "forward_year",
    "forward_eps_fy1_year": "forward_year_label",
    "forward_eps_fy2_year": "forward_year_label",
    "forward_eps_fy3_year": "forward_year_label",
    "yoy": "monthly_or_growth",
    "mom": "monthly_or_growth",
}


def normalize_candidate_review_status(status):
    """標準化候選資料審核狀態，避免 UI / cache 使用不同字串。"""
    text = str(status or "pending").strip().lower()
    aliases = {
        "待審核": "pending",
        "採用": "accepted",
        "接受": "accepted",
        "accepted_ai": "accepted",
        "拒絕": "rejected",
        "保留原值": "kept_original",
        "keep_original": "kept_original",
        "需追查": "needs_followup",
        "followup": "needs_followup",
        "忽略": "ignored",
    }
    text = aliases.get(text, text)
    return text if text in REVIEW_STATUS_LABELS else "pending"


def infer_financial_source_tier(meta=None, source_name=""):
    """依來源名稱推估資料源信任層級；AI 未明確標示時使用保守分層。"""
    meta = meta if isinstance(meta, dict) else {}
    raw_tier = meta.get("source_tier") or meta.get("tier")
    try:
        tier = int(raw_tier)
        if 1 <= tier <= 5:
            return tier
    except Exception:
        pass

    text = " ".join([
        str(source_name or ""),
        str(meta.get("source") or ""),
        str(meta.get("publisher") or ""),
        str(meta.get("note") or ""),
    ]).lower()

    if any(k.lower() in text for k in ["mops", "twse", "tpex", "公開資訊觀測站", "公司公告", "公司財報", "年報", "季報", "法說", "ir"]):
        return 1
    if any(k.lower() in text for k in ["finmind", "fugle", "tej", "證券商 api", "付費資料庫"]):
        return 2
    if any(k.lower() in text for k in ["yahoo", "yfinance", "google finance", "goodinfo", "moneydj", "cmoney", "鉅亨"]):
        return 3
    if any(k.lower() in text for k in ["ai推估", "ai依", "推估", "推論", "inferred"]):
        return 5
    return 4


def _candidate_confidence(meta, source_tier, value):
    meta = meta if isinstance(meta, dict) else {}
    conf = str(meta.get("confidence") or "").strip().lower()
    if conf in {"high", "medium", "low"}:
        return conf
    if value in (None, "", "null"):
        return "low"
    if source_tier <= 2:
        return "high"
    if source_tier <= 4:
        return "medium"
    return "low"


def _candidate_conflict_status(value, original_value=None, meta=None):
    meta = meta if isinstance(meta, dict) else {}
    explicit = str(meta.get("conflict_status") or "").strip()
    if explicit:
        return explicit
    if original_value is None:
        return "not_compared"
    if value in (None, "", "null"):
        return "candidate_missing"
    cand_num = s_float(value)
    orig_num = s_float(original_value)
    if cand_num is not None and orig_num is not None:
        if abs(cand_num - orig_num) <= max(0.0001, abs(orig_num) * 0.005):
            return "same_as_system"
        return "different_from_system"
    return "same_as_system" if str(value).strip() == str(original_value).strip() else "different_from_system"


def _candidate_difference(value, original_value=None):
    cand_num = s_float(value)
    orig_num = s_float(original_value)
    if cand_num is None or orig_num is None:
        return None, None
    diff_abs = cand_num - orig_num
    diff_pct = None if abs(orig_num) < 1e-12 else diff_abs / abs(orig_num)
    return diff_abs, diff_pct


def _candidate_display_fmt(unit):
    if unit == "ratio_decimal":
        return "pct"
    if unit == "NTD/share":
        return "price"
    if unit in {"count", "shares"}:
        return "int"
    if unit == "x":
        return "x"
    return "num"


def build_financial_candidate_data(
    ai_fin,
    *,
    system_values=None,
    stock_id="",
    stock_name="",
    retrieved_at=None,
    default_review_status="pending",
    include_null=False,
):
    """把 AI 財報回傳值轉成 candidate_data，供後續 pending_review / audit log 使用。"""
    if not isinstance(ai_fin, dict):
        return []
    system_values = system_values if isinstance(system_values, dict) else {}
    retrieved_at = str(retrieved_at or ai_fin.get("retrieved_at") or datetime.datetime.now().isoformat(timespec="seconds"))
    status = normalize_candidate_review_status(default_review_status)
    trace = ai_fin.get("_ai_source_trace") or ai_fin.get("_sources") or ai_fin.get("field_sources") or {}
    if not isinstance(trace, dict):
        trace = {}

    rows = []
    for field_name, default_label in FINANCIAL_CANDIDATE_FIELD_LABELS.items():
        value = ai_fin.get(field_name)
        if not include_null and value in (None, "", "null"):
            continue
        meta = trace.get(field_name) or {}
        if isinstance(meta, str):
            meta = {"source": meta}
        if not isinstance(meta, dict):
            meta = {}

        source_name = str(meta.get("source") or meta.get("publisher") or ("AI聯網搜尋" if value not in (None, "", "null") else "")).strip()
        source_date = str(meta.get("published_date") or meta.get("source_date") or meta.get("date") or meta.get("data_date") or "").strip()
        period = str(meta.get("period") or meta.get("data_period") or source_date or ai_fin.get("data_period") or "").strip()
        unit = str(meta.get("unit") or FINANCIAL_CANDIDATE_FIELD_UNITS.get(field_name, "number")).strip()
        source_tier = infer_financial_source_tier(meta, source_name)
        original_value = system_values.get(field_name)
        diff_abs, diff_pct = _candidate_difference(value, original_value)
        conflict_status = _candidate_conflict_status(value, original_value, meta)
        seed = f"{stock_id}|{field_name}|{period}|{source_name}|{source_date}|{value}"
        digest = hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:12]

        rows.append({
            "candidate_id": f"fin:{stock_id or 'UNKNOWN'}:{field_name}:{digest}",
            "stock_id": str(stock_id or ai_fin.get("_stock_id") or ""),
            "company_name": str(stock_name or ai_fin.get("_stock_name") or ""),
            "field_name": field_name,
            "field_label": str(meta.get("label") or default_label),
            "value": s_float(value) if s_float(value) is not None else value,
            "unit": unit,
            "period": period or "unknown",
            "period_type": str(meta.get("period_type") or FINANCIAL_CANDIDATE_PERIOD_TYPES.get(field_name, "unknown")),
            "source_tier": source_tier,
            "source_name": source_name or "AI聯網搜尋",
            "source_url_or_ref": str(meta.get("source_url") or meta.get("url") or meta.get("link") or "").strip(),
            "source_date": source_date or period or "unknown",
            "retrieved_at": retrieved_at,
            "confidence": _candidate_confidence(meta, source_tier, value),
            "conflict_status": conflict_status,
            "review_status": normalize_candidate_review_status(meta.get("review_status") or status),
            "original_value": original_value,
            "original_source": system_values.get(f"{field_name}_source") or "",
            "difference_abs": diff_abs,
            "difference_pct": diff_pct,
            "notes": str(meta.get("note") or meta.get("notes") or "").strip(),
        })
    return rows


def build_candidate_data_report(candidate_data):
    """將 candidate_data 轉為 UI 可讀表格；不改變審核狀態。"""
    rows = []
    for item in candidate_data or []:
        if not isinstance(item, dict):
            continue
        unit = item.get("unit", "number")
        fmt = _candidate_display_fmt(unit)
        diff_pct = s_float(item.get("difference_pct"))
        diff_abs = s_float(item.get("difference_abs"))
        if diff_abs is None:
            diff_text = "—"
        elif diff_pct is None:
            diff_text = f"{diff_abs:,.4f}"
        else:
            diff_text = f"{diff_abs:,.4f} / {diff_pct * 100:.2f}%"
        status = normalize_candidate_review_status(item.get("review_status"))
        rows.append({
            "候選ID": item.get("candidate_id", ""),
            "股票": f"{item.get('stock_id', '')} {item.get('company_name', '')}".strip(),
            "欄位": item.get("field_label") or item.get("field_name", ""),
            "候選值": format_quality_value(item.get("value"), fmt),
            "原系統值": format_quality_value(item.get("original_value"), fmt),
            "差異": diff_text,
            "資料期間": item.get("period", "unknown"),
            "期間類型": item.get("period_type", "unknown"),
            "來源層級": f"Level {item.get('source_tier', '—')}",
            "來源": item.get("source_name", "—"),
            "來源日期": item.get("source_date", "—"),
            "信心": item.get("confidence", "medium"),
            "衝突狀態": item.get("conflict_status", "not_compared"),
            "審核狀態": REVIEW_STATUS_LABELS.get(status, status),
            "備註": item.get("notes") or "—",
        })
    return pd.DataFrame(rows)


def financial_candidate_review_cache_path(cache_path=None):
    """候選資料審核狀態 JSON cache 路徑。"""
    if cache_path:
        return os.fspath(cache_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".way_cache", "financial_candidate_reviews.json")


def _normalize_candidate_review_cache(raw):
    if isinstance(raw, dict) and isinstance(raw.get("reviews"), dict):
        return {
            "version": raw.get("version") or "financial_candidate_review_v1",
            "updated_at": raw.get("updated_at") or "",
            "reviews": raw.get("reviews") or {},
        }
    if isinstance(raw, dict):
        return {"version": "financial_candidate_review_v1", "updated_at": "", "reviews": raw}
    return {"version": "financial_candidate_review_v1", "updated_at": "", "reviews": {}}


def load_financial_candidate_review_cache(cache_path=None):
    """載入候選資料審核狀態；檔案不存在時回傳空 cache。"""
    path = financial_candidate_review_cache_path(cache_path)
    if not os.path.exists(path):
        return {"version": "financial_candidate_review_v1", "updated_at": "", "reviews": {}}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return _normalize_candidate_review_cache(json.loads(fh.read() or "{}"))
    except Exception as exc:
        log_exception("CandidateReviewCache", "load_financial_candidate_review_cache", exc)
        return {"version": "financial_candidate_review_v1", "updated_at": "", "reviews": {}}


def save_financial_candidate_review_cache(review_cache, cache_path=None):
    """保存候選資料審核狀態 JSON cache。"""
    path = financial_candidate_review_cache_path(cache_path)
    cache = _normalize_candidate_review_cache(review_cache)
    cache["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=2)
    return cache


def financial_candidate_review_key(stock_id, candidate_id):
    return f"{str(stock_id or '').strip()}::{str(candidate_id or '').strip()}"


def update_financial_candidate_review(
    *,
    stock_id,
    candidate_id,
    review_status,
    decision_note="",
    candidate_snapshot=None,
    cache_path=None,
):
    """更新單筆候選資料審核狀態，並寫入 JSON cache。"""
    status = normalize_candidate_review_status(review_status)
    cache = load_financial_candidate_review_cache(cache_path)
    reviews = cache.setdefault("reviews", {})
    snapshot = dict(candidate_snapshot or {})
    field_name = snapshot.get("field_name", "")
    record = {
        "stock_id": str(stock_id or snapshot.get("stock_id") or ""),
        "candidate_id": str(candidate_id or snapshot.get("candidate_id") or ""),
        "field_name": field_name,
        "field_label": snapshot.get("field_label") or field_name,
        "review_status": status,
        "decision_note": str(decision_note or ""),
        "candidate_value": snapshot.get("value"),
        "original_value": snapshot.get("original_value"),
        "source_tier": snapshot.get("source_tier"),
        "source_name": snapshot.get("source_name"),
        "source_date": snapshot.get("source_date"),
        "decided_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    reviews[financial_candidate_review_key(record["stock_id"], record["candidate_id"])] = record
    cache = save_financial_candidate_review_cache(cache, cache_path)
    return record


def apply_financial_candidate_reviews(candidate_data, review_cache=None, *, stock_id=""):
    """把已保存的 review_status 套回 candidate_data，供 UI 與後續正式採用流程使用。"""
    cache = _normalize_candidate_review_cache(review_cache or {})
    reviews = cache.get("reviews", {})
    rows = []
    for item in candidate_data or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        sid = str(stock_id or row.get("stock_id") or "")
        cid = str(row.get("candidate_id") or "")
        record = reviews.get(financial_candidate_review_key(sid, cid))
        if isinstance(record, dict):
            row["review_status"] = normalize_candidate_review_status(record.get("review_status"))
            row["decision_note"] = record.get("decision_note", "")
            row["decided_at"] = record.get("decided_at", "")
        else:
            row["review_status"] = normalize_candidate_review_status(row.get("review_status"))
        rows.append(row)
    return rows


FIELD_SOURCE_PRIORITY_TABLE = [
    {
        "field": "現價",
        "code": "current_price",
        "aliases": ["current_price", "price", "股價", "收盤價", "最新收盤價"],
        "priority": ["Fugle API 即時/延遲行情", "Yahoo Finance/yfinance", "Yahoo Finance CSV fallback", "FinMind 股價備援"],
        "adoption_rule": "以可連線且時間最新的系統行情為準；AI 不得覆蓋現價。",
        "validation_rule": "若股價為 0、負值或缺值，估值相關欄位不得產生買進燈號。",
    },
    {
        "field": "P/E",
        "code": "pe",
        "aliases": ["pe", "trailing_pe", "歷史本益比", "本益比"],
        "priority": ["Yahoo Finance/yfinance trailing PE", "FinMind TaiwanStockPER PER 備援", "AI 聯網查證", "現價 / TTM EPS 反推"],
        "adoption_rule": "系統 PE 優先；系統缺值或明顯異常時才採 FinMind 或 AI 查證，反推值需標示。",
        "validation_rule": "PE <= 0 或 EPS <= 0 時不可作一般 P/E 估值，應改看 P/B、現金流或週期指標。",
    },
    {
        "field": "Forward P/E",
        "code": "forward_pe",
        "aliases": ["forward_pe", "forwardpe", "前瞻本益比"],
        "priority": ["yfinance forwardPE", "系統 Forward EPS 反推", "法人 FY1 EPS 反推", "AI 聯網查證"],
        "adoption_rule": "優先用系統 forwardPE；缺值才用 Forward EPS 反推，並需標示 EPS 年期。",
        "validation_rule": "若 Forward EPS 疑似 FY2 年期錯位，公式估值需降權採 FY1 EPS。",
    },
    {
        "field": "PEG",
        "code": "peg",
        "aliases": ["peg", "目標peg"],
        "priority": ["Forward P/E / 法人 FY1 成長率", "Forward P/E / 月營收 YoY 備援", "AI CAGR 查證"],
        "adoption_rule": "PEG 是衍生值，不直接採單一網站值；需先確認 Forward P/E 與成長率口徑。",
        "validation_rule": "成長率為負時 PEG 無意義，需標示 NULL 或觀望。",
    },
    {
        "field": "P/B",
        "code": "pb",
        "aliases": ["pb", "pbr", "股價淨值比"],
        "priority": ["Yahoo Finance/yfinance P/B", "FinMind TaiwanStockPER PBR 備援", "AI 聯網查證"],
        "adoption_rule": "系統 P/B 優先；P/E 不適用、EPS 為負或週期股時，P/B 權重提高。",
        "validation_rule": "P/B 與 ROE、產業週期需一起看；不可單靠低 P/B 判斷便宜。",
    },
    {
        "field": "最新單月 EPS",
        "code": "latest_month_eps",
        "aliases": ["latest_month_eps", "單月eps", "自結eps", "月eps", "最新單月eps"],
        "priority": ["公司自結公告 / 公開資訊觀測站重大訊息", "交易所注意股自結公告", "AI 聯網查證最新單月 EPS"],
        "adoption_rule": "若取得最新單月 EPS，目前估值優先採單月 EPS x12；缺值才退回最新單季 EPS x4 或 TTM EPS。",
        "validation_rule": "需標示月份，例如 2026/04；年化估值需清楚寫成單月 EPS x12，不能與單季 EPS 混用。",
    },
    {
        "field": "最新單季 EPS",
        "code": "latest_quarter_eps",
        "aliases": ["latest_quarter_eps", "單季eps", "最新eps", "目前eps"],
        "priority": ["公開資訊觀測站 / 最新財報", "AI 聯網查證最新季度 EPS", "系統欄位若能明確提供單季 EPS"],
        "adoption_rule": "不得用 TTM EPS 冒充單季 EPS；缺值時目前估值改用 TTM EPS 備援。",
        "validation_rule": "需標示季度，例如 2026Q1；年化估值需清楚寫成單季 EPS x4。",
    },
    {
        "field": "近二季 EPS",
        "code": "last_two_quarter_eps",
        "aliases": ["last_two_quarter_eps", "previous_quarter_eps", "近二季eps", "前一季eps"],
        "priority": ["公開資訊觀測站 / 最新兩季財報", "AI 聯網查證最新兩季 EPS", "FinMind 財報季度 EPS"],
        "adoption_rule": "只用於 Run-rate EPS 動能估值，不取代 TTM EPS、FY1 或 FY2 年度估值。",
        "validation_rule": "必須標示是近二季合計或前一季 EPS；近二季年化=近二季 EPS 合計 x2。",
    },
    {
        "field": "TTM EPS",
        "code": "ttm_eps",
        "aliases": ["ttm_eps", "trailing_eps", "近四季eps", "ttmeps"],
        "priority": ["近四季財報 EPS 合計", "可信 TTM EPS", "yfinance trailingEps 備援", "現價 / P/E 反推", "AI 聯網查證"],
        "adoption_rule": "近四季 EPS 合計優先；yfinance trailingEps 僅作備援與交叉檢查，不可覆蓋較新的四季合計值。",
        "validation_rule": "若 yfinance trailingEps 與近四季合計差距 >10%，標示 yfinance EPS 可能過舊；反推值需標示為反推。",
    },
    {
        "field": "完整年度 EPS",
        "code": "fiscal_year_eps",
        "aliases": ["fiscal_year_eps", "年度eps", "完整年度eps"],
        "priority": ["公開資訊觀測站 / 年報", "公司財報 / 法說資料", "AI 聯網查證"],
        "adoption_rule": "年度 EPS 只作年度基準，不得覆蓋 TTM EPS 或 Forward EPS。",
        "validation_rule": "需標示會計年度；若年期不明，降為資料待確認。",
    },
    {
        "field": "Forward EPS－系統",
        "code": "forward_eps_system",
        "aliases": ["forward_eps_system", "系統forwardeps", "forwardeps系統"],
        "priority": ["yfinance forwardEps", "TTM EPS x 預估成長率推估"],
        "adoption_rule": "只代表系統估值原始口徑；不得用 AI/FY1 冒充系統 Forward EPS。",
        "validation_rule": "需與 FY1/FY2 EPS 交叉檢查，疑似 FY2 時公式估值降權。",
    },
    {
        "field": "Forward EPS－AI/共識",
        "code": "forward_eps_consensus",
        "aliases": ["forward_eps_consensus", "forward_eps_ai", "法人共識eps", "ai forward eps", "forward eps ai"],
        "priority": ["多家法人共識 EPS", "券商目標價/研究報告引用 EPS", "公司法說會指引", "AI 依成長率推估"],
        "adoption_rule": "共識 EPS 優先；單一券商或 AI 推估需降權，並與系統 Forward EPS 分開比較。",
        "validation_rule": "必須標示來源日期、FY 年度與是否為共識；年期不明不得直接進公式買點。",
    },
    {
        "field": "Forward EPS－FY1",
        "code": "forward_eps_fy1",
        "aliases": ["forward_eps_fy1", "fy1 eps", "fy1eps", "forward eps fy1"],
        "priority": ["法人 FY1 年度共識 EPS", "多家券商最新 FY1 EPS", "單一券商 FY1 EPS", "AI 推估 FY1 EPS"],
        "adoption_rule": "FY1 是前瞻 PEG 年度估值與手動情境預設基準；缺值不可用 FY2/FY3 自動代替。",
        "validation_rule": "必須標示 FY1 對應年度；若來源非共識，資料分級至少為待確認。",
    },
    {
        "field": "Forward EPS－FY2",
        "code": "forward_eps_fy2",
        "aliases": ["forward_eps_fy2", "fy2 eps", "fy2eps", "forward eps fy2"],
        "priority": ["法人 FY2 年度共識 EPS", "多家券商最新 FY2 EPS", "單一券商 FY2 EPS", "AI 推估 FY2 EPS"],
        "adoption_rule": "FY2 只作市場先行定價與樂觀年度情境，不直接當買點。",
        "validation_rule": "若現價只能靠 FY2 解釋，需明確標示估值先行與風險。",
    },
    {
        "field": "Forward EPS－FY3",
        "code": "forward_eps_fy3",
        "aliases": ["forward_eps_fy3", "fy3 eps", "fy3eps", "forward eps fy3"],
        "priority": ["法人 FY3 年度共識 EPS", "長期法人情境", "公司長期指引", "AI 推估 FY3 EPS"],
        "adoption_rule": "FY3 是高風險遠期情境，只能作壓力測試或題材先行情境。",
        "validation_rule": "不得用 FY3 支撐一般買進燈號；需列為極限或高風險情境。",
    },
    {
        "field": "營收 YoY",
        "code": "revenue_yoy",
        "aliases": ["revenue_yoy", "rev_growth", "yoy", "營收年增", "月營收yoy"],
        "priority": ["公開資訊觀測站 / MOPS 月營收", "FinMind TaiwanStockMonthRevenue 單月 YoY", "Yahoo 股市月營收單月 YoY", "AI 查證公告月份"],
        "adoption_rule": "以實際公告月份的單月 YoY 為準；yfinance revenueGrowth 只作診斷備註，不進月營收 YoY 採用值。",
        "validation_rule": "若 AI 抓到累計 YoY、季度 YoY、不同月份或 yfinance revenueGrowth，需列口徑差異並降權。",
    },
    {
        "field": "營收 MoM",
        "code": "revenue_mom",
        "aliases": ["mom", "revenue_mom", "營收月增", "月營收mom"],
        "priority": ["公開資訊觀測站 / MOPS 月營收", "FinMind TaiwanStockMonthRevenue 單月 MoM", "Yahoo 股市月營收單月 MoM", "AI 查證公告月份"],
        "adoption_rule": "以實際公告月份單月 MoM 為準；缺值才採 AI 查證。",
        "validation_rule": "不可用查詢當月推定最新公告月份。",
    },
    {
        "field": "毛利率",
        "code": "gross_margin",
        "aliases": ["gross_margin", "毛利率", "gm"],
        "priority": ["yfinance grossMargins", "FinMind 財報健康度", "公開資訊觀測站 / 最新財報", "AI 聯網查證"],
        "adoption_rule": "系統值優先；AI 只在缺值或校驗時補齊，需標示季度/年度口徑。",
        "validation_rule": "需標準化成小數；毛利率不合理或低於營益率時列資料異常。",
    },
    {
        "field": "營益率",
        "code": "operating_margin",
        "aliases": ["operating_margin", "營益率", "op_margin", "om"],
        "priority": ["yfinance operatingMargins", "FinMind 財報健康度", "公開資訊觀測站 / 最新財報", "AI 聯網查證"],
        "adoption_rule": "系統值優先；AI 只在缺值或校驗時補齊，需標示季度/年度口徑。",
        "validation_rule": "營益率高於毛利率超過容忍值時，視為硬性資料矛盾。",
    },
    {
        "field": "ROE",
        "code": "roe",
        "aliases": ["roe", "股東權益報酬率"],
        "priority": ["yfinance returnOnEquity", "P/B ÷ P/E 恆等式校正", "公開資訊觀測站 / 最新財報", "AI 聯網查證"],
        "adoption_rule": "系統值優先；P/B/P/E 可作交叉校正，不可在 PE 或 PB 異常時強行反推。",
        "validation_rule": "需標準化成小數；極端值需確認是否百分比/倍數口徑錯置。",
    },
    {
        "field": "D/E",
        "code": "debt_to_equity",
        "aliases": ["debt_to_equity", "de", "d/e", "負債權益比"],
        "priority": ["yfinance debtToEquity", "FinMind 財報健康度", "公開資訊觀測站 / 最新財報", "AI 聯網查證"],
        "adoption_rule": "採用前一律標準化成倍數；例如 132.1% 轉為 1.321 倍。",
        "validation_rule": "D/E > 8 倍視為單位疑似錯置或極端財務風險，需停用買賣判斷。",
    },
    {
        "field": "法人目標價",
        "code": "target_price",
        "aliases": ["target_price", "target_price_avg", "目標價", "法人目標價"],
        "priority": ["多家法人目標價彙整", "券商最新目標價與報告日期", "yfinance targetMeanPrice/High/Low", "AI 聯網查證"],
        "adoption_rule": "法人目標價面板同源值優先；需同步高/均/低與分析師人數。",
        "validation_rule": "分析師人數少於 3 或高低標分歧過大時，目標價可信度降權。",
    },
    {
        "field": "自由現金流",
        "code": "free_cash_flow",
        "aliases": ["free_cash_flow", "fcf", "自由現金流"],
        "priority": ["yfinance freeCashflow", "FinMind 現金流量表", "公開資訊觀測站 / 最新財報", "AI 聯網查證"],
        "adoption_rule": "系統值優先；AI 只補缺值，並需標示期間。",
        "validation_rule": "FCF 為負需與成長投資、庫存與營運現金流一起解讀。",
    },
    {
        "field": "流動比率",
        "code": "current_ratio",
        "aliases": ["current_ratio", "流動比率"],
        "priority": ["yfinance currentRatio", "公開資訊觀測站 / 最新財報", "AI 聯網查證"],
        "adoption_rule": "系統值優先；AI 只補缺值。",
        "validation_rule": "流動比率低於 1 需列短期流動性風險。",
    },
    {
        "field": "融資融券",
        "code": "margin_credit",
        "aliases": ["margin_credit", "融資", "融券", "信用交易"],
        "priority": ["FinMind TaiwanStockMarginPurchaseShortSale", "TWSE/TPEx 信用交易官方資料", "AI 查證"],
        "adoption_rule": "以最近交易日官方/FinMind 信用交易資料為準，AI 不覆蓋系統值。",
        "validation_rule": "融資使用率或融資餘額變化偏高時，只作籌碼風險，不直接改 EPS/估值。",
    },
    {
        "field": "ETF 持有",
        "code": "etf_holders",
        "aliases": ["etf_holders", "etf持有", "etf曝險"],
        "priority": ["投信官網/PCF/投資組合明細", "MoneyDJ / Yahoo ETF 持股頁", "Pocket / CMoney", "AI 補查"],
        "adoption_rule": "系統掃描與投信官方資料優先；AI 只補主動式 ETF 或缺漏來源。",
        "validation_rule": "需標示資料日期；來源未揭露時不可視為完整持股證據。",
    },
    {
        "field": "產業分類",
        "code": "industry_classification",
        "aliases": ["industry_classification", "primary_taxon", "產業分類", "stock_mapping"],
        "priority": ["stock_mapping.py 正式對應", "industry_taxonomy.py 模型分類", "stocklist/keyword fallback", "AI 建議分類"],
        "adoption_rule": "正式 stock_mapping.py 優先；AI 建議分類一律待人工確認，不直接覆蓋模型庫。",
        "validation_rule": "分類調整需有產品、營收結構或獲利來源轉變證據。",
    },
]


def _normalize_source_priority_key(value):
    text = str(value or "").strip().lower()
    text = text.replace("－", "-").replace("—", "-")
    text = re.sub(r"[\s_/\-()（）]+", "", text)
    return text


def get_field_source_priority(field):
    """依資料欄位名稱取得來源優先規則。"""
    needle = _normalize_source_priority_key(field)
    if not needle:
        return None
    for item in FIELD_SOURCE_PRIORITY_TABLE:
        candidates = [item.get("field"), item.get("code")] + list(item.get("aliases") or [])
        if needle in {_normalize_source_priority_key(x) for x in candidates}:
            return item
    for item in FIELD_SOURCE_PRIORITY_TABLE:
        candidates = [item.get("field"), item.get("code")] + list(item.get("aliases") or [])
        for candidate in candidates:
            key = _normalize_source_priority_key(candidate)
            if key and (key in needle or needle in key):
                return item
    return None


def source_priority_summary_for_field(field, include_rule=True):
    """回傳單一欄位的來源優先序摘要，供資料品質表與提示詞使用。"""
    item = get_field_source_priority(field)
    if not item:
        return ""
    priority_text = " > ".join([f"{idx + 1}.{name}" for idx, name in enumerate(item.get("priority") or [])])
    if include_rule:
        rule = item.get("adoption_rule") or ""
        if rule:
            return f"{priority_text}；規則：{rule}"
    return priority_text


def build_field_source_priority_report(fields=None):
    """建立欄位來源優先表。fields 可指定顯示欄位；不指定則回傳完整表。"""
    selected = []
    if fields:
        seen = set()
        for field in fields:
            item = get_field_source_priority(field)
            if item and item.get("code") not in seen:
                selected.append(item)
                seen.add(item.get("code"))
    else:
        selected = FIELD_SOURCE_PRIORITY_TABLE

    rows = []
    for item in selected:
        rows.append({
            "資料欄位": item.get("field", ""),
            "欄位代碼": item.get("code", ""),
            "來源優先序": " > ".join([f"{idx + 1}.{name}" for idx, name in enumerate(item.get("priority") or [])]),
            "採用規則": item.get("adoption_rule", ""),
            "校驗/降權規則": item.get("validation_rule", ""),
        })
    return pd.DataFrame(rows)


def format_field_source_priority_for_prompt(fields=None, max_rows=18):
    """將欄位來源優先表壓成適合打包給外部 AI 的文字。"""
    df = build_field_source_priority_report(fields)
    if df is None or df.empty:
        return "NULL"
    rows = []
    for _, row in df.head(max_rows).iterrows():
        rows.append(
            "- "
            f"欄位={row.get('資料欄位', '')}；"
            f"優先序={row.get('來源優先序', '')}；"
            f"採用規則={row.get('採用規則', '')}；"
            f"校驗={row.get('校驗/降權規則', '')}"
        )
    return "\n".join(rows) if rows else "NULL"



# ==========================================
# 1.0.1 系統 / AI 分歧警告層
# ==========================================
def _relative_gap(a, b, denominator="min"):
    """計算兩個數值的相對差距。預設以較小絕對值作為分母，符合「分歧警告」需求。"""
    a = s_float(a)
    b = s_float(b)
    if a is None or b is None:
        return None
    base_candidates = [abs(x) for x in [a, b] if x is not None and abs(x) > 1e-12]
    if not base_candidates:
        return None
    if denominator == "avg":
        base = sum(base_candidates) / len(base_candidates)
    elif denominator == "max":
        base = max(base_candidates)
    else:
        base = min(base_candidates)
    if base <= 1e-12:
        return None
    return abs(a - b) / base


def _fmt_gap_pct(gap):
    return "N/A" if gap is None else f"{gap * 100:.1f}%"


def build_ttm_eps_adoption(
    *,
    system_ttm_eps=None,
    ai_ttm_eps=None,
    current_price=None,
    pe_ratio=None,
    system_source="yfinance trailingEps",
    ai_source="近四季財報 EPS 合計",
    ai_has_trace=False,
    system_is_inferred=False,
    stale_gap_threshold=0.10,
):
    """決定 TTM EPS 採用值。

    原則：
    1. 明確的近四季 EPS 合計優先。
    2. yfinance trailingEps 只作備援與交叉檢查。
    3. 現價 / P/E 反推值只作最後備援，必須標示。
    """
    sys_eps = s_float(system_ttm_eps)
    ai_eps = s_float(ai_ttm_eps)
    inferred_eps = None
    if sys_eps is None and current_price is not None and pe_ratio is not None:
        price = s_float(current_price)
        pe = s_float(pe_ratio)
        if price is not None and price > 0 and pe is not None and pe > 0:
            inferred_eps = price / pe
            sys_eps = inferred_eps
            system_is_inferred = True
            system_source = "現價 / P/E 反推"

    ai_trusted = ai_eps is not None and ai_eps > 0 and bool(ai_has_trace)
    sys_valid = sys_eps is not None and sys_eps > 0
    notes = []
    warnings = []
    adopted = None
    adopted_source = "無可用資料"
    adopted_rule = "缺少 TTM EPS，無法建立歷史 P/E。"

    if ai_trusted:
        adopted = ai_eps
        adopted_source = ai_source
        adopted_rule = "近四季 EPS 合計優先採用。"
    elif sys_valid:
        adopted = sys_eps
        adopted_source = system_source
        adopted_rule = "未取得可信近四季 EPS 合計，採系統備援值。"
    elif ai_eps is not None and ai_eps > 0:
        adopted = ai_eps
        adopted_source = ai_source
        adopted_rule = "AI 提供 TTM EPS 但來源/期間不足，暫作備援採用。"
        warnings.append("AI TTM EPS 缺少來源或期間，需人工確認。")

    if system_is_inferred and sys_valid:
        notes.append("系統 TTM EPS 為現價 / P/E 反推，只能作備援。")
    elif sys_valid:
        notes.append("系統 TTM EPS 來自 yfinance trailingEps，僅作備援與交叉檢查。")

    if ai_trusted:
        notes.append("AI/外部校對 TTM EPS 標示為近四季 EPS 合計，優先於 yfinance trailingEps。")

    gap = _relative_gap(sys_eps, ai_eps, "max")
    if gap is not None and gap > stale_gap_threshold:
        warnings.append(f"yfinance trailingEps 與近四季 TTM EPS 差距 {_fmt_gap_pct(gap)}，yfinance EPS 可能過舊。")

    return {
        "adopted_value": adopted,
        "adopted_source": adopted_source,
        "adopted_rule": adopted_rule,
        "system_ttm_eps": sys_eps,
        "ai_ttm_eps": ai_eps,
        "system_source": system_source,
        "ai_source": ai_source,
        "system_is_inferred": bool(system_is_inferred),
        "ai_has_trace": bool(ai_has_trace),
        "gap": gap,
        "warnings": warnings,
        "notes": notes,
    }


def detect_forward_eps_period_mismatch(system_forward_eps=None, fy1_eps=None, fy2_eps=None, threshold=0.30):
    """Detect when system Forward EPS likely reflects FY2 instead of FY1."""
    sys_eps = s_float(system_forward_eps)
    fy1 = s_float(fy1_eps)
    fy2 = s_float(fy2_eps)
    result = {
        "has_mismatch": False,
        "severity": "none",
        "system_forward_eps": sys_eps,
        "fy1_eps": fy1,
        "fy2_eps": fy2,
        "fy1_gap": None,
        "fy2_gap": None,
        "recommended_eps": sys_eps,
        "recommended_eps_source": "系統 Forward EPS",
        "note": "未偵測到 Forward EPS 年期錯位。",
    }
    if sys_eps is None or sys_eps <= 0 or fy1 is None or fy1 <= 0 or fy2 is None or fy2 <= 0:
        result["note"] = "Forward EPS / FY1 / FY2 EPS 資料不足，無法檢查年期錯位。"
        return result

    fy1_gap = abs(sys_eps - fy1) / fy1
    fy2_gap = abs(sys_eps - fy2) / fy2
    result["fy1_gap"] = fy1_gap
    result["fy2_gap"] = fy2_gap

    if fy1_gap > threshold and fy2_gap < fy1_gap:
        result.update({
            "has_mismatch": True,
            "severity": "warning",
            "recommended_eps": fy1,
            "recommended_eps_source": "FY1 EPS（系統 Forward EPS 疑似 FY2，已降權）",
            "note": (
                f"系統 Forward EPS={sys_eps:.2f} 與 FY1 EPS={fy1:.2f} 差距 {_fmt_gap_pct(fy1_gap)}，"
                f"且更接近 FY2 EPS={fy2:.2f}；公式合理估值應降權採 FY1 EPS，FY2 僅用於市場先行定價判斷。"
            ),
        })
    return result


def build_divergence_warnings(
    *,
    system_forward_eps=None,
    ai_forward_eps=None,
    system_yoy=None,
    ai_yoy=None,
    system_peg=None,
    ai_peg=None,
    system_forward_pe=None,
    ai_forward_pe=None,
    system_growth_yoy=None,
    ai_growth_yoy=None,
    system_fair_value=None,
    ai_fair_value=None,
    system_de=None,
    ai_de=None,
    system_pb=None,
    ai_pb=None,
    stock_id="",
    stock_name="",
):
    """
    建立「系統值 vs AI值」分歧警告。

    目的：
    - EPS / YoY / PEG / 合理價 / D/E 發生重大矛盾時，不讓使用者只看到單一結論。
    - 此函式只產生警告，不直接修改估值模型，避免和前面的資料校驗層互相干擾。
    """
    label = f"{stock_name} ({stock_id})" if stock_name and stock_id else (stock_name or stock_id or "目前標的")
    warnings = []

    def add(rule, message, severity="warning", system_value=None, ai_value=None, gap=None, suggestion=""):
        warnings.append({
            "規則": rule,
            "嚴重度": severity,
            "警告文字": message,
            "系統值": system_value,
            "AI值": ai_value,
            "差距": gap,
            "建議處理": suggestion or "請先確認資料口徑，再使用估值結論。",
        })

    # 1) Forward EPS 分歧：abs(system-ai)/min(abs(system),abs(ai)) > 30%
    eps_gap = _relative_gap(system_forward_eps, ai_forward_eps, "min")
    if eps_gap is not None and eps_gap > 0.30:
        add(
            "EPS 分歧",
            f"{label} 的 Forward EPS 預估分歧過大，估值可信度下降。",
            "danger" if eps_gap > 0.50 else "warning",
            format_quality_value(system_forward_eps, "num"),
            format_quality_value(ai_forward_eps, "num"),
            _fmt_gap_pct(eps_gap),
            "請優先確認 Forward EPS 是單一券商、AI 推估，還是多家法人共識；可操作估值應採較保守 EPS。",
        )

    # 2) YoY 分歧：單月 YoY 是核心動能欄位，差距超過 5 個百分點且相對差距 >20% 就警示。
    sy = s_float(system_yoy)
    ay = s_float(ai_yoy)
    if sy is not None and ay is not None:
        yoy_gap_pp = abs(sy - ay) * 100
        yoy_rel_gap = _relative_gap(sy, ay, "min")
        if yoy_gap_pp >= 5 and (yoy_rel_gap is None or yoy_rel_gap > 0.20):
            yoy_severity = "danger" if yoy_gap_pp >= 10 else "warning"
            add(
                "YoY 分歧",
                f"{label} 的營收年增率口徑可能混淆，請確認單月 YoY / 累計 YoY / yfinance revenueGrowth。",
                yoy_severity,
                format_quality_value(sy, "pct"),
                format_quality_value(ay, "pct"),
                f"{yoy_gap_pp:.1f} 個百分點",
                "YoY 差距達 10 個百分點以上時禁止輸出可買；月營收判斷應優先採公告月份的單月 YoY，AI 若抓到累計 YoY 不能直接比較。",
            )

    # 3) PEG 矛盾：系統 PEG < 1 且 AI PEG > 3，或反向發生
    sp = s_float(system_peg)
    ap = s_float(ai_peg)
    if sp is not None and ap is not None and sp > 0 and ap > 0:
        if (sp < 1 and ap > 3) or (ap < 1 and sp > 3):
            add(
                "PEG 矛盾",
                f"{label} 的 PEG 結論矛盾，請勿直接判定低估或高估。",
                "danger",
                format_quality_value(sp, "x"),
                format_quality_value(ap, "x"),
                _fmt_gap_pct(_relative_gap(sp, ap, "min")),
                "請回頭檢查 Forward P/E 與成長率分母，特別是低基期 EPS 或 AI 成長率口徑。",
            )

    # 3.1) Forward P/E 分歧：估值核心倍數，差距 >20% 即降權。
    sfpe = s_float(system_forward_pe)
    afpe = s_float(ai_forward_pe)
    fpe_gap = _relative_gap(sfpe, afpe, "min")
    if fpe_gap is not None and fpe_gap > 0.20:
        add(
            "Forward P/E 分歧",
            f"{label} 的 Forward P/E 系統值與 AI 反推值差距過大，估值口徑需降權。",
            "warning",
            format_quality_value(sfpe, "x"),
            format_quality_value(afpe, "x"),
            _fmt_gap_pct(fpe_gap),
            "請確認 Forward EPS 採用系統 forwardEps、法人 FY1 共識，或單一券商預估；不可混用。",
        )

    # 3.2) PEG 分歧：即使不是 <1 vs >3 的極端矛盾，差距 >50% 也要列警告。
    peg_gap = _relative_gap(sp, ap, "min")
    if peg_gap is not None and peg_gap > 0.50 and not ((sp < 1 and ap > 3) or (ap < 1 and sp > 3)):
        add(
            "PEG 分歧",
            f"{label} 的 PEG 系統值與 AI 推估值差距過大，成長率或 Forward P/E 口徑需確認。",
            "warning",
            format_quality_value(sp, "x"),
            format_quality_value(ap, "x"),
            _fmt_gap_pct(peg_gap),
            "PEG 對成長率分母非常敏感；請確認預估獲利成長 YoY 是否為同一年度、同一口徑。",
        )

    # 3.3) 預估獲利成長 YoY 分歧：會直接影響 PEG 與系統 Forward EPS 反推。
    sg = s_float(system_growth_yoy)
    ag = s_float(ai_growth_yoy)
    if sg is not None and ag is not None:
        growth_gap_pp = abs(sg - ag) * 100
        growth_rel_gap = _relative_gap(sg, ag, "min")
        if growth_gap_pp >= 10 and (growth_rel_gap is None or growth_rel_gap > 0.30):
            add(
                "預估獲利成長 YoY 分歧",
                f"{label} 的預估獲利成長 YoY 系統值與 AI 推估值差距過大，PEG 與 Forward EPS 可信度需降權。",
                "warning",
                format_quality_value(sg, "pct"),
                format_quality_value(ag, "pct"),
                f"{growth_gap_pp:.1f} 個百分點",
                "請確認成長率是年度 EPS 成長、營收成長、或單一券商推估；不宜直接帶入 PEG。",
            )

    # 4) 合理價分歧：公式合理價與 AI 公式合理價差距 > 50%
    fair_gap = _relative_gap(system_fair_value, ai_fair_value, "min")
    if fair_gap is not None and fair_gap > 0.50:
        add(
            "合理價分歧",
            f"{label} 的系統公式合理價與 AI 公式合理價分歧過大，請以保守情境為主。",
            "danger" if fair_gap > 1.00 else "warning",
            format_quality_value(system_fair_value, "price"),
            format_quality_value(ai_fair_value, "price"),
            _fmt_gap_pct(fair_gap),
            "不要把公式合理價或極限價直接視為買賣目標；應等待可操作估值區間完成後再判斷。",
        )

    # 5) D/E 分歧：系統 D/E 與 AI D/E 差距 > 50%
    de_gap = _relative_gap(system_de, ai_de, "min")
    if de_gap is not None and de_gap > 0.50:
        add(
            "D/E 分歧",
            f"{label} 的負債權益比資料口徑不一致，防禦力評分應降級。",
            "warning",
            format_quality_value(system_de, "x"),
            format_quality_value(ai_de, "x"),
            _fmt_gap_pct(de_gap),
            "請確認 D/E 是倍數、百分比、還是總負債/股東權益欄位來源不同。",
        )


    # 6) P/B 分歧：EPS 為負或 P/E 不可用時，P/B 是重要替代估值，需特別警告。
    pb_gap = _relative_gap(system_pb, ai_pb, "min")
    if pb_gap is not None and pb_gap > 0.50:
        add(
            "P/B 分歧",
            f"{label} 的股價淨值比 P/B 系統值與 AI 值差距過大，請先確認 BVPS / 股價 / 口徑。",
            "danger" if pb_gap > 1.00 else "warning",
            format_quality_value(system_pb, "x"),
            format_quality_value(ai_pb, "x"),
            _fmt_gap_pct(pb_gap),
            "EPS 為負或 P/E 不可用時，P/B 是重要替代估值；P/B 分歧未釐清前不宜做買賣判斷。",
        )

    return warnings


DATA_QUALITY_LEVEL_DEFINITIONS = {
    "L1": {
        "label": "L1 口徑差異",
        "action": "主採用值可確認時不影響主結論，列備註。",
        "rank": 1,
    },
    "L2": {
        "label": "L2 資料過舊 / 來源待確認",
        "action": "改採較可信來源或降權該來源。",
        "rank": 2,
    },
    "L3": {
        "label": "L3 年期 / 估值口徑錯位",
        "action": "公式估值降權，採保守 EPS 或保守倍率。",
        "rank": 3,
    },
    "L4": {
        "label": "L4 關鍵欄位錯誤",
        "action": "暫停買進判斷，先確認 EPS、營收月份、現價或槓桿口徑。",
        "rank": 4,
    },
    "L5": {
        "label": "L5 多核心衝突",
        "action": "資料包不可用，停止買賣判斷並重新抓取。",
        "rank": 5,
    },
}


def classify_data_quality_warning(warning):
    """把現有分歧警告映射成 L1-L5 資料品質等級。"""
    w = warning or {}
    rule = str(w.get("規則", "") or "")
    severity = str(w.get("嚴重度", "") or "").lower()
    message = " ".join(str(w.get(k, "") or "") for k in ["警告文字", "建議處理"])
    level = "L2"

    if "Forward EPS 年期錯位" in rule:
        level = "L3"
    elif "EPS 分歧" in rule:
        level = "L4" if severity == "danger" else "L3"
    elif "YoY 分歧" in rule:
        level = "L1" if "revenueGrowth" in message and severity != "danger" else "L3"
    elif "Forward P/E 分歧" in rule:
        level = "L3"
    elif "PEG 矛盾" in rule or "PEG 分歧" in rule or "預估獲利成長 YoY 分歧" in rule:
        level = "L3"
    elif "合理價分歧" in rule:
        level = "L4" if severity == "danger" else "L3"
    elif "P/B 分歧" in rule:
        level = "L4" if severity == "danger" else "L2"
    elif "D/E 分歧" in rule:
        level = "L2"
    elif severity == "danger":
        level = "L4"
    elif severity == "warning":
        level = "L2"
    elif severity in {"info", "note", "none", ""}:
        level = "L1"

    info = DATA_QUALITY_LEVEL_DEFINITIONS[level]
    return {
        "level": level,
        "label": info["label"],
        "rank": info["rank"],
        "action": info["action"],
    }


def annotate_data_quality_warnings(warnings):
    """回傳含 L1-L5 欄位的分歧警告，不修改原 list。"""
    annotated = []
    for warning in warnings or []:
        row = dict(warning or {})
        quality = classify_data_quality_warning(row)
        row["資料等級"] = quality["level"]
        row["資料等級說明"] = quality["label"]
        row["採用動作"] = quality["action"]
        row["_quality_rank"] = quality["rank"]
        annotated.append(row)
    return annotated


def summarize_data_quality_levels(warnings, critical_reasons=None):
    """彙總本次資料品質等級；L5 僅在多個核心衝突或硬性錯誤時出現。"""
    critical_reasons = [str(x) for x in (critical_reasons or []) if str(x).strip()]
    annotated = annotate_data_quality_warnings(warnings)
    if critical_reasons:
        return {
            "level": "L4",
            "label": DATA_QUALITY_LEVEL_DEFINITIONS["L4"]["label"],
            "rank": 4,
            "action": DATA_QUALITY_LEVEL_DEFINITIONS["L4"]["action"],
            "reasons": critical_reasons,
        }
    if not annotated:
        return {
            "level": "L0",
            "label": "資料未見重大異常",
            "rank": 0,
            "action": "可依一般估值流程使用。",
            "reasons": [],
        }
    ranks = [int(row.get("_quality_rank") or 0) for row in annotated]
    l4_count = sum(1 for r in ranks if r >= 4)
    l3_count = sum(1 for r in ranks if r == 3)
    if l4_count >= 2 or (l4_count >= 1 and l3_count >= 2):
        level = "L5"
    else:
        max_rank = max(ranks)
        level = next((k for k, v in DATA_QUALITY_LEVEL_DEFINITIONS.items() if v["rank"] == max_rank), "L2")
    info = DATA_QUALITY_LEVEL_DEFINITIONS[level]
    reasons = [f"{row.get('規則', '資料警告')}({row.get('資料等級', level)})" for row in annotated]
    return {
        "level": level,
        "label": info["label"],
        "rank": info["rank"],
        "action": info["action"],
        "reasons": reasons,
    }


def build_divergence_warning_report(warnings):
    """將分歧警告整理成 DataFrame，供 Streamlit 顯示。"""
    return pd.DataFrame(
        annotate_data_quality_warnings(warnings),
        columns=["規則", "資料等級", "資料等級說明", "嚴重度", "警告文字", "系統值", "AI值", "差距", "建議處理", "採用動作"],
    )


def infer_quality_status(adopted_value, system_value=None, ai_value=None, is_stale=False, notes=""):
    """依欄位是否有採用值、是否過期、是否被校驗提醒標記，產生一致的品質狀態。"""
    note_text = str(notes or "")
    if adopted_value is None:
        return "❌ 缺資料"
    if is_stale:
        return "⚠️ 可能過期"
    high_risk_keywords = ["校驗失敗", "不合理", "已排除", "NULL", "過舊", "錯置", "幻覺"]
    if any(k in note_text for k in high_risk_keywords):
        return "⚠️ 已校正/需留意"
    if system_value is not None and ai_value is not None:
        return "✅ 系統+AI交叉"
    return "✅ 可用"


def build_financial_quality_report(rows):
    """將各欄位資料來源、AI 補值、採用值與品質狀態統一整理成 DataFrame。"""
    table = []
    for r in rows or []:
        fmt = r.get("fmt", "num")
        system_value = r.get("system_value")
        ai_value = r.get("ai_value")
        adopted_value = r.get("adopted_value")
        notes = r.get("notes", "")
        table.append({
            "資料欄位": r.get("field", ""),
            "系統來源": r.get("system_source", "系統"),
            "營收所屬月份": r.get("revenue_month", "—") or "—",
            "公告月份": r.get("announce_month", "—") or "—",
            "公告日": r.get("announce_date", "—") or "—",
            "來源規則": r.get("source_rule", "—") or "—",
            "系統來源網址": r.get("system_source_url", "—") or "—",
            "系統值": format_quality_value(system_value, fmt),
            "AI來源/日期": r.get("ai_source", "未啟動AI") if ai_value is None else r.get("ai_source", "AI補齊"),
            "AI來源網址": r.get("ai_source_url", "—") or "—",
            "AI值": format_quality_value(ai_value, fmt),
            "採用值": format_quality_value(adopted_value, fmt),
            "採用來源": r.get("adopted_source", "系統優先/AI備援"),
            "來源優先序": r.get("source_priority") or source_priority_summary_for_field(r.get("field", ""), include_rule=True) or "—",
            "最新日期/期間": r.get("period", "未揭露"),
            "品質狀態": infer_quality_status(adopted_value, system_value, ai_value, r.get("is_stale", False), notes),
            "備註": notes or "—",
        })
    return pd.DataFrame(table)


# ==========================================
# 1.1 財務資料合理性校驗 / 欄位錯位防呆
# ==========================================
def normalize_financial_ratio(val, default=None):
    """將一般百分比欄位統一成小數格式：31.5 -> 0.315；0.315 -> 0.315。
    注意：D/E 不可使用此函式，因為 2.69 可能代表 2.69 倍，而不是 2.69%。
    """
    v = s_float(val, default)
    if v is None:
        return default
    # Yahoo / AI / 不同 API 有時會把百分比以 31.5 而非 0.315 回傳
    if abs(v) > 1.5 and abs(v) <= 100:
        return v / 100.0
    return v


def normalize_debt_to_equity(val, default=None):
    """將 D/E 統一成「倍數」：0.608=60.8%；2.69=269%；132.1=132.1%。

    為什麼要獨立處理：
    - 毛利率/ROE 這類欄位的 12.01 通常代表 12.01%。
    - 但 D/E 的 2.69 常代表 2.69 倍，而不是 2.69%。
    - yfinance 或台灣財報來源常回傳 132.1 代表 132.1%，需轉成 1.321 倍。
    """
    v = s_float(val, default)
    if v is None:
        return default

    av = abs(v)
    # 2.69 這種常見寫法多半是 2.69 倍 = 269%。
    if 1.5 < av <= 10:
        return v
    # 60.8 / 132.1 / 269 這種通常是百分比數字。
    if 10 < av <= 1000:
        return v / 100.0
    # 0.608 / 1.321 這種已是倍數。
    return v

def normalize_revenue_month(val):
    """將 2026-04 / 2026年4月 / 202604 等格式盡量統一成 YYYY/MM。"""
    if val is None:
        return ""
    s = str(val).strip().replace("None", "")
    if not s:
        return ""
    m = re.search(r"(20\d{2})\D{0,3}(0?[1-9]|1[0-2])", s)
    if m:
        return f"{int(m.group(1)):04d}/{int(m.group(2)):02d}"
    m = re.search(r"(20\d{2})(0[1-9]|1[0-2])", s)
    if m:
        return f"{int(m.group(1)):04d}/{int(m.group(2)):02d}"
    return s


def build_monthly_revenue_growth_frame(df, date_col="date", revenue_col="revenue"):
    """用營收所屬月份明確比對前月與去年同月，建立月營收 MoM / YoY。

    回傳欄位的 YoY / MoM 單位維持百分點，例如 16.14 代表 16.14%。
    """
    if df is None or getattr(df, "empty", True):
        return pd.DataFrame()
    if date_col not in df.columns or revenue_col not in df.columns:
        return pd.DataFrame()

    out = df.copy()
    out["_revenue_date"] = pd.to_datetime(out[date_col], errors="coerce")
    out["_revenue_value"] = pd.to_numeric(out[revenue_col], errors="coerce")
    out = out.dropna(subset=["_revenue_date", "_revenue_value"]).copy()
    if out.empty:
        return pd.DataFrame()

    out["_period"] = out["_revenue_date"].dt.to_period("M")
    out = out.sort_values("_period").drop_duplicates("_period", keep="last").reset_index(drop=True)
    revenue_by_period = out.set_index("_period")["_revenue_value"].to_dict()

    def _growth(period, months):
        current = revenue_by_period.get(period)
        previous = revenue_by_period.get(period - months)
        if current is None or previous is None or previous <= 0:
            return None
        return (current / previous - 1) * 100

    out["revenue_month"] = out["_period"].apply(lambda p: f"{p.year:04d}/{p.month:02d}")
    out["actual_revenue_month"] = out["revenue_month"]
    out["monthly_revenue"] = out["_revenue_value"]
    out["monthly_revenue_mom"] = out["_period"].apply(lambda p: _growth(p, 1))
    out["monthly_revenue_yoy"] = out["_period"].apply(lambda p: _growth(p, 12))
    out["Month"] = out["revenue_month"]
    out["Revenue"] = out["monthly_revenue"] / 100000000
    out["MoM"] = out["monthly_revenue_mom"]
    out["YoY"] = out["monthly_revenue_yoy"]
    out["source_rule"] = "monthly revenue only; not yfinance revenueGrowth"
    return out.drop(columns=["_revenue_date", "_revenue_value", "_period"])


def calc_monthly_revenue_growth(df, date_col="date", revenue_col="revenue"):
    """回傳最新月份的單月營收、MoM、YoY，YoY 以去年同月明確比對。"""
    growth_df = build_monthly_revenue_growth_frame(df, date_col=date_col, revenue_col=revenue_col)
    if growth_df.empty:
        return {
            "revenue_month": "",
            "monthly_revenue": None,
            "monthly_revenue_mom": None,
            "monthly_revenue_yoy": None,
            "source_rule": "monthly revenue only; not yfinance revenueGrowth",
        }
    latest = growth_df.iloc[-1]
    return {
        "revenue_month": latest.get("revenue_month"),
        "monthly_revenue": s_float(latest.get("monthly_revenue")),
        "monthly_revenue_mom": s_float(latest.get("monthly_revenue_mom")),
        "monthly_revenue_yoy": s_float(latest.get("monthly_revenue_yoy")),
        "source_rule": latest.get("source_rule") or "monthly revenue only; not yfinance revenueGrowth",
    }


def previous_calendar_month(today=None):
    """回傳查詢日之前一個日曆月份，格式 YYYY/MM。

    例：2026/06/01 查詢時，上一個日曆月份是 2026/05。
    這個欄位只用來產生「某月尚未公告」提示，不可拿來假設最新公告月份。
    """
    today = today or datetime.date.today()
    first_day = today.replace(day=1)
    prev_last_day = first_day - datetime.timedelta(days=1)
    return prev_last_day.strftime("%Y/%m")


def expected_latest_revenue_month(today=None, announcement_day=10):
    """依台股月營收公告節奏推估「應已公告的最新月份」。

    多數公司月營收於次月 10 日前公告。若查詢日期仍在 10 日含以前，
    不能把上一個日曆月份視為理所當然已公告，避免 6/1 查詢時把 5 月
    誤標為最新公告月份。因此：
    - 每月 1～10 日：保守預期最新公告月份為「前兩個月」。
    - 每月 11 日起：保守預期最新公告月份為「上一個月」。

    注意：真正顯示仍以資料來源回傳的 actual_revenue_month 為準。
    """
    today = today or datetime.date.today()
    first_day = today.replace(day=1)
    prev_last_day = first_day - datetime.timedelta(days=1)
    if today.day <= announcement_day:
        prev_first = prev_last_day.replace(day=1)
        expected_last_day = prev_first - datetime.timedelta(days=1)
        return expected_last_day.strftime("%Y/%m")
    return prev_last_day.strftime("%Y/%m")


def revenue_month_is_older(actual_month, expected_month=None):
    actual = normalize_revenue_month(actual_month)
    expected = normalize_revenue_month(expected_month or expected_latest_revenue_month())
    try:
        return bool(actual and expected and actual < expected)
    except Exception:
        return False


def build_revenue_month_notice(actual_month, today=None):
    """建立月營收月份提示文字，避免把查詢月份或上一月份誤當公告月份。

    Returns
    -------
    dict: {actual_month, previous_month, expected_month, display_label, notice, is_pending_previous_month, is_older_than_expected}
    """
    actual = normalize_revenue_month(actual_month)
    previous_month = previous_calendar_month(today)
    expected = expected_latest_revenue_month(today)
    is_pending_previous = bool(actual and previous_month and actual < previous_month)
    is_older = revenue_month_is_older(actual, expected) if actual else False

    notice = ""
    if not actual:
        display_label = "公告月份：未取得"
    else:
        display_label = f"公告月份：{actual}"
        if is_pending_previous:
            try:
                pending_m = int(previous_month.split("/")[1])
                notice = f"{pending_m} 月營收尚未公告，目前最新公告月份為 {actual}。"
            except Exception:
                notice = f"{previous_month} 營收尚未公告，目前最新公告月份為 {actual}。"
        elif is_older:
            notice = f"月營收資料可能落後；目前最新公告月份為 {actual}，保守預期應至少為 {expected}。"

    return {
        "actual_month": actual,
        "previous_month": previous_month,
        "expected_month": expected,
        "display_label": display_label,
        "notice": notice,
        "is_pending_previous_month": is_pending_previous,
        "is_older_than_expected": is_older,
    }


def validate_and_correct_financial_metrics(system_vals, ai_vals=None, monthly_rev_df=None, stock_id="", stock_name=""):
    """
    財務資料品質閘門：
    1) 營益率不可高於毛利率；
    2) 最新單月 YoY 優先採用月營收資料，不直接吃 yfinance revenueGrowth；
    3) D/E 若疑似單位錯置或與 AI/財報校對差距過大，先剔除系統值；
    4) AI 交叉校對值也必須通過合理區間，否則設為 NULL，避免幻覺進入估值模型。

    回傳：corrected_system, normalized_ai, warnings
    """
    ai_vals = ai_vals or {}
    corrected = dict(system_vals or {})
    ai_norm = dict(ai_vals or {})
    warnings = []
    label = f"{stock_name} ({stock_id})" if stock_name and stock_id else (stock_name or stock_id or "目前標的")

    # v1.24 欄位相容：rev_growth/revenue_yoy、mom/revenue_mom 新舊欄位可互通。
    if ai_norm.get("revenue_yoy") is None and ai_norm.get("rev_growth") is not None:
        ai_norm["revenue_yoy"] = ai_norm.get("rev_growth")
    if ai_norm.get("rev_growth") is None and ai_norm.get("revenue_yoy") is not None:
        ai_norm["rev_growth"] = ai_norm.get("revenue_yoy")

    # 統一百分比欄位尺度；D/E 需獨立正規化，避免 2.69 倍被誤判成 2.69%。
    for key in ["gross_margin", "operating_margin", "rev_growth", "revenue_yoy", "revenue_mom", "earnings_cagr", "eps_growth_yoy"]:
        corrected[key] = normalize_financial_ratio(corrected.get(key))
        ai_norm[key] = normalize_financial_ratio(ai_norm.get(key))
    corrected["debt_to_equity"] = normalize_debt_to_equity(corrected.get("debt_to_equity"))
    ai_norm["debt_to_equity"] = normalize_debt_to_equity(ai_norm.get("debt_to_equity"))

    def is_reasonable_ratio(v, lo=-1.0, hi=1.0):
        return v is None or (lo <= v <= hi)

    def margin_pair_is_valid(gm, om):
        if not is_reasonable_ratio(gm, -1.0, 1.0) or not is_reasonable_ratio(om, -1.0, 1.0):
            return False
        if gm is None or om is None:
            return True
        # 營益率理論上不得高於毛利率；0.3% 容許極小四捨五入誤差
        return om <= gm + 0.003

    sys_gm = corrected.get("gross_margin")
    sys_om = corrected.get("operating_margin")
    ai_gm = ai_norm.get("gross_margin")
    ai_om = ai_norm.get("operating_margin")

    if not margin_pair_is_valid(sys_gm, sys_om):
        warnings.append(
            f"{label} 的毛利率/營益率校驗失敗：系統值 {to_val_str(sys_gm, 'pct')} / {to_val_str(sys_om, 'pct')} 不合理，已排除系統毛利率與營益率。"
        )
        corrected["gross_margin"] = None
        corrected["operating_margin"] = None

    if not margin_pair_is_valid(ai_gm, ai_om):
        warnings.append(
            f"{label} 的 AI 毛利率/營益率也未通過校驗：{to_val_str(ai_gm, 'pct')} / {to_val_str(ai_om, 'pct')}，已設為 NULL，避免 AI 幻覺進入估值。"
        )
        ai_norm["gross_margin"] = None
        ai_norm["operating_margin"] = None

    # 最新單月 YoY：優先用月營收表，不用 yfinance info 的 revenueGrowth 當月 YoY
    try:
        if monthly_rev_df is not None and not monthly_rev_df.empty and ("monthly_revenue_yoy" in monthly_rev_df.columns or "YoY" in monthly_rev_df.columns):
            monthly_yoy_col = "monthly_revenue_yoy" if "monthly_revenue_yoy" in monthly_rev_df.columns else "YoY"
            monthly_yoy_pct = s_float(monthly_rev_df[monthly_yoy_col].iloc[-1])
            monthly_yoy = monthly_yoy_pct / 100.0 if monthly_yoy_pct is not None else None
            monthly_period = ""
            if "Month" in monthly_rev_df.columns:
                monthly_period = normalize_revenue_month(monthly_rev_df["Month"].iloc[-1])
            if monthly_yoy is not None and -1.0 <= monthly_yoy <= 10.0:
                # yfinance revenueGrowth 多半不是台股最新單月營收 YoY 口徑；
                # 兩者差異屬正常資料源期間差異，不應常駐成黃色資料品質警告。
                corrected["rev_growth"] = monthly_yoy
                corrected["revenue_yoy"] = monthly_yoy
    except Exception:
        pass

    # AI YoY 也做合理範圍防呆；極端值多半是抓到錯欄或摘要幻覺
    ai_yoy = ai_norm.get("rev_growth")
    if ai_yoy is not None and not (-1.0 <= ai_yoy <= 10.0):
        warnings.append(
            f"{label} 的 AI 營收 YoY={to_val_str(ai_yoy, 'pct')} 超出合理範圍，已設為 NULL。"
        )
        ai_norm["rev_growth"] = None

    # D/E：系統值與 AI 值雙層防呆。D/E > 800% 直接視為高風險異常值，不進估值模型。
    def debt_to_equity_is_valid(v):
        return v is None or (0 <= v <= 8.0)

    sys_de = corrected.get("debt_to_equity")
    ai_de = ai_norm.get("debt_to_equity")

    if not debt_to_equity_is_valid(ai_de):
        warnings.append(
            f"{label} 的 AI D/E={to_val_str(ai_de, 'pct')} 超出 800% 安全上限，已設為 NULL，避免 AI 幻覺污染模型。"
        )
        ai_norm["debt_to_equity"] = None
        ai_de = None

    if sys_de is not None:
        if not debt_to_equity_is_valid(sys_de):
            warnings.append(f"{label} 的 D/E 系統值 {to_val_str(sys_de, 'pct')} 超出合理範圍，已排除。")
            corrected["debt_to_equity"] = None
        elif ai_de is not None:
            # 例如系統 0.76% vs AI 31.53%，極可能是單位或欄位錯位
            if sys_de < 0.02 and ai_de >= 0.10:
                warnings.append(
                    f"{label} 的 D/E 疑似單位/欄位錯位：系統 {to_val_str(sys_de, 'pct')} vs AI {to_val_str(ai_de, 'pct')}，已排除系統 D/E。"
                )
                corrected["debt_to_equity"] = None
            elif abs(sys_de - ai_de) >= max(0.15, abs(ai_de) * 0.80):
                warnings.append(
                    f"{label} 的 D/E 與交叉校對差距過大：系統 {to_val_str(sys_de, 'pct')} vs AI {to_val_str(ai_de, 'pct')}，已排除系統 D/E。"
                )
                corrected["debt_to_equity"] = None

    # 最終防線：系統值被排除時，如果 AI 也不可用，後續 eff_de 會自然維持 None/NULL。
    return corrected, ai_norm, warnings



def build_eps_breakdown_report(rows):
    """
    將 EPS 拆欄資料整理成 DataFrame。
    目的：避免「目前 EPS」混用最新單季、TTM、年度、Forward EPS。
    rows 每列建議包含：field, definition, system_value, ai_value, adopted_value, source, period, notes。
    """
    import pandas as pd

    def _fmt_eps(v):
        v = s_float(v)
        return "NULL" if v is None else f"{v:.2f}"

    out = []
    for r in rows or []:
        out.append({
            "EPS欄位": r.get("field", ""),
            "定義/用途": r.get("definition", ""),
            "系統值": _fmt_eps(r.get("system_value")),
            "AI值": _fmt_eps(r.get("ai_value")),
            "採用值": _fmt_eps(r.get("adopted_value")),
            "採用來源": r.get("source", ""),
            "期間/口徑": r.get("period", ""),
            "備註": r.get("notes", ""),
        })
    return pd.DataFrame(out)


def pick_first_number(*values):
    """回傳第一個可轉成 float 的數字。"""
    for v in values:
        x = s_float(v)
        if x is not None:
            return x
    return None

def validate_ai_financial_json(ai_fin, stock_id="", stock_name=""):
    """
    AI 財報 JSON 集中驗證器：
    在 Gemini 回傳後、進入 UI/估值模型前，統一完成數值轉型、合理區間檢查與目標價排序防呆。

    驗證原則：
    1) 可修正的單位問題先修正，例如百分比 25.5 -> 0.255、D/E 132.1 -> 1.321。
    2) 明顯不合理的值設為 None，不讓 AI 幻覺污染估值模型。
    3) 目標價高/均/低若只是順序錯置，會排序修正；若為負值或荒謬值則排除。
    4) FY1/FY2/FY3 必須各自帶有可解析年度，且年度需依序連續遞增。
    5) 所有修正記錄在 _ai_validation_warnings，供 UI 顯示與除錯。
    """
    if not isinstance(ai_fin, dict):
        return ai_fin

    data = dict(ai_fin)
    warnings = []
    invalid_fields = []
    label = f"{stock_name} ({stock_id})" if stock_name and stock_id else (stock_name or stock_id or "目前標的")

    def add_warning(field, message):
        invalid_fields.append(field)
        warnings.append(message)

    def num(field, default=None):
        v = s_float(data.get(field), default)
        data[field] = v
        return v

    def null_field(field, reason):
        data[field] = None
        add_warning(field, f"{label} AI 欄位 {field} 已排除：{reason}")

    # 數值欄位基本轉型
    numeric_fields = [
        "current_price", "pe",
        # EPS 拆欄：保留 legacy 欄位，也支援新標準欄位。
        "trailing_eps", "forward_eps",
        "latest_month_eps", "latest_quarter_eps", "previous_quarter_eps", "last_two_quarter_eps", "ttm_eps", "fiscal_year_eps",
        "forward_eps_system", "forward_eps_ai", "forward_eps_consensus",
        "forward_eps_fy1", "forward_eps_fy2", "forward_eps_fy3",
        "pb", "target_price", "target_price_high",
        "target_price_avg", "target_price_low", "target_price_analyst_count", "free_cash_flow",
        "current_ratio", "shares_outstanding"
    ]
    for field in numeric_fields:
        if field in data:
            num(field)

    current_price = data.get("current_price")
    if current_price is not None and current_price <= 0:
        null_field("current_price", f"目前股價={current_price} 不可小於等於 0")

    # EPS 拆欄向下相容：舊版 AI 只回 trailing_eps / forward_eps 時，映射到新口徑。
    if data.get("ttm_eps") is None and data.get("trailing_eps") is not None:
        data["ttm_eps"] = data.get("trailing_eps")
    if data.get("trailing_eps") is None and data.get("ttm_eps") is not None:
        data["trailing_eps"] = data.get("ttm_eps")
    if data.get("forward_eps_ai") is None and data.get("forward_eps") is not None:
        data["forward_eps_ai"] = data.get("forward_eps")
    if data.get("forward_eps") is None:
        data["forward_eps"] = data.get("forward_eps_consensus") or data.get("forward_eps_ai") or data.get("forward_eps_system")

    # 百分比/比率欄位標準化。AI 常把 25.5% 寫成 25.5，這裡轉為 0.255。
    ratio_fields = ["gross_margin", "operating_margin", "roe", "yoy", "mom", "dividend_yield"]
    for field in ratio_fields:
        if field in data:
            data[field] = normalize_financial_ratio(data.get(field))

    if "debt_to_equity" in data:
        data["debt_to_equity"] = normalize_debt_to_equity(data.get("debt_to_equity"))

    # 估值倍數合理性
    pe = data.get("pe")
    if pe is not None and (pe < 0 or pe > 300):
        null_field("pe", f"P/E={pe:.2f} 超出 0～300 安全範圍")

    pb = data.get("pb")
    if pb is not None and (pb < 0 or pb > 100):
        null_field("pb", f"P/B={pb:.2f} 超出 0～100 安全範圍")

    # EPS：允許虧損，但極端值通常是單位或股本欄位誤抓
    for field in ["trailing_eps", "forward_eps", "latest_month_eps", "latest_quarter_eps", "previous_quarter_eps", "last_two_quarter_eps", "ttm_eps", "fiscal_year_eps", "forward_eps_system", "forward_eps_ai", "forward_eps_consensus", "forward_eps_fy1", "forward_eps_fy2", "forward_eps_fy3"]:
        v = data.get(field)
        if v is not None and abs(v) > 10000:
            null_field(field, f"EPS={v:,.2f} 絕對值過大，疑似單位錯置")

    # FY 年期防呆：年度缺漏、格式錯誤或序列錯位的 AI EPS 不得進入正式估值。
    current_year = datetime.date.today().year
    previous_valid_year = None
    for tier in (1, 2, 3):
        eps_field = f"forward_eps_fy{tier}"
        year_field = f"forward_eps_fy{tier}_year"
        raw_year = data.get(year_field)
        parsed_year = None
        if raw_year not in (None, "", "null"):
            match = re.search(r"(?:19|20)\d{2}", str(raw_year))
            if match:
                parsed_year = int(match.group(0))
        data[year_field] = parsed_year

        if data.get(eps_field) is None:
            continue
        if parsed_year is None:
            null_field(eps_field, f"缺少可解析的 {year_field}，不得將無年度 EPS 當成 FY{tier}")
            continue
        if not (current_year - 1 <= parsed_year <= current_year + 5):
            data[year_field] = None
            null_field(eps_field, f"年度 {parsed_year} 超出目前年度附近的合理範圍")
            continue
        if previous_valid_year is not None and parsed_year != previous_valid_year + 1:
            data[year_field] = None
            null_field(eps_field, f"年度 {parsed_year} 未接續前一層年度 {previous_valid_year}，FY 序列必須逐年連續")
            continue
        previous_valid_year = parsed_year

    # 毛利率/營益率/ROE/成長/殖利率
    gm = data.get("gross_margin")
    om = data.get("operating_margin")
    if gm is not None and not (-1.0 <= gm <= 1.0):
        null_field("gross_margin", f"毛利率={gm:.4f} 超出 -100%～100%")
        gm = None
    if om is not None and not (-1.0 <= om <= 1.0):
        null_field("operating_margin", f"營益率={om:.4f} 超出 -100%～100%")
        om = None
    if gm is not None and om is not None and om > gm + 0.003:
        data["gross_margin"] = None
        data["operating_margin"] = None
        add_warning("gross_margin", f"{label} AI 毛利率/營益率邏輯不合理：營益率 {om:.2%} 高於毛利率 {gm:.2%}，兩欄皆設為 NULL。")
        add_warning("operating_margin", f"{label} AI 毛利率/營益率邏輯不合理：營益率 {om:.2%} 高於毛利率 {gm:.2%}，兩欄皆設為 NULL。")

    roe = data.get("roe")
    if roe is not None and not (-1.0 <= roe <= 1.0):
        null_field("roe", f"ROE={roe:.2%} 超出 -100%～100%")

    yoy = data.get("yoy")
    if yoy is not None and not (-1.0 <= yoy <= 10.0):
        null_field("yoy", f"YoY/CAGR={yoy:.2%} 超出 -100%～1000% 安全範圍")

    mom = data.get("mom")
    if mom is not None and not (-1.0 <= mom <= 5.0):
        null_field("mom", f"MoM={mom:.2%} 超出 -100%～500% 安全範圍")

    dy = data.get("dividend_yield")
    if dy is not None and not (0 <= dy <= 0.20):
        null_field("dividend_yield", f"殖利率={dy:.2%} 超出 0%～20%，疑似百分比尺度錯誤或抓錯欄位")

    de = data.get("debt_to_equity")
    if de is not None and not (0 <= de <= 8.0):
        null_field("debt_to_equity", f"D/E={de:.2f} 倍超出 0～8 倍安全範圍")

    cr = data.get("current_ratio")
    if cr is not None and not (0 <= cr <= 20):
        null_field("current_ratio", f"流動比率={cr:.2f} 超出 0～20 安全範圍")

    shares = data.get("shares_outstanding")
    if shares is not None and shares <= 0:
        null_field("shares_outstanding", "總發行股數/股本不可小於等於 0")

    # 目標價合理性與 high/avg/low 排序
    price_fields = ["target_price", "target_price_high", "target_price_avg", "target_price_low"]
    for field in price_fields:
        v = data.get(field)
        if v is not None and v <= 0:
            null_field(field, f"目標價={v} 不可小於等於 0")

    hi = data.get("target_price_high")
    avg = data.get("target_price_avg")
    lo = data.get("target_price_low")
    if hi is not None and avg is not None and lo is not None:
        if not (hi >= avg >= lo):
            sorted_vals = sorted([hi, avg, lo], reverse=True)
            data["target_price_high"], data["target_price_avg"], data["target_price_low"] = sorted_vals
            add_warning("target_price_high", f"{label} AI 目標價高/均/低順序錯置，已自動排序為 high≥avg≥low：{sorted_vals[0]:.2f}/{sorted_vals[1]:.2f}/{sorted_vals[2]:.2f}")
    elif hi is not None and lo is not None and hi < lo:
        data["target_price_high"], data["target_price_low"] = lo, hi
        add_warning("target_price_high", f"{label} AI 目標價 high/low 順序錯置，已交換。")

    # target_price 若缺漏，用 avg 補；若和 avg 差太大，以 avg 為主，避免 target_price 抓到個別券商極端值。
    avg = data.get("target_price_avg")
    tp = data.get("target_price")
    if tp is None and avg is not None:
        data["target_price"] = avg
    elif tp is not None and avg is not None and avg > 0 and abs(tp - avg) / avg > 0.5:
        data["target_price"] = avg
        add_warning("target_price", f"{label} AI target_price 與平均目標價差距超過 50%，已改採 target_price_avg。")

    cnt = data.get("target_price_analyst_count")
    if cnt is not None:
        if cnt < 0 or cnt > 100:
            null_field("target_price_analyst_count", f"分析師人數={cnt:.0f} 超出 0～100 安全範圍")
        else:
            data["target_price_analyst_count"] = int(round(cnt))



    # 17-C-1：AI 產業分類補齊欄位驗證。
    # 原則：AI 建議分類只作「待確認分類」，不直接覆蓋 stock_mapping.py。
    raw_ic = data.get("industry_classification")
    if isinstance(raw_ic, dict):
        try:
            from industry_taxonomy import INDUSTRY_TAXONOMY
            valid_taxons = set(INDUSTRY_TAXONOMY.keys())
        except Exception:
            valid_taxons = {"GENERAL", "THEME_EVENT"}

        ic = dict(raw_ic)
        suggested = str(ic.get("suggested_primary_taxon") or "GENERAL").strip().upper()
        if suggested not in valid_taxons:
            add_warning("industry_classification", f"{label} AI 建議產業分類 {suggested} 不在系統 taxonomy 內，已改為 GENERAL 並標示待確認。")
            suggested = "GENERAL"

        conf = str(ic.get("confidence") or "low").strip().lower()
        if conf not in {"high", "medium", "low"}:
            conf = "low"

        themes = ic.get("suggested_themes") or []
        if not isinstance(themes, list):
            themes = [str(themes)] if str(themes).strip() else []
        themes = [str(x).strip() for x in themes if str(x).strip()][:10]

        data["industry_classification"] = {
            "suggested_primary_taxon": suggested,
            "suggested_display_name": str(ic.get("suggested_display_name") or "").strip(),
            "suggested_themes": themes,
            "confidence": conf,
            "reason": str(ic.get("reason") or "").strip(),
            "evidence": str(ic.get("evidence") or "").strip(),
            "needs_manual_review": True if ic.get("needs_manual_review") is None else bool(ic.get("needs_manual_review")),
            "status": "AI 建議分類，待人工確認；不會自動覆蓋正式 stock_mapping.py。",
        }
    elif raw_ic not in (None, "", "null"):
        data["industry_classification"] = None
        add_warning("industry_classification", f"{label} AI 產業分類格式不是 JSON 物件，已忽略。")

    # data_period 至少轉字串，避免後續 UI 出現 None。
    data["data_period"] = str(data.get("data_period") or "").strip()

    # 記錄驗證結果，UI 可直接顯示。
    data["_ai_validation_warnings"] = warnings
    data["_ai_invalid_fields"] = sorted(set(invalid_fields))
    data["_ai_validation_status"] = "⚠️ 已校正/排除部分 AI 欄位" if warnings else "✅ AI JSON 合理性驗證通過"
    return data


# ==========================================
# 1.0.3 最終操作燈號：可買 / 觀望 / 不建議 / 資料分歧 / 資料異常
# ==========================================
def _confidence_label_from_score(score):
    """將 0-100 分轉成文字可信度。"""
    try:
        v = float(score)
    except Exception:
        return "資料不足"
    if v >= 80:
        return "高"
    if v >= 65:
        return "中高"
    if v >= 50:
        return "中"
    if v >= 35:
        return "偏低"
    return "低"


def data_signal_grading(
    *,
    critical_reasons=None,
    downgrade_reasons=None,
    watch_reasons=None,
    warning_count=0,
    danger_count=0,
    data_score=None,
    valuation_score=None,
    operation_score=None,
    target_rank=1,
):
    """將資料問題分級，避免把一般分歧全部視為不可判斷。"""
    critical_reasons = [str(x) for x in (critical_reasons or []) if str(x).strip()]
    downgrade_reasons = [str(x) for x in (downgrade_reasons or []) if str(x).strip()]
    watch_reasons = [str(x) for x in (watch_reasons or []) if str(x).strip()]
    warning_count = int(warning_count or 0)
    danger_count = int(danger_count or 0)
    data_score = s_float(data_score, 0) or 0
    valuation_score = s_float(valuation_score, 0) or 0
    operation_score = s_float(operation_score, 0) or 0
    target_rank = int(target_rank or 1)

    if critical_reasons:
        return {
            "grade": "資料異常-不可判斷",
            "color": "#ff4d4d",
            "advice": "核心資料無法建立或出現硬性矛盾，先修正資料，不做買賣判斷。",
            "reasons": critical_reasons,
            "can_use_conservative_valuation": False,
            "position_limit": "停止判斷",
        }

    if danger_count >= 1 or warning_count >= 3 or downgrade_reasons or data_score < 50:
        reasons = list(downgrade_reasons)
        if danger_count >= 1:
            reasons.append(f"重大分歧警告 {danger_count} 項")
        if warning_count >= 3:
            reasons.append(f"分歧警告 {warning_count} 項")
        if data_score < 50:
            reasons.append("資料可信度偏低，需使用保守值")
        return {
            "grade": "資料分歧-降權判斷",
            "color": "#ff8c00",
            "advice": "資料有分歧但仍可判斷較可靠來源；可用保守估值觀察，不宜重倉或追價。",
            "reasons": reasons,
            "can_use_conservative_valuation": True,
            "position_limit": "小量 / 降權",
        }

    if warning_count > 0 or watch_reasons or target_rank <= 2 or data_score < 65:
        reasons = list(watch_reasons)
        if warning_count > 0:
            reasons.append(f"輕度分歧警告 {warning_count} 項")
        if target_rank <= 2:
            reasons.append("法人目標價樣本數偏低")
        if data_score < 65:
            reasons.append("資料可信度尚未達中高")
        return {
            "grade": "觀望-資料待確認",
            "color": "#FFD700",
            "advice": "資料方向可判斷，但仍有欄位待確認；先觀察或小量試單，不宜一次買滿。",
            "reasons": reasons,
            "can_use_conservative_valuation": True,
            "position_limit": "觀望 / 小量試單",
        }

    return {
        "grade": "資料可用",
        "color": "#00cc66" if operation_score >= 65 and valuation_score >= 65 else "#FFD700",
        "advice": "資料分歧可控，可依估值區間與操作規則判斷。",
        "reasons": [],
        "can_use_conservative_valuation": True,
        "position_limit": "依估值區間",
    }


def build_final_operation_signal(
    *,
    current_price=None,
    valuation_separation=None,
    divergence_warnings=None,
    target_confidence=None,
    industry_profile=None,
    pe=None,
    forward_pe=None,
    peg=None,
    pb=None,
    roe=None,
    debt_to_equity=None,
    revenue_yoy=None,
    gross_margin=None,
    operating_margin=None,
    has_ai_fin_fetch=False,
    pricing_horizon=None,
    future_evidence=None,
):
    """
    產生最終操作燈號。

    燈號定義：
    - 可買：資料一致、估值落在可操作區間下緣附近、基本面未明顯轉弱。
    - 觀望：基本面可，但估值未到買點，或資料有輕度分歧。
    - 不建議：價格高於可操作區間、估值偏高、產業模型不適合純 P/E 買進，或基本面不支撐。
    - 資料異常-不可判斷：核心欄位無法建立或硬性矛盾，停止買賣判斷。
    - 資料分歧-降權判斷：有分歧但可採較可靠來源或保守值，可保守估值但不可重倉。
    - 觀望-資料待確認：方向可判斷，但關鍵欄位仍需等待確認。

    回傳 dict，含 signal、scores、reason、report。
    """
    valuation_separation = valuation_separation or {}
    warnings = divergence_warnings or []
    industry_profile = industry_profile or {}
    target_confidence = target_confidence or valuation_separation.get("target_confidence") or classify_target_price_confidence(None)

    cp = s_float(current_price)
    op_low = s_float(valuation_separation.get("operable_low"))
    op_mid = s_float(valuation_separation.get("operable_mid"))
    op_high = s_float(valuation_separation.get("operable_high"))
    warning_count = int(valuation_separation.get("warning_count", len(warnings)) or 0)
    danger_count = int(valuation_separation.get("danger_count", sum(1 for w in warnings if str(w.get("嚴重度", "")).lower() == "danger")) or 0)

    pe_model_suitable = bool(industry_profile.get("pe_model_suitable", True))
    target_rank = int(target_confidence.get("rank", 1) or 1)
    pricing_pack = pricing_horizon if isinstance(pricing_horizon, dict) else {"code": str(pricing_horizon or ""), "label": str(pricing_horizon or "未判斷"), "explanation": "", "decision_rule": ""}
    if pricing_pack.get("code") == "FY1_SOFT_OR_FY2_WATCH":
        pricing_pack = dict(pricing_pack)
        pricing_pack.update({
            "code": "FY1_SOFT_PRICED",
            "label": "FY1 樂觀定價",
            "rank": _pricing_horizon_rank("FY1_SOFT_PRICED"),
            "is_future_priced": False,
            "explanation": "現價可由 FY1 一年預估 EPS × soft 樂觀倍率解釋；這是 FY1 樂觀區，不代表必須用 FY2 EPS 才能解釋。",
            "decision_rule": "估值偏樂觀，新買需保留安全邊際；若高於可操作區間，應等待回檔或基本面再確認。",
        })
    pricing_code = pricing_pack.get("code", "")
    pricing_label = pricing_pack.get("label", pricing_code or "未判斷")
    pricing_rank = _pricing_horizon_rank(pricing_code)
    is_fy1_soft_priced = pricing_code in {"FY1_SOFT_PRICED", "FY1_SOFT_OR_FY2_WATCH"}
    future_pack = future_evidence if isinstance(future_evidence, dict) else {}
    future_score = s_float(future_pack.get("score"))
    future_label = future_pack.get("label", "未評分")
    future_action = future_pack.get("action", "")

    # 資料分級防呆：把硬性不可判斷與可降權判斷的分歧拆開。
    critical_reasons = []
    downgrade_reasons = []
    watch_reasons = []
    fy = s_float(forward_pe)
    pe_v = s_float(pe)
    peg_v = s_float(peg)
    pb_v = s_float(pb)
    roe_v = s_float(roe)
    de_v = s_float(debt_to_equity)
    yoy_v = s_float(revenue_yoy)
    gm_v = s_float(gross_margin)
    om_v = s_float(operating_margin)

    if danger_count >= 2:
        downgrade_reasons.append("重大分歧警告達 2 項以上，需採保守估值")
    if warning_count >= 4:
        downgrade_reasons.append("系統 / AI 分歧警告較多，需降權判斷")
    if is_fy1_soft_priced:
        watch_reasons.append(f"市場定價年期為 {pricing_label}，屬 FY1 樂觀區，需檢查安全邊際")
    elif pricing_rank == 2:
        downgrade_reasons.append(f"市場定價年期為 {pricing_label}，新買需降權")
    elif pricing_rank >= 3 and pricing_rank < 6:
        downgrade_reasons.append(f"市場定價年期為 {pricing_label}，不支援一般買進")
    if op_low is None or op_high is None:
        critical_reasons.append("可操作估值區間無法建立")
    if om_v is not None and gm_v is not None and om_v > gm_v + 0.05:
        critical_reasons.append("營益率高於毛利率，財報口徑疑似異常")
    if de_v is not None and de_v > 8:
        critical_reasons.append("D/E 異常偏高，需確認單位")
    if peg_v is not None and peg_v < 0:
        watch_reasons.append("PEG 為負值，成長估值不可直接使用")

    quality_level = summarize_data_quality_levels(warnings, critical_reasons=critical_reasons)

    # 三個可信度分數：資料、估值、操作。
    data_score = 85
    data_score -= warning_count * 8
    data_score -= danger_count * 18
    if has_ai_fin_fetch:
        data_score += 5
    if target_rank <= 2:
        data_score -= 8
    if critical_reasons or downgrade_reasons or watch_reasons:
        data_score -= 18
    data_score = max(0, min(100, data_score))

    valuation_score = 75
    if fy is not None:
        if fy > 35:
            valuation_score -= 20
        elif fy > 25:
            valuation_score -= 10
        elif fy < 15 and fy > 0:
            valuation_score += 8
    if peg_v is not None:
        if peg_v > 2:
            valuation_score -= 16
        elif 0 < peg_v <= 1:
            valuation_score += 10
    if pb_v is not None and pb_v > 4:
        valuation_score -= 8
    if not pe_model_suitable:
        valuation_score -= 15
    if op_low is not None and op_high is not None and cp is not None:
        if cp <= op_low:
            valuation_score += 8
        elif cp > op_high:
            valuation_score -= 15
    if is_fy1_soft_priced:
        valuation_score -= 4
    elif pricing_rank == 2:
        valuation_score -= 8
    elif pricing_rank == 3:
        valuation_score -= 16
    elif pricing_rank >= 4 and pricing_rank < 6:
        valuation_score -= 24
    if future_score is not None:
        if future_score >= 80:
            valuation_score += 6
        elif future_score >= 60:
            valuation_score += 3
        elif pricing_rank >= 2 and future_score < 50:
            valuation_score -= 12
    valuation_score -= danger_count * 12
    valuation_score = max(0, min(100, valuation_score))

    operation_score = min(data_score, valuation_score)
    if roe_v is not None and roe_v >= 0.15:
        operation_score += 5
    if yoy_v is not None and yoy_v > 0:
        operation_score += 5
    if de_v is not None and de_v > 1.5:
        operation_score -= 8
    if target_rank <= 2:
        operation_score -= 6
    if is_fy1_soft_priced:
        operation_score -= 4
    elif pricing_rank == 2:
        operation_score -= 8
    elif pricing_rank >= 3 and pricing_rank < 6:
        operation_score -= 14
    if future_score is not None and pricing_rank >= 2:
        if future_score >= 80:
            operation_score += 6
        elif future_score < 50:
            operation_score -= 10
    operation_score = max(0, min(100, operation_score))

    data_grade = data_signal_grading(
        critical_reasons=critical_reasons,
        downgrade_reasons=downgrade_reasons,
        watch_reasons=watch_reasons,
        warning_count=warning_count,
        danger_count=danger_count,
        data_score=data_score,
        valuation_score=valuation_score,
        operation_score=operation_score,
        target_rank=target_rank,
    )

    # 燈號決策
    reasons = []
    color = "#FFD700"
    signal = "觀望"

    if data_grade["grade"] == "資料異常-不可判斷":
        signal = data_grade["grade"]
        color = data_grade["color"]
        reasons.extend(data_grade["reasons"])
        advice = data_grade["advice"]
    elif not pe_model_suitable:
        signal = "不建議"
        color = "#ff8c00"
        reasons.append("產業模型不適合用純 P/E 公式價作買進依據")
        advice = "若屬題材 / 事件驅動股，請改用題材、籌碼、訂單與技術面人工確認。"
    elif cp is not None and op_low is not None and op_high is not None:
        if cp <= op_low and data_score >= 65 and valuation_score >= 65 and danger_count == 0:
            signal = "可買-小量分批" if data_grade["grade"] in {"資料可用", "觀望-資料待確認"} else data_grade["grade"]
            color = "#00cc66" if data_grade["grade"] == "資料可用" else data_grade["color"]
            reasons.append("現價低於或接近可操作估值區間下緣，且資料分歧不嚴重")
            reasons.extend(data_grade["reasons"])
            advice = "可考慮小量分批，仍需搭配技術面、籌碼與停損；不可一次買滿。" if signal == "可買-小量分批" else data_grade["advice"]
        elif cp <= op_high and operation_score >= 50:
            signal = data_grade["grade"] if data_grade["grade"] in {"資料分歧-降權判斷", "觀望-資料待確認"} else "觀望"
            color = data_grade["color"] if data_grade["grade"] != "資料可用" else "#FFD700"
            reasons.append("現價位於可操作估值區間內，尚未形成明確便宜買點")
            reasons.extend(data_grade["reasons"])
            advice = data_grade["advice"] if data_grade["grade"] != "資料可用" else "不追高，等待回檔或右側確認。"
        else:
            signal = "不建議"
            color = "#ff8c00"
            reasons.append("現價高於可操作估值區間，追價風險偏高")
            advice = "不把公式極限價當作買進目標。"
    else:
        signal = "觀望-資料待確認"
        color = "#FFD700"
        reasons.append("關鍵資料不足，無法產生明確買進燈號")
        advice = "補齊 EPS、月營收、法人目標價與分歧檢查後再判斷。"

    if signal == "可買-小量分批" and target_rank <= 2:
        signal = "觀望-資料待確認"
        color = "#FFD700"
        reasons.append("法人目標價樣本數偏低，可買燈號降為觀望")
        advice = "可列入觀察，不宜直接重倉。"

    # 市場定價年期風控：FY2/FY3 只能解釋市場先行，不直接支撐一般買進。
    if data_grade["grade"] != "資料異常-不可判斷" and pricing_rank >= 2 and pricing_rank < 6:
        pricing_reason = f"市場定價年期：{pricing_label}"
        if pricing_reason not in reasons:
            reasons.append(pricing_reason)
        if pricing_rank == 2:
            fy2_soft_policy = "現價需 FY2 soft 樂觀情境才合理；買進燈號不得直接升級，只允許既有部位續抱或回檔小量，不追價、不重倉新買。"
            if future_score is not None and future_score < 50:
                signal = "不建議"
                color = "#ff8c00"
                advice = fy2_soft_policy if pricing_code == "FY2_SOFT_PRICED" else "現價需 FY2 才能解釋，但未來證據不足，不可用 FY2 支撐買進。"
            elif future_score is not None and future_score >= 80:
                if signal != "不建議":
                    signal = "資料分歧-降權判斷"
                    color = "#ff9900"
                    advice = fy2_soft_policy if pricing_code == "FY2_SOFT_PRICED" else "現價需 FY2 / 樂觀情境才合理；未來證據高度落地時，只能小部位或既有持股續抱，不宜重倉新買。"
                else:
                    advice = fy2_soft_policy if pricing_code == "FY2_SOFT_PRICED" else "新買不追；若是低成本既有部位，可續抱觀察 EPS / 營收是否持續落地並設定風控。"
            elif future_score is not None and future_score >= 60:
                if signal in {"可買-小量分批", "資料分歧-降權判斷"}:
                    signal = "觀望-資料待確認"
                    color = "#FFD700"
                    advice = fy2_soft_policy if pricing_code == "FY2_SOFT_PRICED" else "現價已提前反映 FY2，證據逐步形成但安全邊際不足；新買等回檔或 EPS / 營收再確認。"
            elif signal == "可買-小量分批":
                signal = "不建議"
                color = "#ff8c00"
                advice = fy2_soft_policy if pricing_code == "FY2_SOFT_PRICED" else "現價需 FY2 才能解釋，但未來證據尚未評分，不可直接用 FY2 支撐買進。"
        elif pricing_rank >= 3:
            if future_score is not None and future_score >= 80 and signal != "不建議":
                signal = "觀望-資料待確認"
                color = "#FFD700"
                advice = "現價屬 FY3 / 題材重評價等高風險遠期定價；未來證據雖強，新買仍不宜追價，低成本既有部位可看事件節點續抱。"
            else:
                signal = "不建議"
                color = "#ff8c00"
                advice = "現價需 FY3、極限未來或題材重評價才能解釋；不支援一般買進，需等事件 / EPS / 營收落地。"

    report = pd.DataFrame([
        {"項目": "最終操作燈號", "結果": signal, "說明": advice},
        {"項目": "資料可信度", "結果": f"{data_score:.0f} / 100（{_confidence_label_from_score(data_score)}）", "說明": f"分歧警告 {warning_count} 項，重大 {danger_count} 項。"},
        {"項目": "估值可信度", "結果": f"{valuation_score:.0f} / 100（{_confidence_label_from_score(valuation_score)}）", "說明": "依 Forward P/E、PEG、P/B、產業模型與可操作區間判斷。"},
        {"項目": "操作可信度", "結果": f"{operation_score:.0f} / 100（{_confidence_label_from_score(operation_score)}）", "說明": "取資料與估值可信度後，再納入 ROE、營收 YoY、D/E 與法人樣本數。"},
        {"項目": "市場定價年期", "結果": f"{pricing_label}（{pricing_code or 'NULL'}）", "說明": f"{pricing_pack.get('explanation', '—')}｜{pricing_pack.get('decision_rule', '—')}"},
        {"項目": "未來證據落地", "結果": "NULL" if future_score is None else f"{future_score:.0f} / 100（{future_label}）", "說明": future_action or "—"},
        {"項目": "資料分級", "結果": data_grade["grade"], "說明": f"{data_grade['advice']}｜倉位限制：{data_grade['position_limit']}"},
        {"項目": "資料品質 L級", "結果": f"{quality_level['level']}｜{quality_level['label']}", "說明": quality_level["action"]},
        {"項目": "可操作估值區間", "結果": "NULL" if op_low is None else f"{op_low:,.2f}～{op_high:,.2f}", "說明": "用保守 EPS、法人樣本數、分歧警告與產業模型折減。"},
        {"項目": "主要原因", "結果": "；".join(reasons) if reasons else "—", "說明": industry_profile.get("warning_note", "—")},
    ])

    return {
        "signal": signal,
        "color": color,
        "advice": advice,
        "reasons": reasons,
        "data_score": data_score,
        "valuation_score": valuation_score,
        "operation_score": operation_score,
        "data_confidence": _confidence_label_from_score(data_score),
        "valuation_confidence": _confidence_label_from_score(valuation_score),
        "operation_confidence": _confidence_label_from_score(operation_score),
        "data_grade": data_grade,
        "data_grade_label": data_grade["grade"],
        "data_quality_level": quality_level,
        "data_quality_level_label": f"{quality_level['level']}｜{quality_level['label']}",
        "pricing_horizon": pricing_pack,
        "pricing_horizon_code": pricing_code,
        "pricing_horizon_label": pricing_label,
        "future_evidence": future_pack,
        "future_evidence_score": future_score,
        "future_evidence_label": future_label,
        "report": report,
    }

def get_watchlist():
    watchlist = []
    if os.path.exists("stocklist.txt"):
        try:
            with open("stocklist.txt", "r", encoding="utf-8") as f:
                for line in f:
                    if "," in line: watchlist.append(line.split(",")[0].strip())
        except Exception as e:
            log_exception("Utils", "get_watchlist:read_stocklist", e)
    return watchlist

def load_stocklist_structure():
    """解析 stocklist.txt 為 (分類順序, 分類->[(code,name)], 錯誤訊息)。"""
    cat_order = []
    cat_map = {}
    errors = []
    current_cat = None

    if not os.path.exists("stocklist.txt"):
        return [], {}, []

    try:
        with open("stocklist.txt", "r", encoding="utf-8") as f:
            for ln, raw in enumerate(f, start=1):
                line = raw.strip()
                if not line:
                    continue
                if "," in line:
                    parts = [p.strip() for p in line.split(",", 1)]
                    if len(parts) != 2 or not parts[0] or not parts[1]:
                        errors.append(f"第 {ln} 行格式錯誤：{line}")
                        continue
                    if current_cat is None:
                        current_cat = "未分類"
                        cat_order.append(current_cat)
                        cat_map[current_cat] = []
                    cat_map[current_cat].append((parts[0], parts[1]))
                else:
                    current_cat = line
                    if current_cat not in cat_map:
                        cat_order.append(current_cat)
                        cat_map[current_cat] = []
    except Exception as e:
        errors.append(f"讀取失敗：{str(e)}")

    return cat_order, cat_map, errors

def save_stocklist_structure(cat_order, cat_map):
    lines = []
    for cat in cat_order:
        lines.append(f"{cat}\n")
        for code, name in cat_map.get(cat, []):
            lines.append(f"{code},{name}\n")
        lines.append("\n")
    with open("stocklist.txt", "w", encoding="utf-8") as f:
        f.writelines(lines)

def validate_stocklist_structure(cat_order, cat_map):
    issues = []
    seen = set()
    for cat in cat_order:
        if not cat or "," in cat:
            issues.append(f"分類名稱不合法：{cat}")
        for code, name in cat_map.get(cat, []):
            if not code.isdigit():
                issues.append(f"代號非純數字：{code} ({name})")
            if code in seen:
                issues.append(f"重複代號：{code}")
            seen.add(code)
    return issues

def add_category_to_stocklist(category_name):
    cat = category_name.strip()
    if not cat:
        return False, "分類名稱不可空白。"
    if "," in cat:
        return False, "分類名稱不可包含逗號。"
    cat_order, cat_map, _ = load_stocklist_structure()
    if cat in cat_map:
        return False, "分類已存在。"
    cat_order.append(cat)
    cat_map[cat] = []
    save_stocklist_structure(cat_order, cat_map)
    return True, f"已新增分類：{cat}"

def add_stock_to_category(code, name, category):
    sc = str(code).strip()
    sn = str(name).strip()
    if not sc or not sn:
        return False, "股票代號與名稱皆不可空白。"
    if not sc.isdigit():
        return False, "股票代號必須為純數字。"
    cat_order, cat_map, _ = load_stocklist_structure()
    if category not in cat_map:
        cat_order.append(category)
        cat_map[category] = []
    for c in cat_order:
        for ec, _ in cat_map.get(c, []):
            if ec == sc:
                return False, f"代號 {sc} 已存在於分類「{c}」。"
    cat_map[category].append((sc, sn))
    save_stocklist_structure(cat_order, cat_map)
    return True, f"已加入 {sc} {sn} 到「{category}」。"

def remove_stock_from_stocklist(code):
    sc = str(code).strip()
    cat_order, cat_map, _ = load_stocklist_structure()
    removed = False
    for c in cat_order:
        old_len = len(cat_map.get(c, []))
        cat_map[c] = [(ec, en) for ec, en in cat_map.get(c, []) if ec != sc]
        if len(cat_map[c]) != old_len:
            removed = True
    if not removed:
        return False, f"找不到代號 {sc}。"
    save_stocklist_structure(cat_order, cat_map)
    return True, f"已刪除代號 {sc}。"

def move_stock_to_category(code, target_category):
    sc = str(code).strip()
    target = str(target_category).strip()
    if not target:
        return False, "目標分類不可空白。"
    cat_order, cat_map, _ = load_stocklist_structure()
    found = None
    for c in cat_order:
        for i, (ec, en) in enumerate(cat_map.get(c, [])):
            if ec == sc:
                found = (c, i, en)
                break
        if found:
            break
    if not found:
        return False, f"找不到代號 {sc}。"
    from_cat, idx, name = found
    if target not in cat_map:
        cat_order.append(target)
        cat_map[target] = []
    if from_cat == target:
        return False, "已在同一分類。"
    cat_map[from_cat].pop(idx)
    cat_map[target].append((sc, name))
    save_stocklist_structure(cat_order, cat_map)
    return True, f"已將 {sc} 移動至「{target}」。"

def move_stock_order_within_category(category, code, direction="up"):
    cat_order, cat_map, _ = load_stocklist_structure()
    if category not in cat_map:
        return False, "分類不存在。"
    arr = cat_map[category]
    idx = next((i for i, (c, _) in enumerate(arr) if c == str(code).strip()), -1)
    if idx == -1:
        return False, "找不到該代號。"
    if direction == "up" and idx > 0:
        arr[idx-1], arr[idx] = arr[idx], arr[idx-1]
    elif direction == "down" and idx < len(arr)-1:
        arr[idx+1], arr[idx] = arr[idx], arr[idx+1]
    else:
        return False, "已在邊界，無法移動。"
    cat_map[category] = arr
    save_stocklist_structure(cat_order, cat_map)
    return True, "排序已更新。"

def toggle_watchlist(code, name):
    lines = []
    if os.path.exists("stocklist.txt"):
        try:
            with open("stocklist.txt", "r", encoding="utf-8") as f: lines = f.readlines()
        except Exception as e:
            log_exception("Utils", "toggle_watchlist:read_stocklist", e)
    new_lines = []
    is_removed = False
    for line in lines:
        if "," in line and line.split(",")[0].strip() == str(code):
            is_removed = True
            continue
        new_lines.append(line)
    if not is_removed:
        if new_lines and not new_lines[-1].endswith("\n"): new_lines[-1] = new_lines[-1] + "\n"
        new_lines.append(f"{code},{name}\n")
    with open("stocklist.txt", "w", encoding="utf-8") as f:
        f.writelines(new_lines)

def get_streak(series):
    streak = 0
    for val in reversed(series.tolist()):
        if val > 0:
            if streak >= 0: streak += 1
            else: break
        elif val < 0:
            if streak <= 0: streak -= 1
            else: break
        else:
            break
    return streak

# ==========================================
# 2. Session State 初始化 & 狀態管理
# ==========================================
def init_session_state():
    if 'selected_stock' not in st.session_state: st.session_state.selected_stock = ""  # 初始不自動查詢，避免冷啟動時誤顯示找不到 2330
    if 'api_key' not in st.session_state: st.session_state.api_key = ""
    if 'fugle_key' not in st.session_state: st.session_state.fugle_key = "" 
    if 'finmind_key' not in st.session_state: st.session_state.finmind_key = "" 
    if 'ai_fetched_financials' not in st.session_state: st.session_state.ai_fetched_financials = {}
    if 'financial_candidate_reviews' not in st.session_state:
        st.session_state.financial_candidate_reviews = load_financial_candidate_review_cache().get("reviews", {})
    if 'show_pk' not in st.session_state: st.session_state.show_pk = False
    if 'ai_industry_result' not in st.session_state: st.session_state.ai_industry_result = None
    if 'quick_select' not in st.session_state: st.session_state.quick_select = "-- 快速切換標的 --"
    if 'stock_input_widget' not in st.session_state: st.session_state.stock_input_widget = ""  # 初始輸入框留白，由使用者輸入後再查詢
    if 'show_watchlist_manager' not in st.session_state: st.session_state.show_watchlist_manager = False
    if 'data_health_stats' not in st.session_state:
        st.session_state.data_health_stats = {
            "Yahoo": {"last_success": None, "error_count": 0, "last_status": "N/A"},
            "Fugle": {"last_success": None, "error_count": 0, "last_status": "N/A"},
            "FinMind": {"last_success": None, "error_count": 0, "last_status": "N/A"},
            "Gemini": {"last_success": None, "error_count": 0, "last_status": "N/A"},
        }

def log_data_health(source, ok, status_code=None):
    src = str(source).strip()
    if not src:
        return
    if 'data_health_stats' not in st.session_state:
        init_session_state()
    stats = st.session_state.data_health_stats
    if src not in stats:
        stats[src] = {"last_success": None, "error_count": 0, "last_status": "N/A"}

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    s = stats[src]
    s["last_status"] = str(status_code) if status_code is not None else ("OK" if ok else "ERR")
    if ok:
        s["last_success"] = now_str
    else:
        s["error_count"] = int(s.get("error_count", 0)) + 1
    stats[src] = s
    st.session_state.data_health_stats = stats

def reset_all_states_on_stock_change(stock_code):
    stock_code = str(stock_code or "").strip()
    st.session_state.selected_stock = stock_code
    st.session_state.quick_select = "-- 快速切換標的 --"
    st.session_state.show_pk = False
    st.session_state.ai_industry_result = None

# ==========================================
# 🌟 這裡就是修正的部分：加入 .get() 安全讀取機制
# ==========================================
def on_stock_input_change():
    new_stock = str(st.session_state.get('stock_input_widget', '') or '').strip()
    selected_stock = str(st.session_state.get('selected_stock', '') or '').strip()
    
    if new_stock != selected_stock: 
        reset_all_states_on_stock_change(new_stock)

def on_quick_select_change():
    selected = st.session_state.get('quick_select', '-- 快速切換標的 --')
    selected_stock = str(st.session_state.get('selected_stock', '') or '').strip()
    
    if selected != "-- 快速切換標的 --":
        if not selected.startswith("🏷️"):
            q_code = selected.replace("　🔸 ", "").split(" ")[0].strip()
            if q_code != selected_stock: 
                reset_all_states_on_stock_change(q_code)
        st.session_state.quick_select = "-- 快速切換標的 --"

def get_selected_model_id():
    """AI 財報/分析模型鎖定付費版高階模型，避免自動降級造成資料失真。"""
    return "gemini-3.1-pro-preview"

# ==========================================
# 1.0.2 法人目標價可信度 + 公式估值 / 可操作估值分離
# ==========================================
def classify_target_price_confidence(analyst_count):
    """
    依分析師樣本數判斷法人目標價可信度。
    規則：NULL=低；1-2=偏低；3-5=中；6-10=中高；10以上=高。
    """
    n = s_float(analyst_count)
    if n is None:
        return {
            "level": "低",
            "rank": 1,
            "label": "低可信",
            "message": "分析師人數為 NULL，不宜視為市場共識。",
            "color": "#ff4d4d",
        }
    n = int(n)
    if n <= 0:
        return {"level": "低", "rank": 1, "label": "低可信", "message": "無有效分析師樣本，不宜視為市場共識。", "color": "#ff4d4d"}
    if n <= 2:
        return {"level": "偏低", "rank": 2, "label": "偏低可信", "message": "僅 1-2 位分析師，僅供參考，需人工確認來源。", "color": "#ff9900"}
    if n <= 5:
        return {"level": "中", "rank": 3, "label": "中可信", "message": "3-5 位分析師，可作區間參考，但需檢查 EPS 口徑是否一致。", "color": "#FFD700"}
    if n <= 10:
        return {"level": "中高", "rank": 4, "label": "中高可信", "message": "6-10 位分析師，可納入基準估值參考。", "color": "#66ccff"}
    return {"level": "高", "rank": 5, "label": "高可信", "message": "10 位以上分析師，可視為較可靠共識，但仍需確認資料日期。", "color": "#00cc66"}


def _positive_numbers(*values):
    out = []
    for v in values:
        fv = s_float(v)
        if fv is not None and fv > 0:
            out.append(fv)
    return out


def build_target_price_confidence_report(analyst_count, high=None, avg=None, low=None, rationale=""):
    """將法人目標價可信度整理成單列表格。"""
    c = classify_target_price_confidence(analyst_count)
    return pd.DataFrame([{
        "分析師人數": "NULL" if s_float(analyst_count) is None else int(s_float(analyst_count)),
        "可信度": c["level"],
        "系統標籤": c["label"],
        "最高價": format_quality_value(high, "price"),
        "平均價": format_quality_value(avg, "price"),
        "最低價": format_quality_value(low, "price"),
        "判斷說明": c["message"],
        "核心理由": rationale or "—",
    }])


def build_valuation_separation_report(
    *,
    current_price=None,
    system_formula_fair_value=None,
    ai_formula_fair_value=None,
    system_formula_extreme_value=None,
    ai_formula_extreme_value=None,
    broker_target_avg=None,
    broker_target_low=None,
    analyst_count=None,
    system_forward_eps=None,
    ai_forward_eps=None,
    consensus_forward_eps=None,
    target_pe_cap=None,
    divergence_warnings=None,
    industry_profile=None,
    dynamic_cap_pack=None,
    pb_ratio=None,
):
    """
    產生「公式估值」與「可操作估值區間」分離報告。

    原則：
    - 公式合理估值 / 公式極限價：純公式輸出，不直接作買賣依據。
    - 可操作估值區間：用估值採用 Forward EPS、法人樣本數、分歧警告與產業折減後產生。
    - 此函式只提供風險調整後區間，不取代人工投資判斷。
    """
    target_conf = classify_target_price_confidence(analyst_count)
    warnings = divergence_warnings or []
    danger_count = sum(1 for w in warnings if str(w.get("嚴重度", "")).lower() == "danger")
    warning_count = len(warnings)
    industry_profile = industry_profile or {}
    industry_label = industry_profile.get("model_label", "一般產業 / 尚未分類")
    industry_discount = s_float(industry_profile.get("operable_discount_factor"))
    if industry_discount is None or industry_discount <= 0:
        industry_discount = 1.0
    industry_discount = max(0.50, min(industry_discount, 1.05))
    pe_model_suitable = bool(industry_profile.get("pe_model_suitable", True))
    dynamic_cap_pack = dynamic_cap_pack or {}
    eps_mismatch = dynamic_cap_pack.get("forward_eps_period_mismatch") if isinstance(dynamic_cap_pack.get("forward_eps_period_mismatch"), dict) else {}
    formula_eps_source = dynamic_cap_pack.get("formula_eps_source") or "系統 Forward EPS"
    raw_system_formula_fair_value = dynamic_cap_pack.get("system_formula_fair_value_raw")
    primary_valuation = str(industry_profile.get("primary_valuation") or "")
    pb_range = industry_profile.get("pb_range")
    pb_model_active = primary_valuation.startswith("pb_cycle") or (dynamic_cap_pack.get("valuation_mode") == "pb_cycle")

    conservative_eps_candidates = _positive_numbers(consensus_forward_eps, system_forward_eps, ai_forward_eps)
    conservative_eps = min(conservative_eps_candidates) if conservative_eps_candidates else None

    # 可納入可操作估值的基準價：系統公式合理價為主；法人平均目標價需至少中可信才納入；法人低標可作風險下緣參考。
    # 17-C-16：AI/法人 FY1 已在 Forward PEG 年度三情境呈現，不再作為獨立 AI 公式價進入可操作區間。
    base_candidates = _positive_numbers(system_formula_fair_value)
    if target_conf["rank"] >= 3:
        base_candidates.extend(_positive_numbers(broker_target_avg))
    if not base_candidates and conservative_eps is not None and s_float(target_pe_cap) is not None:
        # 沒有公式價時，用保守 EPS × 65% Cap 作保守替代，不使用完整極限 Cap。
        base_candidates.append(conservative_eps * max(float(target_pe_cap) * 0.65, 1))

    formula_base = min(base_candidates) if base_candidates else None

    # 第 17-B：P/B 週期模型。金融、記憶體、面板、航運等產業不硬套 P/E。
    pb_operable_low = pb_operable_high = pb_bvps = None
    if pb_model_active:
        try:
            pb_val = s_float(pb_ratio)
            cp_val = s_float(current_price)
            if cp_val is not None and pb_val is not None and pb_val > 0:
                pb_bvps = cp_val / pb_val
            if isinstance(pb_range, (tuple, list)) and len(pb_range) == 2 and pb_bvps is not None:
                pb_low = s_float(pb_range[0]); pb_high = s_float(pb_range[1])
                if pb_low is not None and pb_high is not None:
                    pb_operable_low = pb_bvps * pb_low
                    pb_operable_high = pb_bvps * pb_high
                    formula_base = (pb_operable_low + pb_operable_high) / 2
        except Exception:
            pass

    # 依法人可信度與分歧警告折減可操作價格。
    conf_discount_map = {5: 1.00, 4: 0.95, 3: 0.90, 2: 0.82, 1: 0.75}
    discount = conf_discount_map.get(target_conf["rank"], 0.75)
    if danger_count >= 1:
        discount *= 0.75
    elif warning_count >= 2:
        discount *= 0.85
    elif warning_count == 1:
        discount *= 0.92

    # 第 13 階段：依產業模型折減可操作估值。題材股或不適用 P/E 模型者，額外降級。
    discount *= industry_discount
    if not pe_model_suitable:
        discount *= 0.85

    operable_mid = formula_base * discount if formula_base is not None else None
    operable_low = operable_mid * 0.90 if operable_mid is not None else None
    operable_high = operable_mid * 1.10 if operable_mid is not None else None

    cp = s_float(current_price)
    if pb_model_active and pb_operable_low is not None and pb_operable_high is not None:
        operable_low = pb_operable_low
        operable_high = pb_operable_high
        operable_mid = (operable_low + operable_high) / 2
        action_hint = "P/B 週期模型已建立，P/E 僅作輔助，請搭配週期位置與報價/運價判斷"
    elif not pe_model_suitable:
        action_hint = "產業模型不適合純 P/E 買進判斷，請改看題材、籌碼、訂單與現金流"
    elif operable_low is None or operable_high is None:
        action_hint = "資料異常-不可判斷 / 先補資料"
    elif warning_count >= 3 or danger_count >= 2:
        action_hint = "資料分歧-降權判斷 / 保守確認"
    elif cp is not None and cp <= operable_low:
        action_hint = "接近可操作區間下緣，可進一步人工確認"
    elif cp is not None and cp <= operable_high:
        action_hint = "位於可操作區間內，仍需搭配技術面與籌碼"
    elif cp is not None and cp > operable_high:
        action_hint = "高於可操作區間，不宜把公式極限價當追價目標"
    else:
        action_hint = "觀望 / 資料不足"

    rows = [
        {
            "估值類型": "系統公式合理估值",
            "數值": format_quality_value(system_formula_fair_value, "price"),
            "用途": "純公式輸出，用於觀察估值中樞，不直接作買賣依據。",
            "可信度/限制": (
                f"採用 {formula_eps_source} × 公式倍率。"
                + (
                    f" 系統原始公式價 {format_quality_value(raw_system_formula_fair_value, 'price')}；{eps_mismatch.get('note')}"
                    if eps_mismatch.get("has_mismatch") else
                    " 第 17-C-6a 後 PEG 僅作輔助檢查，不直接推公式價。"
                )
            ),
        },
        {
            "估值類型": "系統公式極限價",
            "數值": format_quality_value(system_formula_extreme_value, "price"),
            "用途": "情境上限 / 風險提醒，不作為買進目標價。",
            "可信度/限制": "Forward EPS × Cap，容易被樂觀 EPS 放大。",
        },
        {
            "估值類型": "產業估值模型",
            "數值": industry_label,
            "用途": "依股票所屬產業決定主要估值框架與折減係數。",
            "可信度/限制": industry_profile.get("warning_note", "若分類不準，請人工調整 stocklist.txt 或產業模型規則。"),
        },
        {
            "估值類型": "Dynamic Cap 2.0 可操作倍率",
            "數值": "NULL" if dynamic_cap_pack.get("final_cap") is None else f"{float(dynamic_cap_pack.get('final_cap')):.1f}x",
            "用途": "中性可操作倍率；已納入資料可信度、估值風險與流動性折扣。",
            "可信度/限制": dynamic_cap_pack.get("explanation", "若為 P/B 週期模型，P/E Cap 僅作輔助。"),
        },
        {
            "估值類型": "Dynamic Cap 2.0 可操作倍率區間",
            "數值": "NULL" if dynamic_cap_pack.get("operable_cap_low") is None else f"{float(dynamic_cap_pack.get('operable_cap_low')):.1f}x～{float(dynamic_cap_pack.get('operable_cap_high')):.1f}x",
            "用途": "循環復甦股與資料分歧情境下，不只看單點倍率，而是看保守～中性～偏樂觀可操作範圍。",
            "可信度/限制": "此區間不等於公式極限價；高於區間時不宜追價。",
        },
        {
            "估值類型": "Dynamic Cap 2.0 公式/樂觀倍率",
            "數值": "NULL" if dynamic_cap_pack.get("formula_cap") is None else f"公式 {float(dynamic_cap_pack.get('formula_cap')):.1f}x｜樂觀 {float(dynamic_cap_pack.get('optimistic_cap')):.1f}x｜Hard {float(dynamic_cap_pack.get('hard_ceiling_cap')):.1f}x",
            "用途": "公式合理倍率與樂觀情境倍率分開顯示，避免把折扣後可操作倍率誤當公式極限價。",
            "可信度/限制": "Hard ceiling 僅為強制上限，不作買進目標。",
        },
        {
            "估值類型": "可操作估值區間",
            "數值": "NULL" if operable_low is None else f"{operable_low:,.2f}～{operable_high:,.2f}",
            "用途": "用保守 EPS、Dynamic Cap 2.0、法人樣本數、分歧警告與產業模型折減後的輔助區間。",
            "可信度/限制": (f"P/B 週期模型；BVPS 推估：{pb_bvps:.2f}；P/B 區間：{pb_range}" if pb_model_active and pb_bvps is not None else f"法人目標價可信度：{target_conf['level']}；分歧警告：{warning_count} 項；產業折減：{industry_discount:.2f}；總折減係數：約 {discount:.2f}。"),
        },
    ]
    return {
        "target_confidence": target_conf,
        "conservative_eps": conservative_eps,
        "formula_base": formula_base,
        "discount": discount,
        "industry_profile": industry_profile,
        "industry_discount": industry_discount,
        "operable_low": operable_low,
        "operable_mid": operable_mid,
        "operable_high": operable_high,
        "action_hint": action_hint,
        "warning_count": warning_count,
        "danger_count": danger_count,
        "dynamic_cap_pack": dynamic_cap_pack,
        "pb_model_active": pb_model_active,
        "pb_bvps": pb_bvps,
        "pb_operable_low": pb_operable_low,
        "pb_operable_high": pb_operable_high,
        "report": pd.DataFrame(rows),
    }



# =========================================================
# 第 17-C-8A：產業模型單次快照稽核表
# =========================================================
def build_industry_model_snapshot_audit(
    *,
    stock_id=None,
    stock_name=None,
    current_price=None,
    adopted_forward_eps=None,
    market_implied_pe=None,
    broker_avg_implied_pe=None,
    broker_high_implied_pe=None,
    formula_cap=None,
    operable_cap_mid=None,
    soft_ceiling=None,
    hard_ceiling=None,
    industry_profile=None,
    dynamic_cap_pack=None,
    revenue_yoy=None,
    revenue_mom=None,
    gross_margin=None,
    operating_margin=None,
    roe=None,
    analyst_count=None,
    target_confidence=None,
    divergence_warnings=None,
    dq_warnings=None,
    current_date=None,
):
    """單次快照稽核：只判斷本次模型是否需要人工檢查，不判斷連續幾次。

    輸出：
    - audit_label：正常 / 觀察 / 建議人工檢查 hybrid 權重 / 建議人工檢查 primary_taxon / 可能市場過熱 / 資料不足
    - audit_score：稽核分數
    - report：DataFrame
    """
    def sf(v, default=None):
        try:
            return float(v) if v is not None else default
        except Exception:
            return default

    p = industry_profile or {}
    dcp = dynamic_cap_pack or {}
    warnings = divergence_warnings or []
    dq = dq_warnings or []
    tc = target_confidence or {}

    eps = sf(adopted_forward_eps)
    cp = sf(current_price)
    hard = sf(hard_ceiling if hard_ceiling is not None else dcp.get("hard_ceiling_cap"))
    soft = sf(soft_ceiling if soft_ceiling is not None else dcp.get("optimistic_cap"))
    formula = sf(formula_cap if formula_cap is not None else dcp.get("formula_cap"))
    operable = sf(operable_cap_mid if operable_cap_mid is not None else dcp.get("final_cap"))

    m_pe = sf(market_implied_pe)
    if m_pe is None and cp is not None and eps is not None and eps > 0:
        m_pe = cp / eps

    b_avg_pe = sf(broker_avg_implied_pe)
    b_high_pe = sf(broker_high_implied_pe)

    rev_yoy = sf(revenue_yoy)
    rev_mom = sf(revenue_mom)
    gm = sf(gross_margin)
    om = sf(operating_margin)
    roev = sf(roe)
    analysts = sf(analyst_count, 0) or 0

    score = 0
    positives = []
    negatives = []
    checks = []

    def add_check(item, value, result, note):
        checks.append({"稽核項目": item, "數值": value, "判斷": result, "說明": note})

    if eps is None or eps <= 0:
        add_check("Forward EPS 採用值", "NULL", "資料不足", "缺少正數 Forward EPS，無法判斷隱含本益比是否合理。")
        negatives.append("Forward EPS 缺值或非正數")
        score -= 3
    else:
        add_check("Forward EPS 採用值", f"{eps:.2f}", "可用", "本次快照可計算市場 / 法人隱含 Forward P/E。")

    if hard is None or hard <= 0:
        add_check("系統 hard ceiling", "NULL", "資料不足", "缺少產業 hard ceiling，無法做模型偏離判斷。")
        negatives.append("hard ceiling 缺值")
        score -= 2
    else:
        add_check("系統 hard ceiling", f"{hard:.2f}x", "可用", "作為本次快照稽核的估值上限參考。")

    if m_pe is not None and hard is not None:
        if m_pe > hard:
            score += 2
            add_check("現價隱含 Forward P/E vs hard", f"{m_pe:.2f}x / {hard:.2f}x", "超過 hard", "本次快照顯示現價已進入市場重估 / 題材動能區。")
        elif soft is not None and m_pe > soft:
            score += 1
            add_check("現價隱含 Forward P/E vs soft", f"{m_pe:.2f}x / {soft:.2f}x", "偏樂觀", "現價高於 soft 但未超過 hard，暫列觀察。")
        else:
            add_check("現價隱含 Forward P/E", f"{m_pe:.2f}x", "正常", "現價未明顯突破系統模型上緣。")

    if b_avg_pe is not None and hard is not None:
        if b_avg_pe > hard:
            score += 2
            add_check("法人均價隱含 P/E vs hard", f"{b_avg_pe:.2f}x / {hard:.2f}x", "超過 hard", "法人均價也高於系統 hard，建議檢查是否為模型偏保守或法人過度樂觀。")
        else:
            add_check("法人均價隱含 P/E", f"{b_avg_pe:.2f}x", "未超過 hard", "法人均價未明顯挑戰系統 hard。")

    if b_high_pe is not None and hard is not None:
        if b_high_pe > hard * 1.30:
            score += 1
            add_check("法人高標隱含 P/E", f"{b_high_pe:.2f}x", "高標大幅超過", "法人高標超過 hard 30% 以上，僅供樂觀情境觀察，不可直接調模型。")
        elif b_high_pe > hard:
            add_check("法人高標隱含 P/E", f"{b_high_pe:.2f}x", "超過 hard", "法人高標高於系統 hard，需確認 EPS 假設。")

    if analysts >= 5:
        score += 1
        positives.append("法人樣本數較足")
        add_check("分析師人數", f"{analysts:.0f}", "支持度較高", "法人目標價樣本數較足，可提高估值中樞參考價值。")
    elif analysts >= 3:
        add_check("分析師人數", f"{analysts:.0f}", "中可信", "可作區間參考，但不足以單次快照直接調高模型。")
    else:
        score -= 1
        negatives.append("法人樣本數不足")
        add_check("分析師人數", f"{analysts:.0f}", "偏低", "法人目標價可信度不足，不宜據此更新模型。")

    if rev_yoy is not None:
        if rev_yoy > 0.20:
            score += 1
            positives.append("月營收 YoY 強")
            add_check("月營收 YoY", f"{rev_yoy*100:.2f}%", "基本面支持", "營收成長有助支撐較高估值。")
        elif rev_yoy < 0:
            score -= 1
            negatives.append("月營收 YoY 為負")
            add_check("月營收 YoY", f"{rev_yoy*100:.2f}%", "基本面不支持", "營收年減時不宜只因高估值而調高模型。")
        else:
            add_check("月營收 YoY", f"{rev_yoy*100:.2f}%", "中性", "營收成長尚未明顯支持模型升級。")

    if rev_mom is not None and rev_mom < -0.20:
        negatives.append("月營收 MoM 明顯轉弱")
        add_check("月營收 MoM", f"{rev_mom*100:.2f}%", "短期轉弱", "MoM 明顯下滑，需避免把短線高估值誤判為模型升級。")

    if gm is not None:
        if gm >= 0.45:
            score += 1
            positives.append("毛利率高")
            add_check("毛利率", f"{gm*100:.2f}%", "品質支持", "毛利率具高品質特徵，但仍需搭配營益率與 EPS。")
        elif gm < 0.20:
            score -= 1
            negatives.append("毛利率偏低")
            add_check("毛利率", f"{gm*100:.2f}%", "品質偏弱", "毛利率偏低不支持提高估值模型。")

    if om is not None:
        if om >= 0.18:
            score += 1
            positives.append("營益率佳")
            add_check("營益率", f"{om*100:.2f}%", "獲利品質支持", "營益率足以支持較高品質係數。")
        elif om < 0.08:
            score -= 1
            negatives.append("營益率偏低")
            add_check("營益率", f"{om*100:.2f}%", "費用/營運槓桿壓力", "高毛利若未轉化為營益率，不宜提高估值模型。")

    if roev is not None:
        if roev >= 0.20:
            score += 1
            positives.append("ROE 佳")
            add_check("ROE", f"{roev*100:.2f}%", "品質支持", "ROE 支持較高估值，但不等於可直接調高 hard。")
        elif roev < 0.08:
            score -= 1
            negatives.append("ROE 偏低")
            add_check("ROE", f"{roev*100:.2f}%", "品質偏弱", "ROE 偏低不支持模型升級。")

    if warnings:
        score -= min(len(warnings), 3)
        negatives.append(f"分歧警告 {len(warnings)} 項")
        add_check("系統 / AI 分歧", f"{len(warnings)} 項", "資料風險", "資料分歧存在，模型稽核只能保守判斷。")
    if dq:
        score -= min(len(dq), 2)
        add_check("資料品質提醒", f"{len(dq)} 項", "資料風險", "資料品質提醒存在，需先確認來源。")

    has_over_hard = (m_pe is not None and hard is not None and m_pe > hard)
    broker_over_hard = (b_avg_pe is not None and hard is not None and b_avg_pe > hard)
    fundamental_support = sum(1 for x in positives if x in {"月營收 YoY 強", "毛利率高", "營益率佳", "ROE 佳"}) >= 2
    weak_fundamental = any(x in negatives for x in ["月營收 YoY 為負", "月營收 MoM 明顯轉弱", "營益率偏低"])

    if eps is None or hard is None:
        label = "資料不足，先不判斷"
        action = "先補 Forward EPS 與產業 hard ceiling，再做模型稽核。"
        severity = "gray"
    elif has_over_hard and broker_over_hard and fundamental_support and analysts >= 3:
        label = "建議人工檢查 hybrid 權重"
        action = "檢查新成長曲線是否已提高 EPS / 營收貢獻；若只是單次快照，不自動調高模型。"
        severity = "orange"
    elif has_over_hard and broker_over_hard and not fundamental_support:
        label = "可能市場過熱，不調模型"
        action = "市場與法人估值高於 hard，但基本面支持不足；先維持模型，追蹤 EPS / 營收是否落地。"
        severity = "red"
    elif has_over_hard:
        label = "建議觀察 / 人工檢查"
        action = "現價超過 hard；需人工確認是模型偏保守，還是短線題材過熱。"
        severity = "orange"
    elif m_pe is not None and soft is not None and m_pe > soft:
        label = "偏樂觀觀察"
        action = "現價高於 soft 但未突破 hard，暫不調整模型。"
        severity = "yellow"
    else:
        label = "正常"
        action = "本次快照未顯示模型明顯偏離。"
        severity = "green"

    if weak_fundamental and label.startswith("建議人工檢查"):
        label = "建議人工檢查，但基本面短期轉弱"
        action = "可檢查 hybrid 權重，但因營收或營益率轉弱，不宜直接調高模型。"
        severity = "orange"

    summary = {
        "audit_label": label,
        "audit_score": score,
        "severity": severity,
        "action": action,
        "history_note": "目前未啟用歷史紀錄，本表僅為本次快照稽核，不能判斷連續幾次或長期重估。",
        "positives": positives,
        "negatives": negatives,
        "model_built_at": p.get("model_built_at", "未標示"),
        "model_maintenance_note": p.get("model_maintenance_note", "—"),
        "primary_taxon": p.get("model_key") or p.get("taxon_key"),
        "hybrid_taxons": p.get("hybrid_taxons_text", "—"),
        "mixed_caps": (
            f"v18.2 Company {dynamic_cap_pack.get('base_multiple')}x / {dynamic_cap_pack.get('optimistic_cap')}x / {dynamic_cap_pack.get('hard_ceiling_cap')}x"
            if isinstance(dynamic_cap_pack, dict) and dynamic_cap_pack.get("v18_2_caps_available")
            else p.get("hybrid_mixed_caps_text", "—")
        ),
    }
    report = pd.DataFrame(checks or [{"稽核項目": "快照稽核", "數值": "—", "判斷": label, "說明": action}])
    return {"summary": summary, "report": report}




# =========================================================
# 第 17-C-9：Forward EPS 年期分層估值模型
# =========================================================
def _pricing_horizon_rank(code):
    order = {
        "TTM_PRICED": 0,
        "FY1_PRICED": 1,
        "FY1_SOFT_PRICED": 1,
        "FY1_SOFT_OR_FY2_WATCH": 1,
        "FY2_PRICED": 2,
        "FY2_SOFT_PRICED": 2,
        "THEME_RE_RATING": 3,
        "FY3_HIGH_RISK": 3,
        "FY2_HARD_PRICED": 3,
        "EXTREME_FUTURE_PRICED": 4,
        "UNSUPPORTED": 5,
        "DATA_INSUFFICIENT": 6,
    }
    return order.get(str(code or ""), 6)


def infer_pricing_horizon(
    *,
    price=None,
    ttm_eps=None,
    fy1_eps=None,
    fy2_eps=None,
    fy3_eps=None,
    base_pe=None,
    soft_pe=None,
    hard_pe=None,
    theme_re_rating_flag=False,
):
    """判斷現價主要需要哪個 EPS 年期或題材重評價才能解釋。

    回傳 code / label / rank / explanation。FY2 以後都只能視為先行定價或高風險情境，
    不直接支撐一般買進燈號。
    """
    def sf(v):
        return s_float(v)

    p = sf(price)
    base = sf(base_pe)
    soft = sf(soft_pe)
    hard = sf(hard_pe)
    ttm = sf(ttm_eps)
    fy1 = sf(fy1_eps)
    fy2 = sf(fy2_eps)
    fy3 = sf(fy3_eps)

    if soft is not None and base is not None:
        soft = max(soft, base)
    if hard is not None and soft is not None:
        hard = max(hard, soft)

    def supported(eps, cap):
        return p is not None and p > 0 and eps is not None and eps > 0 and cap is not None and cap > 0 and p <= eps * cap

    def pack(code, label, explanation, decision_rule):
        return {
            "code": code,
            "label": label,
            "rank": _pricing_horizon_rank(code),
            "is_future_priced": _pricing_horizon_rank(code) >= 2,
            "explanation": explanation,
            "decision_rule": decision_rule,
        }

    if p is None or p <= 0 or base is None or base <= 0:
        return pack("DATA_INSUFFICIENT", "資料不足", "缺少現價或 base 倍率，無法判斷市場定價年期。", "補齊現價、EPS 與產業倍率後再判斷。")
    if supported(ttm, base):
        return pack("TTM_PRICED", "TTM 定價", "現價可由近四季已實現 EPS × base 倍率解釋。", "可用一般估值規則判斷。")
    if supported(fy1, base):
        return pack("FY1_PRICED", "FY1 定價", "現價需 FY1 一年預估 EPS × base 倍率才可解釋。", "可分批，但需追蹤 FY1 EPS 是否兌現。")
    if supported(fy1, soft):
        return pack("FY1_SOFT_PRICED", "FY1 樂觀定價", "現價可由 FY1 一年預估 EPS × soft 樂觀倍率解釋；這是 FY1 樂觀區，不代表必須用 FY2 EPS 才能解釋。", "估值偏樂觀，新買需保留安全邊際；若高於可操作區間，應等待回檔或基本面再確認。")
    if supported(fy2, base):
        return pack("FY2_PRICED", "FY2 先行定價", "現價需 FY2 第二年預估 EPS × base 倍率才可解釋。", "新買自動降權，只能小部位或既有持股續抱觀察。")
    if supported(fy2, soft):
        return pack("FY2_SOFT_PRICED", "FY2 樂觀先行定價", "現價需 FY2 第二年預估 EPS × soft 樂觀倍率才可解釋。", "買進燈號不得直接升級，需降權；只允許既有部位續抱或回檔小量，需追蹤 EPS、毛利率與法人共識是否持續上修。")
    if supported(fy2, hard):
        return pack("FY2_HARD_PRICED", "FY2 極限先行定價", "現價需 FY2 第二年預估 EPS × hard 極限倍率才可解釋。", "屬高風險先行定價，不支援一般新買；需等回檔或 EPS 再上修。")
    if supported(fy3, base):
        return pack("FY3_HIGH_RISK", "FY3 高風險遠期定價", "現價需 FY3 第三年預估 EPS × base 倍率才可解釋。", "不支援一般買進，只能高風險題材觀察。")
    if supported(fy3, hard):
        return pack("EXTREME_FUTURE_PRICED", "極限未來定價", "現價需 FY3 EPS 搭配 hard 極限倍率才可接近解釋。", "屬極限風控區，不作買進依據。")
    if theme_re_rating_flag:
        return pack("THEME_RE_RATING", "題材重評價", "EPS 堆疊尚不足以解釋現價，但產業定位或題材可能正在重評價。", "改用事件里程碑追蹤，不單用 FY1 估值停利。")
    return pack("UNSUPPORTED", "EPS 堆疊不支撐", "即使用 FY2/FY3 或 hard 情境仍難以解釋現價。", "不建議追價，需等 EPS / 營收 / 事件落地。")


def calculate_future_evidence_score(
    *,
    revenue_yoy=None,
    revenue_mom=None,
    gross_margin=None,
    operating_margin=None,
    roe=None,
    fy1_eps=None,
    fy2_eps=None,
    fy3_eps=None,
    analyst_count=None,
    target_confidence=None,
    divergence_warnings=None,
    dq_warnings=None,
    pricing_horizon=None,
    theme_re_rating_flag=False,
):
    """評估市場看的未來是否正在落地，避免 FY2/FY3 被無條件合理化。"""
    def sf(v):
        return s_float(v)

    def ratio(v):
        x = sf(v)
        if x is None:
            return None
        return x / 100.0 if abs(x) > 1.5 else x

    score = 45
    positives = []
    negatives = []
    checks = []

    def add(item, value, result, delta, note):
        checks.append({"項目": item, "數值": value, "判斷": result, "分數影響": delta, "說明": note})

    yoy = ratio(revenue_yoy)
    mom = ratio(revenue_mom)
    gm = ratio(gross_margin)
    om = ratio(operating_margin)
    roev = ratio(roe)
    fy1 = sf(fy1_eps)
    fy2 = sf(fy2_eps)
    fy3 = sf(fy3_eps)
    warnings = divergence_warnings or []
    dq = dq_warnings or []

    if yoy is None:
        add("月營收 YoY", "NULL", "未納入", 0, "缺少單月 YoY，未來落地分數不加分。")
    elif yoy >= 0.50:
        score += 18; positives.append("月營收 YoY 高成長"); add("月營收 YoY", f"{yoy*100:.2f}%", "高度落地", +18, "營收年增強，支持市場看未來。")
    elif yoy >= 0.20:
        score += 14; positives.append("月營收 YoY 強"); add("月營收 YoY", f"{yoy*100:.2f}%", "明確支持", +14, "營收年增足以支撐先行定價。")
    elif yoy > 0:
        score += 8; positives.append("月營收 YoY 正成長"); add("月營收 YoY", f"{yoy*100:.2f}%", "溫和支持", +8, "營收成長為正，但仍需 EPS / 毛利率配合。")
    else:
        score -= 14; negatives.append("月營收 YoY 轉負"); add("月營收 YoY", f"{yoy*100:.2f}%", "證據反轉", -14, "營收年減不支持遠期高估值。")

    if mom is None:
        add("月營收 MoM", "NULL", "未納入", 0, "缺少 MoM，無法確認短期落地節奏。")
    elif mom >= 0.05:
        score += 8; positives.append("月營收 MoM 轉強"); add("月營收 MoM", f"{mom*100:.2f}%", "短期加速", +8, "MoM 明顯成長，支持出貨或需求落地。")
    elif mom >= 0:
        score += 4; positives.append("月營收 MoM 非負"); add("月營收 MoM", f"{mom*100:.2f}%", "穩定", +4, "MoM 未轉負，短期動能未明顯破壞。")
    elif mom <= -0.10:
        score -= 10; negatives.append("月營收 MoM 明顯轉弱"); add("月營收 MoM", f"{mom*100:.2f}%", "短期轉弱", -10, "MoM 明顯下滑，需降低遠期樂觀假設。")
    else:
        score -= 5; negatives.append("月營收 MoM 轉負"); add("月營收 MoM", f"{mom*100:.2f}%", "輕度轉弱", -5, "MoM 轉負，追價需更保守。")

    if gm is not None:
        if gm >= 0.40:
            score += 8; positives.append("毛利率高"); add("毛利率", f"{gm*100:.2f}%", "品質支持", +8, "產品組合或產業地位支持較高估值。")
        elif gm >= 0.25:
            score += 5; positives.append("毛利率穩健"); add("毛利率", f"{gm*100:.2f}%", "穩健", +5, "毛利率具基本品質支撐。")
        elif gm < 0.15:
            score -= 6; negatives.append("毛利率偏低"); add("毛利率", f"{gm*100:.2f}%", "品質不足", -6, "毛利率偏低，不支持遠期估值放大。")

    if om is not None:
        if om >= 0.18:
            score += 8; positives.append("營益率佳"); add("營益率", f"{om*100:.2f}%", "獲利落地", +8, "營收可轉化為營業利益。")
        elif om >= 0.10:
            score += 4; positives.append("營益率可用"); add("營益率", f"{om*100:.2f}%", "可用", +4, "營運槓桿尚可。")
        elif om < 0.05:
            score -= 8; negatives.append("營益率偏弱"); add("營益率", f"{om*100:.2f}%", "獲利未落地", -8, "營收尚未有效轉為獲利。")
    if gm is not None and om is not None and om > gm + 0.03:
        score -= 12; negatives.append("毛利率 / 營益率口徑異常"); add("毛利率 / 營益率", f"{gm*100:.2f}% / {om*100:.2f}%", "資料疑慮", -12, "營益率高於毛利率，需先確認資料口徑。")

    if roev is not None:
        if roev >= 0.20:
            score += 6; positives.append("ROE 佳"); add("ROE", f"{roev*100:.2f}%", "品質支持", +6, "股東報酬率支持較高品質評價。")
        elif roev >= 0.12:
            score += 3; add("ROE", f"{roev*100:.2f}%", "中性偏正", +3, "ROE 尚可。")
        elif roev < 0.06:
            score -= 6; negatives.append("ROE 偏低"); add("ROE", f"{roev*100:.2f}%", "品質偏弱", -6, "ROE 偏低，不支持遠期高估值。")

    if fy1 is not None and fy1 > 0:
        score += 3; add("FY1 EPS", f"{fy1:.2f}", "可用", +3, "有正數 FY1 EPS 可作防守基準。")
    if fy1 is not None and fy1 > 0 and fy2 is not None and fy2 > 0:
        fy2_growth = fy2 / fy1 - 1
        if fy2_growth >= 0.20:
            score += 12; positives.append("FY2 EPS 明顯高於 FY1"); add("FY2 / FY1 EPS", f"{fy2_growth*100:.2f}%", "法人遠期上修假設強", +12, "FY2 EPS 結構支持先行定價，但仍需來源驗證。")
        elif fy2_growth >= 0.10:
            score += 8; positives.append("FY2 EPS 高於 FY1"); add("FY2 / FY1 EPS", f"{fy2_growth*100:.2f}%", "遠期成長", +8, "FY2 EPS 高於 FY1，支持部分先行定價。")
        elif fy2_growth >= 0:
            score += 4; add("FY2 / FY1 EPS", f"{fy2_growth*100:.2f}%", "小幅成長", +4, "FY2 EPS 略高於 FY1。")
        else:
            score -= 10; negatives.append("FY2 EPS 低於 FY1"); add("FY2 / FY1 EPS", f"{fy2_growth*100:.2f}%", "遠期下修", -10, "FY2 低於 FY1，不支持用遠期 EPS 合理化現價。")
    if fy2 is not None and fy2 > 0 and fy3 is not None and fy3 > fy2:
        score += 2; add("FY3 / FY2 EPS", f"{(fy3 / fy2 - 1)*100:.2f}%", "長期情境", +2, "FY3 僅作長期情境，低權重加分。")

    tc = target_confidence or {}
    rank = int(tc.get("rank") or classify_target_price_confidence(analyst_count).get("rank", 1))
    if rank >= 4:
        score += 8; positives.append("法人共識可信度高"); add("法人共識", tc.get("label", f"rank {rank}"), "樣本支持", +8, "法人樣本數較足，可提高遠期 EPS 可信度。")
    elif rank == 3:
        score += 4; add("法人共識", tc.get("label", f"rank {rank}"), "中可信", +4, "法人樣本可參考，但仍需追蹤 EPS 來源。")
    else:
        score -= 8; negatives.append("法人共識樣本不足"); add("法人共識", tc.get("label", f"rank {rank}"), "可信度不足", -8, "單一或低樣本法人目標不宜支撐遠期定價。")

    danger_count = sum(1 for w in warnings if str(w.get("嚴重度", "")).lower() == "danger")
    warning_count = max(0, len(warnings) - danger_count)
    if danger_count:
        penalty = min(24, danger_count * 12)
        score -= penalty; negatives.append(f"重大分歧 {danger_count} 項"); add("資料分歧", f"danger {danger_count}", "重大風險", -penalty, "重大分歧會降低未來落地可信度。")
    if warning_count:
        penalty = min(12, warning_count * 4)
        score -= penalty; add("資料分歧", f"warning {warning_count}", "需留意", -penalty, "一般分歧需降權。")
    if dq:
        penalty = min(12, len(dq) * 4)
        score -= penalty; add("資料品質提醒", f"{len(dq)} 項", "需確認", -penalty, "資料品質提醒存在，先降低未來落地信任度。")

    if theme_re_rating_flag:
        score += 4; positives.append("題材重評價需事件驗證"); add("題材重評價", "是", "事件追蹤", +4, "題材可解釋估值轉換，但需訂單 / 客戶 / 量產節點驗證。")

    score = int(max(0, min(100, round(score))))
    if score >= 80:
        label = "未來高度落地"
        action = "可接受 FY2 先行定價，但仍需分批；新買不可重倉。"
    elif score >= 60:
        label = "證據逐步形成"
        action = "既有部位可續抱觀察，新買需等回檔或確認。"
    elif score >= 40:
        label = "證據不足"
        action = "只能觀察，不宜用 FY2/FY3 支撐買進。"
    else:
        label = "純題材或證據反轉"
        action = "不建議追價，已有部位需風控。"

    horizon_code = pricing_horizon.get("code") if isinstance(pricing_horizon, dict) else str(pricing_horizon or "")
    if _pricing_horizon_rank(horizon_code) >= 3 and score < 80:
        action += " 現價已屬高風險遠期定價，需更嚴格事件證據。"

    return {
        "score": score,
        "label": label,
        "action": action,
        "positives": positives,
        "negatives": negatives,
        "report": pd.DataFrame(checks),
    }


def build_forward_eps_tiered_valuation_report(
    *,
    current_price=None,
    broker_target_avg=None,
    broker_target_high=None,
    broker_target_low=None,
    ttm_eps=None,
    fy1_eps=None,
    fy2_eps=None,
    fy3_eps=None,
    fy1_year=None,
    fy2_year=None,
    fy3_year=None,
    base_cap=None,
    formula_cap=None,
    operable_cap=None,
    soft_ceiling=None,
    hard_ceiling=None,
    eps_source_note=None,
    eps_basis=None,
    theme_re_rating_flag=False,
    revenue_yoy=None,
    revenue_mom=None,
    gross_margin=None,
    operating_margin=None,
    roe=None,
    analyst_count=None,
    target_confidence=None,
    divergence_warnings=None,
    dq_warnings=None,
    current_date=None,
):
    """建立 TTM / FY1 / FY2 / FY3 EPS 分層估值與法人目標價反推表。

    第 17-C-9c-hotfix44 定義：
    - TTM EPS：近四季已實現 EPS，用於目前實際獲利估值與風控。
    - FY1/FY2/FY3 EPS：法人預估「年度 EPS 序列」，不是從查詢日起算 1/2/3 年後 EPS。
    - FY1：一年預估 EPS。
    - FY2：第二年預估 EPS。
    - FY3：第三年預估 EPS 或長期情境 EPS；僅供高風險情境。
    """
    def sf(v):
        try:
            return float(v) if v is not None else None
        except Exception:
            return None

    eps_basis_code = str(eps_basis or "").strip().lower()
    ttm_only = eps_basis_code in {"ttm_only", "ttm only", "ttm-only"}
    if ttm_only:
        # v18.2 TTM reference caps are not transferable to forward EPS years.
        fy1_eps = None
        fy2_eps = None
        fy3_eps = None

    cp = sf(current_price)
    tgt_avg = sf(broker_target_avg)
    tgt_hi = sf(broker_target_high)
    tgt_lo = sf(broker_target_low)
    caps = {
        "base": sf(base_cap),
        "formula": sf(formula_cap),
        "operable": sf(operable_cap),
        "soft": sf(soft_ceiling),
        "hard": sf(hard_ceiling),
    }
    if caps["base"] is None:
        caps["base"] = caps["formula"] or caps["operable"]
    if caps["soft"] is not None and caps["base"] is not None:
        caps["soft"] = max(caps["soft"], caps["base"])
    if caps["hard"] is not None and caps["soft"] is not None:
        caps["hard"] = max(caps["hard"], caps["soft"])

    fy_definition = (
        "v18.2 本股為 TTM 參考倍率，僅能搭配 TTM EPS；FY1/FY2/FY3 估值已停用。"
        if ttm_only
        else "FY1/FY2/FY3 EPS 是預估年度 EPS 序列；FY1=一年預估EPS、FY2=第二年預估EPS、FY3=第三年預估EPS，實際年度請以 EPS 對應年度欄位解讀。"
    )

    def year_label(y):
        return format_fy_year_label(y)

    fy1_label = f"{year_label(fy1_year)}，一年預估 EPS" if fy1_year is not None else "年期未明，一年預估 EPS，請人工確認"
    fy2_label = f"{year_label(fy2_year)}，第二年預估 EPS" if fy2_year is not None else "年期未明，第二年預估 EPS，請人工確認"
    fy3_label = f"{year_label(fy3_year)}，第三年預估 EPS / 長期情境 EPS" if fy3_year is not None else "年期未明，第三年預估 EPS / 長期情境 EPS，請人工確認"
    fy_calendar_notice = build_forward_eps_calendar_notice(
        current_date=current_date,
        fy1_year=fy1_year,
        fy2_year=fy2_year,
        fy3_year=fy3_year,
    )

    rows = []
    tiers = [
        ("TTM 目前實際獲利估值", "TTM EPS", "近四季已實現 EPS", ttm_eps, "近四季", "看目前已實現獲利與風控；不反映未來成長。"),
        ("FY1 一年預估估值", "FY1 EPS", fy1_label, fy1_eps, year_label(fy1_year), "一年預估 EPS；主要作防守與合理估值參考。"),
        ("FY2 第二年預估估值", "FY2 EPS", fy2_label, fy2_eps, year_label(fy2_year), "第二年預估 EPS；可解釋市場先行 6～18 個月，但需折扣看待。"),
        ("FY3 第三年預估 / 高風險情境", "FY3 EPS", fy3_label, fy3_eps, year_label(fy3_year), "第三年預估 EPS 或長期情境 EPS；不可直接視為買進目標。"),
    ]

    for tier_name, eps_label, display_name, eps, year, note in tiers:
        e = sf(eps)
        base_c = sf(caps["base"])
        soft_c = sf(caps["soft"])
        hard_c = sf(caps["hard"])
        base_price = e * base_c if e is not None and e > 0 and base_c is not None else None
        soft_price = e * soft_c if e is not None and e > 0 and soft_c is not None else None
        hard_price = e * hard_c if e is not None and e > 0 and hard_c is not None else None
        market_pe = cp / e if cp is not None and e is not None and e > 0 else None
        avg_pe = tgt_avg / e if tgt_avg is not None and e is not None and e > 0 else None
        hi_pe = tgt_hi / e if tgt_hi is not None and e is not None and e > 0 else None
        lo_pe = tgt_lo / e if tgt_lo is not None and e is not None and e > 0 else None
        rows.append({
            "估值層": tier_name,
            "EPS口徑": eps_label,
            "顯示名稱": display_name,
            "EPS對應年度/期間": year if year is not None else "未標示",
            "EPS數值": e,
            "採用倍率": base_c,
            "估值": base_price,
            "基礎倍率(base)": base_c,
            "樂觀倍率(soft)": soft_c,
            "極限倍率(hard)": hard_c,
            "基礎估值": base_price,
            "樂觀估值": soft_price,
            "極限估值": hard_price,
            "現價隱含PE": market_pe,
            "法人均價隱含PE": avg_pe,
            "法人高標隱含PE": hi_pe,
            "法人低標隱含PE": lo_pe,
            "用途/限制": note,
        })

    report = pd.DataFrame(rows)

    # 判斷市場比較可能在看哪一年 EPS。
    market_view = "資料不足，無法判斷市場看哪一個 EPS 年期"
    hard = caps["hard"]
    ttm = sf(ttm_eps)
    fy1 = sf(fy1_eps)
    fy2 = sf(fy2_eps)
    fy3 = sf(fy3_eps)
    cp_pe_ttm = cp / ttm if cp and ttm and ttm > 0 else None
    cp_pe_fy1 = cp / fy1 if cp and fy1 and fy1 > 0 else None
    cp_pe_fy2 = cp / fy2 if cp and fy2 and fy2 > 0 else None
    cp_pe_fy3 = cp / fy3 if cp and fy3 and fy3 > 0 else None

    if ttm_only and cp_pe_ttm is not None and hard is not None and cp_pe_ttm <= hard:
        market_view = "v18.2 僅依 TTM EPS 判斷；現價隱含 TTM P/E 仍在 hard ceiling 內。"
    elif ttm_only and cp_pe_ttm is not None and hard is not None and cp_pe_ttm > hard:
        market_view = "v18.2 僅依 TTM EPS 判斷；現價隱含 TTM P/E 已高於 hard ceiling，不得改用 FY1/FY2/FY3 稀釋。"
    elif cp_pe_fy1 is not None and hard is not None and cp_pe_fy1 <= hard:
        market_view = "現價用 FY1 EPS 看仍在 hard ceiling 內，市場尚未明顯透支遠期 EPS。"
    elif cp_pe_fy1 is not None and hard is not None and cp_pe_fy1 > hard:
        if cp_pe_fy2 is not None and hard is not None and cp_pe_fy2 <= hard:
            market_view = "用 FY1 EPS 看高於 hard，但用 FY2 EPS 看回到 hard 內；市場可能已在看 FY2 EPS。"
        elif cp_pe_fy3 is not None and hard is not None and cp_pe_fy3 <= hard:
            market_view = "用 FY1/FY2 EPS 看偏高，但用 FY3 EPS 看回到 hard 內；市場可能在提前反映 FY3，高風險。"
        else:
            market_view = "即使用 FY2/FY3 EPS 仍高於 hard 或資料不足，較可能是市場過熱、EPS 假設太樂觀或倍率假設偏高。"
    elif cp_pe_ttm is not None and hard is not None and cp_pe_ttm > hard and cp_pe_fy1 is not None and cp_pe_fy1 <= hard:
        market_view = "用 TTM EPS 看偏高，但用 FY1 EPS 看可回到 hard 內；市場可能已反映 FY1 成長。"

    pricing_horizon = infer_pricing_horizon(
        price=cp,
        ttm_eps=ttm,
        fy1_eps=fy1,
        fy2_eps=fy2,
        fy3_eps=fy3,
        base_pe=caps["base"],
        soft_pe=caps["soft"],
        hard_pe=caps["hard"],
        theme_re_rating_flag=theme_re_rating_flag,
    )
    future_evidence = calculate_future_evidence_score(
        revenue_yoy=revenue_yoy,
        revenue_mom=revenue_mom,
        gross_margin=gross_margin,
        operating_margin=operating_margin,
        roe=roe,
        fy1_eps=fy1,
        fy2_eps=fy2,
        fy3_eps=fy3,
        analyst_count=analyst_count,
        target_confidence=target_confidence,
        divergence_warnings=divergence_warnings,
        dq_warnings=dq_warnings,
        pricing_horizon=pricing_horizon,
        theme_re_rating_flag=theme_re_rating_flag,
    )

    summary = {
        "fy_definition": fy_definition,
        "ttm_eps": ttm,
        "fy1_eps": fy1,
        "fy2_eps": fy2,
        "fy3_eps": fy3,
        "fy1_year": fy1_year,
        "fy2_year": fy2_year,
        "fy3_year": fy3_year,
        "fy1_label": fy1_label,
        "fy2_label": fy2_label,
        "fy3_label": fy3_label,
        "eps_basis": eps_basis or "未標示",
        "eps_source_note": eps_source_note or "—",
        "base_cap": caps["base"],
        "soft_cap": caps["soft"],
        "hard_cap": caps["hard"],
        "cap_definition": (
            "v18.2 TTM-only：base/soft/hard 僅能乘以 TTM EPS；hard 只作風控上限。"
            if ttm_only
            else "base=基礎估值倍率；soft=樂觀估值倍率；hard=極限估值倍率。hard 只作風控上限，不是買進目標。"
        ),
        "market_view": market_view,
        "market_pe_ttm": cp_pe_ttm,
        "market_pe_fy1": cp_pe_fy1,
        "market_pe_fy2": cp_pe_fy2,
        "market_pe_fy3": cp_pe_fy3,
        "pricing_horizon": pricing_horizon,
        "pricing_horizon_code": pricing_horizon.get("code"),
        "pricing_horizon_label": pricing_horizon.get("label"),
        "pricing_horizon_rank": pricing_horizon.get("rank"),
        "pricing_horizon_explanation": pricing_horizon.get("explanation"),
        "pricing_horizon_decision_rule": pricing_horizon.get("decision_rule"),
        "future_evidence": future_evidence,
        "future_evidence_score": future_evidence.get("score"),
        "future_evidence_label": future_evidence.get("label"),
        "future_evidence_action": future_evidence.get("action"),
        "fy_calendar_phase": fy_calendar_notice.get("phase"),
        "fy_calendar_date": fy_calendar_notice.get("date"),
        "fy_calendar_month": fy_calendar_notice.get("month"),
        "fy_sequence_text": fy_calendar_notice.get("fy_sequence_text"),
        "fy_calendar_ui_notice": fy_calendar_notice.get("ui_notice"),
        "fy_calendar_prompt_notice": fy_calendar_notice.get("prompt_notice"),
    }
    return {"summary": summary, "report": report}
