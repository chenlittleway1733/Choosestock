"""Prompt-pack data context helpers for ui_main.render_main_page."""

from ui_common import *
from ui_context.financial_context import first_valid_analyst_count


def build_essential_version_prompt(*, app_title, stock_id, stock_name, fields):
    """Build one compact prompt and silently omit every uncaptured field."""
    missing_markers = ("n/a", "null", "none", "nan", "無資料", "未取得", "未捕捉到", "未知")

    def _usable_text(value):
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass
        text = re.sub(r"\s+", " ", str(value)).strip()
        if not text or any(marker in text.lower() for marker in missing_markers):
            return ""
        return text

    data_lines = []
    for item in fields or []:
        if isinstance(item, dict):
            label = _usable_text(item.get("label"))
            value = _usable_text(item.get("value"))
        elif isinstance(item, (tuple, list)) and len(item) >= 2:
            label = _usable_text(item[0])
            value = _usable_text(item[1])
        else:
            continue
        if label and value:
            data_lines.append(f"- {label}：{value}")

    stock_label = f"{_usable_text(stock_name)} ({_usable_text(stock_id)})".strip()
    if stock_label == "()":
        stock_label = "目前標的"
    core_data = "\n".join(data_lines) if data_lines else "- 請先查證核心數據後再分析"
    return (
        f"你是台股估值與風險分析助手。請用繁體中文，僅根據下列 {app_title} "
        f"已取得的核心數據分析 {stock_label}。若有資料缺失，請先上網查詢儘量補齊，再來判斷；"
        "外部補齊值必須標示來源與日期，且不得覆蓋系統已取得值。\n\n"
        f"【核心數據】\n{core_data}\n\n"
        "【任務】\n"
        "1. 判斷現價相對 TTM、FY1、FY2、FY3 情境價與法人目標價是低估、合理或偏高。\n"
        "2. 分析毛利率、營益率與 YoY 是否支撐預估 EPS；FY2/FY3 只作遠期風險情境。\n"
        "3. 給出一句話結論、分批買進條件、減碼/停損條件，以及最重要的 3 個風險。\n"
        "4. 若需外部查證，請另列來源與日期，不得擅自替換上列系統值。"
    )


def prompt_nullize_text(value):
    value = str(value) if value is not None else ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("N/A", "NULL").replace("無資料", "NULL").replace("未捕捉到", "NULL")
    value = re.sub(r"\s+", " ", value)
    return value.strip() if value.strip() else "NULL"


def prompt_first_float(*values):
    for value in values:
        float_value = s_float(value)
        if float_value is not None and float_value > 0:
            return float_value
    return None


def prompt_df(df, max_rows=20):
    """Compress a dataframe into copyable prompt text."""
    try:
        if df is None or getattr(df, "empty", True):
            return "NULL"
        rows = []
        for _, row in df.head(max_rows).iterrows():
            parts = []
            for col in df.columns:
                value = prompt_nullize_text(row.get(col, ""))
                if value != "NULL":
                    parts.append(f"{col}={value}")
            if parts:
                rows.append("- " + "；".join(parts))
        return "\n".join(rows) if rows else "NULL"
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_df", exc)
        except Exception:
            pass
        return "NULL"


def prompt_warnings(warnings):
    try:
        if not warnings:
            return "NULL"
        rows = []
        for warning in warnings[:12]:
            if not isinstance(warning, dict):
                continue
            rows.append(
                "- "
                f"規則={prompt_nullize_text(warning.get('規則'))}；"
                f"嚴重度={prompt_nullize_text(warning.get('嚴重度'))}；"
                f"警告={prompt_nullize_text(warning.get('警告文字'))}；"
                f"系統值={prompt_nullize_text(warning.get('系統值'))}；"
                f"AI值={prompt_nullize_text(warning.get('AI值'))}；"
                f"差距={prompt_nullize_text(warning.get('差距'))}；"
                f"建議={prompt_nullize_text(warning.get('建議處理'))}"
            )
        return "\n".join(rows) if rows else "NULL"
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_warnings", exc)
        except Exception:
            pass
        return "NULL"


def build_prompt_target_context(*, target_panel, ai_fin, info, ai_hi_val, ai_me_val, ai_lo_val, ai_analyst_count):
    """Build prompt values that mirror the target-price panel."""
    target_panel = target_panel if isinstance(target_panel, dict) else {}
    ai_fin = ai_fin if isinstance(ai_fin, dict) else {}
    info = info if isinstance(info, dict) else {}

    tp_hi = prompt_first_float(
        target_panel.get("high"),
        ai_hi_val,
        ai_fin.get("target_price_high"),
        info.get("targetHighPrice"),
    )
    tp_me = prompt_first_float(
        target_panel.get("mean"),
        ai_me_val,
        ai_fin.get("target_price_avg"),
        ai_fin.get("target_price"),
        info.get("targetMeanPrice"),
    )
    tp_lo = prompt_first_float(
        target_panel.get("low"),
        ai_lo_val,
        ai_fin.get("target_price_low"),
        info.get("targetLowPrice"),
    )

    analyst_count = first_valid_analyst_count(
        target_panel.get("analyst_count"),
        ai_analyst_count,
        ai_fin.get("target_price_analyst_count"),
        ai_fin.get("analyst_count"),
        ai_fin.get("target_analyst_count"),
        info.get("numberOfAnalystOpinions"),
    )

    if tp_hi is not None or tp_me is not None or tp_lo is not None:
        if target_panel.get("source"):
            target_source = str(target_panel.get("source"))
        elif ai_hi_val is not None or ai_me_val is not None or ai_lo_val is not None:
            target_source = "法人目標價面板同源：AI/法人聯網 target_price_high-target_price_avg-target_price_low"
        else:
            target_source = "系統/info 法人目標價備援：targetHighPrice-targetMeanPrice-targetLowPrice"
    else:
        target_source = "無可用法人目標價"

    target_confidence = classify_target_price_confidence(analyst_count)
    target_rationale = target_panel.get("rationale") or ai_fin.get("target_price_rationale") or ""
    target_confidence_report = build_target_price_confidence_report(analyst_count, tp_hi, tp_me, tp_lo, target_rationale)

    return {
        "target_panel": target_panel,
        "tp_hi": tp_hi,
        "tp_me": tp_me,
        "tp_lo": tp_lo,
        "prompt_hi_str": f"{tp_hi:.1f}" if tp_hi is not None else "N/A",
        "prompt_me_str": f"{tp_me:.1f}" if tp_me is not None else "N/A",
        "prompt_lo_str": f"{tp_lo:.1f}" if tp_lo is not None else "N/A",
        "prompt_analyst_count": analyst_count,
        "prompt_target_source": target_source,
        "prompt_target_confidence": target_confidence,
        "prompt_target_rationale": target_rationale,
        "target_confidence_report_for_prompt": target_confidence_report,
    }


def prompt_quality_summary(df):
    """Summarize important quality rows instead of packing the full table."""
    try:
        if df is None or getattr(df, "empty", True):
            return "NULL"
        cols = list(df.columns)
        field_col = next((c for c in cols if "欄位" in str(c) or "項目" in str(c)), cols[0])
        adopted_col = next((c for c in cols if "採用" in str(c) and ("值" in str(c) or "來源" in str(c))), None)
        status_col = next((c for c in cols if "品質" in str(c) or "狀態" in str(c)), None)
        note_col = next((c for c in cols if "備註" in str(c) or "警告" in str(c) or "說明" in str(c)), None)
        rows = []
        important_fields = ["P/E", "Forward", "PEG", "P/B", "EPS", "營收", "YoY", "MoM", "毛利", "營益", "ROE", "D/E", "目標價"]
        for _, row in df.iterrows():
            field = prompt_nullize_text(row.get(field_col, ""))
            row_text = " ".join([prompt_nullize_text(row.get(c, "")) for c in cols])
            is_important = any(keyword.lower() in row_text.lower() for keyword in important_fields)
            is_abnormal = any(keyword in row_text for keyword in ["異常", "分歧", "校正", "過期", "警告"])
            adopted_text = prompt_nullize_text(row.get(adopted_col, "")) if adopted_col else "NULL"
            status_text = prompt_nullize_text(row.get(status_col, "")) if status_col else ""
            if adopted_col and adopted_text == "NULL" and not is_abnormal:
                continue
            if any(keyword in status_text for keyword in ["❌", "缺資料", "無可用資料"]):
                continue
            if is_important or is_abnormal:
                parts = [f"欄位={field}"]
                if adopted_col:
                    parts.append(f"採用={adopted_text}")
                if status_col and status_text != "NULL":
                    parts.append(f"狀態={status_text}")
                if note_col:
                    note = prompt_nullize_text(row.get(note_col, ""))
                    if note != "NULL":
                        parts.append(f"備註={note}")
                rows.append("- " + "；".join(parts))
            if len(rows) >= 14:
                break
        return "\n".join(rows) if rows else prompt_df(df, max_rows=8)
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_quality_summary", exc)
        except Exception:
            pass
        return "NULL"


def prompt_ai_source_summary(df):
    """Summarize adopted/divergent/valuation-critical AI source rows."""
    try:
        if df is None or getattr(df, "empty", True):
            return "NULL"
        keywords = ["eps", "forward", "gross", "margin", "roe", "debt", "d/e", "revenue", "yoy", "target", "price", "毛利", "營益", "目標", "負債", "營收", "分歧", "校正", "採用"]
        blocked_field_codes = {"trailing_eps", "forward_eps", "forward_eps_system", "forward_eps_fy1_year", "forward_eps_fy2_year", "forward_eps_fy3_year"}
        blocked_name_tokens = ["legacy"]
        keep = []
        for _, row in df.iterrows():
            field_code = prompt_nullize_text(row.get("欄位代碼", row.get("field", row.get("code", "")))).strip()
            field_name = prompt_nullize_text(row.get("欄位名稱", row.get("name", ""))).strip()
            if field_code in blocked_field_codes or any(token.lower() in field_name.lower() for token in blocked_name_tokens):
                continue
            row_text = " ".join([prompt_nullize_text(row.get(c, "")) for c in df.columns])
            if any(keyword.lower() in row_text.lower() for keyword in keywords):
                parts = []
                for col in df.columns:
                    value = prompt_nullize_text(row.get(col, ""))
                    if value != "NULL":
                        parts.append(f"{col}={value}")
                if parts:
                    keep.append("- " + "；".join(parts))
            if len(keep) >= 12:
                break
        return "\n".join(keep) if keep else "NULL"
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_ai_source_summary", exc)
        except Exception:
            pass
        return "NULL"


def prompt_field_source_priority_summary(fields=None, max_rows=18):
    """Format the field-level source priority table for prompt packs."""
    try:
        return format_field_source_priority_for_prompt(fields, max_rows=max_rows)
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_field_source_priority_summary", exc)
        except Exception:
            pass
        return "NULL"


def prompt_m10_margin_benchmark_summary(pack_or_summary=None, mode="compact"):
    """Format M10 margin benchmark status for prompt packs."""
    try:
        source = pack_or_summary if isinstance(pack_or_summary, dict) else {}
        summary = source.get("m10_margin_benchmark") if isinstance(source.get("m10_margin_benchmark"), dict) else source
        if not isinstance(summary, dict):
            return "NULL"

        def _fmt_pct(v):
            x = s_float(v)
            if x is None:
                return "NULL"
            if abs(x) <= 3:
                x *= 100
            return f"{x:.1f}%"

        if not summary.get("available"):
            return "- M10 margin benchmark: 未建立；Dynamic Cap 沿用既有產業品質係數設定。"

        line = (
            "- M10 margin benchmark: "
            f"狀態={prompt_nullize_text(summary.get('status_label'))}；"
            f"分類={prompt_nullize_text(summary.get('category_name'))}；"
            f"品質={prompt_nullize_text(summary.get('margin_quality'))}；"
            f"規則={prompt_nullize_text(summary.get('margin_rule_label'))}；"
            f"毛利率base/low/high={_fmt_pct(summary.get('base_gross_margin_pct'))}/{_fmt_pct(summary.get('gross_margin_low_pct'))}/{_fmt_pct(summary.get('gross_margin_high_pct'))}；"
            f"營益率base/low/high={_fmt_pct(summary.get('base_operating_margin_pct'))}/{_fmt_pct(summary.get('operating_margin_low_pct'))}/{_fmt_pct(summary.get('operating_margin_high_pct'))}；"
            f"估值用途={prompt_nullize_text(summary.get('usage_label'))}"
        )
        if str(mode).lower() in {"decision", "buy", "compact"}:
            return line

        lines = [line]
        if prompt_nullize_text(summary.get("margin_reference_stocks")) != "NULL":
            lines.append(f"- M10 margin 參考公司: {prompt_nullize_text(summary.get('margin_reference_stocks'))}")
        if prompt_nullize_text(summary.get("margin_model_usage")) != "NULL":
            lines.append(f"- M10 margin 使用說明: {prompt_nullize_text(summary.get('margin_model_usage'))}")
        if prompt_nullize_text(summary.get("warning")) != "NULL":
            lines.append(f"- M10 margin 提醒: {prompt_nullize_text(summary.get('warning'))}")
        return "\n".join(lines)
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_m10_margin_benchmark_summary", exc)
        except Exception:
            pass
        return "NULL"


def prompt_dynamic_cap_core(pack, mode="research", divergence_warnings=None, final_signal=None, fallback_values=None):
    """Format Dynamic Cap inputs for prompt packs without leaking raw dictionaries."""
    try:
        if not isinstance(pack, dict):
            return "NULL"

        fallback_values = fallback_values if isinstance(fallback_values, dict) else {}

        def _sf2(v):
            try:
                return s_float(v)
            except Exception:
                return None

        def _fmt_num(v, digits=2):
            x = _sf2(v)
            return "NULL" if x is None else f"{x:.{digits}f}"

        def _fmt_x(v, digits=1):
            x = _sf2(v)
            return "NULL" if x is None else f"{x:.{digits}f}x"

        def _fmt_pct(v, digits=1):
            x = _sf2(v)
            if x is None:
                return "NULL"
            if abs(x) <= 3:
                x *= 100
            return f"{x:.{digits}f}%"

        def _fmt_money(v):
            x = _sf2(v)
            if x is None:
                return "NULL"
            ax = abs(x)
            if ax >= 1_000_000_000_000:
                return f"約 {x/1_000_000_000_000:.2f} 兆"
            if ax >= 100_000_000:
                return f"約 {x/100_000_000:.1f} 億"
            return f"{x:,.0f}"

        def _fmt_factor(raw):
            if isinstance(raw, dict):
                factor = _fmt_num(raw.get("factor"), 2)
                label = prompt_nullize_text(raw.get("label"))
                reason = prompt_nullize_text(raw.get("reason"))
                avg_lots = _sf2(raw.get("avg_lots"))
                parts = []
                if factor != "NULL":
                    parts.append(f"×{factor}")
                if label != "NULL":
                    parts.append(label)
                if avg_lots is not None:
                    parts.append(f"近20日均量約 {avg_lots:,.0f} 張")
                if reason != "NULL":
                    parts.append(f"原因: {reason}")
                return "；".join(parts) if parts else "NULL"
            x = _sf2(raw)
            return "NULL" if x is None else f"×{x:.2f}"

        def _fmt_list(v):
            if isinstance(v, (list, tuple, set)):
                vals = [prompt_nullize_text(x) for x in v if prompt_nullize_text(x) != "NULL"]
                return "；".join(vals) if vals else "無"
            t = prompt_nullize_text(v)
            if t in ("NULL", "[]"):
                return "無"
            return t

        def _get_input(inp, key, fallback=None):
            if isinstance(inp, dict) and key in inp and prompt_nullize_text(inp.get(key)) != "NULL":
                return inp.get(key)
            return fallback

        cap_inputs = pack.get("cap_inputs") if isinstance(pack.get("cap_inputs"), dict) else {}
        warnings = _fmt_list(pack.get("warnings"))
        notes = _fmt_list(pack.get("cap_adoption_notes"))
        try:
            actual_divergence_count = len(divergence_warnings) if isinstance(divergence_warnings, list) else 0
        except Exception:
            actual_divergence_count = 0
        try:
            is_data_abnormal_signal = isinstance(final_signal, dict) and str(final_signal.get("signal", "")).strip().startswith("資料異常")
        except Exception:
            is_data_abnormal_signal = False

        valuation_mode = prompt_nullize_text(pack.get("valuation_mode"))
        model_version = prompt_nullize_text(pack.get("model_version"))
        cap_eps_basis = prompt_nullize_text(pack.get("cap_eps_basis"))
        v18_engine = prompt_nullize_text(pack.get("v18_2_engine"))
        v18_status = prompt_nullize_text(pack.get("v18_2_status"))
        base_multiple = _fmt_x(pack.get("base_multiple"), 1)
        op_low = _fmt_x(pack.get("operable_cap_low"), 1)
        op_high = _fmt_x(pack.get("operable_cap_high"), 1)
        final_cap = _fmt_x(pack.get("final_cap"), 1)
        formula_cap = _fmt_x(pack.get("formula_cap"), 1)
        optimistic_cap = _fmt_x(pack.get("optimistic_cap"), 1)
        hard_cap = _fmt_x(pack.get("hard_ceiling_cap"), 1)

        ttm_eps = _get_input(cap_inputs, "ttm_eps", fallback_values.get("eff_t_eps"))
        sys_feps = _get_input(cap_inputs, "system_forward_eps", fallback_values.get("sys_forward_eps_system"))
        ai_feps = _get_input(cap_inputs, "ai_forward_eps", fallback_values.get("ai_f_eps_calc"))
        adopted_eps = _get_input(cap_inputs, "adopted_valuation_forward_eps", fallback_values.get("cap_adopted_forward_eps"))
        fy1_eps = _get_input(cap_inputs, "adopted_fy1_eps", fallback_values.get("ai_forward_eps_fy1"))
        fy2_eps = _get_input(cap_inputs, "adopted_fy2_eps", fallback_values.get("ai_forward_eps_fy2"))
        fy3_eps = _get_input(cap_inputs, "adopted_fy3_eps", fallback_values.get("ai_forward_eps_fy3"))
        fy1_year = _get_input(cap_inputs, "fy1_year", fallback_values.get("ai_forward_eps_fy1_year"))
        fy2_year = _get_input(cap_inputs, "fy2_year", fallback_values.get("ai_forward_eps_fy2_year"))
        fy3_year = _get_input(cap_inputs, "fy3_year", fallback_values.get("ai_forward_eps_fy3_year"))
        fy_note = _get_input(cap_inputs, "fy_eps_source_note", fallback_values.get("ai_forward_eps_fy_source_note"))

        gm = _get_input(cap_inputs, "gross_margin")
        om = _get_input(cap_inputs, "operating_margin")
        roe = _get_input(cap_inputs, "roe")
        de = _get_input(cap_inputs, "debt_to_equity")
        rev_yoy = _get_input(cap_inputs, "revenue_yoy")
        fcf = _get_input(cap_inputs, "free_cash_flow")

        lines = []
        if valuation_mode != "NULL":
            lines.append(f"- 使用模型: {valuation_mode}")
        if model_version != "NULL":
            lines.append(f"- 模型版本: {model_version}")
        if v18_engine != "NULL" or v18_status != "NULL":
            lines.append(f"- v18.2 引擎 / 狀態: {v18_engine} / {v18_status}")
        if cap_eps_basis != "NULL":
            lines.append(f"- v18.2 EPS 適用口徑: {cap_eps_basis}")
        if base_multiple != "NULL":
            lines.append(f"- Company Base 倍率: {base_multiple}")
        if op_low != "NULL" or op_high != "NULL":
            lines.append(f"- 可操作倍率區間: {op_low} ～ {op_high}")
        if final_cap != "NULL":
            lines.append(f"- 中性可操作倍率: {final_cap}")
        if formula_cap != "NULL":
            lines.append(f"- 公式合理倍率: {formula_cap}（模型理論估值，不等於買點）")
        if optimistic_cap != "NULL":
            lines.append(f"- 樂觀情境倍率: {optimistic_cap}（高風險情境，不等於買點）")
        if hard_cap != "NULL":
            lines.append(f"- hard ceiling: {hard_cap}（強制估值上限，不可因股價上漲直接調高）")
        m10_margin_text = prompt_m10_margin_benchmark_summary(pack, mode=mode)
        if m10_margin_text != "NULL":
            lines.append(m10_margin_text)

        discount_parts = []
        for label, key in [
            ("資料可信度", "data_confidence_factor"),
            ("估值風險", "valuation_risk_factor"),
            ("流動性", "liquidity_factor"),
        ]:
            txt = _fmt_factor(pack.get(key))
            if txt != "NULL":
                if label == "資料可信度" and actual_divergence_count > 0:
                    try:
                        txt = re.sub(r"分歧警告\s*\d+\s*項", f"分歧警告 {actual_divergence_count} 項", txt)
                    except Exception:
                        pass
                    if "分歧警告" not in txt:
                        txt = f"{txt}；原因: 分歧警告 {actual_divergence_count} 項"
                discount_parts.append(f"{label} {txt}")
        if discount_parts:
            lines.append("- 折扣摘要: " + "；".join(discount_parts))
        if actual_divergence_count > 0:
            lines.append(f"- 資料分歧同步: 分歧警告 {actual_divergence_count} 項，已與【5. 分歧與資料品質】同步；Dynamic Cap 與可操作區間需降權解讀。")
        if is_data_abnormal_signal:
            lines.append("- 資料異常-不可判斷保護: 最終燈號為資料異常-不可判斷，本區只保留壓力測試與風險提示，不作買賣判斷。")

        eps_parts = []
        if _fmt_num(adopted_eps, 2) != "NULL":
            eps_parts.append(f"Dynamic Cap 採用估值 EPS={_fmt_num(adopted_eps, 2)}")
        if _fmt_num(ttm_eps, 2) != "NULL":
            eps_parts.append(f"TTM EPS={_fmt_num(ttm_eps, 2)}")
        if _fmt_num(sys_feps, 2) != "NULL":
            eps_parts.append(f"系統 Forward EPS={_fmt_num(sys_feps, 2)}")
        if _fmt_num(ai_feps, 2) != "NULL":
            eps_parts.append(f"AI/法人 Forward EPS={_fmt_num(ai_feps, 2)}")
        if eps_parts:
            lines.append("- EPS 採用摘要: " + "；".join(eps_parts))
        if any(_fmt_num(v, 2) != "NULL" for v in [fy1_eps, fy2_eps, fy3_eps]):
            lines.append(f"- FY1 / FY2 / FY3 EPS: {_fmt_num(fy1_eps, 2)} / {_fmt_num(fy2_eps, 2)} / {_fmt_num(fy3_eps, 2)}")
        if any(prompt_nullize_text(v) != "NULL" for v in [fy1_year, fy2_year, fy3_year]):
            lines.append(f"- FY 年度: {prompt_nullize_text(fy1_year)} / {prompt_nullize_text(fy2_year)} / {prompt_nullize_text(fy3_year)}")
        if prompt_nullize_text(fy_note) != "NULL":
            lines.append(f"- EPS 來源說明: {prompt_nullize_text(fy_note)}")
        if notes != "無":
            lines.append(f"- AI校對採用紀錄: {notes}")
        if warnings != "無":
            lines.append(f"- 模型警告: {warnings}")
        lines.append("- 使用限制: v18.2 倍率不回退舊版，市場熱度不上修 Hard；TTM-only 不得乘 FY1/FY2/FY3；公式、soft/hard 情境都不是買點。")

        if str(mode).lower() in {"decision", "buy", "compact"}:
            return "\n".join(lines) if lines else "NULL"

        research_lines = list(lines)
        factor_parts = []
        if _fmt_pct(gm) != "NULL":
            factor_parts.append(f"毛利率 {_fmt_pct(gm)}")
        if _fmt_pct(om) != "NULL":
            factor_parts.append(f"營益率 {_fmt_pct(om)}")
        if _fmt_pct(roe) != "NULL":
            factor_parts.append(f"ROE {_fmt_pct(roe)}")
        if _fmt_num(de, 2) != "NULL":
            factor_parts.append(f"D/E {_fmt_num(de, 2)}")
        if factor_parts:
            research_lines.append("\n【9-1. Dynamic Cap 採用品質/風險因子】")
            research_lines.append("- " + "；".join(factor_parts))
        growth_parts = []
        if _fmt_pct(rev_yoy) != "NULL":
            growth_parts.append(f"營收 YoY {_fmt_pct(rev_yoy)}")
        if _fmt_money(fcf) != "NULL":
            growth_parts.append(f"FCF {_fmt_money(fcf)}")
        if growth_parts:
            research_lines.append("\n【9-2. Dynamic Cap 採用成長/現金流因子】")
            research_lines.append("- " + "；".join(growth_parts))
        research_lines.append("\n【9-3. EPS 採用規則】")
        if str(pack.get("cap_eps_basis") or "") == "ttm_only":
            research_lines.append("- v18.2 TTM-only：只能使用 TTM EPS；FY1/FY2/FY3 估值全部停用。")
        else:
            research_lines.append("- v18.2 前瞻倍率只能搭配同年度 FY1 EPS；FY2/FY3 僅保留為不套用倍率的財報序列資料。")
        return "\n".join(research_lines) if research_lines else "NULL"
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_dynamic_cap_core", exc)
        except Exception:
            pass
        return "NULL"


def prompt_forward_eps_tier_core(pack):
    """Format Forward EPS year-tier valuation summary for prompt packs."""
    try:
        if not isinstance(pack, dict):
            return "NULL"
        summary = pack.get("summary", {}) or {}
        report = pack.get("report")

        def _fmt_price(v):
            x = s_float(v)
            return "NULL" if x is None else f"{x:.1f}元"

        def _fmt_cap(v):
            x = s_float(v)
            return "NULL" if x is None else f"{x:.1f}x"

        lines = [
            f"- FY 定義: {prompt_nullize_text(summary.get('fy_definition'))}",
            f"- FY 年度提示: {prompt_nullize_text(summary.get('fy_sequence_text'))}",
            f"- 目前月份/FY2參考提示: {prompt_nullize_text(summary.get('fy_calendar_prompt_notice'))}",
            f"- 年度估值倍率 base / soft / hard: {_fmt_cap(summary.get('base_cap'))} / {_fmt_cap(summary.get('soft_cap'))} / {_fmt_cap(summary.get('hard_cap'))}",
            f"- 倍率意義: {prompt_nullize_text(summary.get('cap_definition'))}",
            f"- TTM EPS: {prompt_nullize_text(summary.get('ttm_eps'))}｜近四季已實現 EPS，用於目前實際獲利估值",
            f"- FY1 EPS: {prompt_nullize_text(summary.get('fy1_eps'))}｜{prompt_nullize_text(summary.get('fy1_label'))}",
            f"- FY2 EPS: {prompt_nullize_text(summary.get('fy2_eps'))}｜{prompt_nullize_text(summary.get('fy2_label'))}",
            f"- FY3 EPS: {prompt_nullize_text(summary.get('fy3_eps'))}｜{prompt_nullize_text(summary.get('fy3_label'))}",
            f"- EPS 年份/期間: 近四季 / {prompt_nullize_text(summary.get('fy1_year'))} / {prompt_nullize_text(summary.get('fy2_year'))} / {prompt_nullize_text(summary.get('fy3_year'))}",
            f"- EPS 年期基準: {prompt_nullize_text(summary.get('eps_basis'))}",
            f"- EPS 來源備註: {prompt_nullize_text(summary.get('eps_source_note'))}",
            f"- 現價隱含 P/E（TTM/FY1/FY2/FY3）: {prompt_nullize_text(summary.get('market_pe_ttm'))}x / {prompt_nullize_text(summary.get('market_pe_fy1'))}x / {prompt_nullize_text(summary.get('market_pe_fy2'))}x / {prompt_nullize_text(summary.get('market_pe_fy3'))}x",
            f"- 市場 EPS 年期判讀: {prompt_nullize_text(summary.get('market_view'))}",
            f"- 市場定價年期 pricing_horizon: {prompt_nullize_text(summary.get('pricing_horizon_label'))}｜code={prompt_nullize_text(summary.get('pricing_horizon_code'))}｜{prompt_nullize_text(summary.get('pricing_horizon_explanation'))}",
            f"- 定價年期操作規則: {prompt_nullize_text(summary.get('pricing_horizon_decision_rule'))}",
            f"- 未來證據落地 future_evidence_score: {prompt_nullize_text(summary.get('future_evidence_score'))}｜{prompt_nullize_text(summary.get('future_evidence_label'))}｜{prompt_nullize_text(summary.get('future_evidence_action'))}",
        ]
        if report is not None and not getattr(report, "empty", True):
            for label in ["FY1", "FY2", "FY3"]:
                try:
                    mask = report["EPS口徑"].astype(str).str.contains(label, na=False)
                    if mask.any():
                        row = report[mask].iloc[0]
                        lines.append(
                            f"- {label} base/soft/hard 估值: "
                            f"{_fmt_price(row.get('基礎估值'))} / {_fmt_price(row.get('樂觀估值'))} / {_fmt_price(row.get('極限估值'))}"
                        )
                except Exception:
                    pass
        lines.extend([
            "- 請 AI 判斷：目前股價/法人目標價偏高，是因為 Dynamic Cap 倍率太低，還是因為市場已經在看 FY2/FY3 EPS？也請同時對照 TTM EPS，看目前實際獲利是否能支撐股價。",
            "- 重要限制：FY1/FY2/FY3 是預估年度 EPS 序列，不是查詢日後1/2/3年；base 是基礎估值，soft 是樂觀估值，hard 是極限風控上限；FY1_SOFT_PRICED 代表 FY1 樂觀區，不代表必須用 FY2 EPS 才能解釋；FY2 只能用來解釋市場先行，不等於可操作買點；FY3 屬高風險遠期情境，不可直接作為買進目標。",
            "- 新增規則：若 pricing_horizon 為 FY2/FY3/題材重評價，請同時檢查 future_evidence_score；證據不足時不得用 FY2/FY3 支撐買進，證據高時也只能解讀為小部位或低成本既有部位續抱。"
        ])
        return "\n".join(lines)
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_forward_eps_tier_core", exc)
        except Exception:
            pass
        return "NULL"


def prompt_peg_valuation_layers(
    system_eps=None,
    system_eps_raw=None,
    fy1_eps=None,
    fy2_eps=None,
    fy3_eps=None,
    fy1_year=None,
    fy2_year=None,
    fy3_year=None,
    fy1_eps_for_annual=None,
    formula_cap=None,
    base_cap=None,
    soft_cap=None,
    hard_cap=None,
    manual_cap=None,
    manual_cap_source=None,
    system_price=None,
    system_raw_price=None,
    formula_eps_source=None,
    forward_eps_mismatch_note=None,
    current_eps=None,
    current_eps_raw=None,
    current_eps_source=None,
    current_eps_formula_note=None,
    current_eps_period=None,
    current_price=None,
    run_rate_1q_eps=None,
    run_rate_2q_eps=None,
    run_rate_reference_eps=None,
    run_rate_1q_price=None,
    run_rate_2q_price=None,
    run_rate_reference_price=None,
    run_rate_label=None,
    run_rate_action=None,
    fy1_base_price=None,
    fy1_soft_price=None,
    fy1_hard_price=None,
    fy2_base_price=None,
    fy2_soft_price=None,
    fy2_hard_price=None,
    fy3_base_price=None,
    fy3_soft_price=None,
    fy3_hard_price=None,
    manual_price=None,
    current_date=None,
    fallback_text="",
):
    """Format Forward PEG valuation layers for prompt packs."""
    try:
        def _price(v):
            x = s_float(v)
            return "NULL" if x is None else f"{x:.1f}元"

        def _eps(v):
            x = s_float(v)
            return "NULL" if x is None else f"{x:.2f}"

        def _cap(v):
            x = s_float(v)
            return "NULL" if x is None else f"{x:.1f}x"

        def _year(v):
            t = prompt_nullize_text(v)
            return "年期未明" if t == "NULL" else t

        fy_calendar_notice = build_forward_eps_calendar_notice(
            current_date=current_date,
            fy1_year=fy1_year,
            fy2_year=fy2_year,
            fy3_year=fy3_year,
        )
        lines = []
        source_text = prompt_nullize_text(formula_eps_source or "系統 Forward EPS")
        mismatch_note = prompt_nullize_text(forward_eps_mismatch_note)
        raw_parts = []
        if _eps(system_eps_raw) != "NULL":
            raw_parts.append(f"系統原始EPS={_eps(system_eps_raw)}")
        if _price(system_raw_price) != "NULL":
            raw_parts.append(f"系統原始公式價={_price(system_raw_price)}")
        if mismatch_note != "NULL":
            raw_parts.append(f"年期判讀={mismatch_note}")
        raw_text = "｜" + "｜".join(raw_parts) if raw_parts else ""
        lines.append(f"- 1. 公式合理估值: {_price(system_price)}｜{source_text} × formula cap｜EPS={_eps(system_eps)}｜倍率={_cap(formula_cap)}{raw_text}｜判讀=若系統 Forward EPS 疑似 FY2 年期錯位，公式價降權採 FY1 EPS；FY2 只作市場先行定價，不直接作買點。")
        lines.append(
            f"- 1-1. 目前估值: {_price(current_price)}｜{prompt_nullize_text(current_eps_source or '目前 EPS')} × formula cap"
            f"｜EPS={_eps(current_eps)}｜原始EPS={_eps(current_eps_raw)}｜計算={prompt_nullize_text(current_eps_formula_note)}｜期間={prompt_nullize_text(current_eps_period)}"
            "｜判讀=用已抓到的最新單季年化 EPS 或 TTM EPS 檢查目前實際獲利支撐度，不代表 Forward 合理價。"
        )
        if any(_eps(v) != "NULL" for v in [run_rate_1q_eps, run_rate_2q_eps, run_rate_reference_eps]):
            lines.append(
                f"- 1-2. Run-rate EPS 動能估值: {_price(run_rate_reference_price)}"
                f"｜近二季年化EPS={_eps(run_rate_2q_eps)} / 近一季年化EPS={_eps(run_rate_1q_eps)}"
                f"｜參考EPS={_eps(run_rate_reference_eps)}｜近二季/近一季估值={_price(run_rate_2q_price)} / {_price(run_rate_1q_price)}"
                f"｜判讀={prompt_nullize_text(run_rate_label)}；{prompt_nullize_text(run_rate_action)}"
                "｜限制=只作 AI 高成長股獲利動能檢查，不取代 TTM、FY1 或 FY2。"
            )
        lines.append(f"- 年度情境倍率: base={_cap(base_cap)}（基礎） / soft={_cap(soft_cap)}（樂觀） / hard={_cap(hard_cap)}（極限風控上限）")
        lines.append(f"- FY 年度提示: {prompt_nullize_text(fy_calendar_notice.get('fy_sequence_text'))}")
        lines.append(f"- 目前月份/FY2參考提示: {prompt_nullize_text(fy_calendar_notice.get('prompt_notice'))}")

        for title, eps, year, base_price, soft_price, hard_price, note in [
            ("2. FY1年度估值", fy1_eps, fy1_year, fy1_base_price, fy1_soft_price, fy1_hard_price, "一年預估 EPS 的年度主估值參考。"),
            ("3. FY2第二年度估值", fy2_eps, fy2_year, fy2_base_price, fy2_soft_price, fy2_hard_price, "只用於判斷市場是否提前反映第二年獲利，不直接當買點。"),
            ("4. FY3第三年度估值", fy3_eps, fy3_year, fy3_base_price, fy3_soft_price, fy3_hard_price, "高風險遠期情境，需多家法人共識或人工確認，不可直接當買進目標。"),
        ]:
            lines.append(
                f"- {title}: base/soft/hard={_price(base_price)} / {_price(soft_price)} / {_price(hard_price)}"
                f"｜EPS={_eps(eps)}｜年度={_year(year)}｜判讀={note}"
            )
        lines.append(f"- 5. 手動年度情境價: {_price(manual_price)}｜FY1 EPS × {prompt_nullize_text(manual_cap_source or '使用者手動 Cap')}｜EPS={_eps(fy1_eps_for_annual)}｜倍率={_cap(manual_cap)}｜判讀=壓力測試/反推現價倍率；不代表系統建議買點。")
        lines.append("- 使用規則: 前瞻 PEG 面板不再單列 AI估值，避免與 FY1 年度估值重複；AI/法人 EPS 留在 EPS 來源與 FY 年度層。FY2 只解釋市場先行定價；FY3 是高風險遠期情境；hard 是極限風控上限，不是買進目標。7 月後需同步參考 FY2；10 月後 FY2 可作主要前瞻參考，但不得無條件支撐買進。")
        return "\n".join(lines)
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_peg_valuation_layers", exc)
        except Exception:
            pass
        return prompt_nullize_text(fallback_text)


def _prompt_audit_clean(value, default="無"):
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    if isinstance(value, (list, tuple, set)):
        vals = [str(x).strip() for x in value if str(x).strip() and str(x).strip().upper() not in {"NULL", "NONE", "N/A"}]
        return "、".join(vals) if vals else default
    text = str(value).strip()
    return default if text == "" or text.upper() in {"NULL", "NONE", "N/A", "—", "[]"} else text


def prompt_snapshot_audit_summary(
    audit,
    industry_profile=None,
    dynamic_cap_pack=None,
    market_implied_pe_val=None,
    target_avg_implied_pe_val=None,
    target_high_implied_pe_val=None,
    final_signal=None,
    divergence_warnings=None,
):
    """Format compact industry-model audit summary for decision prompt packs."""
    try:
        if not isinstance(audit, dict):
            return "- 本次無產業模型稽核資料。"
        summary = audit.get("summary", {}) or {}
        dynamic_cap_pack = dynamic_cap_pack or {}

        def _x(v):
            n = s_float(v)
            return "無" if n is None else f"{n:.1f}x"

        def _line(label, value):
            value = _prompt_audit_clean(value)
            return None if value == "無" else f"- {label}: {value}"

        positives = _prompt_audit_clean(summary.get("positives"))
        negatives = _prompt_audit_clean(summary.get("negatives"))
        try:
            is_data_abnormal_signal = isinstance(final_signal, dict) and str(final_signal.get("signal", "")).strip().startswith("資料異常")
        except Exception:
            is_data_abnormal_signal = False
        try:
            actual_divergence_count = len(divergence_warnings) if isinstance(divergence_warnings, list) else 0
        except Exception:
            actual_divergence_count = 0
        if is_data_abnormal_signal:
            return "\n".join([
                "- 稽核結果: 資料異常-不可判斷，暫不判斷模型是否偏離。",
                "- 稽核分數: 暫停判斷",
                f"- 系統建議動作: 先確認 EPS、Forward P/E、PEG、毛利率、ROE、營收 YoY 等口徑；目前分歧警告 {actual_divergence_count} 項，暫不做買賣判斷。",
                f"- 目前 primary_taxon: {_prompt_audit_clean(summary.get('primary_taxon'))}",
                "- 風險/反對因素: 資料異常-不可判斷優先，Dynamic Cap 與產業模型只作壓力測試。",
                "- 重要限制: 資料異常-不可判斷時，不可因模型估值或法人目標價偏高而直接追價。",
            ])

        lines = []
        for item in [
            _line("稽核結果", summary.get("audit_label")),
            _line("稽核分數", summary.get("audit_score")),
            _line("系統建議動作", summary.get("action")),
            _line("目前 primary_taxon", summary.get("primary_taxon")),
        ]:
            if item:
                lines.append(item)

        hard = dynamic_cap_pack.get("hard_ceiling_cap") if isinstance(dynamic_cap_pack, dict) else None
        if s_float(hard) is not None:
            lines.append(f"- 系統 hard ceiling: {_x(hard)}")

        implied_parts = []
        if s_float(market_implied_pe_val) is not None:
            implied_parts.append(f"現價 {_x(market_implied_pe_val)}")
        if s_float(target_avg_implied_pe_val) is not None:
            implied_parts.append(f"法人均價 {_x(target_avg_implied_pe_val)}")
        if s_float(target_high_implied_pe_val) is not None:
            implied_parts.append(f"法人高標 {_x(target_high_implied_pe_val)}")
        if implied_parts:
            lines.append("- 現價 / 法人均價 / 法人高標隱含 Forward P/E: " + " / ".join(implied_parts))

        lines.append(f"- 正面支持因素: {positives}")
        lines.append(f"- 風險/反對因素: {negatives}")
        lines.append("- 重要限制: 本區僅供模型是否失準之輔助判斷，不可因現價或法人目標價接近/高於 hard ceiling 就直接調高模型，也不可直接作為買進依據。")
        return "\n".join(lines)
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_snapshot_audit_summary", exc)
        except Exception:
            pass
        return "- 產業模型稽核摘要產生失敗。"


def prompt_snapshot_audit_core(
    audit,
    industry_profile=None,
    dynamic_cap_pack=None,
    market_implied_pe_val=None,
    target_avg_implied_pe_val=None,
    target_high_implied_pe_val=None,
):
    """Format full industry-model snapshot audit for research prompt packs."""
    try:
        if not isinstance(audit, dict):
            return "- 本次無產業模型稽核資料。"
        summary = audit.get("summary", {}) or {}
        profile = industry_profile or {}
        dynamic_cap_pack = dynamic_cap_pack or {}

        def _x(v):
            n = s_float(v)
            return "無" if n is None else f"{n:.1f}x"

        built_at = _prompt_audit_clean(summary.get("model_built_at"))
        version = _prompt_audit_clean(profile.get("model_build_version"))
        if built_at != "無" and version != "無":
            build_text = f"{built_at} / {version}"
        elif built_at != "無":
            build_text = built_at
        elif version != "無":
            build_text = version
        else:
            build_text = "無"

        lines = []
        for label, value in [
            ("稽核結果", summary.get("audit_label")),
            ("稽核分數", summary.get("audit_score")),
            ("系統建議動作", summary.get("action")),
            ("產業模型建置時間 / 版本", build_text),
            ("目前 primary_taxon", summary.get("primary_taxon")),
            ("目前 hybrid_taxons", summary.get("hybrid_taxons")),
            ("混合後 base / floor / soft / hard", summary.get("mixed_caps")),
        ]:
            value = _prompt_audit_clean(value)
            if value != "無":
                lines.append(f"- {label}: {value}")

        if s_float(market_implied_pe_val) is not None:
            lines.append(f"- 現價隱含 Forward P/E: {_x(market_implied_pe_val)}")
        if s_float(target_avg_implied_pe_val) is not None:
            lines.append(f"- 法人均價隱含 Forward P/E: {_x(target_avg_implied_pe_val)}")
        if s_float(target_high_implied_pe_val) is not None:
            lines.append(f"- 法人高標隱含 Forward P/E: {_x(target_high_implied_pe_val)}")
        hard = dynamic_cap_pack.get("hard_ceiling_cap") if isinstance(dynamic_cap_pack, dict) else None
        if s_float(hard) is not None:
            lines.append(f"- 系統 hard ceiling: {_x(hard)}")

        lines.append(f"- 正面支持因素: {_prompt_audit_clean(summary.get('positives'))}")
        lines.append(f"- 風險/反對因素: {_prompt_audit_clean(summary.get('negatives'))}")
        history_note = _prompt_audit_clean(summary.get("history_note"))
        if history_note != "無":
            lines.append(f"- 歷史紀錄狀態: {history_note}")
        else:
            lines.append("- 歷史紀錄狀態: 目前未啟用歷史紀錄，本表僅為本次快照稽核，不能判斷連續幾次或長期重估。")

        lines.extend([
            "",
            "請 AI 判斷這次差異屬於下列哪一類：",
            "1. 市場短線過熱",
            "2. 法人目標價過度樂觀",
            "3. EPS / 營收 / 毛利率尚未落地",
            "4. hybrid 權重可能偏低",
            "5. primary_taxon 可能已不符合公司營運型態",
            "6. 整個產業 base / soft / hard ceiling 可能需要重新校準",
            "",
            "請 AI 僅能從下列 5 種回答模型更新建議：",
            "- 不建議更新模型",
            "- 暫時觀察",
            "- 建議檢查 hybrid 權重",
            "- 建議檢查 primary_taxon",
            "- 建議檢查整個產業倍率",
            "",
            "重要限制：",
            "- 單次快照不能當成長期重估證據。",
            "- 不可因現價高於 hard ceiling 就直接調高模型。",
            "- 若要正式更新模型，必須說明要改 primary_taxon、hybrid_taxons 或 base/soft/hard。",
            "- 更新依據必須來自 EPS、營收、毛利率、法人共識或產業結構變化，而不是單純股價上漲。",
        ])
        return "\n".join(lines)
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_snapshot_audit_core", exc)
        except Exception:
            pass
        return "- 產業模型稽核內容產生失敗。"


def prompt_eps_adoption_sync_summary(
    sys_latest_quarter_eps_val=None,
    ai_latest_month_eps_val=None,
    ai_latest_quarter_eps_val=None,
    raw_ai_period_val=None,
    sys_ttm_eps_val=None,
    ai_ttm_eps_val=None,
    eff_t_eps_val=None,
    sys_fiscal_year_eps_val=None,
    ai_fiscal_year_eps_val=None,
    sys_forward_eps_system_val=None,
    eff_f_eps_val=None,
    ai_forward_eps_ai_val=None,
    ai_forward_eps_consensus_val=None,
    ai_forward_eps_fy1_val=None,
    ai_forward_eps_fy2_val=None,
    ai_forward_eps_fy3_val=None,
    ai_forward_eps_fy1_year_val=None,
    ai_forward_eps_fy2_year_val=None,
    ai_forward_eps_fy3_year_val=None,
    ai_f_eps_calc_val=None,
    fy1_eps_for_annual_val=None,
    cap_adopted_forward_eps_val=None,
    ai_forward_eps_fy_source_note_val=None,
    ai_forward_eps_fy_basis_val=None,
    formula_pe_cap_val=None,
    formula_eps_for_calc_val=None,
    formula_eps_source_val=None,
    system_formula_fair_value_raw_val=None,
    forward_eps_period_mismatch_val=None,
    base_pe_cap_val=None,
    soft_pe_cap_val=None,
    hard_pe_cap_val=None,
    manual_cap_for_calc_val=None,
    manual_cap_source_val=None,
    sys_target_price_est_val=None,
    current_eps_for_valuation_val=None,
    current_eps_raw_val=None,
    current_eps_source_val=None,
    current_eps_formula_note_val=None,
    current_eps_period_val=None,
    current_target_price_est_val=None,
    run_rate_1q_eps_val=None,
    run_rate_2q_eps_val=None,
    run_rate_reference_eps_val=None,
    run_rate_1q_target_price_val=None,
    run_rate_2q_target_price_val=None,
    run_rate_reference_target_price_val=None,
    run_rate_label_val=None,
    run_rate_action_val=None,
    fy1_base_target_price_val=None,
    fy1_soft_target_price_val=None,
    fy1_hard_target_price_val=None,
    fy2_base_target_price_val=None,
    fy2_soft_target_price_val=None,
    fy2_hard_target_price_val=None,
    fy3_base_target_price_val=None,
    fy3_soft_target_price_val=None,
    fy3_hard_target_price_val=None,
    fy1_manual_target_price_val=None,
):
    """Summarize EPS adoption and valuation layers for prompt packs."""
    try:
        def _n(v):
            return prompt_nullize_text(v)

        def _num(v, digits=2):
            x = s_float(v)
            return "NULL" if x is None else f"{x:.{digits}f}"

        def _cap(v):
            x = s_float(v)
            return "NULL" if x is None else f"{x:.1f}x"

        def _price(v):
            x = s_float(v)
            return "NULL" if x is None else f"{x:.1f}元"

        def _year(v):
            text = prompt_nullize_text(v)
            return "年期未明" if text == "NULL" else text

        fy1_annual = fy1_eps_for_annual_val
        if fy1_annual is None:
            fy1_annual = ai_forward_eps_fy1_val if ai_forward_eps_fy1_val is not None else cap_adopted_forward_eps_val

        fy_calendar_notice = build_forward_eps_calendar_notice(
            fy1_year=ai_forward_eps_fy1_year_val,
            fy2_year=ai_forward_eps_fy2_year_val,
            fy3_year=ai_forward_eps_fy3_year_val,
        )
        lines = []

        def _has(*vals):
            return any(s_float(v) is not None for v in vals)

        if _has(ai_latest_month_eps_val):
            lines.append(f"- 最新單月 / 自結 EPS: AI={_n(ai_latest_month_eps_val)} / 採用={_n(ai_latest_month_eps_val)} / 期間={_n(raw_ai_period_val)} / 估值口徑=單月 EPS x12")
        if _has(sys_latest_quarter_eps_val, ai_latest_quarter_eps_val):
            adopted = ai_latest_quarter_eps_val if s_float(ai_latest_quarter_eps_val) is not None else sys_latest_quarter_eps_val
            lines.append(f"- 最新單季 EPS: 系統={_n(sys_latest_quarter_eps_val)} / AI={_n(ai_latest_quarter_eps_val)} / 採用={_n(adopted)} / 期間={_n(raw_ai_period_val)}")
        if _has(sys_ttm_eps_val, ai_ttm_eps_val, eff_t_eps_val):
            lines.append(f"- TTM EPS: 系統={_n(sys_ttm_eps_val)} / AI={_n(ai_ttm_eps_val)} / 採用={_n(eff_t_eps_val)}")
        if _has(sys_fiscal_year_eps_val, ai_fiscal_year_eps_val):
            adopted = ai_fiscal_year_eps_val if s_float(ai_fiscal_year_eps_val) is not None else sys_fiscal_year_eps_val
            lines.append(f"- 完整年度 EPS: 系統={_n(sys_fiscal_year_eps_val)} / AI={_n(ai_fiscal_year_eps_val)} / 採用={_n(adopted)}")
        if _has(sys_forward_eps_system_val, eff_f_eps_val):
            lines.append(f"- Forward EPS－系統估值採用值: {_num(eff_f_eps_val)}（用於『公式合理估值』；系統原始={_num(sys_forward_eps_system_val)}）")
        if _has(formula_eps_for_calc_val):
            mismatch = forward_eps_period_mismatch_val if isinstance(forward_eps_period_mismatch_val, dict) else {}
            note = prompt_nullize_text(mismatch.get("note") if mismatch.get("has_mismatch") else "")
            if note == "NULL":
                note = "未偵測到年期錯位"
            lines.append(
                f"- 公式合理估值 EPS 實際採用值: {_num(formula_eps_for_calc_val)}"
                f"（{_n(formula_eps_source_val)}；系統原始公式價={_price(system_formula_fair_value_raw_val)}；年期判讀={note}）"
            )
        if _has(current_eps_for_valuation_val):
            lines.append(
                f"- 目前估值 EPS: {_num(current_eps_for_valuation_val)}"
                f"（{_n(current_eps_source_val)}；原始EPS={_num(current_eps_raw_val)}；計算={_n(current_eps_formula_note_val)}；期間={_n(current_eps_period_val)}；用於『目前估值』）"
            )
        if _has(run_rate_1q_eps_val, run_rate_2q_eps_val, run_rate_reference_eps_val):
            lines.append(
                f"- Run-rate EPS 動能: 近二季年化={_num(run_rate_2q_eps_val)} / 近一季年化={_num(run_rate_1q_eps_val)}"
                f" / 參考EPS={_num(run_rate_reference_eps_val)}"
                f"（{_n(run_rate_label_val)}；{_n(run_rate_action_val)}；只作動能檢查，不取代 TTM/FY1/FY2）"
            )
        if _has(ai_forward_eps_ai_val):
            lines.append(f"- Forward EPS－AI一般欄位: {_num(ai_forward_eps_ai_val)}")
        if _has(ai_forward_eps_consensus_val):
            lines.append(f"- Forward EPS－法人共識: {_num(ai_forward_eps_consensus_val)}")
        if _has(ai_forward_eps_fy1_val):
            lines.append(f"- FY1 EPS: {_num(ai_forward_eps_fy1_val)}｜年度={_year(ai_forward_eps_fy1_year_val)}｜用於『FY1年度估值』與年度情境主基準")
        if _has(ai_forward_eps_fy2_val):
            lines.append(f"- FY2 EPS: {_num(ai_forward_eps_fy2_val)}｜年度={_year(ai_forward_eps_fy2_year_val)}｜用於『FY2第二年度估值』，只判斷市場先行定價")
        if _has(ai_forward_eps_fy3_val):
            lines.append(f"- FY3 EPS: {_num(ai_forward_eps_fy3_val)}｜年度={_year(ai_forward_eps_fy3_year_val)}｜用於高風險遠期情境，不可直接當買點")
        lines.append(f"- FY 年度/月份提示: {prompt_nullize_text(fy_calendar_notice.get('prompt_notice'))}")
        if _has(ai_f_eps_calc_val):
            lines.append(f"- AI/法人 Forward EPS 採用值: {_num(ai_f_eps_calc_val)}（只作來源與交叉檢查；不再單列 AI估值，避免與 FY1 重複）")
        if _has(fy1_annual):
            lines.append(f"- 手動年度情境採用 EPS: {_num(fy1_annual)}（優先 FY1 EPS；FY1 無資料才退回採用 Forward EPS）")

        source_parts = []
        if _n(raw_ai_period_val) != "NULL":
            source_parts.append(f"來源日期={_n(raw_ai_period_val)}")
        if _n(ai_forward_eps_fy_source_note_val) != "NULL":
            source_parts.append(f"FY來源說明={_n(ai_forward_eps_fy_source_note_val)}")
        if _n(ai_forward_eps_fy_basis_val) != "NULL":
            source_parts.append(f"FY基準={_n(ai_forward_eps_fy_basis_val)}")
        if source_parts:
            lines.append("- EPS 年期/來源: " + "｜".join(source_parts))

        cap_parts = []
        if _cap(formula_pe_cap_val) != "NULL":
            cap_parts.append(f"formula cap={_cap(formula_pe_cap_val)}")
        if _cap(base_pe_cap_val) != "NULL" or _cap(soft_pe_cap_val) != "NULL" or _cap(hard_pe_cap_val) != "NULL":
            cap_parts.append(f"年度 base/soft/hard={_cap(base_pe_cap_val)} / {_cap(soft_pe_cap_val)} / {_cap(hard_pe_cap_val)}")
        if _cap(manual_cap_for_calc_val) != "NULL":
            cap_parts.append(f"手動情境 Cap={_cap(manual_cap_for_calc_val)}（{_n(manual_cap_source_val)}）")
        if cap_parts:
            lines.append("- 估值倍率: " + "；".join(cap_parts))

        price_parts = []
        for label, value in [
            ("系統公式", sys_target_price_est_val),
            ("系統原始公式", system_formula_fair_value_raw_val),
            ("目前估值", current_target_price_est_val),
            ("Run-rate參考", run_rate_reference_target_price_val),
            ("Run-rate近二季", run_rate_2q_target_price_val),
            ("Run-rate近一季", run_rate_1q_target_price_val),
            ("FY1-base", fy1_base_target_price_val),
            ("FY1-soft", fy1_soft_target_price_val),
            ("FY1-hard", fy1_hard_target_price_val),
            ("FY2-base", fy2_base_target_price_val),
            ("FY2-soft", fy2_soft_target_price_val),
            ("FY2-hard", fy2_hard_target_price_val),
            ("FY3-base", fy3_base_target_price_val),
            ("FY3-soft", fy3_soft_target_price_val),
            ("FY3-hard", fy3_hard_target_price_val),
            ("手動年度", fy1_manual_target_price_val),
        ]:
            if _price(value) != "NULL":
                price_parts.append(f"{label}={_price(value)}")
        if price_parts:
            lines.append("- 新版估值結果: " + "；".join(price_parts))
        lines.append("- 重要規則: 公式合理估值原則上使用系統 Forward EPS；若偵測到系統 Forward EPS 疑似 FY2 年期錯位，公式價降權採 FY1 EPS，系統原始公式價只作追蹤；目前估值使用最新單季 EPS 年化，缺值才退回 TTM EPS，用於目前獲利支撐度檢查；Run-rate EPS 用近一季/近二季年化檢查 AI 高成長動能，但不得取代 TTM、FY1 或 FY2；系統 Forward EPS 缺值時為 NULL，不得用 AI/FY1 冒充系統公式；前瞻 PEG 不再單列 AI估值；FY1/FY2/FY3 各列 base/soft/hard，分別為基礎/樂觀/極限；手動年度情境以 FY1 EPS 為主，未手動調整時採 FY1 base；7 月後需同步參考 FY2，10 月後 FY2 可作主要前瞻參考，但不得無條件支撐買進。")
        return "\n".join(lines) if lines else "無可用 EPS 面板資料，提示詞不納入 EPS 估值判斷。"
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_eps_adoption_sync_summary", exc)
        except Exception:
            pass
        return "NULL"


def prompt_target_price_panel_summary(
    *,
    prompt_hi_str=None,
    prompt_me_str=None,
    prompt_lo_str=None,
    prompt_analyst_count=None,
    target_confidence=None,
    prompt_target_source=None,
    ai_tp_str=None,
    prompt_target_rationale=None,
):
    """Format target-price panel values for prompt packs."""
    try:
        lines = []
        if prompt_nullize_text(prompt_hi_str) != "NULL" or prompt_nullize_text(prompt_me_str) != "NULL" or prompt_nullize_text(prompt_lo_str) != "NULL":
            lines.append(f"- 最高 / 平均 / 最低目標價: {prompt_nullize_text(prompt_hi_str)} / {prompt_nullize_text(prompt_me_str)} / {prompt_nullize_text(prompt_lo_str)}")
        if prompt_nullize_text(prompt_analyst_count) != "NULL":
            lines.append(f"- 分析師人數: {prompt_nullize_text(prompt_analyst_count)}")
        if isinstance(target_confidence, dict):
            lines.append(f"- 目標價可信度: {prompt_nullize_text(target_confidence.get('label'))}｜{prompt_nullize_text(target_confidence.get('message'))}")
        if prompt_nullize_text(prompt_target_source) != "NULL":
            lines.append(f"- 目標價資料來源: {prompt_nullize_text(prompt_target_source)}")
        if prompt_nullize_text(ai_tp_str) != "NULL":
            lines.append(f"- AI 最新目標價補充: {prompt_nullize_text(ai_tp_str)}")
        if prompt_nullize_text(prompt_target_rationale) != "NULL":
            lines.append(f"- 核心理由: {prompt_nullize_text(prompt_target_rationale)}")
        lines.append("- 同步規則: 以法人目標價面板顯示值為準；若面板無系統值，才回填 AI 目標價；沒有資料的 AI 欄位不輸出 NULL。")
        return "\n".join(lines) if lines else "無可用法人目標價面板資料，本次不納入法人目標價判斷。"
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_target_price_panel_summary", exc)
        except Exception:
            pass
        return "無可用法人目標價面板資料，本次不納入法人目標價判斷。"


def _prompt_etf_weight_text(weight):
    try:
        return f"{float(weight):.2f}%" if weight is not None and str(weight).strip() != "" else "N/A"
    except Exception:
        return str(weight) if weight else "N/A"


def prompt_etf_panel_summary(*, etf_holders=None, ai_etf_data=None):
    """Format ETF exposure panel values for prompt packs."""
    try:
        rows = []
        for row in (etf_holders or [])[:8]:
            if not isinstance(row, dict):
                continue
            rows.append(
                f"- 快速ETF｜{prompt_nullize_text(row.get('etf_code'))} {prompt_nullize_text(row.get('etf_name'))}"
                f"｜持股={_prompt_etf_weight_text(row.get('weight'))}"
                f"｜日期={prompt_nullize_text(row.get('data_date'))}"
                f"｜來源={prompt_nullize_text(row.get('source') or row.get('data_type'))}"
            )

        if isinstance(ai_etf_data, dict):
            if ai_etf_data.get("error"):
                rows.append(f"- AI ETF 補查失敗｜{prompt_nullize_text(ai_etf_data.get('error'))}")
            else:
                for row in (ai_etf_data.get("etf_holders_ai") or [])[:8]:
                    if not isinstance(row, dict):
                        continue
                    rows.append(
                        f"- AI ETF｜{prompt_nullize_text(row.get('etf_code'))} {prompt_nullize_text(row.get('etf_name'))}"
                        f"｜持股={_prompt_etf_weight_text(row.get('weight'))}"
                        f"｜日期={prompt_nullize_text(row.get('data_date'))}"
                        f"｜來源={prompt_nullize_text(row.get('source') or row.get('data_type'))}"
                    )
                if ai_etf_data.get("summary"):
                    rows.append(f"- AI ETF 摘要｜{prompt_nullize_text(ai_etf_data.get('summary'))}")

        if not rows:
            return "NULL｜快速 ETF 查無或尚未執行 AI ETF 補查；此區不保證完整，正式持股仍以 ETF 官方/PCF 為準。"
        rows.append("- 限制｜ETF 快速查詢可能只含主要/前十大；AI ETF 補查為交叉檢查，正式持股仍以投信公告、PCF 或 ETF 官方持股明細為準。")
        return "\n".join(rows)
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_etf_panel_summary", exc)
        except Exception:
            pass
        return "NULL"


def prompt_defense_panel_summary(*, dy_str=None, fcf_str=None, cr_str=None, fs_str=None):
    """Format defense and financial-health card values for prompt packs."""
    try:
        return "\n".join([
            f"- 殖利率: {prompt_nullize_text(dy_str)}",
            f"- FCF: {prompt_nullize_text(fcf_str)}",
            f"- 流動比率: {prompt_nullize_text(cr_str)}",
            f"- F-Score: {prompt_nullize_text(fs_str)}",
            "- 備註: 以上數值用於長線/存股防禦力，仍需搭配資料品質與現金流來源確認。",
        ])
    except Exception:
        return "NULL"


def prompt_chip_panel_summary(chip_state=None):
    """Format institutional-flow and ownership values for prompt packs."""
    try:
        chip_state = chip_state if isinstance(chip_state, dict) else {}
        lines = []

        def _fmt_lots(value):
            x = s_float(value)
            return "NULL" if x is None else f"{x:,.0f}張"

        def _fmt_pct(value):
            x = s_float(value)
            return "NULL" if x is None else f"{x:.2%}"

        f_10d = chip_state.get("f_10d")
        t_10d = chip_state.get("t_10d")
        has_inst = bool(chip_state.get("has_institutional_data")) or s_float(f_10d) is not None or s_float(t_10d) is not None
        if has_inst:
            lines.append(f"- 外資近10日淨買賣: {prompt_nullize_text(f_10d)} 張｜動向: {prompt_nullize_text(chip_state.get('f_status'))}")
            lines.append(f"- 投信近10日淨買賣: {prompt_nullize_text(t_10d)} 張｜動向: {prompt_nullize_text(chip_state.get('t_status'))}")
            total_10d = None
            try:
                total_10d = (s_float(f_10d) or 0) + (s_float(t_10d) or 0)
            except Exception:
                total_10d = None
            lines.append(f"- 外資+投信近10日合計: {prompt_nullize_text(total_10d)} 張")
            trap_warning = prompt_nullize_text(chip_state.get("trap_warning"))
            if trap_warning != "NULL":
                lines.append(f"- 籌碼警示: {trap_warning}")
        else:
            lines.append("- 外資/投信近10日資料: NULL（未取得 FinMind 籌碼資料或無近期資料）")

        margin_credit = chip_state.get("margin_credit") if isinstance(chip_state.get("margin_credit"), dict) else {}
        if margin_credit.get("available"):
            lines.append(
                "- 融資融券風險: "
                f"等級={prompt_nullize_text(margin_credit.get('risk_label'))}；"
                f"日期={prompt_nullize_text(margin_credit.get('latest_date'))}；"
                f"融資餘額={_fmt_lots(margin_credit.get('margin_balance'))}；"
                f"融資使用率={_fmt_pct(margin_credit.get('margin_usage_ratio'))}；"
                f"融資占股本={_fmt_pct(margin_credit.get('margin_to_shares_ratio'))}；"
                f"5日變化={_fmt_lots(margin_credit.get('margin_change_5d'))} / {_fmt_pct(margin_credit.get('margin_change_5d_pct'))}；"
                f"20日變化={_fmt_lots(margin_credit.get('margin_change_20d'))} / {_fmt_pct(margin_credit.get('margin_change_20d_pct'))}；"
                f"券資比={_fmt_pct(margin_credit.get('short_margin_ratio'))}；"
                f"判讀={prompt_nullize_text(margin_credit.get('risk_note'))}"
            )
        else:
            lines.append("- 融資融券風險: NULL（未取得 FinMind TaiwanStockMarginPurchaseShortSale 資料）")

        share_capital = s_float(chip_state.get("share_capital"))
        share_capital_100m = None
        if share_capital is not None:
            share_capital_100m = share_capital / 100000000
        lines.extend([
            f"- 機構持股率: {prompt_nullize_text(chip_state.get('inst_str'))}｜判讀: {prompt_nullize_text(chip_state.get('inst_eval'))}",
            f"- 內部人/大股東持股: {prompt_nullize_text(chip_state.get('insider_str'))}｜判讀: {prompt_nullize_text(chip_state.get('in_eval'))}",
            f"- 股本/控盤類型: {prompt_nullize_text(share_capital_100m)} 億｜{prompt_nullize_text(chip_state.get('cap_type'))}｜{prompt_nullize_text(chip_state.get('driver'))}",
            f"- 控盤說明: {prompt_nullize_text(chip_state.get('driver_desc'))}",
        ])
        return "\n".join(lines)
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_chip_panel_summary", exc)
        except Exception:
            pass
        return "NULL"


def prompt_panel_sync_audit(
    *,
    latest_rev_display_label=None,
    eps_adopted_for_prompt=None,
    peg_valuation_text=None,
    prompt_analyst_count=None,
    prompt_hi_str=None,
    prompt_me_str=None,
    prompt_lo_str=None,
    dynamic_cap_pack=None,
    final_signal=None,
    etf_summary=None,
    chip_summary=None,
):
    """Format prompt-panel synchronization checks."""
    try:
        checks = [
            ("月營收公告月份", latest_rev_display_label not in (None, "", "公告月份：未知")),
            ("EPS拆欄/FY1/FY2/FY3", eps_adopted_for_prompt not in (None, "", "NULL")),
            ("Forward PEG 年度三情境估值", peg_valuation_text not in (None, "", "NULL")),
            (
                "法人目標價/分析師人數",
                prompt_nullize_text(prompt_analyst_count) != "NULL"
                or prompt_nullize_text(prompt_hi_str) != "NULL"
                or prompt_nullize_text(prompt_me_str) != "NULL"
                or prompt_nullize_text(prompt_lo_str) != "NULL",
            ),
            ("Dynamic Cap/可操作區間", isinstance(dynamic_cap_pack, dict) and bool(dynamic_cap_pack)),
            ("最終操作燈號", isinstance(final_signal, dict) and bool(final_signal.get("signal"))),
            ("ETF摘要", etf_summary not in (None, "")),
            ("籌碼/股權結構", chip_summary not in (None, "")),
        ]
        lines = []
        for name, ok in checks:
            if name == "法人目標價/分析師人數" and ok:
                lines.append("- 法人目標價/分析師人數: 已同步；仍需確認資料日期與樣本口徑。")
            else:
                lines.append(f"- {name}: {'已同步' if ok else '可能缺值/需人工確認'}")
        lines.append("- 技術面摘要（日線）: 已同步；可依提示詞選項加入或不加入。")
        lines.append("- 技術線圖輸出（第二階段）: 圖表工具列可下載 PNG；若另附圖，外部 AI 應依 10 點規則輔助判讀。")
        lines.append("- 技術線圖輔助規則: 已同步；技術面不可覆蓋基本面、資料品質、Dynamic Cap 與最終燈號。")
        lines.append("- 產業同業PK/估值河流圖: 屬互動視覺輔助，研究完整版以產業模型、Dynamic Cap、估值區間摘要為主，未塞完整圖表資料。")
        return "\n".join(lines)
    except Exception:
        return "NULL"


def prompt_model_gap_trigger_conditions():
    """Research prompt rule block for model-gap diagnostics."""
    return """本區只放在研究完整版；用途是讓外部 AI 在市場價、法人價、系統估值差距過大時，先做模型落差診斷，再給研究結論。

若符合下列任一條件，請啟動模型落差診斷：
- 現價高於系統可操作區間高標 20% 以上。
- 現價高於 FY1 base 基礎估值 30% 以上；若系統公式合理估值為 NULL，不得用系統公式價判斷。
- 法人平均目標價與系統可操作區間中值差距超過 30%。
- 法人最高目標價與最低目標價差距超過平均目標價 60%。
- 現價用 FY1 EPS 看高於 hard ceiling，但用 FY2 / FY3 EPS 看可解釋。
- 系統 pricing_horizon 顯示 FY2_PRICED / FY3_HIGH_RISK / THEME_RE_RATING / EXTREME_FUTURE_PRICED。
- future_evidence_score 低於 60，但外部敘事仍想用 FY2 / FY3 解釋現價。

請 AI 逐項判斷落差可能來源：
1. 市場是否已提前反映 FY2 / FY3 EPS。
1-1. 系統 pricing_horizon 與 future_evidence_score 是否支持這種先行定價。
2. primary_taxon 是否可能已不符合市場定價邏輯。
3. hybrid 權重是否可能不足。
4. 是否只是市場題材或短線過熱。
5. 法人目標價是否分歧過大，導致平均目標價可信度下降。

請 AI 最後只能從下列 5 種模型診斷結論選一種：
- 模型暫不需調整，市場短線過熱。
- 模型暫不需調整，但市場正在提前反映 FY2/FY3。
- 建議檢查 hybrid 權重。
- 建議檢查 primary_taxon。
- 建議檢查整個產業倍率。

重要限制：
- 不可因股價高於模型價就直接調高模型。
- 不可因單一法人高標就調高模型。
- FY2 只能解釋市場先行定價，不等於買點。
- FY1_SOFT_PRICED 只是 FY1 樂觀區或安全邊際不足，不可誤判為 FY2 先行定價。
- FY3 只作高風險遠期情境，不可作一般買進依據。
- future_evidence_score 低於 50 時，不得用 FY2/FY3 合理化現價；60-79 只能續抱或小量，80 以上也不可直接重倉。
- 若建議調整模型，必須說明是 primary_taxon、hybrid 權重，還是 base / soft / hard ceiling 的問題。"""


def prompt_buy_decision_gap_risk_conditions():
    """Buy-decision prompt rule block for safety-margin gap checks."""
    return """本區只放在買進決策版；用途是讓外部 AI 在判斷是否買進前，先檢查市場價、法人目標價、系統可操作估值與 FY1/FY2/FY3 估值是否落差過大。

若符合下列任一條件，請啟動買進風險檢查：
- 現價高於系統可操作區間高標 20% 以上。
- 現價高於 FY1 base 基礎估值 30% 以上；若系統公式合理估值為 NULL，不得用系統公式價判斷。
- 現價只能用 FY2 / FY3 EPS 才能解釋。
- 系統 pricing_horizon 顯示 FY2_PRICED / FY3_HIGH_RISK / THEME_RE_RATING / EXTREME_FUTURE_PRICED。
- future_evidence_score 低於 60，但現價仍需遠期 EPS 才能解釋。
- 法人平均目標價與系統可操作區間中值差距超過 30%。
- 法人最高目標價與最低目標價差距超過平均目標價 60%。

請 AI 判斷此落差對「買進安全邊際」的影響：
1. 現價是否已提前反映 FY2 / FY3 EPS。
1-1. pricing_horizon 與 future_evidence_score 是否允許把此遠期定價視為可續抱，而非可追買。
2. 法人高標是否過度樂觀或高低標分歧過大。
3. 現價是否高於系統可操作區間，導致追價風險偏高。
4. 若只能用 FY2 / FY3 解釋現價，請說明 EPS / 營收 / 毛利率是否已經落地。
5. 若差距過大，請明確標示：不宜追價 / 只能觀察 / 需等 EPS 或營收落地後再評估。

重要限制：
- 本區不是模型庫修正建議，只用於買進風險判斷。
- FY2 只能解釋市場先行定價，不等於買點。
- FY1_SOFT_PRICED 只是 FY1 樂觀區或安全邊際不足，不可誤判為 FY2 先行定價。
- FY3 只作高風險遠期情境，不可作一般買進依據。
- future_evidence_score 低於 50 時，不可用 FY2/FY3 支撐買進；60-79 僅能保守續抱或等待確認；80 以上仍需分批與控倉。
- 法人高標不可直接視為合理買進價。
- 公式合理價、年度 soft/hard 情境價、使用者手動壓力測試價都不是系統建議買點。"""


def prompt_model_library_feedback_request(industry_profile=None):
    """Format model-library feedback request for research prompt packs."""
    try:
        industry_profile = industry_profile if isinstance(industry_profile, dict) else {}
        primary_taxon = prompt_nullize_text(industry_profile.get("primary_taxon"))
        model_label = prompt_nullize_text(industry_profile.get("model_label"))
        hybrid_taxons = prompt_nullize_text(industry_profile.get("hybrid_taxons_text"))
        mixed_caps = prompt_nullize_text(industry_profile.get("hybrid_mixed_caps_text"))
        source = prompt_nullize_text(industry_profile.get("classification_source"))
        confidence = prompt_nullize_text(industry_profile.get("classification_confidence"))
        hard_cap = prompt_nullize_text(industry_profile.get("hard_ceiling_pe"))
        soft_cap = prompt_nullize_text(industry_profile.get("soft_ceiling_pe"))
        re_rating_status = prompt_nullize_text(industry_profile.get("re_rating_status_label") or industry_profile.get("re_rating_status"))
        pricing_policy = prompt_nullize_text(industry_profile.get("pricing_horizon_policy"))
        hard_policy = prompt_nullize_text(industry_profile.get("hard_ceiling_policy"))

        lines = [
            "本區只放在研究完整版；目的不是產生買賣建議，而是把本次個案分析整理成模型庫修正候選清單。",
            f"- 目前 primary_taxon: {primary_taxon}",
            f"- 目前匹配模型: {model_label}",
            f"- 目前 hybrid_taxons / 權重: {hybrid_taxons}",
            f"- 混合後估值區間: {mixed_caps}",
            f"- 模型重評價狀態: {re_rating_status}",
            f"- 重評價操作規則: {pricing_policy}",
            f"- hard ceiling 政策: {hard_policy}",
            f"- 分類來源 / 可信度: {source} / {confidence}",
            f"- 主模型 soft / hard ceiling: {soft_cap} / {hard_cap}",
            "- 可參考落差來源: 現價、法人目標價、系統可操作估值、FY1/FY2/FY3 估值、Dynamic Cap、產業模型單次快照稽核。",
            "",
            "請 AI 僅能從下列模型庫回饋類型選擇，可複選：",
            "- primary_taxon_review：主分類可能需要人工檢查。",
            "- hybrid_weight_review：hybrid 權重可能需要人工檢查。",
            "- industry_cap_review：整個產業 base / soft / hard ceiling 可能需要檢查。",
            "- eps_timing_review：市場可能已提前反映 FY2/FY3 EPS。",
            "- target_confidence_review：法人目標價可信度或高低標分歧規則需檢查。",
            "- no_model_change：目前不建議調整模型庫。",
            "",
            "請 AI 輸出以下欄位：",
            "- 模型庫回饋類型。",
            "- 是否建議立即修改模型庫: 是 / 否 / 觀察。",
            "- 建議檢查的檔案: stock_mapping.py / industry_taxonomy.py / dynamic_cap_model.py / 目標價可信度規則。",
            "- 具體建議。",
            "- 支持證據。",
            "- 反對證據。",
            "- 需要追蹤的條件。",
            "- 信心等級: 高 / 中 / 低。",
            "",
            "重要限制：",
            "- 不可因單次股價上漲就建議調高模型。",
            "- 不可因單一法人高標就建議調高模型。",
            "- 若建議調整 primary_taxon，必須說明公司營收結構或獲利來源已明顯轉型。",
            "- 若建議調整 hybrid 權重，必須說明新成長曲線如何影響 FY1/FY2/FY3 EPS、毛利率或法人目標價。",
            "- 若建議調整產業倍率，必須說明是否多檔同產業股票都出現系統性偏差。",
            "- AI 回饋只進入模型庫修正候選清單，不可自動覆蓋 stock_mapping.py 或產業倍率。",
        ]
        return "\n".join(lines)
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_model_library_feedback_request", exc)
        except Exception:
            pass
        return "NULL"


def prompt_technical_suffix(mode, hist=None, curr_p=None):
    """Build optional technical-analysis suffix for prompt packs."""
    try:
        mode_text = str(mode or "")
        if mode_text.startswith("不加入"):
            return ""

        tech_lines = []
        try:
            tech_df = hist.copy() if hist is not None else pd.DataFrame()
            if tech_df is None or tech_df.empty:
                raise ValueError("hist empty")
            for col in ["Open", "High", "Low", "Close", "Volume"]:
                if col not in tech_df.columns:
                    tech_df[col] = 0.0
            tech_df = tech_df.copy()
            tech_df["MA5"] = tech_df["Close"].rolling(5).mean()
            tech_df["MA10"] = tech_df["Close"].rolling(10).mean()
            tech_df["MA20"] = tech_df["Close"].rolling(20).mean()
            tech_df["MA60"] = tech_df["Close"].rolling(60).mean()
            tech_df["Vol_MA20"] = tech_df["Volume"].rolling(20).mean()
            h9 = tech_df["High"].rolling(9).max()
            l9 = tech_df["Low"].rolling(9).min()
            denom = h9 - l9
            denom = denom.mask(denom == 0, 1e-9)
            rsv = (tech_df["Close"] - l9) / denom * 100
            k_values, d_values = [50.0], [50.0]
            for value in rsv.fillna(50):
                k_values.append(k_values[-1] * (2 / 3) + float(value) * (1 / 3))
                d_values.append(d_values[-1] * (2 / 3) + k_values[-1] * (1 / 3))
            tech_df["K"] = k_values[1:]
            tech_df["D"] = d_values[1:]
            plot_tech = tech_df.tail(120).copy()

            def _last(col, fallback=None):
                try:
                    value = plot_tech[col].dropna().iloc[-1]
                    return float(value)
                except Exception:
                    return fallback

            close_v = _last("Close", curr_p)
            ma5_v = _last("MA5", None)
            ma10_v = _last("MA10", None)
            ma20_v = _last("MA20", None)
            ma60_v = _last("MA60", None)
            k_v = _last("K", None)
            d_v = _last("D", None)
            vol_v = _last("Volume", None)
            vol20_v = _last("Vol_MA20", None)
            vol_ratio = None
            try:
                if vol_v is not None and vol20_v not in (None, 0):
                    vol_ratio = vol_v / vol20_v
            except Exception:
                vol_ratio = None

            recent20 = plot_tech.tail(20)
            recent60 = plot_tech.tail(60)
            high20 = float(recent20["High"].max()) if not recent20.empty else None
            low20 = float(recent20["Low"].min()) if not recent20.empty else None
            high60 = float(recent60["High"].max()) if not recent60.empty else None

            ma_stack = "資料不足"
            if close_v is not None and ma5_v is not None and ma10_v is not None and ma20_v is not None and ma60_v is not None:
                if close_v > ma5_v > ma10_v > ma20_v > ma60_v:
                    ma_stack = "強多頭排列（收盤價 > 5MA > 10MA > 20MA > 60MA）"
                elif close_v < ma5_v < ma10_v < ma20_v < ma60_v:
                    ma_stack = "空頭排列（收盤價 < 5MA < 10MA < 20MA < 60MA）"
                elif close_v >= ma20_v:
                    ma_stack = "偏多整理（收盤價仍在20MA上方）"
                else:
                    ma_stack = "偏弱整理（收盤價低於20MA）"

            above5_days = None
            try:
                above5_days = int((plot_tech.tail(10)["Close"] > plot_tech.tail(10)["MA5"]).sum())
            except Exception:
                above5_days = None

            bias5 = None
            bias20 = None
            try:
                if close_v is not None and ma5_v not in (None, 0):
                    bias5 = (close_v / ma5_v - 1) * 100
                if close_v is not None and ma20_v not in (None, 0):
                    bias20 = (close_v / ma20_v - 1) * 100
            except Exception:
                pass

            heat_text = "資料不足"
            if bias20 is not None:
                if abs(bias20) >= 15:
                    heat_text = "短線乖離偏大，追價風險高"
                elif abs(bias20) >= 8:
                    heat_text = "乖離略高，宜等拉回或站穩再評估"
                else:
                    heat_text = "乖離尚可，仍需搭配量價與基本面"

            kd_text = "資料不足"
            if k_v is not None and d_v is not None:
                kd_text = f"K={k_v:.1f}；D={d_v:.1f}；" + ("KD偏多" if k_v >= d_v else "KD偏弱")
                if k_v >= 80:
                    kd_text += "；K值高檔"
                elif k_v <= 20:
                    kd_text += "；K值低檔"

            support_candidates = [value for value in [ma5_v, ma10_v, ma20_v, ma60_v, low20] if value is not None]
            pressure_candidates = [value for value in [high20, high60] if value is not None]
            support_text = "、".join([f"{value:.2f}" for value in support_candidates[:5]]) if support_candidates else "NULL"
            pressure_text = "、".join([f"{value:.2f}" for value in pressure_candidates[:3]]) if pressure_candidates else "NULL"

            ret10 = None
            try:
                last10 = plot_tech["Close"].dropna().tail(11)
                if len(last10) >= 11 and last10.iloc[0] != 0:
                    ret10 = (last10.iloc[-1] / last10.iloc[0] - 1) * 100
            except Exception:
                pass
            wash_text = "資料不足"
            if ret10 is not None and above5_days is not None:
                if ret10 > 0 and above5_days >= 7:
                    wash_text = "偏多續攻或高檔強勢整理；需觀察是否量縮回測不破5MA/10MA"
                elif ret10 < 0 and close_v is not None and ma20_v is not None and close_v < ma20_v:
                    wash_text = "轉弱風險升高；需觀察是否跌破20MA後反彈無力"
                else:
                    wash_text = "區間整理；需搭配量價與支撐壓力確認"

            tech_lines.extend([
                "【15. 技術面與進出場節奏（日線摘要，選配）】",
                "- 技術週期/資料範圍: 日線 / 近 120 根 K 線",
                f"- 收盤價與均線: 收盤={prompt_nullize_text(f'{close_v:.2f}' if close_v is not None else None)}；5MA={prompt_nullize_text(f'{ma5_v:.2f}' if ma5_v is not None else None)}；10MA={prompt_nullize_text(f'{ma10_v:.2f}' if ma10_v is not None else None)}；20MA={prompt_nullize_text(f'{ma20_v:.2f}' if ma20_v is not None else None)}；60MA={prompt_nullize_text(f'{ma60_v:.2f}' if ma60_v is not None else None)}",
                f"- 均線結構: {ma_stack}",
                f"- 沿線上攻: 近10日有 {prompt_nullize_text(above5_days)} 日收在 5MA 之上",
                f"- 乖離與追價風險: 距5MA={prompt_nullize_text(f'{bias5:.2f}%' if bias5 is not None else None)}；距20MA={prompt_nullize_text(f'{bias20:.2f}%' if bias20 is not None else None)}；{heat_text}",
                f"- KD 狀態: {kd_text}",
                f"- 量價結構: 量能/20日均量={prompt_nullize_text(f'{vol_ratio:.2f}x' if vol_ratio is not None else None)}",
                f"- 支撐平台: {support_text}",
                f"- 賣壓/壓力區: {pressure_text}",
                f"- 洗盤或出貨初判: {wash_text}",
                "- 回測買點節奏: 不宜只因技術面追價；優先觀察回測 5MA / 10MA / 20MA 是否量縮守住，再搭配基本面與估值確認。",
                "- 技術面結論: 技術面只判斷進出場節奏、追價風險、支撐壓力與停損停利，不可覆蓋基本面、資料品質、Dynamic Cap、可操作估值區間與系統最終燈號。",
            ])
        except Exception:
            tech_lines.extend([
                "【15. 技術面與進出場節奏（日線摘要，選配）】",
                "- 技術面摘要: 目前無法由系統資料自動產生，請改以畫面技術線圖輔助判讀。",
                "- 使用限制: 技術面只輔助進出場節奏，不可覆蓋基本面、資料品質、Dynamic Cap 與最終燈號。",
            ])

        if "線圖輔助規則" in mode_text:
            tech_lines.extend([
                "",
                "【16. 技術線圖輔助規則（另附圖時使用）】",
                "請外部 AI 若看到另附 K 線圖，只能依下列規則輔助判讀：",
                "1. 是否沿 5MA / 10MA 強勢上攻。",
                "2. 是否有高檔賣壓區。",
                "3. 是否有明顯支撐平台。",
                "4. 是否屬於洗盤後續攻，還是出貨轉弱。",
                "5. 是否短線乖離過大，不宜追高。",
                "6. 是否適合等回測 5MA / 10MA / 20MA。",
                "7. 量縮拉回若守均線，偏健康；放量跌破均線，需提高風險權重。",
                "8. KD 高檔只代表短線偏熱，不等於基本面轉弱；KD 低檔也不等於可買。",
                "9. 技術面可輔助停利停損與分批節奏，但不可覆蓋月營收、EPS、法人目標價、資料品質、Dynamic Cap 與最終燈號。",
                "10. 若技術面與基本面衝突，請以資料品質、估值安全邊際與最終燈號為主。",
            ])
        return "\n".join(tech_lines).strip()
    except Exception as exc:
        try:
            log_exception("PromptPack", "prompt_technical_suffix", exc)
        except Exception:
            pass
        return ""
