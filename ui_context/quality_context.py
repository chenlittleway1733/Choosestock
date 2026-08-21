"""Financial quality report context builders for ui_main.render_main_page."""

from ui_common import *


def adopt_source(sys_val, ai_val, sys_label="系統", ai_label_text="AI補齊"):
    return sys_label if sys_val is not None else (ai_label_text if ai_val is not None else "無可用資料")


def fy_year_display_safe(year_value):
    try:
        if year_value is None or str(year_value).strip() in ["", "None", "nan"]:
            return "年期未明"
        text = str(year_value).strip()
        return f"{text}E" if re.match(r"^\d{4}$", text) else text
    except Exception:
        return "年期未明"


def _ai_src(ai_fin, has_ai_fin_fetch, ai_period_text, field_key, fallback_label="AI補齊"):
    return format_ai_source_detail(ai_fin, field_key, ai_period_text, fallback_label) if has_ai_fin_fetch else "AI未啟動"


def _ai_url(ai_fin, has_ai_fin_fetch, field_key):
    return get_ai_source_url(ai_fin, field_key) if has_ai_fin_fetch else ""


def build_quality_report_context(
    *,
    curr_p,
    ai_fin,
    has_ai_fin_fetch,
    raw_ai_period,
    dq_warnings,
    latest_rev_month,
    latest_rev_display_label,
    latest_rev_notice,
    latest_mom_val,
    latest_rev_source_url,
    latest_rev_source_rule,
    latest_rev_announce_date,
    latest_rev_announce_month,
    latest_rev_revenue_month,
    pe_ratio,
    ai_pe,
    sys_forward_pe,
    ai_fpe,
    eff_forward_pe,
    orig_peg,
    ai_peg,
    eff_peg,
    pb_ratio,
    ai_pb,
    ai_latest_month_eps,
    sys_latest_quarter_eps,
    ai_latest_quarter_eps,
    sys_ttm_eps,
    ai_ttm_eps,
    eff_t_eps,
    sys_fiscal_year_eps,
    ai_fiscal_year_eps,
    sys_forward_eps_system,
    ai_forward_eps_consensus,
    ai_forward_eps_ai,
    ai_f_eps_calc,
    ai_forward_eps_fy1,
    ai_forward_eps_fy2,
    ai_forward_eps_fy3,
    ai_forward_eps_fy1_year,
    ai_forward_eps_fy2_year,
    ai_forward_eps_fy3_year,
    ai_forward_eps_fy1_source,
    ai_forward_eps_fy2_source,
    ai_forward_eps_fy3_source,
    rev_growth,
    ai_yoy,
    eff_rg,
    ai_mom,
    gross_margin,
    ai_gm,
    eff_gm,
    op_margin,
    ai_om,
    eff_om,
    roe,
    ai_roe,
    eff_roe,
    sys_de,
    ai_de,
    eff_de,
    ttm_eps_adoption=None,
):
    """Build the financial quality report rows and derived period metadata."""
    dq_note_text = "；".join(dq_warnings) if dq_warnings else ""
    ai_period_text = raw_ai_period if raw_ai_period else "AI未啟動或未揭露期間"
    latest_rev_period = latest_rev_display_label if latest_rev_month and latest_rev_month != "無資料" else "未取得月營收"
    rev_is_stale = revenue_month_is_older(latest_rev_month) if latest_rev_month and latest_rev_month != "無資料" else False
    ttm_eps_adoption = ttm_eps_adoption if isinstance(ttm_eps_adoption, dict) else {}
    ttm_notes = "；".join(ttm_eps_adoption.get("notes") or [])
    if ttm_eps_adoption.get("warnings"):
        warn_text = "；".join(str(x) for x in ttm_eps_adoption.get("warnings") or [])
        ttm_notes = (ttm_notes + "；" if ttm_notes else "") + warn_text
    if not ttm_notes:
        ttm_notes = "用於歷史 P/E；近四季 EPS 合計優先，yfinance trailingEps 僅作備援。"
    ttm_adopted_source = ttm_eps_adoption.get("adopted_source") or adopt_source(sys_ttm_eps, ai_ttm_eps)
    ttm_period = ai_period_text if ttm_eps_adoption.get("adopted_value") == ai_ttm_eps and ai_ttm_eps is not None else "系統/備援"

    def src(field_key, fallback_label="AI補齊"):
        return _ai_src(ai_fin, has_ai_fin_fetch, ai_period_text, field_key, fallback_label)

    def url(field_key):
        return _ai_url(ai_fin, has_ai_fin_fetch, field_key)

    quality_rows = [
        {"field": "現價", "system_source": "Yahoo/yfinance 即時或延遲行情", "system_value": curr_p, "ai_source": "不使用AI", "ai_value": None, "adopted_value": curr_p, "adopted_source": "系統行情", "period": "即時/延遲", "fmt": "price"},
        {"field": "P/E", "system_source": "yfinance；異常時 FinMind PER 備援", "system_value": pe_ratio, "ai_source": src("pe"), "ai_source_url": url("pe"), "ai_value": ai_pe, "adopted_value": pe_ratio if pe_ratio is not None else ai_pe, "adopted_source": adopt_source(pe_ratio, ai_pe), "period": ai_period_text if pe_ratio is None and ai_pe is not None else "系統最新可得", "fmt": "x"},
        {"field": "Forward P/E", "system_source": "yfinance forwardPE 或 EPS 反推", "system_value": sys_forward_pe, "ai_source": src("forward_eps"), "ai_source_url": url("forward_eps"), "ai_value": ai_fpe, "adopted_value": eff_forward_pe, "adopted_source": adopt_source(sys_forward_pe, ai_fpe), "period": ai_period_text if sys_forward_pe is None and ai_fpe is not None else "系統/反推", "fmt": "x"},
        {"field": "PEG", "system_source": "Forward P/E ÷ 預估成長率", "system_value": orig_peg, "ai_source": src("yoy"), "ai_source_url": url("yoy"), "ai_value": ai_peg, "adopted_value": None if eff_peg == -999 else eff_peg, "adopted_source": "系統優先/AI備援", "period": "推估值", "fmt": "x", "notes": "成長率為負時 PEG 無意義" if eff_peg == -999 else ""},
        {"field": "P/B", "system_source": "yfinance；異常時 FinMind PBR 備援", "system_value": pb_ratio, "ai_source": src("pb"), "ai_source_url": url("pb"), "ai_value": ai_pb, "adopted_value": pb_ratio if pb_ratio is not None else ai_pb, "adopted_source": adopt_source(pb_ratio, ai_pb), "period": ai_period_text if pb_ratio is None and ai_pb is not None else "系統最新可得", "fmt": "x"},
        {"field": "最新單月 EPS", "system_source": "系統未穩定提供，需 AI 查自結/注意股公告", "system_value": None, "ai_source": src("latest_month_eps"), "ai_source_url": url("latest_month_eps"), "ai_value": ai_latest_month_eps, "adopted_value": ai_latest_month_eps, "adopted_source": "AI補齊/自結公告" if ai_latest_month_eps is not None else "無可用資料", "period": ai_period_text, "fmt": "num", "notes": "若取得，目前估值優先採單月 EPS ×12"},
        {"field": "最新單季 EPS", "system_source": "系統未穩定提供，避免用 TTM 冒充", "system_value": sys_latest_quarter_eps, "ai_source": src("latest_quarter_eps"), "ai_source_url": url("latest_quarter_eps"), "ai_value": ai_latest_quarter_eps, "adopted_value": ai_latest_quarter_eps, "adopted_source": "AI補齊" if ai_latest_quarter_eps is not None else "無可用資料", "period": ai_period_text, "fmt": "num", "notes": "判斷最新獲利動能"},
        {"field": "TTM EPS", "system_source": "yfinance trailingEps / 現價÷P/E 反推備援", "system_value": sys_ttm_eps, "ai_source": src("ttm_eps"), "ai_source_url": url("ttm_eps"), "ai_value": ai_ttm_eps, "adopted_value": eff_t_eps, "adopted_source": ttm_adopted_source, "period": ttm_period, "fmt": "num", "notes": ttm_notes},
        {"field": "完整年度 EPS", "system_source": "未穩定提供，需 AI/年報補齊", "system_value": sys_fiscal_year_eps, "ai_source": src("fiscal_year_eps"), "ai_source_url": url("fiscal_year_eps"), "ai_value": ai_fiscal_year_eps, "adopted_value": ai_fiscal_year_eps, "adopted_source": "AI補齊" if ai_fiscal_year_eps is not None else "無可用資料", "period": ai_period_text, "fmt": "num", "notes": "年度基準，不與 TTM 混用"},
        {"field": "Forward EPS－系統", "system_source": "yfinance forwardEps；必要時由 TTM EPS×成長率推估", "system_value": sys_forward_eps_system, "ai_source": "不使用AI", "ai_source_url": "", "ai_value": None, "adopted_value": sys_forward_eps_system, "adopted_source": "系統/推估" if sys_forward_eps_system is not None else "無可用資料", "period": "系統/推估", "fmt": "num"},
        {"field": "Forward EPS－合併/共識", "system_source": "程式 FY1 優先；缺值才用 AI", "system_value": None, "ai_source": ai_forward_eps_fy1_source or (src("forward_eps_consensus") if ai_forward_eps_consensus is not None else src("forward_eps_ai")), "ai_source_url": url("forward_eps_fy1") or (url("forward_eps_consensus") if ai_forward_eps_consensus is not None else url("forward_eps_ai")), "ai_value": None, "adopted_value": ai_f_eps_calc, "adopted_source": ai_forward_eps_fy1_source or ("法人共識" if ai_forward_eps_consensus is not None else ("AI補齊" if ai_forward_eps_ai is not None else "無可用資料")), "period": fy_year_display_safe(ai_forward_eps_fy1_year) if ai_forward_eps_fy1 is not None else ai_period_text, "fmt": "num", "notes": "程式抓取優先，AI 只補缺值；與單一 forwardEps 分開比較"},
        {"field": "Forward EPS－FY1", "system_source": "程式抓取優先；缺值才用 AI", "system_value": None, "ai_source": ai_forward_eps_fy1_source or src("forward_eps_fy1"), "ai_source_url": url("forward_eps_fy1"), "ai_value": None, "adopted_value": ai_forward_eps_fy1, "adopted_source": ai_forward_eps_fy1_source or ("無可用資料" if ai_forward_eps_fy1 is None else "程式 / AI 補缺"), "period": fy_year_display_safe(ai_forward_eps_fy1_year), "fmt": "num", "notes": "FY1 一年預估估值用；無年度或來源不足的 AI 值不採用"},
        {"field": "Forward EPS－FY2", "system_source": "程式抓取優先；缺值才用 AI", "system_value": None, "ai_source": ai_forward_eps_fy2_source or src("forward_eps_fy2"), "ai_source_url": url("forward_eps_fy2"), "ai_value": None, "adopted_value": ai_forward_eps_fy2, "adopted_source": ai_forward_eps_fy2_source or ("無可用資料" if ai_forward_eps_fy2 is None else "程式 / AI 補缺"), "period": fy_year_display_safe(ai_forward_eps_fy2_year), "fmt": "num", "notes": "FY2 第二年預估估值用，不直接當買點"},
        {"field": "Forward EPS－FY3", "system_source": "程式抓取優先；缺值才用 AI", "system_value": None, "ai_source": ai_forward_eps_fy3_source or src("forward_eps_fy3"), "ai_source_url": url("forward_eps_fy3"), "ai_value": None, "adopted_value": ai_forward_eps_fy3, "adopted_source": ai_forward_eps_fy3_source or ("無可用資料" if ai_forward_eps_fy3 is None else "程式 / AI 補缺"), "period": fy_year_display_safe(ai_forward_eps_fy3_year), "fmt": "num", "notes": "FY3 第三年預估/高風險情境，不作買點"},
        {"field": "營收 YoY", "system_source": "MOPS/FinMind/Yahoo 月營收；不採 yfinance revenueGrowth", "system_source_url": latest_rev_source_url, "source_rule": latest_rev_source_rule, "announce_date": latest_rev_announce_date, "announce_month": latest_rev_announce_month, "revenue_month": latest_rev_revenue_month, "system_value": rev_growth, "ai_source": src("yoy"), "ai_source_url": url("yoy"), "ai_value": ai_yoy, "adopted_value": eff_rg, "adopted_source": adopt_source(rev_growth, ai_yoy, "月營收公告值", "AI補齊"), "period": latest_rev_period, "fmt": "pct", "is_stale": rev_is_stale, "notes": latest_rev_notice or ("月營收可能不是最新公告月份" if rev_is_stale else "")},
        {"field": "營收 MoM", "system_source": "MOPS/FinMind/Yahoo 月營收", "system_source_url": latest_rev_source_url, "source_rule": latest_rev_source_rule, "announce_date": latest_rev_announce_date, "announce_month": latest_rev_announce_month, "revenue_month": latest_rev_revenue_month, "system_value": (latest_mom_val / 100.0) if latest_mom_val is not None else None, "ai_source": src("mom"), "ai_source_url": url("mom"), "ai_value": ai_mom, "adopted_value": (latest_mom_val / 100.0) if latest_mom_val is not None else ai_mom, "adopted_source": "月營收公告值/AI覆蓋", "period": latest_rev_period, "fmt": "pct", "is_stale": rev_is_stale},
        {"field": "毛利率", "system_source": "yfinance；缺值時 FinMind 財報健康度", "system_value": gross_margin, "ai_source": src("gross_margin"), "ai_source_url": url("gross_margin"), "ai_value": ai_gm, "adopted_value": eff_gm, "adopted_source": adopt_source(gross_margin, ai_gm), "period": ai_period_text if gross_margin is None and ai_gm is not None else "系統最新可得", "fmt": "pct", "notes": dq_note_text if "毛利率" in dq_note_text else ""},
        {"field": "營益率", "system_source": "yfinance；缺值時 FinMind 財報健康度", "system_value": op_margin, "ai_source": src("operating_margin"), "ai_source_url": url("operating_margin"), "ai_value": ai_om, "adopted_value": eff_om, "adopted_source": adopt_source(op_margin, ai_om), "period": ai_period_text if op_margin is None and ai_om is not None else "系統最新可得", "fmt": "pct", "notes": dq_note_text if "營益率" in dq_note_text else ""},
        {"field": "ROE", "system_source": "yfinance；或用 P/B÷P/E 校正", "system_value": roe, "ai_source": src("roe"), "ai_source_url": url("roe"), "ai_value": ai_roe, "adopted_value": eff_roe, "adopted_source": adopt_source(roe, ai_roe, "系統/恆等式校正", "AI補齊"), "period": ai_period_text if roe is None and ai_roe is not None else "系統/校正", "fmt": "pct"},
        {"field": "D/E", "system_source": "yfinance；缺值時 FinMind 財報健康度", "system_value": sys_de, "ai_source": src("debt_to_equity"), "ai_source_url": url("debt_to_equity"), "ai_value": ai_de, "adopted_value": eff_de, "adopted_source": adopt_source(sys_de, ai_de), "period": ai_period_text if sys_de is None and ai_de is not None else "系統最新可得", "fmt": "x", "notes": dq_note_text if "D/E" in dq_note_text or "債" in dq_note_text else ""},
    ]
    dq_report_df = build_financial_quality_report(quality_rows)
    return {
        "quality_rows": quality_rows,
        "dq_report_df": dq_report_df,
        "dq_note_text": dq_note_text,
        "ai_period_text": ai_period_text,
        "latest_rev_period": latest_rev_period,
        "rev_is_stale": rev_is_stale,
    }
