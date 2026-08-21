"""Schema helpers for AI financial-fill responses."""

AI_FINANCIAL_FIELD_LABELS = {
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


def normalize_ai_source_metadata(parsed):
    """Normalize AI field-level source metadata into _ai_source_trace."""
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
