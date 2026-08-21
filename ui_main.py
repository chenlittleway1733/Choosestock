import inspect
import re
"""
主畫面 UI 模組：
包含個股儀表板、AI 分析、財務資料、圖表、ETF 曝險等主要畫面。
"""
from app_version import APP_PAGE_TITLE
from ui_common import *
from ui_panels.overview import render_empty_stock_prompt
from ui_panels.financials import (
    render_ai_financial_audit_control,
    render_anomaly_detection_panel,
    render_defense_health_cards,
    render_eps_breakdown_panel,
    render_final_signal_panel,
    render_financial_metric_cards,
    render_financial_quality_report_panel,
    render_target_price_panel,
    render_valuation_detail_panel,
)

_DEPLOYMENT_COMPAT_NOTES = []
try:
    from ui_panels.financials import build_eps_price_calculation_rows, render_eps_price_calculation_panel
except ImportError:
    _DEPLOYMENT_COMPAT_NOTES.append("使用 ui_main 內建 TTM/FY 計算面板。")

    def build_eps_price_calculation_rows(
        *, ttm_eps=None, fy1_eps=None, fy2_eps=None, fy3_eps=None,
        fy1_year=None, fy2_year=None, fy3_year=None,
        base_cap=None, soft_cap=None, hard_cap=None, cap_eps_basis="",
    ):
        def _positive(value):
            value = s_float(value)
            return value if value is not None and value > 0 else None

        base, soft, hard = _positive(base_cap), _positive(soft_cap), _positive(hard_cap)
        basis = str(cap_eps_basis or "").strip().lower()
        items = [
            ("TTM", "近四季", ttm_eps),
            ("FY1", str(fy1_year or "年度未取得"), fy1_eps),
            ("FY2", str(fy2_year or "年度未取得"), fy2_eps),
            ("FY3", str(fy3_year or "年度未取得"), fy3_eps),
        ]
        rows = []
        for tier, period, raw_eps in items:
            eps = _positive(raw_eps)
            if basis == "ttm_only":
                position = "v18.2 正式 TTM 口徑" if tier == "TTM" else "跨口徑情境換算，非正式估值"
            elif basis in {"fy1_forward", "forward_fy1", "fy1"}:
                position = "v18.2 正式 FY1 前瞻口徑" if tier == "FY1" else ("歷史基準情境換算" if tier == "TTM" else "遠期情境換算，不可直接作買點")
            else:
                position = "情境換算，需再確認 EPS 與倍率口徑"
            if eps is None:
                position = f"未取得 {tier} EPS｜{position}"
            rows.append({
                "tier": tier, "period": period, "eps": eps,
                "base_cap": base, "base_price": eps * base if eps is not None and base is not None else None,
                "soft_cap": soft, "soft_price": eps * soft if eps is not None and soft is not None else None,
                "hard_cap": hard, "hard_price": eps * hard if eps is not None and hard is not None else None,
                "position": position,
            })
        return rows

    def render_eps_price_calculation_panel(rows, *, cap_eps_basis=""):
        st.markdown("#### 💰 股票預估價｜TTM / FY1 / FY2 / FY3")
        st.caption("Base / Soft / Hard 來自 Dynamic Cap v18.2；計算價 = EPS × 倍率。跨口徑列只作情境換算。")

        def _fmt(value, suffix=""):
            value = s_float(value)
            return "—" if value is None else f"{value:.2f}{suffix}"

        display_rows = [{
            "口徑": row.get("tier"), "期間": row.get("period"), "EPS": _fmt(row.get("eps")),
            "Base": _fmt(row.get("base_cap"), "x"), "Base計算價": _fmt(row.get("base_price"), "元"),
            "Soft": _fmt(row.get("soft_cap"), "x"), "Soft計算價": _fmt(row.get("soft_price"), "元"),
            "Hard": _fmt(row.get("hard_cap"), "x"), "Hard計算價": _fmt(row.get("hard_price"), "元"),
            "定位": row.get("position"),
        } for row in (rows or [])]
        st_dataframe(pd.DataFrame(display_rows), hide_index=True)
        return rows
from ui_panels.etf import render_etf_exposure_panel
from ui_panels.chips import render_chip_panels
from ui_panels.news import render_financial_news_panel
from ui_panels.peer_compare import render_peer_compare_panel
from ui_panels.prompt_pack import render_prompt_pack_panel
from ui_panels.quote import render_quote_panel
from ui_panels.river_charts import render_valuation_river_charts
from ui_panels.stock_header import render_stock_header_panel
from ui_panels.technical import render_technical_chart_panel
from ui_context.financial_context import build_ai_financial_context, build_financial_base_context
from ui_context.implied_context import build_implied_pe_context
from ui_context.multiple_context import build_multiple_context, fmt_cap, fmt_eps, fmt_price
from ui_context.prompt_context import (
    build_prompt_target_context,
    prompt_ai_source_summary,
    prompt_dynamic_cap_core,
    prompt_df,
    prompt_buy_decision_gap_risk_conditions,
    prompt_defense_panel_summary,
    prompt_etf_panel_summary,
    prompt_eps_adoption_sync_summary,
    prompt_field_source_priority_summary,
    prompt_forward_eps_tier_core,
    prompt_chip_panel_summary,
    prompt_model_gap_trigger_conditions,
    prompt_model_library_feedback_request,
    prompt_panel_sync_audit,
    prompt_peg_valuation_layers,
    prompt_quality_summary,
    prompt_snapshot_audit_core,
    prompt_snapshot_audit_summary,
    prompt_target_price_panel_summary,
    prompt_technical_suffix,
    prompt_warnings,
)
try:
    from ui_context.prompt_context import build_essential_version_prompt
except ImportError:
    _DEPLOYMENT_COMPAT_NOTES.append("使用 ui_main 內建精簡提示詞產生器。")

    def build_essential_version_prompt(*, app_title, stock_id, stock_name, fields):
        missing_markers = ("n/a", "null", "none", "nan", "無資料", "未取得", "未捕捉到", "未知")

        def _usable(value):
            if value is None:
                return ""
            text = re.sub(r"\s+", " ", str(value)).strip()
            return "" if not text or any(marker in text.lower() for marker in missing_markers) else text

        data_lines = []
        for item in fields or []:
            if not isinstance(item, (tuple, list)) or len(item) < 2:
                continue
            label, value = _usable(item[0]), _usable(item[1])
            if label and value:
                data_lines.append(f"- {label}：{value}")
        core_data = "\n".join(data_lines) if data_lines else "- 請先查證核心數據後再分析"
        return (
            f"你是台股估值與風險分析助手。請用繁體中文，根據 {app_title} 分析 {stock_name} ({stock_id})。\n\n"
            f"【核心數據】\n{core_data}\n\n"
            "【任務】\n1. 判斷現價相對 TTM/FY1/FY2/FY3 情境價與法人目標價。\n"
            "2. 檢查毛利率、營益率與 YoY 是否支撐 EPS。\n"
            "3. 給出結論、分批買進、減碼/停損與三項核心風險。"
        )
from ui_context.quality_context import build_quality_report_context, fy_year_display_safe
from ui_context.valuation_context import build_dynamic_cap_context


def _supports_parameter(func, parameter_name):
    try:
        return parameter_name in inspect.signature(func).parameters
    except Exception:
        return False


def _render_ai_financial_audit_compat(*, curr_id, stock_name, info, current_price, compact):
    kwargs = {"curr_id": curr_id, "stock_name": stock_name, "info": info}
    if _supports_parameter(render_ai_financial_audit_control, "current_price"):
        kwargs["current_price"] = current_price
    if _supports_parameter(render_ai_financial_audit_control, "compact"):
        kwargs["compact"] = compact
    return render_ai_financial_audit_control(**kwargs)


def _render_quote_with_ai_compat(*, hist, info, curr_id, stock_name):
    if _supports_parameter(render_quote_panel, "header_action"):
        return render_quote_panel(
            hist=hist,
            info=info,
            header_action=lambda current_price: _render_ai_financial_audit_compat(
                curr_id=curr_id,
                stock_name=stock_name,
                info=info,
                current_price=current_price,
                compact=True,
            ),
        )

    _DEPLOYMENT_COMPAT_NOTES.append("AI 校對按鈕使用相容位置。")
    snapshot = render_quote_panel(hist=hist, info=info)
    current_price = snapshot.get("curr_p", 0) if isinstance(snapshot, dict) else 0
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    snapshot["header_action_result"] = _render_ai_financial_audit_compat(
        curr_id=curr_id,
        stock_name=stock_name,
        info=info,
        current_price=current_price,
        compact=False,
    )
    return snapshot


def _render_prompt_pack_compat(*, curr_id, prompt):
    if _supports_parameter(render_prompt_pack_panel, "prompt"):
        return render_prompt_pack_panel(curr_id=curr_id, prompt=prompt)
    _DEPLOYMENT_COMPAT_NOTES.append("精簡提示詞使用相容複製面板。")
    return render_prompt_pack_panel(
        curr_id=curr_id,
        buy_decision_prompt=prompt,
        research_prompt=prompt,
        build_technical_suffix=lambda _mode: "",
    )


def render_main_page(sidebar_state=None):
    """渲染主畫面。"""

    # 17-C-9c-hotfix：此 helper 會在 Forward EPS 區塊與後方提示詞打包區重複使用，
    # 必須放在 render_main_page 開頭；若放在函式後段，前面先呼叫時會觸發 UnboundLocalError。
    def _nullize_text(s):
        s = str(s) if s is not None else ""
        s = re.sub(r'<[^>]+>', ' ', s)
        s = s.replace("N/A", "NULL").replace("無資料", "NULL").replace("未捕捉到", "NULL")
        s = re.sub(r'\s+', ' ', s)
        return s.strip() if s.strip() else "NULL"

    hi_val = None
    me_val = None
    lo_val = None
    sidebar_state = sidebar_state or {}
    f_ok = sidebar_state.get("f_ok", None)
    m_ok = sidebar_state.get("m_ok", None)

    # ==========================================
    # 5. 主畫面開始
    # ==========================================
    st.markdown(f"## 📈 {APP_PAGE_TITLE}")

    curr_id = str(st.session_state.get("selected_stock", "") or "").strip()

    if st.session_state.fugle_key and not f_ok:
        st.error("🚨 **系統警報**：您輸入的「富果 (Fugle) API Key」驗證失敗！請至左側欄檢查金鑰是否輸入正確。")
    if st.session_state.finmind_key and not m_ok:
        st.error("🚨 **系統警報**：您輸入的「FinMind API Key」驗證失敗！請至左側欄檢查金鑰是否輸入正確。")

    # 2.2-hotfix：首次進入系統、尚未選股時，主畫面顯示明確操作提示，
    # 避免右側畫面只有標題與大片空白，尤其在 iPad / 平板檢視時容易誤以為系統未載入。
    if not curr_id:
        render_empty_stock_prompt()
        return

    if curr_id:
        # 🚀 絕對防呆宣告：避免因任何例外導致變數未定義而觸發 NameError
        ctx_pe, ctx_fpe, ctx_pb, ctx_peg = "N/A", "N/A", "N/A", "N/A"
        hi_str, me_str, lo_str, ai_tp_str = "N/A", "N/A", "N/A", ""
        latest_rev_month, latest_mom_str = "未知", "N/A"
        latest_rev_notice, latest_rev_display_label = "", "公告月份：未知"
        latest_rev_source = ""
        latest_rev_source_url = ""
        latest_rev_source_rule = ""
        latest_rev_announce_date = ""
        latest_rev_announce_month = ""
        latest_rev_revenue_month = ""
        dy_str, fcf_str, cr_str, fs_str = "N/A", "N/A", "N/A", "N/A"
        ctx_eps, ctx_rg, ctx_eg, ctx_gm, ctx_om, ctx_roe, ctx_de = "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"
        tp_est_str, cap_warning_html = "無資料", ""

        with st.spinner('同步數據中...'):
            hist, info = get_stock_data(curr_id, st.session_state.fugle_key, st.session_state.finmind_key)
            if info is None: info = {}
            c_name = get_chinese_name(curr_id) or info.get('shortName', curr_id)
        fallback_notes = info.get('__fallback_notes', []) if isinstance(info, dict) else []
        price_source = info.get('__price_source') if isinstance(info, dict) else None
        info_source = info.get('__info_source') if isinstance(info, dict) else None
        if price_source or info_source:
            st.caption(f"🛰️ 資料來源｜股價: {price_source or '未知'}；財務: {info_source or '未知'}")
        if fallback_notes:
            for note in fallback_notes:
                st.info(f"💡 備援提示：{note}")

        if hist is not None and not hist.empty:
            sector_disp, industry_profile = render_stock_header_panel(curr_id=curr_id, stock_name=c_name, info=info)

            quote_snapshot = _render_quote_with_ai_compat(
                hist=hist,
                info=info,
                curr_id=curr_id,
                stock_name=c_name,
            )
            curr_p = quote_snapshot.get("curr_p", 0)
            open_p = quote_snapshot.get("open_p", 0)
            high_p = quote_snapshot.get("high_p", 0)
            low_p = quote_snapshot.get("low_p", 0)
            vol_shares = quote_snapshot.get("vol_shares", 0)
            vol_lots = quote_snapshot.get("vol_lots", 0)
            prev_vol_lots = quote_snapshot.get("prev_vol_lots", 0)
            prev_close = quote_snapshot.get("prev_close", 0)
            change = quote_snapshot.get("change", 0)
            change_pct = quote_snapshot.get("change_pct", 0)
            amp = quote_snapshot.get("amp", 0)
            avg_price = quote_snapshot.get("avg_price", 0)
            turnover_100m = quote_snapshot.get("turnover_100m", 0)
            _header_ai_result = quote_snapshot.get("header_action_result")
            if isinstance(_header_ai_result, tuple) and len(_header_ai_result) == 2:
                temp_ai_fin, has_ai_fin_fetch = _header_ai_result
            else:
                temp_ai_fin, has_ai_fin_fetch = {}, False

            # 先保留位置，待 EPS / Dynamic Cap / 法人資料完成後回填；畫面順序固定在即時報價正下方。
            eps_price_slot = st.container()
            broker_target_slot = st.container()

            # ==========================================
            # 📌 主要 ETF 持有概況 + 獨立 AI ETF 補查
            # ==========================================
            etf_holders = render_etf_exposure_panel(curr_id=curr_id, stock_name=c_name)

            # ==========================================
            # 📰 近期財報與法說會新聞
            # ==========================================
            render_financial_news_panel(curr_id=curr_id)

            # ==========================================
            # 💼 股票預估價
            # ==========================================
            financial_base = build_financial_base_context(
                stock_id=curr_id,
                info=info,
                current_price=curr_p,
                finmind_key=st.session_state.finmind_key,
                has_ai_financial_snapshot=bool(st.session_state.ai_fetched_financials.get(curr_id)),
            )
            df_rev_bk = financial_base["df_rev_bk"]
            df_per_bk = financial_base["df_per_bk"]
            fm_health = financial_base["fm_health"]
            latest_rev_month = financial_base["latest_rev_month"]
            latest_mom_val = financial_base["latest_mom_val"]
            latest_rev_notice = financial_base["latest_rev_notice"]
            latest_rev_display_label = financial_base["latest_rev_display_label"]
            latest_rev_source = financial_base["latest_rev_source"]
            latest_rev_source_url = financial_base["latest_rev_source_url"]
            latest_rev_source_rule = financial_base["latest_rev_source_rule"]
            latest_rev_announce_date = financial_base["latest_rev_announce_date"]
            latest_rev_announce_month = financial_base["latest_rev_announce_month"]
            latest_rev_revenue_month = financial_base["latest_rev_revenue_month"]
            pe_ratio = financial_base["pe_ratio"]
            pb_ratio = financial_base["pb_ratio"]
            roe = financial_base["roe"]
            sys_de = financial_base["sys_de"]
            gross_margin = financial_base["gross_margin"]
            op_margin = financial_base["op_margin"]
            rev_growth = financial_base["rev_growth"]
            earn_growth = financial_base["earn_growth"]
            t_eps = financial_base["t_eps"]
            sys_f_eps_calc = financial_base["sys_f_eps_calc"]
            sys_latest_quarter_eps = financial_base["sys_latest_quarter_eps"]
            sys_ttm_eps = financial_base["sys_ttm_eps"]
            sys_ttm_eps_source = financial_base.get("sys_ttm_eps_source", "")
            sys_ttm_eps_is_inferred = financial_base.get("sys_ttm_eps_is_inferred", False)
            sys_fiscal_year_eps = financial_base["sys_fiscal_year_eps"]
            sys_forward_eps_system = financial_base["sys_forward_eps_system"]
        
            if latest_rev_notice:
                st.info(f"📅 月營收公告月份提示：{latest_rev_notice}")

            if financial_base["show_ai_financial_warning"]:
                st.warning("⚠️ **全球連線受阻**：目前免費資料庫限制了部分股票的抓取。👉 **解決方案**：請點擊上方【🪄 啟動 AI 全方位校對與補齊財報】讓 AI 強制為您抓回最新數據！")

            ai_financial_context = build_ai_financial_context(
                stock_id=curr_id,
                info=info,
                ai_financial_store=st.session_state.ai_fetched_financials,
            )
            ai_fin = ai_financial_context["ai_fin"]
            has_ai_fin_fetch = ai_financial_context["has_ai_fin_fetch"]
            ai_pe = ai_financial_context["ai_pe"]
            ai_pb = ai_financial_context["ai_pb"]
            ai_latest_month_eps = ai_financial_context["ai_latest_month_eps"]
            ai_latest_quarter_eps = ai_financial_context["ai_latest_quarter_eps"]
            ai_previous_quarter_eps = ai_financial_context["ai_previous_quarter_eps"]
            ai_last_two_quarter_eps = ai_financial_context["ai_last_two_quarter_eps"]
            ai_ttm_eps = ai_financial_context["ai_ttm_eps"]
            ai_fiscal_year_eps = ai_financial_context["ai_fiscal_year_eps"]
            ai_forward_eps_ai = ai_financial_context["ai_forward_eps_ai"]
            ai_forward_eps_consensus = ai_financial_context["ai_forward_eps_consensus"]
            ai_forward_eps_fy1 = ai_financial_context["ai_forward_eps_fy1"]
            ai_forward_eps_fy2 = ai_financial_context["ai_forward_eps_fy2"]
            ai_forward_eps_fy3 = ai_financial_context["ai_forward_eps_fy3"]
            ai_forward_eps_fy1_year = ai_financial_context["ai_forward_eps_fy1_year"]
            ai_forward_eps_fy2_year = ai_financial_context["ai_forward_eps_fy2_year"]
            ai_forward_eps_fy3_year = ai_financial_context["ai_forward_eps_fy3_year"]
            ai_forward_eps_fy1_source = ai_financial_context["ai_forward_eps_fy1_source"]
            ai_forward_eps_fy2_source = ai_financial_context["ai_forward_eps_fy2_source"]
            ai_forward_eps_fy3_source = ai_financial_context["ai_forward_eps_fy3_source"]
            ai_forward_eps_fy_source_note = ai_financial_context["ai_forward_eps_fy_source_note"]
            ai_forward_eps_fy_basis = ai_financial_context["ai_forward_eps_fy_basis"]
            ai_t_eps = ai_financial_context["ai_t_eps"]
            ai_f_eps_calc = ai_financial_context["ai_f_eps_calc"]
            ai_yoy = ai_financial_context["ai_yoy"]
            ai_gm = ai_financial_context["ai_gm"]
            ai_om = ai_financial_context["ai_om"]
            ai_roe = ai_financial_context["ai_roe"]
            ai_de = ai_financial_context["ai_de"]
            ai_dy = ai_financial_context["ai_dy"]
            ai_fcf = ai_financial_context["ai_fcf"]
            ai_cr = ai_financial_context["ai_cr"]
            ai_shares = ai_financial_context["ai_shares"]
            ai_target_price = ai_financial_context["ai_target_price"]
            ai_hi_val = ai_financial_context["ai_hi_val"]
            ai_me_val = ai_financial_context["ai_me_val"]
            ai_lo_val = ai_financial_context["ai_lo_val"]
            ai_analyst_count = ai_financial_context["ai_analyst_count"]
            ai_target_rationale = ai_financial_context["ai_target_rationale"]
            target_price_source = ai_financial_context["target_price_source"]
            ai_mom = ai_financial_context["ai_mom"]
            if ai_mom is not None: 
                latest_mom_val = ai_mom * 100

            # ==========================================
            # 🧯 資料品質閘門：避免欄位錯位直接進估值模型
            # ==========================================
            sys_vals_for_check = {
                "gross_margin": gross_margin,
                "operating_margin": op_margin,
                "rev_growth": rev_growth,
                "debt_to_equity": sys_de,
            }
            ai_vals_for_check = {
                "gross_margin": ai_gm,
                "operating_margin": ai_om,
                "rev_growth": ai_yoy,
                "debt_to_equity": ai_de,
            }
            corrected_sys, corrected_ai, dq_warnings = validate_and_correct_financial_metrics(
                sys_vals_for_check,
                ai_vals_for_check,
                monthly_rev_df=df_rev_bk,
                stock_id=curr_id,
                stock_name=c_name,
            )
            # ✅ 重要：從這一行開始，所有估值、Markdown 顯示與 AI prompt 都只使用「校正後」資料。
            # 不再讓校驗前的 gross_margin / op_margin / rev_growth / sys_de 進入畫面或公式極限價演算法。
            gross_margin = corrected_sys.get("gross_margin")
            op_margin = corrected_sys.get("operating_margin")
            rev_growth = corrected_sys.get("rev_growth")
            sys_de = corrected_sys.get("debt_to_equity")
            ai_gm = corrected_ai.get("gross_margin")
            ai_om = corrected_ai.get("operating_margin")
            ai_yoy = corrected_ai.get("rev_growth")
            ai_de = corrected_ai.get("debt_to_equity")

            # 明確宣告「顯示層專用」變數，避免日後維護時誤拿校驗前欄位組 Markdown。
            display_rev_growth = rev_growth
            display_ai_yoy = ai_yoy
            display_gross_margin = gross_margin
            display_operating_margin = op_margin
            display_ai_gross_margin = ai_gm
            display_ai_operating_margin = ai_om
            display_debt_to_equity = sys_de
            display_ai_debt_to_equity = ai_de

            if dq_warnings:
                # 右下角短提示：讓操盤手知道資料已被校正，不是靜默改值
                toast_key = f"dq_toast_{curr_id}_{hash(tuple(dq_warnings))}"
                if not st.session_state.get(toast_key, False):
                    try:
                        st.toast(f"🩺 目前標的 {c_name} ({curr_id}) 觸發資料品質校驗，已啟動自動校正／NULL 防護。", icon="🩺")
                    except Exception:
                        pass
                    st.session_state[toast_key] = True

                with st.expander("🩺 資料品質校驗提醒", expanded=True):
                    for w in dq_warnings:
                        st.warning(w)
        
            if latest_mom_val is not None:
                latest_mom_str = f"{latest_mom_val:.2f}%"
            else:
                latest_mom_str = "N/A"
        
            # 設定 AI 標籤與時間後綴
            raw_ai_period = str(ai_fin.get('data_period', '')).replace('None', '').strip() if has_ai_fin_fetch else ""
            ai_label = "AI捉取"
            ai_period_val = f"({raw_ai_period})" if raw_ai_period else ""
            ai_ttm_has_trace = bool(
                raw_ai_period
                or get_ai_field_source_meta(ai_fin, "ttm_eps")
                or get_ai_field_source_meta(ai_fin, "trailing_eps")
            )
            ttm_eps_adoption = build_ttm_eps_adoption(
                system_ttm_eps=sys_ttm_eps,
                ai_ttm_eps=ai_ttm_eps,
                current_price=curr_p,
                pe_ratio=pe_ratio,
                system_source=sys_ttm_eps_source or "yfinance trailingEps",
                ai_source="AI/外部校對近四季 EPS 合計",
                ai_has_trace=ai_ttm_has_trace,
                system_is_inferred=sys_ttm_eps_is_inferred,
            )
        
            # 🚀 在目標價 html 生成前，先宣告給 prompt 用的純文字變數，絕對防禦 NameError
            ai_tp_str = f"{ai_target_price:.1f}" if ai_target_price is not None else "未捕捉到"
            target_price_html = ""
            cap_warning_html = ""

            eff_pe = pe_ratio if pe_ratio is not None else ai_pe
            eff_pb = pb_ratio if pb_ratio is not None else ai_pb
            eff_t_eps = ttm_eps_adoption.get("adopted_value")
            eff_rg = rev_growth if rev_growth is not None else ai_yoy
            eff_eg = earn_growth if earn_growth is not None else ai_yoy
            eff_gm = gross_margin if gross_margin is not None else ai_gm
            eff_om = op_margin if op_margin is not None else ai_om
            eff_roe = roe if roe is not None else ai_roe
            eff_de = sys_de if sys_de is not None else ai_de

            if eff_pe and eff_pe > 0 and eff_pb and eff_pb > 0:
                eff_roe = eff_pb / eff_pe
                roe = eff_roe 
            
            if ai_pe and ai_pe > 0 and ai_pb and ai_pb > 0:
                ai_roe = ai_pb / ai_pe
        
            # 只有已按下 AI 財報補齊且 AI 有基礎欄位時，才推算 AI Forward EPS。
            # 未按 AI 按鈕時，不得把系統值包裝成「AI推估」。
            if has_ai_fin_fetch and ai_f_eps_calc is None and ai_t_eps is not None and ai_yoy is not None and -1 <= ai_yoy <= 5:
                ai_f_eps_calc = ai_t_eps * (1 + ai_yoy)
                # 這是 AI TTM EPS × AI 成長率推估，不是法人共識。
                ai_forward_eps_ai = ai_f_eps_calc
            
            if sys_f_eps_calc is None and t_eps is not None and earn_growth is not None and -1 <= earn_growth <= 5:
                sys_f_eps_calc = t_eps * (1 + earn_growth)
            sys_forward_eps_system = sys_f_eps_calc

            dynamic_cap_context = build_dynamic_cap_context(
                stock_id=curr_id,
                stock_name=c_name,
                has_ai_fin_fetch=has_ai_fin_fetch,
                ai_fin=ai_fin,
                raw_ai_period=raw_ai_period,
                gross_margin=gross_margin,
                ai_gm=ai_gm,
                eff_roe=eff_roe,
                ai_roe=ai_roe,
                sys_de=sys_de,
                ai_de=ai_de,
                rev_growth=rev_growth,
                ai_yoy=ai_yoy,
                eff_t_eps=eff_t_eps,
                ai_t_eps=ai_t_eps,
                ai_forward_eps_consensus=ai_forward_eps_consensus,
                ai_forward_eps_ai=ai_forward_eps_ai,
                ai_forward_eps_fy1=ai_forward_eps_fy1,
                sys_forward_eps_system=sys_forward_eps_system,
                ai_f_eps_calc=ai_f_eps_calc,
                pb_ratio=pb_ratio,
                ai_pb=ai_pb,
            )
            cap_adoption_notes = dynamic_cap_context["cap_adoption_notes"]
            cap_gross_margin = dynamic_cap_context["cap_gross_margin"]
            cap_roe = dynamic_cap_context["cap_roe"]
            cap_debt_to_equity = dynamic_cap_context["cap_debt_to_equity"]
            cap_revenue_yoy = dynamic_cap_context["cap_revenue_yoy"]
            cap_ttm_eps = dynamic_cap_context["cap_ttm_eps"]
            cap_ai_forward_eps = dynamic_cap_context["cap_ai_forward_eps"]
            cap_system_forward_eps = dynamic_cap_context["cap_system_forward_eps"]
            cap_adopted_forward_eps = dynamic_cap_context["cap_adopted_forward_eps"]
            cap_divergence_warnings = dynamic_cap_context["cap_divergence_warnings"]

            # EPS 拆欄報告：顯示每一種 EPS 口徑，不再用「目前 EPS」混稱。
            eps_rows = [
                {"field": "最新單月 EPS", "definition": "公司自結或注意股公告的最新月份 EPS；用來看目前獲利支撐", "system_value": None, "ai_value": ai_latest_month_eps, "adopted_value": ai_latest_month_eps, "source": "AI補齊/自結公告" if ai_latest_month_eps is not None else "未取得", "period": ai_period_val or raw_ai_period or "需查最新自結公告", "notes": "若取得，『目前估值』優先採單月 EPS ×12；不得與單季 EPS 混用。"},
                {"field": "最新單季 EPS", "definition": "最新已公告季度 EPS；用來判斷短期獲利動能", "system_value": sys_latest_quarter_eps, "ai_value": ai_latest_quarter_eps, "adopted_value": ai_latest_quarter_eps, "source": "AI補齊" if ai_latest_quarter_eps is not None else "未取得", "period": ai_period_val or raw_ai_period or "需查最新財報", "notes": "系統資料源未穩定提供單季 EPS，避免用 TTM 代替。"},
                {"field": "前一季 EPS", "definition": "最新季度前一季 EPS；與最新單季合計形成近二季 Run-rate", "system_value": None, "ai_value": ai_previous_quarter_eps, "adopted_value": ai_previous_quarter_eps, "source": "AI補齊" if ai_previous_quarter_eps is not None else "未取得", "period": raw_ai_period or "需查前一季財報", "notes": "只用於 Run-rate EPS 動能檢查，不取代 TTM 或 FY1。"},
                {"field": "近二季 EPS 合計", "definition": "最新兩季 EPS 合計；年化後看 AI 高成長股獲利動能", "system_value": None, "ai_value": ai_last_two_quarter_eps, "adopted_value": ai_last_two_quarter_eps, "source": "AI補齊/自動合計" if ai_last_two_quarter_eps is not None else "未取得", "period": raw_ai_period or "最新兩季", "notes": "近二季年化 = 近二季 EPS 合計 ×2；僅為動能口徑。"},
                {"field": "TTM EPS", "definition": "近四季 EPS 合計；用於歷史 P/E", "system_value": sys_ttm_eps, "ai_value": ai_ttm_eps, "adopted_value": eff_t_eps, "source": ttm_eps_adoption.get("adopted_source") or ("AI補齊" if ai_ttm_eps is not None else ("系統備援" if sys_ttm_eps is not None else "未取得")), "period": raw_ai_period if ttm_eps_adoption.get("adopted_value") == ai_ttm_eps and ai_ttm_eps is not None else (sys_ttm_eps_source or "系統/備援"), "notes": (ttm_eps_adoption.get("adopted_rule") or "近四季 EPS 合計優先；yfinance trailingEps 只作備援。") + ("；" + "；".join(ttm_eps_adoption.get("warnings") or []) if ttm_eps_adoption.get("warnings") else "")},
                {"field": "完整年度 EPS", "definition": "最近完整會計年度 EPS；用來看年度基準", "system_value": sys_fiscal_year_eps, "ai_value": ai_fiscal_year_eps, "adopted_value": ai_fiscal_year_eps, "source": "AI補齊" if ai_fiscal_year_eps is not None else "未取得", "period": raw_ai_period or "需查年報", "notes": "不得用 TTM EPS 直接冒充完整年度 EPS。"},
                {"field": "Forward EPS－系統", "definition": "yfinance forwardEps；缺值時由 TTM EPS × 成長率推估", "system_value": sys_forward_eps_system, "ai_value": None, "adopted_value": sys_forward_eps_system, "source": "系統/反推" if sys_forward_eps_system is not None else "未取得", "period": "forwardEps 或 earningsGrowth 推估", "notes": "用於系統 Forward P/E 與公式估值；若後續判定年期錯位，公式合理價會降權採 FY1 EPS。"},
                {"field": "Forward EPS－AI", "definition": "AI 從新聞/券商報告抓取或推估的 Forward EPS", "system_value": None, "ai_value": ai_forward_eps_ai, "adopted_value": ai_forward_eps_ai, "source": "AI補齊" if ai_forward_eps_ai is not None else "未取得", "period": raw_ai_period or "AI未揭露", "notes": "與法人共識 EPS 分開，避免單一來源誤當共識。"},
                {"field": "Forward EPS－法人共識", "definition": "多家法人共識 EPS；若無明確樣本則為 NULL", "system_value": None, "ai_value": ai_forward_eps_consensus, "adopted_value": ai_forward_eps_consensus, "source": "AI/法人共識" if ai_forward_eps_consensus is not None else "未取得", "period": raw_ai_period or "AI未揭露", "notes": "後續可操作估值應優先考慮此欄；無共識不可視為強共識。"},
            ]
            eps_report_df = build_eps_breakdown_report(eps_rows)
            render_eps_breakdown_panel(eps_report_df)

            # ==========================================
            # 🚀 財務儀表板 (乾淨版)
            # ==========================================
            col_eps1, col_eps2 = st.columns([1, 1])
            with col_eps1:
                target_peg_adj = st.selectbox(
                    "🎯 估值情境 (目標 PEG)", 
                    [1.0, 1.2, 1.5], 
                    format_func=lambda x: "保守 (1.0x)" if x==1.0 else ("穩健 (1.2x)" if x==1.2 else "樂觀高空 (1.5x)"),
                    index=0,
                    help="教練密技：目標價逆推公式的乘數。大盤熱度高或作夢空間大時可調升至 1.5。"
                )
            with col_eps2:
                # ⚙️ 第 17-B 階段：Dynamic Cap 2.0 初算。
                # 此處使用已取得的 EPS / 毛利率 / ROE / 題材 / 流動性資料建立可解釋倍率。
                try:
                    dynamic_cap_pack = calculate_dynamic_cap_v2(
                        stock_id=curr_id,
                        stock_name=c_name,
                        current_price=curr_p,
                        info=info,
                        hist_data=hist,
                        industry_profile=industry_profile,
                        gross_margin=cap_gross_margin,
                        operating_margin=eff_om,
                        roe=cap_roe,
                        debt_to_equity=cap_debt_to_equity,
                        revenue_yoy=cap_revenue_yoy,
                        free_cash_flow=ai_fcf,
                        ttm_eps=cap_ttm_eps,
                        system_forward_eps=cap_system_forward_eps,
                        ai_forward_eps=cap_ai_forward_eps,
                        consensus_forward_eps=ai_forward_eps_consensus,
                        ai_ttm_eps=ai_t_eps,
                        pb_ratio=eff_pb,
                        divergence_warnings=cap_divergence_warnings,
                        dq_warnings=dq_warnings,
                    )
                except Exception as e:
                    log_exception("DynamicCapV2", "ui_main:calculate_dynamic_cap_v2", e)
                    dynamic_cap_pack = {
                        "available": False,
                        "valuation_mode": "v18_2_error",
                        "v18_2_caps_available": False,
                        "cap_eps_basis": industry_profile.get("dynamic_cap_v18_2_eps_basis", "insufficient"),
                        "final_cap": None,
                        "report": pd.DataFrame(),
                        "warnings": ["Dynamic Cap v18.2 計算失敗；為避免舊倍率污染，不回退產業預設值。"],
                    }

                if dynamic_cap_pack.get("available") and dynamic_cap_pack.get("final_cap") is not None:
                    suggested_cap = float(dynamic_cap_pack.get("final_cap"))
                    # 第 17-B-3：保存 Dynamic Cap 實際採用值與 AI 校對採用備註，供 UI 與打包提示詞使用。
                    dynamic_cap_pack["cap_adoption_notes"] = cap_adoption_notes
                    dynamic_cap_pack["cap_inputs"] = {
                        "gross_margin": cap_gross_margin,
                        "operating_margin": eff_om,
                        "roe": cap_roe,
                        "debt_to_equity": cap_debt_to_equity,
                        "revenue_yoy": cap_revenue_yoy,
                        "free_cash_flow": ai_fcf,
                        "ttm_eps": cap_ttm_eps,
                        "system_forward_eps": cap_system_forward_eps,
                        "ai_forward_eps": cap_ai_forward_eps,
                        "adopted_valuation_forward_eps": cap_adopted_forward_eps,
                        "adopted_fy1_eps": ai_forward_eps_fy1,
                        "adopted_fy2_eps": ai_forward_eps_fy2,
                        "adopted_fy3_eps": ai_forward_eps_fy3,
                        "fy1_year": ai_forward_eps_fy1_year,
                        "fy2_year": ai_forward_eps_fy2_year,
                        "fy3_year": ai_forward_eps_fy3_year,
                        "fy1_source": ai_forward_eps_fy1_source,
                        "fy2_source": ai_forward_eps_fy2_source,
                        "fy3_source": ai_forward_eps_fy3_source,
                        "fy_eps_source_note": ai_forward_eps_fy_source_note,
                        "fy_eps_basis": ai_forward_eps_fy_basis,
                        "valuation_eps_rule": "v18.2 TTM 參考倍率僅能搭配 TTM EPS；暫行前瞻倍率僅搭配同年度 FY1 EPS；不得用 TTM 倍率直接乘 FY1/FY2/FY3。",
                    }
                    _cap_low = dynamic_cap_pack.get("operable_cap_low")
                    _cap_high = dynamic_cap_pack.get("operable_cap_high")
                    if _cap_low is not None and _cap_high is not None:
                        cap_reason = f"Dynamic Cap v18.2 逐股倍率：Company Base {suggested_cap:.2f}x，可操作參考 {float(_cap_low):.2f}～{float(_cap_high):.2f}x；Soft / Hard 與 EPS 適用口徑依清冊鎖定。"
                    else:
                        cap_reason = f"Dynamic Cap v18.2 Company Base：{suggested_cap:.2f}x；不回退舊版，不以市場熱度上修。"
                else:
                    suggested_cap = 0.0
                    _v18_status = dynamic_cap_pack.get("v18_2_status") or industry_profile.get("dynamic_cap_v18_2_status") or "v18.2 倍率未建立"
                    cap_reason = f"{_v18_status}：本股不輸出 P/E Base/Soft/Hard 或公式價，且不回退 v18.1 / taxonomy 預設倍率。"

                cap_refresh_token = st.session_state.get(f"dynamic_cap_refresh_token_{curr_id}", "base")
                target_pe_cap = st.number_input(
                    "⚙️ 逐股本益比倍率 (Dynamic Cap v18.2)",
                    value=float(suggested_cap),
                    step=0.1,
                    key=f"dynamic_cap_input_{curr_id}_{cap_refresh_token}",
                    disabled=dynamic_cap_pack.get("v18_2_caps_available") is False,
                    help="v18.2 依逐股清冊採 Company Base / Soft / Hard；市場熱度不上修倍率，TTM 參考倍率不得乘 FY1/FY2/FY3 EPS。"
                )
                if dynamic_cap_pack.get("available"):
                    # 使用者仍可手動覆寫 Cap；若覆寫，估值公式採手動值，拆解表仍保留系統建議值。
                    dynamic_cap_pack["user_selected_cap"] = target_pe_cap
                st.markdown(f"<div style='color:#00bfff; font-size:0.75rem; margin-top:-10px; line-height:1.2;'>💡 {cap_reason}</div>", unsafe_allow_html=True)
                if cap_adoption_notes:
                    with st.expander("🔄 Dynamic Cap 2.0 採用 AI 校對值紀錄", expanded=False):
                        for note in cap_adoption_notes[:20]:
                            st.caption(f"- {note}")

            is_base_normalized = False 

            eff_f_eps = sys_f_eps_calc
            eps_source_text = f"海外系統或反推 ({eff_f_eps:.2f}元)" if eff_f_eps is not None else "系統預估 (無資料)"
            
            # 使用新的排版函數呼叫
            f_eps_display = build_cmp_dual_str(t_eps, sys_f_eps_calc, ai_t_eps, ai_f_eps_calc, 'num', 'num', 'AI推估', show_ai_missing=has_ai_fin_fetch, period=ai_period_val)
    
            sys_forward_pe = s_float(info.get('forwardPE'))
            if sys_forward_pe is None and eff_f_eps is not None and eff_f_eps > 0: sys_forward_pe = curr_p / eff_f_eps
        
            ai_fpe = curr_p / ai_f_eps_calc if has_ai_fin_fetch and ai_f_eps_calc and ai_f_eps_calc > 0 else None
            eff_forward_pe = sys_forward_pe if sys_forward_pe is not None else ai_fpe
        
            if eff_f_eps is not None and t_eps is not None and t_eps > 0:
                if t_eps < 0.5:
                    safe_base_eps = 0.5
                    is_base_normalized = True
                else: safe_base_eps = t_eps
                real_cg = (eff_f_eps - safe_base_eps) / safe_base_eps
            else: real_cg = earn_growth
        
            orig_peg = sys_forward_pe / (real_cg * 100) if sys_forward_pe is not None and real_cg is not None and real_cg > 0 else None
        
            ai_cg = None
            if has_ai_fin_fetch:
                if ai_f_eps_calc is not None and ai_t_eps is not None and ai_t_eps > 0:
                    safe_base_eps_ai = 0.5 if ai_t_eps < 0.5 else ai_t_eps
                    ai_cg = (ai_f_eps_calc - safe_base_eps_ai) / safe_base_eps_ai
                else:
                    ai_cg = ai_yoy
            
            ai_peg = ai_fpe / (ai_cg * 100) if has_ai_fin_fetch and ai_fpe is not None and ai_cg is not None and ai_cg > 0 else None
        
            eff_peg = orig_peg if orig_peg is not None else ai_peg
            if real_cg is not None and real_cg <= 0: eff_peg = -999

            quality_context = build_quality_report_context(
                curr_p=curr_p,
                ai_fin=ai_fin,
                has_ai_fin_fetch=has_ai_fin_fetch,
                raw_ai_period=raw_ai_period,
                dq_warnings=dq_warnings,
                latest_rev_month=latest_rev_month,
                latest_rev_display_label=latest_rev_display_label,
                latest_rev_notice=latest_rev_notice,
                latest_mom_val=latest_mom_val,
                latest_rev_source_url=latest_rev_source_url,
                latest_rev_source_rule=latest_rev_source_rule,
                latest_rev_announce_date=latest_rev_announce_date,
                latest_rev_announce_month=latest_rev_announce_month,
                latest_rev_revenue_month=latest_rev_revenue_month,
                pe_ratio=pe_ratio,
                ai_pe=ai_pe,
                sys_forward_pe=sys_forward_pe,
                ai_fpe=ai_fpe,
                eff_forward_pe=eff_forward_pe,
                orig_peg=orig_peg,
                ai_peg=ai_peg,
                eff_peg=eff_peg,
                pb_ratio=pb_ratio,
                ai_pb=ai_pb,
                ai_latest_month_eps=ai_latest_month_eps,
                sys_latest_quarter_eps=sys_latest_quarter_eps,
                ai_latest_quarter_eps=ai_latest_quarter_eps,
                sys_ttm_eps=sys_ttm_eps,
                ai_ttm_eps=ai_ttm_eps,
                eff_t_eps=eff_t_eps,
                sys_fiscal_year_eps=sys_fiscal_year_eps,
                ai_fiscal_year_eps=ai_fiscal_year_eps,
                sys_forward_eps_system=sys_forward_eps_system,
                ai_forward_eps_consensus=ai_forward_eps_consensus,
                ai_forward_eps_ai=ai_forward_eps_ai,
                ai_f_eps_calc=ai_f_eps_calc,
                ai_forward_eps_fy1=ai_forward_eps_fy1,
                ai_forward_eps_fy2=ai_forward_eps_fy2,
                ai_forward_eps_fy3=ai_forward_eps_fy3,
                ai_forward_eps_fy1_year=ai_forward_eps_fy1_year,
                ai_forward_eps_fy2_year=ai_forward_eps_fy2_year,
                ai_forward_eps_fy3_year=ai_forward_eps_fy3_year,
                ai_forward_eps_fy1_source=ai_forward_eps_fy1_source,
                ai_forward_eps_fy2_source=ai_forward_eps_fy2_source,
                ai_forward_eps_fy3_source=ai_forward_eps_fy3_source,
                rev_growth=rev_growth,
                ai_yoy=ai_yoy,
                eff_rg=eff_rg,
                ai_mom=ai_mom,
                gross_margin=gross_margin,
                ai_gm=ai_gm,
                eff_gm=eff_gm,
                op_margin=op_margin,
                ai_om=ai_om,
                eff_om=eff_om,
                roe=roe,
                ai_roe=ai_roe,
                eff_roe=eff_roe,
                sys_de=sys_de,
                ai_de=ai_de,
                eff_de=eff_de,
                ttm_eps_adoption=ttm_eps_adoption,
            )
            quality_rows = quality_context["quality_rows"]
            dq_report_df = quality_context["dq_report_df"]
            dq_note_text = quality_context["dq_note_text"]
            ai_period_text = quality_context["ai_period_text"]
            latest_rev_period = quality_context["latest_rev_period"]
            rev_is_stale = quality_context["rev_is_stale"]
            _fy_year_display_safe = fy_year_display_safe
            render_financial_quality_report_panel(dq_report_df)
        
            # 17-C-16：倍率分層。FY 年度估值使用模型庫 base / soft / hard，
            # 手動情境若未調整，預設使用 FY1 base，避免把 Dynamic Cap 中性倍率誤當年度手動倍率。
            multiple_context = build_multiple_context(
                target_pe_cap=target_pe_cap,
                suggested_cap=suggested_cap,
                dynamic_cap_pack=dynamic_cap_pack,
                industry_profile=industry_profile,
                eff_f_eps=eff_f_eps,
                has_ai_fin_fetch=has_ai_fin_fetch,
                ai_f_eps_calc=ai_f_eps_calc,
                ai_forward_eps_fy1=ai_forward_eps_fy1,
                ai_forward_eps_fy2=ai_forward_eps_fy2,
                ai_forward_eps_fy3=ai_forward_eps_fy3,
                cap_adopted_forward_eps=cap_adopted_forward_eps,
                sys_latest_quarter_eps=sys_latest_quarter_eps,
                ai_latest_month_eps=ai_latest_month_eps,
                ai_latest_quarter_eps=ai_latest_quarter_eps,
                ai_previous_quarter_eps=ai_previous_quarter_eps,
                ai_last_two_quarter_eps=ai_last_two_quarter_eps,
                eff_t_eps=eff_t_eps,
                raw_ai_period=raw_ai_period,
            )
            operable_pe_cap = multiple_context["operable_pe_cap"]
            base_pe_cap_for_calc = multiple_context["base_pe_cap_for_calc"]
            formula_pe_cap = multiple_context["formula_pe_cap"]
            soft_pe_cap = multiple_context["soft_pe_cap"]
            hard_pe_cap = multiple_context["hard_pe_cap"]
            soft_pe_cap_for_calc = multiple_context["soft_pe_cap_for_calc"]
            hard_pe_cap_for_calc = multiple_context["hard_pe_cap_for_calc"]
            extreme_pe_cap_for_calc = multiple_context["extreme_pe_cap_for_calc"]
            sys_target_price_est = multiple_context["sys_target_price_est"]
            sys_target_price_raw = multiple_context["sys_target_price_raw"]
            formula_eps_for_calc = multiple_context["formula_eps_for_calc"]
            formula_eps_source = multiple_context["formula_eps_source"]
            forward_eps_period_mismatch = multiple_context["forward_eps_period_mismatch"]
            current_eps_raw = multiple_context["current_eps_raw"]
            current_eps_for_valuation = multiple_context["current_eps_for_valuation"]
            current_eps_source = multiple_context["current_eps_source"]
            current_eps_source_detail = multiple_context["current_eps_source_detail"]
            current_eps_formula_note = multiple_context["current_eps_formula_note"]
            current_eps_period = multiple_context["current_eps_period"]
            current_target_price_est = multiple_context["current_target_price_est"]
            run_rate_eps_context = multiple_context["run_rate_eps_context"]
            run_rate_1q_eps_annualized = multiple_context["run_rate_1q_eps_annualized"]
            run_rate_2q_eps_annualized = multiple_context["run_rate_2q_eps_annualized"]
            run_rate_1q_target_price = multiple_context["run_rate_1q_target_price"]
            run_rate_2q_target_price = multiple_context["run_rate_2q_target_price"]
            run_rate_reference_eps = multiple_context["run_rate_reference_eps"]
            run_rate_reference_target_price = multiple_context["run_rate_reference_target_price"]
            run_rate_label = multiple_context["run_rate_label"]
            run_rate_action = multiple_context["run_rate_action"]
            is_capped = multiple_context["is_capped"]
            extreme_target_price = multiple_context["extreme_target_price"]
            extreme_target_price_raw = multiple_context["extreme_target_price_raw"]
            manual_cap_user_adjusted = multiple_context["manual_cap_user_adjusted"]
            manual_cap_input = multiple_context["manual_cap_input"]
            manual_cap_source_text = multiple_context["manual_cap_source_text"]
            manual_cap_for_calc = multiple_context["manual_cap_for_calc"]
            manual_cap_hit_hard = multiple_context["manual_cap_hit_hard"]
            manual_target_price = multiple_context["manual_target_price"]
            ai_target_price_est = multiple_context["ai_target_price_est"]
            ai_is_capped = multiple_context["ai_is_capped"]
            ai_extreme_target_price = multiple_context["ai_extreme_target_price"]
            ai_manual_target_price = multiple_context["ai_manual_target_price"]
            fy1_eps_for_annual = multiple_context["fy1_eps_for_annual"]
            fy1_formula_target_price = multiple_context["fy1_formula_target_price"]
            fy2_formula_target_price = multiple_context["fy2_formula_target_price"]
            fy3_formula_target_price = multiple_context["fy3_formula_target_price"]
            fy1_base_target_price = multiple_context["fy1_base_target_price"]
            fy1_soft_target_price = multiple_context["fy1_soft_target_price"]
            fy1_hard_target_price = multiple_context["fy1_hard_target_price"]
            fy2_base_target_price = multiple_context["fy2_base_target_price"]
            fy2_soft_target_price = multiple_context["fy2_soft_target_price"]
            fy2_hard_target_price = multiple_context["fy2_hard_target_price"]
            fy3_base_target_price = multiple_context["fy3_base_target_price"]
            fy3_soft_target_price = multiple_context["fy3_soft_target_price"]
            fy3_hard_target_price = multiple_context["fy3_hard_target_price"]
            fy1_manual_target_price = multiple_context["fy1_manual_target_price"]

            # 17-C-9c-hotfix44：市場 / 法人隱含 Forward P/E 對照。用來解釋現價、法人價與系統估值差距。
            implied_context = build_implied_pe_context(
                current_price=curr_p,
                adopted_forward_eps=cap_adopted_forward_eps,
                broker_target_avg=ai_me_val,
                broker_target_high=ai_hi_val,
                broker_target_low=ai_lo_val,
                hard_pe_cap=hard_pe_cap,
                soft_pe_cap=soft_pe_cap,
                operable_pe_cap=operable_pe_cap,
                dynamic_cap_pack=dynamic_cap_pack,
            )
            implied_eps = implied_context["implied_eps"]
            market_implied_pe = implied_context["market_implied_pe"]
            target_avg_implied_pe = implied_context["target_avg_implied_pe"]
            target_high_implied_pe = implied_context["target_high_implied_pe"]
            target_low_implied_pe = implied_context["target_low_implied_pe"]
            implied_status = implied_context["implied_status"]
            implied_html = implied_context["implied_html"]

            # ==========================================
            # ⚠️ 系統 / AI 分歧警告：EPS / YoY / PEG / 合理價 / D/E
            # ==========================================
            divergence_warnings = build_divergence_warnings(
                system_forward_eps=sys_forward_eps_system,
                ai_forward_eps=ai_f_eps_calc,
                system_yoy=rev_growth,
                ai_yoy=ai_yoy,
                system_peg=orig_peg,
                ai_peg=ai_peg,
                system_forward_pe=sys_forward_pe,
                ai_forward_pe=ai_fpe,
                system_growth_yoy=real_cg,
                ai_growth_yoy=ai_cg,
                system_fair_value=sys_target_price_est,
                ai_fair_value=ai_target_price_est,
                system_de=sys_de,
                ai_de=ai_de,
                system_pb=pb_ratio,
                ai_pb=ai_pb,
                stock_id=curr_id,
                stock_name=c_name,
            )
            if isinstance(forward_eps_period_mismatch, dict) and forward_eps_period_mismatch.get("has_mismatch"):
                divergence_warnings.append({
                    "規則": "Forward EPS 年期錯位",
                    "嚴重度": "warning",
                    "警告文字": forward_eps_period_mismatch.get("note", "系統 Forward EPS 疑似不是 FY1 口徑。"),
                    "系統值": fmt_eps(forward_eps_period_mismatch.get("system_forward_eps")),
                    "AI值": f"FY1 {fmt_eps(forward_eps_period_mismatch.get('fy1_eps'))} / FY2 {fmt_eps(forward_eps_period_mismatch.get('fy2_eps'))}",
                    "差距": "FY1差距 " + ("N/A" if forward_eps_period_mismatch.get("fy1_gap") is None else f"{forward_eps_period_mismatch.get('fy1_gap') * 100:.1f}%"),
                    "建議處理": "公式合理估值已降權採 FY1 EPS；FY2 只用於市場先行定價，不直接作買點。",
                })

            # 2.2 final：分歧警告要回寫到資料品質摘要，避免提示詞出現「有分歧但仍標示系統+AI交叉」。
            try:
                _div_field_map = {
                    "EPS 分歧": ["Forward EPS－系統", "Forward EPS－AI/共識", "Forward EPS－FY1"],
                    "Forward EPS 年期錯位": ["Forward EPS－系統", "Forward EPS－FY1", "Forward EPS－FY2"],
                    "YoY 分歧": ["營收 YoY"],
                    "Forward P/E 分歧": ["Forward P/E"],
                    "PEG 分歧": ["PEG"],
                    "PEG 矛盾": ["PEG"],
                    "預估獲利成長 YoY 分歧": ["預估獲利成長 YoY"],
                    "D/E 分歧": ["D/E"],
                    "P/B 分歧": ["P/B"],
                    "合理價分歧": ["Forward EPS－系統", "Forward EPS－AI/共識"],
                }
                _warn_fields = set()
                for _w in (divergence_warnings or []):
                    _rule = str(_w.get("規則", ""))
                    for _f in _div_field_map.get(_rule, []):
                        _warn_fields.add(_f)
                if dq_report_df is not None and not getattr(dq_report_df, "empty", True) and _warn_fields:
                    _field_col = next((c for c in dq_report_df.columns if "欄位" in str(c) or "項目" in str(c)), dq_report_df.columns[0])
                    _status_col = next((c for c in dq_report_df.columns if "品質" in str(c) or "狀態" in str(c)), None)
                    _note_col = next((c for c in dq_report_df.columns if "備註" in str(c)), None)
                    if _status_col:
                        _mask = dq_report_df[_field_col].astype(str).isin(_warn_fields)
                        dq_report_df.loc[_mask, _status_col] = "⚠️ 系統/AI分歧"
                    if _note_col:
                        _mask = dq_report_df[_field_col].astype(str).isin(_warn_fields)
                        dq_report_df.loc[_mask, _note_col] = dq_report_df.loc[_mask, _note_col].astype(str).apply(
                            lambda x: (x if x and x != "—" else "") + ("；" if x and x != "—" else "") + "系統/AI 分歧，請降權解讀"
                        )
            except Exception as _e:
                try:
                    log_exception("PromptPack", "sync_divergence_to_quality_report", _e)
                except Exception:
                    pass

            if divergence_warnings:
                danger_count = sum(1 for w in divergence_warnings if w.get("嚴重度") == "danger")
                with st.expander(f"⚠️ 系統 / AI 分歧警告（{len(divergence_warnings)} 項）", expanded=True):
                    if danger_count:
                        st.error("偵測到重大估值分歧：請先確認 EPS、YoY、PEG、合理價或 D/E 口徑，再使用買賣結論。")
                    else:
                        st.warning("偵測到資料口徑分歧：建議先檢查來源與期間，再解讀估值。")
                    for w in divergence_warnings:
                        msg = (
                            f"**{w.get('規則', '分歧警告')}**：{w.get('警告文字', '')}  \n"
                            f"系統值：`{w.get('系統值', 'NULL')}`｜AI值：`{w.get('AI值', 'NULL')}`｜差距：`{w.get('差距', 'N/A')}`  \n"
                            f"建議：{w.get('建議處理', '')}"
                        )
                        if w.get("嚴重度") == "danger":
                            st.error(msg)
                        else:
                            st.warning(msg)
                    st_dataframe(build_divergence_warning_report(divergence_warnings), hide_index=True)
        
            # 手動組合區域
            time_str = f", {ai_period_val}" if ai_period_val else ""

            # 1. 預估獲利成長 (YoY)
            eg_str_disp = build_cmp_str(real_cg, ai_cg, 'pct', 'AI推估', show_ai_missing=has_ai_fin_fetch, period=ai_period_val)
            if is_base_normalized: eg_str_disp += "<br><span style='color:#FFD700; font-size:0.75rem; font-weight:normal;'>⚠️ 啟動低基期防護(分母=0.5)</span>"
            eg_color = "#ff4d4d" if real_cg and real_cg > 0 else ("#00cc66" if real_cg and real_cg < 0 else "#fff")
        
            # 2. 前瞻 PEG
            orig_peg_str = f"{orig_peg:.2f}" if orig_peg is not None else ("分母為負" if real_cg is not None and real_cg <= 0 else "N/A")
            peg_str_disp = f"{orig_peg_str}<br><span style='color:#FFD700; font-size:0.85rem;'>(AI推估: {ai_peg:.2f}{time_str})</span>" if ai_peg is not None else orig_peg_str
        
            # 3. 前瞻 P/E
            orig_fpe_str = f"{sys_forward_pe:.1f}x" if sys_forward_pe is not None else "N/A"
            fpe_str = f"{orig_fpe_str}<br><span style='color:#FFD700; font-size:0.85rem;'>(AI推估: {ai_fpe:.1f}x{time_str})</span>" if ai_fpe is not None else orig_fpe_str
        
            pe_str = build_cmp_str(pe_ratio, ai_pe, 'x', ai_label, show_ai_missing=has_ai_fin_fetch, period=ai_period_val)
            # ✅ 顯示字串只吃 validate_and_correct_financial_metrics() 校正後的 display_* 變數。
            rg_str = build_cmp_str(display_rev_growth, display_ai_yoy, 'pct', ai_label, show_ai_missing=has_ai_fin_fetch, period=ai_period_val)
            gm_om_str = build_cmp_dual_str(display_gross_margin, display_operating_margin, display_ai_gross_margin, display_ai_operating_margin, 'pct', 'pct', ai_label, show_ai_missing=has_ai_fin_fetch, period=ai_period_val)
            roe_str = build_cmp_str(roe, ai_roe, 'pct', ai_label, show_ai_missing=has_ai_fin_fetch, period=ai_period_val)
            de_str = build_cmp_str(display_debt_to_equity, display_ai_debt_to_equity, 'pct', ai_label, show_ai_missing=has_ai_fin_fetch, period=ai_period_val)
            pb_str = build_cmp_str(pb_ratio, ai_pb, 'x', ai_label, show_ai_missing=has_ai_fin_fetch, period=ai_period_val)
        
            rg_color = "#ff4d4d" if eff_rg and eff_rg > 0 else ("#00cc66" if eff_rg and eff_rg < 0 else "#fff")
            roe_eval = " <span style='color:#00cc66; font-size:0.8rem; margin-left:5px;' title='大於15%視為資金運用效率極佳 (已透過恆等式校正)'>⭐ 優質</span>" if eff_roe is not None and eff_roe >= 0.15 else ""
        
            if eff_de is None: de_eval = ""
            elif eff_de < 0.5: de_eval = " <span style='color:#00cc66; font-size:0.8rem; margin-left:5px;' title='小於50%財務極度穩健'>⭐ 優質</span>"
            elif eff_de > 1.0: de_eval = " <span style='color:#ff4d4d; font-size:0.8rem; margin-left:5px;' title='大於100%視為高槓桿風險'>⚠️ 高槓桿</span>"
            else: de_eval = " <span style='color:#FFD700; font-size:0.8rem; margin-left:5px;' title='50%~100%為資本密集產業常見合理區間'>🆗 合理</span>"

            if eff_pe is None: pe_color, pe_text = "gray", "數據不足"
            elif eff_pe > 25: pe_color, pe_text = "#ff4d4d", "高成長溢價"
            elif eff_pe < 15: pe_color, pe_text = "#00cc66", "相對便宜"
            else: pe_color, pe_text = "#FFD700", "合理區間"

            if eff_pb is None: pb_color, pb_text = "gray", "數據不足"
            elif eff_pb > 3: pb_color, pb_text = "#ff4d4d", "偏高溢價"
            elif eff_pb < 1.5: pb_color, pb_text = "#00cc66", "具資產保護"
            else: pb_color, pb_text = "#FFD700", "合理區間"

            if eff_forward_pe is None: fpe_color, fpe_text = "gray", "數據不足"
            else:
                if eff_forward_pe > 25: fpe_color, fpe_text = "#ff4d4d", "高成長期望"
                elif eff_forward_pe < 15: fpe_color, fpe_text = "#00cc66", "相對便宜"
                else: fpe_color, fpe_text = "#FFD700", "合理區間"

            if eff_peg == -999: peg_color, peg_text = "gray", "分母為負，無意義"
            elif eff_peg is None: peg_color, peg_text = "gray", "衰退或無數據"
            else: 
                if eff_forward_pe is not None and target_pe_cap is not None and eff_forward_pe > target_pe_cap:
                    peg_color, peg_text = "#ff8c00", "估值過熱(超越Cap)" 
                elif eff_peg > 2: peg_color, peg_text = "#ff4d4d", "透支未來成長"
                elif eff_peg <= 1: peg_color, peg_text = "#00cc66", "低估 (成長性支撐)"
                else: peg_color, peg_text = "#FFD700", "合理區間"
            if sys_target_price_est or ai_target_price_est or ai_forward_eps_fy1 is not None or ai_forward_eps_fy2 is not None or ai_forward_eps_fy3 is not None:
                cap_warning_html = ""
                if dynamic_cap_pack.get("valuation_mode") == "turnaround_event" or dynamic_cap_pack.get("available") is False and dynamic_cap_pack.get("valuation_mode") in {"turnaround_event", "event_chip"}:
                    cap_warning_html += "<br><span style='color:#FFD700; font-weight:bold;'>⚠️ EPS 尚未穩定轉正或產業/題材尚待確認，系統已停用 P/E 公式估值；請改看轉機事件、P/B、營收與單季 EPS 是否連續改善。</span>"
                if dynamic_cap_pack.get("hit_hard_ceiling"):
                    cap_msg = f"🚨 觸發產業 hard ceiling 封頂防護 ({hard_pe_cap:.0f}x)"
                    cap_warning_html = f"<br><span style='color:#ff4d4d; font-weight:bold;'>{cap_msg}，模型輸入偏樂觀，不可直接作為買進乘數！</span>"
                elif is_capped or ai_is_capped:
                    cap_msg = f"⚠️ PEG 公式倍率已受公式合理倍率限制 ({formula_pe_cap:.1f}x)"
                    cap_warning_html = f"<br><span style='color:#FFD700; font-weight:bold;'>{cap_msg}；這不是產業 hard ceiling 封頂。</span>"
                if (extreme_target_price and curr_p > extreme_target_price) or (ai_extreme_target_price and curr_p > ai_extreme_target_price):
                    cap_warning_html += "<br><span style='color:#ff4d4d; font-weight:bold;'>現價已高於 soft 情境公式價，追高風險極大！</span>"
                sys_tp_str = f"{sys_target_price_est:.1f}元" if sys_target_price_est else "N/A"
                ai_tp_est_html = f"<span style='color:#FFD700; font-size:0.95rem;'>(AI推估: {ai_target_price_est:.1f}元{time_str})</span>" if ai_target_price_est else ""            
                sys_ext_str = f"{extreme_target_price:.1f}元" if extreme_target_price else "N/A"
                ai_ext_str = f"<span style='color:#FFD700; font-size:0.95rem;'>(AI推估: {ai_extreme_target_price:.1f}元{time_str})</span>" if ai_extreme_target_price else ""   
                manual_tp_str = f"{manual_target_price:.1f}元" if manual_target_price else "N/A"
                ai_manual_str = f"<span style='color:#FFD700; font-size:0.95rem;'>(AI推估: {ai_manual_target_price:.1f}元{time_str})</span>" if ai_manual_target_price else ""
                if manual_cap_hit_hard:
                    cap_warning_html += f"<br><span style='color:#ff4d4d; font-weight:bold;'>手動情境倍率 {manual_cap_input:.1f}x 已超過產業 hard ceiling，情境價以 {hard_pe_cap:.1f}x 截斷。</span>"
                if isinstance(forward_eps_period_mismatch, dict) and forward_eps_period_mismatch.get("has_mismatch"):
                    cap_warning_html += (
                        "<br><span style='color:#FCD34D; font-weight:bold;'>"
                        "⚠️ Forward EPS 年期錯位疑慮：系統 Forward EPS 更接近 FY2，公式合理估值已降權採 FY1 EPS；FY2 僅作市場先行定價觀察。"
                        "</span>"
                    )
                # 17-C-16：估值顯示口徑重整。
                # 1) 公式合理估值保留「系統 Forward EPS × formula cap」。
                # 2) 不再單列 AI估值，避免與 FY1 EPS 重複；AI/法人 EPS 留在 EPS 來源與 FY 年度層。
                # 3) FY1/FY2/FY3 各自列出 base / soft / hard：基礎 / 樂觀 / 極限。
                # 4) 手動年度情境價以 FY1 EPS × 使用者手動 Cap；若未手動調整，倍率採 FY1 base。
                _fmt_price = fmt_price
                _fmt_eps = fmt_eps
                _fmt_cap = fmt_cap
                fy1_year_text = _fy_year_display_safe(ai_forward_eps_fy1_year)
                fy2_year_text = _fy_year_display_safe(ai_forward_eps_fy2_year)
                fy3_year_text = _fy_year_display_safe(ai_forward_eps_fy3_year)
                fy_calendar_notice = build_forward_eps_calendar_notice(
                    fy1_year=ai_forward_eps_fy1_year,
                    fy2_year=ai_forward_eps_fy2_year,
                    fy3_year=ai_forward_eps_fy3_year,
                )
                fy_sequence_html = (
                    "<div style='color:#D1D5DB; font-size:0.84rem; margin-top:4px;'>"
                    f"FY 年度提示：{fy_calendar_notice.get('fy_sequence_text', '年期未明')}"
                    "</div>"
                )
                fy_rollover_html = ""
                if fy_calendar_notice.get("ui_notice"):
                    fy_rollover_html = (
                        "<div style='background:#2A2407; color:#FDE68A; border:1px solid #6B5E12; "
                        "padding:7px 9px; border-radius:6px; margin-top:8px; line-height:1.5; font-size:0.85rem;'>"
                        f"{fy_calendar_notice.get('ui_notice')}"
                        "</div>"
                    )

                sys_tp_str = _fmt_price(sys_target_price_est)
                sys_raw_tp_str = _fmt_price(sys_target_price_raw)
                current_value_str = _fmt_price(current_target_price_est)
                fy1_range_txt = f"{_fmt_price(fy1_base_target_price)} / {_fmt_price(fy1_soft_target_price)} / {_fmt_price(fy1_hard_target_price)}"
                fy2_range_txt = f"{_fmt_price(fy2_base_target_price)} / {_fmt_price(fy2_soft_target_price)} / {_fmt_price(fy2_hard_target_price)}"
                fy3_range_txt = f"{_fmt_price(fy3_base_target_price)} / {_fmt_price(fy3_soft_target_price)} / {_fmt_price(fy3_hard_target_price)}"
                fy1_manual_txt = _fmt_price(fy1_manual_target_price)

                if fy1_hard_target_price is not None and curr_p is not None and curr_p > fy1_hard_target_price:
                    cap_warning_html += "<br><span style='color:#ff4d4d; font-weight:bold;'>現價已高於 FY1 極限情境價，追高風險極大！</span>"

                tp_est_str = (
                    f"公式合理估值({formula_eps_source}×formula cap): {sys_tp_str}；"
                    f"系統原始公式價(系統Forward EPS×formula cap): {sys_raw_tp_str}；"
                    f"目前估值({current_eps_source}×formula cap): {current_value_str}；"
                    f"Run-rate動能估值(近二季/近一季年化×formula cap): {_fmt_price(run_rate_2q_target_price)} / {_fmt_price(run_rate_1q_target_price)}；"
                    f"FY1年度估值 base/soft/hard(基礎/樂觀/極限): {fy1_range_txt}；"
                    f"FY2第二年度估值 base/soft/hard(基礎/樂觀/極限): {fy2_range_txt}；"
                    f"FY3第三年度估值 base/soft/hard(基礎/樂觀/極限，高風險): {fy3_range_txt}；"
                    f"手動年度情境價(FY1 EPS×{manual_cap_source_text}，壓力測試): {fy1_manual_txt}；"
                    f"年度倍率 base/soft/hard: {_fmt_cap(base_pe_cap_for_calc)} / {_fmt_cap(soft_pe_cap_for_calc)} / {_fmt_cap(hard_pe_cap_for_calc)}；"
                    f"公式倍率: {_fmt_cap(formula_pe_cap)}；手動情境倍率: {_fmt_cap(manual_cap_for_calc)}"
                )

                eps_period_note = raw_ai_period or "系統/推估，請確認 EPS 年期"
                debug_eps = eff_f_eps if eff_f_eps else (ai_f_eps_calc if ai_f_eps_calc else 0)

                _valuation_rows_html = ""
                formula_desc = f"{formula_eps_source} × formula cap，非買賣目標"
                if isinstance(forward_eps_period_mismatch, dict) and forward_eps_period_mismatch.get("has_mismatch"):
                    formula_desc += f"｜原始系統公式價 {_fmt_price(sys_target_price_raw)}｜{forward_eps_period_mismatch.get('note', '')}"

                def _single_valuation_row(_title, _desc, _eps, _cap, _price, _color):
                    return (
                        f"<div style='border-bottom:1px solid #333; padding:6px 0; line-height:1.45;'>"
                        f"<div style='display:flex; justify-content:space-between; gap:10px;'>"
                        f"<span style='color:{_color}; font-weight:bold;'>{_title}</span>"
                        f"<span style='color:{_color}; font-weight:bold; font-size:1.05rem;'>{_fmt_price(_price)}</span>"
                        f"</div>"
                        f"<div style='color:#aaa; font-size:0.78rem;'>{_desc}｜EPS: {_fmt_eps(_eps)}｜倍率: {_fmt_cap(_cap)}</div>"
                        f"</div>"
                    )

                def _fy_matrix_row(_title, _desc, _eps, _base_price, _soft_price, _hard_price, _color):
                    return (
                        f"<div style='border-bottom:1px solid #333; padding:8px 0; line-height:1.45;'>"
                        f"<div style='color:{_color}; font-weight:bold; margin-bottom:5px;'>{_title}</div>"
                        f"<div style='display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:6px;'>"
                        f"<div style='background:#111827; padding:6px 7px; border-radius:6px;'><div style='color:#93C5FD;font-size:0.76rem;'>基礎 base</div><div style='color:#E5E7EB;font-weight:bold;'>{_fmt_price(_base_price)}</div></div>"
                        f"<div style='background:#111827; padding:6px 7px; border-radius:6px;'><div style='color:#FCD34D;font-size:0.76rem;'>樂觀 soft</div><div style='color:#E5E7EB;font-weight:bold;'>{_fmt_price(_soft_price)}</div></div>"
                        f"<div style='background:#111827; padding:6px 7px; border-radius:6px;'><div style='color:#FCA5A5;font-size:0.76rem;'>極限 hard</div><div style='color:#E5E7EB;font-weight:bold;'>{_fmt_price(_hard_price)}</div></div>"
                        f"</div>"
                        f"<div style='color:#aaa; font-size:0.78rem; margin-top:4px;'>{_desc}｜EPS: {_fmt_eps(_eps)}｜倍率 base/soft/hard: {_fmt_cap(base_pe_cap_for_calc)} / {_fmt_cap(soft_pe_cap_for_calc)} / {_fmt_cap(hard_pe_cap_for_calc)}</div>"
                        f"</div>"
                    )

                _valuation_rows_html += _single_valuation_row(
                    "🎯 1. 公式合理估值",
                    formula_desc,
                    formula_eps_for_calc,
                    formula_pe_cap,
                    sys_target_price_est,
                    "#ffffff",
                )
                _valuation_rows_html += _single_valuation_row(
                    "📍 1-1. 目前估值（年化 EPS）",
                    f"{current_eps_source} × formula cap｜{current_eps_source_detail}｜{current_eps_formula_note}｜{current_eps_period}",
                    current_eps_for_valuation,
                    formula_pe_cap,
                    current_target_price_est,
                    "#FCD34D",
                )
                _valuation_rows_html += _single_valuation_row(
                    "⚡ 1-2. Run-rate EPS 動能估值",
                    f"近二季/近一季年化 × formula cap｜{run_rate_label}｜{run_rate_action}",
                    run_rate_reference_eps,
                    formula_pe_cap,
                    run_rate_reference_target_price,
                    "#34D399",
                )
                _valuation_rows_html += _fy_matrix_row(
                    "📅 2. FY1年度估值",
                    f"FY1 EPS 年度主估值參考｜{fy1_year_text}",
                    ai_forward_eps_fy1,
                    fy1_base_target_price,
                    fy1_soft_target_price,
                    fy1_hard_target_price,
                    "#93C5FD",
                )
                _valuation_rows_html += _fy_matrix_row(
                    "📆 3. FY2第二年度估值",
                    f"只用於判斷市場先行定價，不直接當買點｜{fy2_year_text}",
                    ai_forward_eps_fy2,
                    fy2_base_target_price,
                    fy2_soft_target_price,
                    fy2_hard_target_price,
                    "#A7F3D0",
                )
                _valuation_rows_html += _fy_matrix_row(
                    "🚧 4. FY3第三年度估值",
                    f"第三年預估或長期情境，高風險解讀｜{fy3_year_text}",
                    ai_forward_eps_fy3,
                    fy3_base_target_price,
                    fy3_soft_target_price,
                    fy3_hard_target_price,
                    "#FCA5A5",
                )
                _valuation_rows_html += _single_valuation_row(
                    "🛠️ 5. 手動年度情境價",
                    f"FY1 EPS × {manual_cap_source_text}（壓力測試 / 反推現價倍率）",
                    fy1_eps_for_annual,
                    manual_cap_for_calc,
                    fy1_manual_target_price,
                    "#00BFFF",
                )

                target_price_html = f"""
                <div style='background:#1e1e1e; padding:16px 18px; border-radius:10px; border-left:6px solid {peg_color}; margin-top:4px; margin-bottom:20px;'>
                    <div style='display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:12px;'>
                        <div>
                            <div style='font-weight:bold; color:#F3F4F6; font-size:1.25rem;'>📈 前瞻 PEG (Forward PEG)｜詳細估值分層</div>
                            <div style='color:#AAB2C0; font-size:0.88rem; margin-top:4px;'>系統公式與 FY1/FY2/FY3 年度三情境分開顯示；AI/法人 EPS 不再另列重複估值。</div>
                            {fy_sequence_html}
                            {fy_rollover_html}
                        </div>
                        <div style='text-align:right; min-width:170px;'>
                            <div style='background:{peg_color}; color:#000; padding:4px 10px; border-radius:999px; font-size:0.85rem; font-weight:bold; display:inline-block;'>{peg_text}</div>
                            <div style='font-size:2.0rem; font-weight:bold; color:#fff; margin-top:6px; line-height:1.1;'>{peg_str_disp}</div>
                        </div>
                    </div>
                    <div style='border-top:1px solid #333; padding-top:8px; color:#aaa; font-size:0.85rem;'>
                    {_valuation_rows_html}
                    <div style='background:#111827; color:#E5E7EB; padding:7px 9px; border-radius:6px; margin-top:7px; line-height:1.55;'>
                        <b>使用規則</b><br>
                        公式合理估值原則上使用系統 Forward EPS；若偵測到系統 Forward EPS 疑似 FY2 年期錯位，公式價會降權採 FY1 EPS。FY1/FY2/FY3 同時列出 base / soft / hard，分別代表基礎 / 樂觀 / 極限。FY2 只用於市場先行定價判斷；FY3 為高風險遠期情境，不可直接當買點；手動情境若未調整，預設採 FY1 base。
                    </div>
                    <div style='background:#2c2c2c; padding:4px 8px; border-radius:4px; margin-top:4px;'>
                        <small style='color:#00bfff;'>🐛 [底層運算除錯] 系統EPS: {_fmt_eps(eff_f_eps)}｜公式採用 EPS: {_fmt_eps(formula_eps_for_calc)}（{formula_eps_source}）｜目前 EPS: {_fmt_eps(current_eps_raw)}（估值採用 {_fmt_eps(current_eps_for_valuation)}；{current_eps_source}）｜AI/法人 EPS: {_fmt_eps(ai_f_eps_calc)}｜FY1 EPS: {_fmt_eps(ai_forward_eps_fy1)}｜FY2 EPS: {_fmt_eps(ai_forward_eps_fy2)}｜FY3 EPS: {_fmt_eps(ai_forward_eps_fy3)}｜EPS 年期/來源: {eps_period_note}｜formula: {_fmt_cap(formula_pe_cap)}｜base/soft/hard: {_fmt_cap(base_pe_cap_for_calc)} / {_fmt_cap(soft_pe_cap_for_calc)} / {_fmt_cap(hard_pe_cap_for_calc)}｜手動倍率: {_fmt_cap(manual_cap_for_calc)} ({manual_cap_source_text})</small>
                    </div>
                    {implied_html}{cap_warning_html}
                    </div>
                </div>
                """


            # ==========================================
            # 🧭 法人目標價可信度 + 公式估值 / 可操作估值分離
            # ==========================================
            if isinstance(dynamic_cap_pack, dict):
                dynamic_cap_pack["forward_eps_period_mismatch"] = forward_eps_period_mismatch
                dynamic_cap_pack["formula_eps_for_calc"] = formula_eps_for_calc
                dynamic_cap_pack["formula_eps_source"] = formula_eps_source
                dynamic_cap_pack["system_formula_fair_value_raw"] = sys_target_price_raw
            valuation_separation = build_valuation_separation_report(
                current_price=curr_p,
                system_formula_fair_value=sys_target_price_est,
                ai_formula_fair_value=ai_target_price_est,
                system_formula_extreme_value=extreme_target_price,
                ai_formula_extreme_value=ai_extreme_target_price,
                broker_target_avg=ai_me_val,
                broker_target_low=ai_lo_val,
                analyst_count=ai_analyst_count,
                system_forward_eps=sys_forward_eps_system,
                ai_forward_eps=ai_forward_eps_ai,
                consensus_forward_eps=ai_forward_eps_consensus,
                target_pe_cap=target_pe_cap,
                divergence_warnings=divergence_warnings,
                industry_profile=industry_profile,
                dynamic_cap_pack=dynamic_cap_pack,
                pb_ratio=eff_pb,
            )
            target_confidence = valuation_separation.get('target_confidence', classify_target_price_confidence(ai_analyst_count))
            # ==========================================
            # 📆 第 17-C-9c-hotfix44：Forward EPS 年期分層估值
            # ==========================================
            _theme_text_for_pricing = " ".join([
                str(industry_profile.get("themes_text", "")) if isinstance(industry_profile, dict) else "",
                str(industry_profile.get("event_switch_note", "")) if isinstance(industry_profile, dict) else "",
                str(industry_profile.get("risk_flags", "")) if isinstance(industry_profile, dict) else "",
                str(industry_profile.get("primary_valuation", "")) if isinstance(industry_profile, dict) else "",
            ])
            topic_re_rating_flag = (
                (isinstance(industry_profile, dict) and not bool(industry_profile.get("pe_model_suitable", True)))
                or any(k in _theme_text_for_pricing for k in ["題材", "事件", "重評價", "CPO", "玻璃載板", "ASIC", "先進封裝"])
            )
            forward_eps_tier_pack = build_forward_eps_tiered_valuation_report(
                current_price=curr_p,
                broker_target_avg=ai_me_val,
                broker_target_high=ai_hi_val,
                broker_target_low=ai_lo_val,
                ttm_eps=eff_t_eps,
                fy1_eps=ai_forward_eps_fy1,
                fy2_eps=ai_forward_eps_fy2,
                fy3_eps=ai_forward_eps_fy3,
                fy1_year=ai_forward_eps_fy1_year,
                fy2_year=ai_forward_eps_fy2_year,
                fy3_year=ai_forward_eps_fy3_year,
                base_cap=base_pe_cap_for_calc,
                formula_cap=formula_pe_cap,
                operable_cap=operable_pe_cap,
                soft_ceiling=soft_pe_cap,
                hard_ceiling=hard_pe_cap,
                eps_source_note=ai_forward_eps_fy_source_note,
                eps_basis=dynamic_cap_pack.get("cap_eps_basis") or ai_forward_eps_fy_basis,
                theme_re_rating_flag=topic_re_rating_flag,
                revenue_yoy=display_rev_growth,
                revenue_mom=(latest_mom_val / 100.0) if latest_mom_val is not None else ai_mom,
                gross_margin=display_gross_margin,
                operating_margin=display_operating_margin,
                roe=eff_roe,
                analyst_count=ai_analyst_count,
                target_confidence=target_confidence,
                divergence_warnings=divergence_warnings,
                dq_warnings=dq_warnings,
            )
            if not isinstance(forward_eps_tier_pack, dict):
                forward_eps_tier_pack = {"summary": {}, "report": None}
            _ft_summary_safe = forward_eps_tier_pack.get("summary", {}) if isinstance(forward_eps_tier_pack, dict) else {}
            if not isinstance(_ft_summary_safe, dict):
                _ft_summary_safe = {}
            pricing_horizon_pack = _ft_summary_safe.get("pricing_horizon", {}) if isinstance(_ft_summary_safe, dict) else {}
            future_evidence_pack = _ft_summary_safe.get("future_evidence", {}) if isinstance(_ft_summary_safe, dict) else {}

            eps_price_rows = build_eps_price_calculation_rows(
                ttm_eps=eff_t_eps,
                fy1_eps=cap_adopted_forward_eps,
                fy2_eps=ai_forward_eps_fy2,
                fy3_eps=ai_forward_eps_fy3,
                fy1_year=ai_forward_eps_fy1_year,
                fy2_year=ai_forward_eps_fy2_year,
                fy3_year=ai_forward_eps_fy3_year,
                base_cap=base_pe_cap_for_calc,
                soft_cap=soft_pe_cap_for_calc,
                hard_cap=hard_pe_cap_for_calc,
                cap_eps_basis=dynamic_cap_pack.get("cap_eps_basis"),
            )
            with eps_price_slot:
                render_eps_price_calculation_panel(
                    eps_price_rows,
                    cap_eps_basis=dynamic_cap_pack.get("cap_eps_basis"),
                )
            with broker_target_slot:
                target_panel_for_prompt, target_confidence = render_target_price_panel(
                    curr_p=curr_p,
                    ai_hi_val=ai_hi_val,
                    ai_me_val=ai_me_val,
                    ai_lo_val=ai_lo_val,
                    ai_analyst_count=ai_analyst_count,
                    ai_target_rationale=ai_target_rationale,
                    target_confidence=target_confidence,
                    ai_label=ai_label,
                    ai_period_val=ai_period_val,
                    target_price_source=target_price_source,
                )
            # ==========================================
            # 🧪 第 17-C-9c-hotfix44：產業模型單次快照稽核表
            # ==========================================
            snapshot_audit = build_industry_model_snapshot_audit(
                stock_id=curr_id,
                stock_name=c_name,
                current_price=curr_p,
                adopted_forward_eps=cap_adopted_forward_eps,
                market_implied_pe=(curr_p / cap_adopted_forward_eps) if curr_p is not None and cap_adopted_forward_eps is not None and cap_adopted_forward_eps > 0 else None,
                broker_avg_implied_pe=(ai_me_val / cap_adopted_forward_eps) if ai_me_val is not None and cap_adopted_forward_eps is not None and cap_adopted_forward_eps > 0 else None,
                broker_high_implied_pe=(ai_hi_val / cap_adopted_forward_eps) if ai_hi_val is not None and cap_adopted_forward_eps is not None and cap_adopted_forward_eps > 0 else None,
                formula_cap=formula_pe_cap,
                operable_cap_mid=dynamic_cap_pack.get("final_cap") if isinstance(dynamic_cap_pack, dict) else None,
                soft_ceiling=dynamic_cap_pack.get("optimistic_cap") if isinstance(dynamic_cap_pack, dict) else None,
                hard_ceiling=dynamic_cap_pack.get("hard_ceiling_cap") if isinstance(dynamic_cap_pack, dict) else None,
                industry_profile=industry_profile,
                dynamic_cap_pack=dynamic_cap_pack,
                revenue_yoy=display_rev_growth,
                revenue_mom=(latest_mom_val / 100.0) if latest_mom_val is not None else ai_mom,
                gross_margin=display_gross_margin,
                operating_margin=display_operating_margin,
                roe=eff_roe,
                analyst_count=ai_analyst_count,
                target_confidence=target_confidence,
                divergence_warnings=divergence_warnings,
                dq_warnings=dq_warnings,
            )
            val_html = f"""
            <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-bottom:20px;'>
                <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {pe_color};'>
                    <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                        <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>📊 歷史本益比 (Trailing P/E)</div>
                        <div style='background:{pe_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{pe_text}</div>
                    </div>
                    <div style='font-size:1.6rem; font-weight:bold; color:#fff; margin-bottom:10px;'>{pe_str}</div>
                </div>
                <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {fpe_color};'>
                    <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                        <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🚀 前瞻本益比 (Forward P/E)</div>
                        <div style='background:{fpe_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{fpe_text}</div>
                    </div>
                    <div style='font-size:1.6rem; font-weight:bold; color:#fff; margin-bottom:5px;'>{fpe_str}</div>
                    <div style='color:#ffd700; font-size:0.85rem; font-weight:bold;'>基準：{eps_source_text}</div>
                </div>
                <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {pb_color};'>
                    <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                        <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🏦 股價淨值比 (P/B Ratio)</div>
                        <div style='background:{pb_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{pb_text}</div>
                    </div>
                    <div style='font-size:1.6rem; font-weight:bold; color:#fff; margin-bottom:10px;'>{pb_str}</div>
                </div>
            </div>
            """
            render_valuation_detail_panel(
                val_html=val_html,
                target_price_html=target_price_html,
                target_confidence=target_confidence,
                valuation_separation=valuation_separation,
                forward_eps_tier_pack=forward_eps_tier_pack,
                industry_profile=industry_profile,
                snapshot_audit=snapshot_audit,
                dynamic_cap_pack=dynamic_cap_pack,
                ai_analyst_count=ai_analyst_count,
                ai_hi_val=ai_hi_val,
                ai_me_val=ai_me_val,
                ai_lo_val=ai_lo_val,
                ai_target_rationale=ai_target_rationale,
            )

            # ==========================================
            # 🚦 最終操作燈號：可買-小量分批 / 觀望 / 不建議 / 資料分歧-降權判斷 / 資料異常-不可判斷
            # ==========================================
            final_signal = build_final_operation_signal(
                current_price=curr_p,
                valuation_separation=valuation_separation,
                divergence_warnings=divergence_warnings,
                target_confidence=target_confidence,
                industry_profile=industry_profile,
                pe=pe_ratio,
                forward_pe=eff_forward_pe,
                peg=orig_peg,
                pb=pb_ratio,
                roe=eff_roe,
                debt_to_equity=display_debt_to_equity,
                revenue_yoy=display_rev_growth,
                gross_margin=display_gross_margin,
                operating_margin=display_operating_margin,
                has_ai_fin_fetch=has_ai_fin_fetch,
                pricing_horizon=pricing_horizon_pack,
                future_evidence=future_evidence_pack,
            )
            render_final_signal_panel(final_signal)

            render_financial_metric_cards(
                pe_str=pe_str,
                f_eps_display=f_eps_display,
                latest_rev_display_label=latest_rev_display_label,
                rg_color=rg_color,
                rg_str=rg_str,
                latest_mom_val=latest_mom_val,
                latest_mom_str=latest_mom_str,
                eg_color=eg_color,
                eg_str_disp=eg_str_disp,
                gm_om_str=gm_om_str,
                roe_str=roe_str,
                roe_eval=roe_eval,
                de_str=de_str,
                de_eval=de_eval,
            )
        
            render_anomaly_detection_panel(eff_pb=eff_pb, df_rev_bk=df_rev_bk, hist=hist, curr_p=curr_p)
            div_yield = s_float(info.get('dividendYield')) or s_float(info.get('trailingAnnualDividendYield'))
        
            if ai_dy is not None:
                div_yield = ai_dy
            elif div_yield is not None and div_yield > 1.0: 
                div_yield = div_yield / 100.0

            fcf = s_float(info.get('freeCashflow'))
            if fcf is None and fm_health.get('cfo_l'): fcf = fm_health.get('cfo_l')
            if ai_fcf is not None: fcf = ai_fcf
            
            current_ratio = s_float(info.get('currentRatio'))
            if ai_cr is not None: current_ratio = ai_cr

            dy_str = to_pct(div_yield)
            if div_yield is None: dy_color, dy_eval = "gray", "無資料"
            elif div_yield >= 0.05: dy_color, dy_eval = "#ff4d4d", "高息護體(>5%)"
            elif div_yield >= 0.03: dy_color, dy_eval = "#FFD700", "穩健配息"
            else: dy_color, dy_eval = "#00cc66", "殖利率偏低"

            if fcf is None: fcf_str, fcf_color, fcf_eval = "無資料", "gray", "無資料"
            elif fcf > 0: fcf_str, fcf_color, fcf_eval = f"{fcf/100000000:,.0f} 億", "#ff4d4d", "現金流健康"
            else: fcf_str, fcf_color, fcf_eval = f"{fcf/100000000:,.0f} 億", "#00cc66", "⚠️ 留意燒錢風險"

            if current_ratio is None: cr_str, cr_color, cr_eval = "無資料", "gray", "無資料"
            elif current_ratio >= 1.5: cr_str, cr_color, cr_eval = f"{current_ratio:.2f}", "#ff4d4d", "短期無債務風險"
            elif current_ratio >= 1.0: cr_str, cr_color, cr_eval = f"{current_ratio:.2f}", "#FFD700", "流動性及格"
            else: cr_str, cr_color, cr_eval = f"{current_ratio:.2f}", "#00cc66", "⚠️ 流動性吃緊"
        
            f_score_val = fm_health.get('f_score')
            if f_score_val is None: 
                fs_str, fs_color, fs_eval = "無資料", "gray", "資料不足"
            elif f_score_val >= 7: 
                fs_str, fs_color, fs_eval = f"{f_score_val} 分", "#ff4d4d", "⭐ 體質極優"
            elif f_score_val >= 5: 
                fs_str, fs_color, fs_eval = f"{f_score_val} 分", "#FFD700", "🆗 體質及格"
            else: 
                fs_str, fs_color, fs_eval = f"{f_score_val} 分", "#00cc66", "🚨 孱弱/高風險"

            render_defense_health_cards(
                dy_color=dy_color,
                dy_eval=dy_eval,
                dy_str=dy_str,
                fcf_color=fcf_color,
                fcf_eval=fcf_eval,
                fcf_str=fcf_str,
                cr_color=cr_color,
                cr_eval=cr_eval,
                cr_str=cr_str,
                fs_color=fs_color,
                fs_eval=fs_eval,
                fs_str=fs_str,
            )

            chip_panel_state = render_chip_panels(curr_id=curr_id, info=info, ai_shares=ai_shares, eff_eg=eff_eg)
            if chip_panel_state.get("has_institutional_data"):
                f_10d = chip_panel_state.get("f_10d")
                t_10d = chip_panel_state.get("t_10d")
                f_status = chip_panel_state.get("f_status")
                t_status = chip_panel_state.get("t_status")
                trap_warning = chip_panel_state.get("trap_warning")
            inst_str = chip_panel_state.get("inst_str")
            inst_eval = chip_panel_state.get("inst_eval")
            insider_str = chip_panel_state.get("insider_str")
            in_eval = chip_panel_state.get("in_eval")
            share_capital = chip_panel_state.get("share_capital")
            cap_type = chip_panel_state.get("cap_type")
            driver = chip_panel_state.get("driver")
            driver_desc = chip_panel_state.get("driver_desc")
            
            _prompt_df = prompt_df
            _prompt_warnings = prompt_warnings
            _prompt_quality_summary = prompt_quality_summary
            _prompt_ai_source_summary = prompt_ai_source_summary

            # 面板核心數值（系統/AI/推估）
            ctx_tp_est = _nullize_text(tp_est_str)
            panel_pe = _nullize_text(pe_str)
            panel_fpe = _nullize_text(fpe_str)
            panel_pb = _nullize_text(pb_str)
            panel_peg = _nullize_text(peg_str_disp)
            panel_eps = _nullize_text(f_eps_display)
            # ✅ AI prompt / 戰情面板也沿用已校正後的 Markdown 字串，避免 prompt 吃到舊值。
            panel_rg = _nullize_text(rg_str)
            panel_eg = _nullize_text(eg_str_disp)
            panel_gmom = _nullize_text(gm_om_str)
            panel_roe = _nullize_text(roe_str)
            panel_de = _nullize_text(de_str)

            prompt_target_context = build_prompt_target_context(
                target_panel=target_panel_for_prompt,
                ai_fin=ai_fin,
                info=info,
                ai_hi_val=ai_hi_val,
                ai_me_val=ai_me_val,
                ai_lo_val=ai_lo_val,
                ai_analyst_count=ai_analyst_count,
            )
            _target_panel = prompt_target_context["target_panel"]
            _tp_hi = prompt_target_context["tp_hi"]
            _tp_me = prompt_target_context["tp_me"]
            _tp_lo = prompt_target_context["tp_lo"]
            prompt_hi_str = prompt_target_context["prompt_hi_str"]
            prompt_me_str = prompt_target_context["prompt_me_str"]
            prompt_lo_str = prompt_target_context["prompt_lo_str"]
            prompt_analyst_count = prompt_target_context["prompt_analyst_count"]
            prompt_target_source = prompt_target_context["prompt_target_source"]
            prompt_target_confidence = prompt_target_context["prompt_target_confidence"]
            target_confidence = prompt_target_confidence
            prompt_target_rationale = prompt_target_context["prompt_target_rationale"]

            ai_source_trace_df_for_prompt = build_ai_source_trace_report(temp_ai_fin) if isinstance(temp_ai_fin, dict) else pd.DataFrame()
            ai_validation_warnings_for_prompt = temp_ai_fin.get("_ai_validation_warnings", []) if isinstance(temp_ai_fin, dict) else []
            ai_validation_status_for_prompt = temp_ai_fin.get("_ai_validation_status", "") if isinstance(temp_ai_fin, dict) else ""
            final_signal_report_for_prompt = final_signal.get("report") if isinstance(final_signal, dict) else None
            valuation_report_for_prompt = valuation_separation.get("report") if isinstance(valuation_separation, dict) else None
            target_confidence_report_for_prompt = prompt_target_context["target_confidence_report_for_prompt"]
            industry_report_for_prompt = build_industry_valuation_model_report(industry_profile)
            dynamic_cap_report_for_prompt = dynamic_cap_pack.get("report") if isinstance(dynamic_cap_pack, dict) else None

            prompt_dynamic_cap_fallbacks = {
                "eff_t_eps": locals().get("eff_t_eps"),
                "sys_forward_eps_system": locals().get("sys_forward_eps_system"),
                "ai_f_eps_calc": locals().get("ai_f_eps_calc"),
                "cap_adopted_forward_eps": locals().get("cap_adopted_forward_eps"),
                "ai_forward_eps_fy1": locals().get("ai_forward_eps_fy1"),
                "ai_forward_eps_fy2": locals().get("ai_forward_eps_fy2"),
                "ai_forward_eps_fy3": locals().get("ai_forward_eps_fy3"),
                "ai_forward_eps_fy1_year": locals().get("ai_forward_eps_fy1_year"),
                "ai_forward_eps_fy2_year": locals().get("ai_forward_eps_fy2_year"),
                "ai_forward_eps_fy3_year": locals().get("ai_forward_eps_fy3_year"),
                "ai_forward_eps_fy_source_note": locals().get("ai_forward_eps_fy_source_note"),
            }

            def _prompt_dynamic_cap_core(pack, mode="research"):
                return prompt_dynamic_cap_core(
                    pack,
                    mode=mode,
                    divergence_warnings=divergence_warnings,
                    final_signal=final_signal,
                    fallback_values=prompt_dynamic_cap_fallbacks,
            )

            _prompt_forward_eps_tier_core = prompt_forward_eps_tier_core

            prompt_peg_values = {
                "eff_f_eps": locals().get("eff_f_eps"),
                "formula_eps_for_calc": locals().get("formula_eps_for_calc"),
                "formula_eps_source": locals().get("formula_eps_source"),
                "forward_eps_period_mismatch": locals().get("forward_eps_period_mismatch"),
                "ai_forward_eps_fy1": locals().get("ai_forward_eps_fy1"),
                "ai_forward_eps_fy2": locals().get("ai_forward_eps_fy2"),
                "ai_forward_eps_fy3": locals().get("ai_forward_eps_fy3"),
                "ai_forward_eps_fy1_year": locals().get("ai_forward_eps_fy1_year"),
                "ai_forward_eps_fy2_year": locals().get("ai_forward_eps_fy2_year"),
                "ai_forward_eps_fy3_year": locals().get("ai_forward_eps_fy3_year"),
                "fy1_eps_for_annual": locals().get("fy1_eps_for_annual"),
                "formula_pe_cap": locals().get("formula_pe_cap"),
                "base_pe_cap_for_calc": locals().get("base_pe_cap_for_calc"),
                "soft_pe_cap_for_calc": locals().get("soft_pe_cap_for_calc"),
                "hard_pe_cap_for_calc": locals().get("hard_pe_cap_for_calc"),
                "manual_cap_for_calc": locals().get("manual_cap_for_calc"),
                "manual_cap_source_text": locals().get("manual_cap_source_text"),
                "sys_target_price_est": locals().get("sys_target_price_est"),
                "sys_target_price_raw": locals().get("sys_target_price_raw"),
                "current_eps_raw": locals().get("current_eps_raw"),
                "current_eps_for_valuation": locals().get("current_eps_for_valuation"),
                "current_eps_source": locals().get("current_eps_source"),
                "current_eps_formula_note": locals().get("current_eps_formula_note"),
                "current_eps_period": locals().get("current_eps_period"),
                "current_target_price_est": locals().get("current_target_price_est"),
                "run_rate_1q_eps_annualized": locals().get("run_rate_1q_eps_annualized"),
                "run_rate_2q_eps_annualized": locals().get("run_rate_2q_eps_annualized"),
                "run_rate_1q_target_price": locals().get("run_rate_1q_target_price"),
                "run_rate_2q_target_price": locals().get("run_rate_2q_target_price"),
                "run_rate_reference_eps": locals().get("run_rate_reference_eps"),
                "run_rate_reference_target_price": locals().get("run_rate_reference_target_price"),
                "run_rate_label": locals().get("run_rate_label"),
                "run_rate_action": locals().get("run_rate_action"),
                "fy1_base_target_price": locals().get("fy1_base_target_price"),
                "fy1_soft_target_price": locals().get("fy1_soft_target_price"),
                "fy1_hard_target_price": locals().get("fy1_hard_target_price"),
                "fy2_base_target_price": locals().get("fy2_base_target_price"),
                "fy2_soft_target_price": locals().get("fy2_soft_target_price"),
                "fy2_hard_target_price": locals().get("fy2_hard_target_price"),
                "fy3_base_target_price": locals().get("fy3_base_target_price"),
                "fy3_soft_target_price": locals().get("fy3_soft_target_price"),
                "fy3_hard_target_price": locals().get("fy3_hard_target_price"),
                "fy1_manual_target_price": locals().get("fy1_manual_target_price"),
            }

            def _prompt_peg_valuation_layers():
                _mismatch_pack = prompt_peg_values.get("forward_eps_period_mismatch")
                _mismatch_note = _mismatch_pack.get("note") if isinstance(_mismatch_pack, dict) and _mismatch_pack.get("has_mismatch") else None
                return prompt_peg_valuation_layers(
                    system_eps=prompt_peg_values.get("formula_eps_for_calc"),
                    system_eps_raw=prompt_peg_values.get("eff_f_eps"),
                    fy1_eps=prompt_peg_values.get("ai_forward_eps_fy1"),
                    fy2_eps=prompt_peg_values.get("ai_forward_eps_fy2"),
                    fy3_eps=prompt_peg_values.get("ai_forward_eps_fy3"),
                    fy1_year=prompt_peg_values.get("ai_forward_eps_fy1_year"),
                    fy2_year=prompt_peg_values.get("ai_forward_eps_fy2_year"),
                    fy3_year=prompt_peg_values.get("ai_forward_eps_fy3_year"),
                    fy1_eps_for_annual=prompt_peg_values.get("fy1_eps_for_annual"),
                    formula_cap=prompt_peg_values.get("formula_pe_cap"),
                    base_cap=prompt_peg_values.get("base_pe_cap_for_calc"),
                    soft_cap=prompt_peg_values.get("soft_pe_cap_for_calc"),
                    hard_cap=prompt_peg_values.get("hard_pe_cap_for_calc"),
                    manual_cap=prompt_peg_values.get("manual_cap_for_calc"),
                    manual_cap_source=prompt_peg_values.get("manual_cap_source_text"),
                    system_price=prompt_peg_values.get("sys_target_price_est"),
                    system_raw_price=prompt_peg_values.get("sys_target_price_raw"),
                    formula_eps_source=prompt_peg_values.get("formula_eps_source"),
                    forward_eps_mismatch_note=_mismatch_note,
                    current_eps=prompt_peg_values.get("current_eps_for_valuation"),
                    current_eps_raw=prompt_peg_values.get("current_eps_raw"),
                    current_eps_source=prompt_peg_values.get("current_eps_source"),
                    current_eps_formula_note=prompt_peg_values.get("current_eps_formula_note"),
                    current_eps_period=prompt_peg_values.get("current_eps_period"),
                    current_price=prompt_peg_values.get("current_target_price_est"),
                    run_rate_1q_eps=prompt_peg_values.get("run_rate_1q_eps_annualized"),
                    run_rate_2q_eps=prompt_peg_values.get("run_rate_2q_eps_annualized"),
                    run_rate_reference_eps=prompt_peg_values.get("run_rate_reference_eps"),
                    run_rate_1q_price=prompt_peg_values.get("run_rate_1q_target_price"),
                    run_rate_2q_price=prompt_peg_values.get("run_rate_2q_target_price"),
                    run_rate_reference_price=prompt_peg_values.get("run_rate_reference_target_price"),
                    run_rate_label=prompt_peg_values.get("run_rate_label"),
                    run_rate_action=prompt_peg_values.get("run_rate_action"),
                    fy1_base_price=prompt_peg_values.get("fy1_base_target_price"),
                    fy1_soft_price=prompt_peg_values.get("fy1_soft_target_price"),
                    fy1_hard_price=prompt_peg_values.get("fy1_hard_target_price"),
                    fy2_base_price=prompt_peg_values.get("fy2_base_target_price"),
                    fy2_soft_price=prompt_peg_values.get("fy2_soft_target_price"),
                    fy2_hard_price=prompt_peg_values.get("fy2_hard_target_price"),
                    fy3_base_price=prompt_peg_values.get("fy3_base_target_price"),
                    fy3_soft_price=prompt_peg_values.get("fy3_soft_target_price"),
                    fy3_hard_price=prompt_peg_values.get("fy3_hard_target_price"),
                    manual_price=prompt_peg_values.get("fy1_manual_target_price"),
                    fallback_text=tp_est_str,
                )

            prompt_audit_implied_values = {
                "market_implied_pe": locals().get("market_implied_pe"),
                "target_avg_implied_pe": locals().get("target_avg_implied_pe"),
                "target_high_implied_pe": locals().get("target_high_implied_pe"),
            }

            def _prompt_snapshot_audit_summary(
                audit,
                industry_profile=None,
                dynamic_cap_pack=None,
                market_implied_pe_val=None,
                target_avg_implied_pe_val=None,
                target_high_implied_pe_val=None,
            ):
                if market_implied_pe_val is None:
                    market_implied_pe_val = prompt_audit_implied_values.get("market_implied_pe")
                if target_avg_implied_pe_val is None:
                    target_avg_implied_pe_val = prompt_audit_implied_values.get("target_avg_implied_pe")
                if target_high_implied_pe_val is None:
                    target_high_implied_pe_val = prompt_audit_implied_values.get("target_high_implied_pe")
                return prompt_snapshot_audit_summary(
                    audit,
                    industry_profile=industry_profile,
                    dynamic_cap_pack=dynamic_cap_pack,
                    market_implied_pe_val=market_implied_pe_val,
                    target_avg_implied_pe_val=target_avg_implied_pe_val,
                    target_high_implied_pe_val=target_high_implied_pe_val,
                    final_signal=final_signal,
                    divergence_warnings=divergence_warnings,
                )

            def _prompt_snapshot_audit_core(
                audit,
                industry_profile=None,
                dynamic_cap_pack=None,
                market_implied_pe_val=None,
                target_avg_implied_pe_val=None,
                target_high_implied_pe_val=None,
            ):
                if market_implied_pe_val is None:
                    market_implied_pe_val = prompt_audit_implied_values.get("market_implied_pe")
                if target_avg_implied_pe_val is None:
                    target_avg_implied_pe_val = prompt_audit_implied_values.get("target_avg_implied_pe")
                if target_high_implied_pe_val is None:
                    target_high_implied_pe_val = prompt_audit_implied_values.get("target_high_implied_pe")
                return prompt_snapshot_audit_core(
                    audit,
                    industry_profile=industry_profile,
                    dynamic_cap_pack=dynamic_cap_pack,
                    market_implied_pe_val=market_implied_pe_val,
                    target_avg_implied_pe_val=target_avg_implied_pe_val,
                    target_high_implied_pe_val=target_high_implied_pe_val,
                )

            eps_adopted_for_prompt = prompt_eps_adoption_sync_summary(
                sys_latest_quarter_eps_val=locals().get("sys_latest_quarter_eps"),
                ai_latest_month_eps_val=locals().get("ai_latest_month_eps"),
                ai_latest_quarter_eps_val=locals().get("ai_latest_quarter_eps"),
                raw_ai_period_val=locals().get("raw_ai_period"),
                sys_ttm_eps_val=locals().get("sys_ttm_eps"),
                ai_ttm_eps_val=locals().get("ai_ttm_eps"),
                eff_t_eps_val=locals().get("eff_t_eps"),
                sys_fiscal_year_eps_val=locals().get("sys_fiscal_year_eps"),
                ai_fiscal_year_eps_val=locals().get("ai_fiscal_year_eps"),
                sys_forward_eps_system_val=locals().get("sys_forward_eps_system"),
                eff_f_eps_val=locals().get("eff_f_eps"),
                ai_forward_eps_ai_val=locals().get("ai_forward_eps_ai"),
                ai_forward_eps_consensus_val=locals().get("ai_forward_eps_consensus"),
                ai_forward_eps_fy1_val=locals().get("ai_forward_eps_fy1"),
                ai_forward_eps_fy2_val=locals().get("ai_forward_eps_fy2"),
                ai_forward_eps_fy3_val=locals().get("ai_forward_eps_fy3"),
                ai_forward_eps_fy1_year_val=locals().get("ai_forward_eps_fy1_year"),
                ai_forward_eps_fy2_year_val=locals().get("ai_forward_eps_fy2_year"),
                ai_forward_eps_fy3_year_val=locals().get("ai_forward_eps_fy3_year"),
                ai_f_eps_calc_val=locals().get("ai_f_eps_calc"),
                fy1_eps_for_annual_val=locals().get("fy1_eps_for_annual"),
                cap_adopted_forward_eps_val=locals().get("cap_adopted_forward_eps"),
                ai_forward_eps_fy_source_note_val=locals().get("ai_forward_eps_fy_source_note"),
                ai_forward_eps_fy_basis_val=locals().get("ai_forward_eps_fy_basis"),
                formula_pe_cap_val=locals().get("formula_pe_cap"),
                formula_eps_for_calc_val=locals().get("formula_eps_for_calc"),
                formula_eps_source_val=locals().get("formula_eps_source"),
                system_formula_fair_value_raw_val=locals().get("sys_target_price_raw"),
                forward_eps_period_mismatch_val=locals().get("forward_eps_period_mismatch"),
                base_pe_cap_val=locals().get("base_pe_cap_for_calc"),
                soft_pe_cap_val=locals().get("soft_pe_cap_for_calc"),
                hard_pe_cap_val=locals().get("hard_pe_cap_for_calc"),
                manual_cap_for_calc_val=locals().get("manual_cap_for_calc"),
                manual_cap_source_val=locals().get("manual_cap_source_text"),
                sys_target_price_est_val=locals().get("sys_target_price_est"),
                current_eps_for_valuation_val=locals().get("current_eps_for_valuation"),
                current_eps_raw_val=locals().get("current_eps_raw"),
                current_eps_source_val=locals().get("current_eps_source"),
                current_eps_formula_note_val=locals().get("current_eps_formula_note"),
                current_eps_period_val=locals().get("current_eps_period"),
                current_target_price_est_val=locals().get("current_target_price_est"),
                run_rate_1q_eps_val=locals().get("run_rate_1q_eps_annualized"),
                run_rate_2q_eps_val=locals().get("run_rate_2q_eps_annualized"),
                run_rate_reference_eps_val=locals().get("run_rate_reference_eps"),
                run_rate_1q_target_price_val=locals().get("run_rate_1q_target_price"),
                run_rate_2q_target_price_val=locals().get("run_rate_2q_target_price"),
                run_rate_reference_target_price_val=locals().get("run_rate_reference_target_price"),
                run_rate_label_val=locals().get("run_rate_label"),
                run_rate_action_val=locals().get("run_rate_action"),
                fy1_base_target_price_val=locals().get("fy1_base_target_price"),
                fy1_soft_target_price_val=locals().get("fy1_soft_target_price"),
                fy1_hard_target_price_val=locals().get("fy1_hard_target_price"),
                fy2_base_target_price_val=locals().get("fy2_base_target_price"),
                fy2_soft_target_price_val=locals().get("fy2_soft_target_price"),
                fy2_hard_target_price_val=locals().get("fy2_hard_target_price"),
                fy3_base_target_price_val=locals().get("fy3_base_target_price"),
                fy3_soft_target_price_val=locals().get("fy3_soft_target_price"),
                fy3_hard_target_price_val=locals().get("fy3_hard_target_price"),
                fy1_manual_target_price_val=locals().get("fy1_manual_target_price"),
            )

            def _prompt_target_price_panel_summary():
                return prompt_target_price_panel_summary(
                    prompt_hi_str=prompt_hi_str,
                    prompt_me_str=prompt_me_str,
                    prompt_lo_str=prompt_lo_str,
                    prompt_analyst_count=prompt_analyst_count,
                    target_confidence=target_confidence,
                    prompt_target_source=prompt_target_source,
                    ai_tp_str=ai_tp_str,
                    prompt_target_rationale=prompt_target_rationale,
                )


            try:
                ai_etf_data_for_prompt = st.session_state.get("ai_etf_holders", {}).get(curr_id) if isinstance(st.session_state.get("ai_etf_holders"), dict) else None
            except Exception:
                ai_etf_data_for_prompt = None
            etf_summary_for_prompt = prompt_etf_panel_summary(etf_holders=etf_holders, ai_etf_data=ai_etf_data_for_prompt)

            def _prompt_etf_panel_summary():
                return etf_summary_for_prompt

            defense_summary_for_prompt = prompt_defense_panel_summary(dy_str=dy_str, fcf_str=fcf_str, cr_str=cr_str, fs_str=fs_str)

            def _prompt_defense_panel_summary():
                return defense_summary_for_prompt

            chip_summary_for_prompt = prompt_chip_panel_summary(chip_panel_state)

            def _prompt_chip_panel_summary():
                return chip_summary_for_prompt

            def _prompt_panel_sync_audit():
                return prompt_panel_sync_audit(
                    latest_rev_display_label=latest_rev_display_label,
                    eps_adopted_for_prompt=eps_adopted_for_prompt,
                    peg_valuation_text=_prompt_peg_valuation_layers(),
                    prompt_analyst_count=prompt_analyst_count,
                    prompt_hi_str=prompt_hi_str,
                    prompt_me_str=prompt_me_str,
                    prompt_lo_str=prompt_lo_str,
                    dynamic_cap_pack=dynamic_cap_pack,
                    final_signal=final_signal,
                    etf_summary=etf_summary_for_prompt,
                    chip_summary=chip_summary_for_prompt,
                )

            def _prompt_model_gap_trigger_conditions():
                return prompt_model_gap_trigger_conditions()

            def _prompt_buy_decision_gap_risk_conditions():
                return prompt_buy_decision_gap_risk_conditions()

            def _prompt_model_library_feedback_request():
                return prompt_model_library_feedback_request(industry_profile)
            context_str = f"""
【0. {APP_PAGE_TITLE} 精簡判讀總覽】
- 股票: {c_name} ({curr_id})
- 最新收盤價: {_nullize_text(curr_p)} 元
- 系統版本: {APP_PAGE_TITLE}
- 最終操作燈號: {_nullize_text(final_signal.get('signal') if isinstance(final_signal, dict) else 'NULL')}
- 操作含義: {_nullize_text(final_signal.get('advice') if isinstance(final_signal, dict) else 'NULL')}
- 資料可信度 / 估值可信度 / 操作可信度: {_nullize_text(final_signal.get('data_confidence') if isinstance(final_signal, dict) else 'NULL')} / {_nullize_text(final_signal.get('valuation_confidence') if isinstance(final_signal, dict) else 'NULL')} / {_nullize_text(final_signal.get('operation_confidence') if isinstance(final_signal, dict) else 'NULL')}

【1. 月營收公告月份與財務動能】
- 營收公告月份標籤: {_nullize_text(latest_rev_display_label)}
- 最新單月營收 YoY / MoM: {panel_rg} / {_nullize_text(latest_mom_str)}
- 月營收資料源: {_nullize_text(latest_rev_source)}
- 月營收來源URL: {_nullize_text(latest_rev_source_url)}
- 月營收來源規則: {_nullize_text(latest_rev_source_rule)}
- 月營收所屬月份 / 公告月份 / 公告日: {_nullize_text(latest_rev_revenue_month)} / {_nullize_text(latest_rev_announce_month)} / {_nullize_text(latest_rev_announce_date)}
- 月營收月份提示: {_nullize_text(latest_rev_notice)}

【2. EPS 口徑摘要（不可混用）】
{_prompt_df(eps_report_df, max_rows=8)}
- 新版 EPS / 年期 / 估值同步摘要：
{eps_adopted_for_prompt}

【3. 盤面與基礎估值摘要】
- Trailing P/E / Forward P/E / P/B / PEG: {panel_pe} / {panel_fpe} / {panel_pb} / {panel_peg}
- EPS（TTM / Forward 顯示值）: {panel_eps}
- 預估獲利成長 YoY: {panel_eg}
- 毛利率 / 營益率: {panel_gmom}
- ROE / D/E: {panel_roe} / {panel_de}
- 殖利率 / FCF / 流動比率 / F-Score: {_nullize_text(dy_str)} / {_nullize_text(fcf_str)} / {_nullize_text(cr_str)} / {_nullize_text(fs_str)}

【4. 系統 / AI 分歧警告（必須完整解讀）】
{_prompt_warnings(divergence_warnings)}

【5. 資料品質摘要（只列採用、缺值、異常、校正、關鍵欄位）】
{_prompt_quality_summary(dq_report_df)}

【5-1. 欄位來源優先表（系統 / AI 衝突時採用規則）】
{prompt_field_source_priority_summary(max_rows=18)}

【6. 法人目標價與可信度】
{_prompt_target_price_panel_summary()}

【7. 前瞻 PEG 詳細估值分層（系統公式 + FY1/FY2/FY3 base/soft/hard）】
{_prompt_peg_valuation_layers()}

【8. TTM + Forward EPS 年期分層估值（17-C-9c-hotfix44，判斷目前EPS與FY1/FY2/FY3）】
{_prompt_forward_eps_tier_core(forward_eps_tier_pack)}

【9. 公式估值 / 手動情境 / 可操作估值分離】
- 系統逆向推算估值摘要: {ctx_tp_est}
- 可操作估值提示: {_nullize_text(valuation_separation.get('action_hint') if isinstance(valuation_separation, dict) else 'NULL')}
- 可操作估值區間低/中/高: {_nullize_text(valuation_separation.get('operable_low') if isinstance(valuation_separation, dict) else 'NULL')} / {_nullize_text(valuation_separation.get('operable_mid') if isinstance(valuation_separation, dict) else 'NULL')} / {_nullize_text(valuation_separation.get('operable_high') if isinstance(valuation_separation, dict) else 'NULL')}
- 手動年度情境價（FY1 EPS × 手動情境 Cap；未調整時採 FY1 base）: {_nullize_text(fy1_manual_target_price if 'fy1_manual_target_price' in locals() else None)}
- 年度 base / soft / hard 倍率: {_nullize_text(base_pe_cap_for_calc if 'base_pe_cap_for_calc' in locals() else None)} / {_nullize_text(soft_pe_cap_for_calc if 'soft_pe_cap_for_calc' in locals() else None)} / {_nullize_text(hard_pe_cap_for_calc if 'hard_pe_cap_for_calc' in locals() else None)}
- 警告數 / 重大警告數: {_nullize_text(valuation_separation.get('warning_count') if isinstance(valuation_separation, dict) else 'NULL')} / {_nullize_text(valuation_separation.get('danger_count') if isinstance(valuation_separation, dict) else 'NULL')}
- 提醒: 手動年度情境價為壓力測試，不等於系統可操作買點；公式合理價、年度 soft/hard 情境價與 hard ceiling 也不是買進目標；買賣以系統可操作區間與最終燈號為主。

【10. 產業估值模型（只列本股模型）】
- 匹配模型: {_nullize_text(industry_profile.get('model_label') if isinstance(industry_profile, dict) else 'NULL')}
- 主分類 / stocklist 分類: {_nullize_text(industry_profile.get('parent_category') if isinstance(industry_profile, dict) else 'NULL')} / {_nullize_text(industry_profile.get('stocklist_category') if isinstance(industry_profile, dict) else 'NULL')}
- 題材標籤: {_nullize_text(industry_profile.get('themes_text') if isinstance(industry_profile, dict) else 'NULL')}
- 模型重評價狀態: {_nullize_text(industry_profile.get('re_rating_status_label') if isinstance(industry_profile, dict) else 'NULL')}｜{_nullize_text(industry_profile.get('re_rating_status') if isinstance(industry_profile, dict) else 'NULL')}
- 重評價操作規則: {_nullize_text(industry_profile.get('pricing_horizon_policy') if isinstance(industry_profile, dict) else 'NULL')}
- hard ceiling 政策: {_nullize_text(industry_profile.get('hard_ceiling_policy') if isinstance(industry_profile, dict) else 'NULL')}
- 產業分類來源 / 可信度 / 折扣: {_nullize_text(industry_profile.get('classification_source') if isinstance(industry_profile, dict) else 'NULL')} / {_nullize_text(industry_profile.get('classification_confidence') if isinstance(industry_profile, dict) else 'NULL')} / ×{_nullize_text(industry_profile.get('classification_confidence_factor') if isinstance(industry_profile, dict) else 'NULL')}
- 是否待人工確認: {_nullize_text(industry_profile.get('classification_needs_manual_review') if isinstance(industry_profile, dict) else 'NULL')}｜{_nullize_text(industry_profile.get('classification_warning') if isinstance(industry_profile, dict) else 'NULL')}
- AI 建議分類: {_nullize_text(industry_profile.get('ai_suggested_taxon') if isinstance(industry_profile, dict) else 'NULL')}｜{_nullize_text(industry_profile.get('ai_suggested_themes') if isinstance(industry_profile, dict) else 'NULL')}
- AI 分類依據: {_nullize_text(industry_profile.get('ai_classification_reason') if isinstance(industry_profile, dict) else 'NULL')}
- 主要 / 次要估值方式: {_nullize_text(industry_profile.get('primary_valuation') if isinstance(industry_profile, dict) else 'NULL')} / {_nullize_text(industry_profile.get('secondary_valuation') if isinstance(industry_profile, dict) else 'NULL')}
- P/E 適用性: {_nullize_text(industry_profile.get('pe_applicability_text') if isinstance(industry_profile, dict) else 'NULL')}
- 是否循環股 / P/E 陷阱: {_nullize_text(industry_profile.get('cyclical') if isinstance(industry_profile, dict) else 'NULL')} / {_nullize_text(industry_profile.get('pe_trap_warning') if isinstance(industry_profile, dict) else 'NULL')}
- Dynamic Cap floor / soft / hard: {_nullize_text(industry_profile.get('floor_pe') if isinstance(industry_profile, dict) else 'NULL')} / {_nullize_text(industry_profile.get('soft_ceiling_pe') if isinstance(industry_profile, dict) else 'NULL')} / {_nullize_text(industry_profile.get('hard_ceiling_pe') if isinstance(industry_profile, dict) else 'NULL')}
- P/B 參考區間: {_nullize_text(industry_profile.get('pb_range') if isinstance(industry_profile, dict) else 'NULL')}
- 事件模型切換: {_nullize_text(industry_profile.get('event_switch_note') if isinstance(industry_profile, dict) else 'NULL')}
- 校準來源: {_nullize_text(industry_profile.get('calibration_source') if isinstance(industry_profile, dict) else 'NULL')}
- 風險旗標: {_nullize_text(industry_profile.get('risk_flags') if isinstance(industry_profile, dict) else 'NULL')}

【11. Dynamic Cap 2.0 摘要（核心拆解，不含完整表格）】
{_prompt_dynamic_cap_core(dynamic_cap_pack, mode="research")}

【12. 產業模型單次快照稽核與更新判斷】
{_prompt_snapshot_audit_core(snapshot_audit, industry_profile, dynamic_cap_pack)}

【13. 最終操作燈號明細】
{_prompt_df(final_signal_report_for_prompt, max_rows=12)}

【14. AI 來源與 JSON 驗證摘要】
- AI 模型/資料期間: {_nullize_text(temp_ai_fin.get('model_used') if isinstance(temp_ai_fin, dict) else 'NULL')}｜{_nullize_text(raw_ai_period)}
- AI JSON 驗證狀態: {_nullize_text(ai_validation_status_for_prompt)}
- AI JSON 驗證警告: {_nullize_text('；'.join([str(x) for x in ai_validation_warnings_for_prompt[:8]]) if ai_validation_warnings_for_prompt else 'NULL')}
- AI 產業分類建議: {_nullize_text(temp_ai_fin.get('industry_classification') if isinstance(temp_ai_fin, dict) else 'NULL')}
- 重要 AI 來源追蹤（只列被採用、分歧、異常或估值關鍵欄位）:
{_prompt_ai_source_summary(ai_source_trace_df_for_prompt)}

【15. ETF 持有與曝險摘要】
{_prompt_etf_panel_summary()}

【16. 防禦力與籌碼面板同步摘要】
- 防禦力/財務健康：
{_prompt_defense_panel_summary()}
- 籌碼/股權結構：
{_prompt_chip_panel_summary()}

【17. 提示詞與面板同步自檢】
{_prompt_panel_sync_audit()}

【18. 模型落差觸發條件與診斷要求（研究完整版專用）】
{_prompt_model_gap_trigger_conditions()}

【19. 模型庫回饋建議（研究完整版專用）】
{_prompt_model_library_feedback_request()}
"""


            # 第 17-C-2：買進決策版資料包。只保留會影響「現在是否值得買進」的關鍵欄位。
            # 原 context_str 保留為研究完整版資料包。
            decision_context_str = f"""
【0. 系統判讀總覽】
- 股票: {c_name} ({curr_id})
- 最新收盤價: {_nullize_text(curr_p)} 元
- 系統版本: {APP_PAGE_TITLE}
- 最終操作燈號: {_nullize_text(final_signal.get('signal') if isinstance(final_signal, dict) else 'NULL')}
- 系統建議: {_nullize_text(final_signal.get('advice') if isinstance(final_signal, dict) else 'NULL')}
- 資料 / 估值 / 操作可信度: {_nullize_text(final_signal.get('data_confidence') if isinstance(final_signal, dict) else 'NULL')} / {_nullize_text(final_signal.get('valuation_confidence') if isinstance(final_signal, dict) else 'NULL')} / {_nullize_text(final_signal.get('operation_confidence') if isinstance(final_signal, dict) else 'NULL')}

【1. 月營收與動能】
- 最新公告月份: {_nullize_text(latest_rev_display_label)}
- 月營收 YoY / MoM: {panel_rg} / {_nullize_text(latest_mom_str)}
- 資料源 / 提醒: {_nullize_text(latest_rev_source)} / {_nullize_text(latest_rev_notice)}
- 來源URL / 規則 / 營收月份: {_nullize_text(latest_rev_source_url)} / {_nullize_text(latest_rev_source_rule)} / {_nullize_text(latest_rev_revenue_month)}

【2. EPS 口徑與採用值（新版同步：系統 / AI / FY1 / FY2 / FY3）】
{eps_adopted_for_prompt}
- 市場 / 法人隱含倍率：現價隱含 {_nullize_text(market_implied_pe if 'market_implied_pe' in locals() else None)}x；法人均價隱含 {_nullize_text(target_avg_implied_pe if 'target_avg_implied_pe' in locals() else None)}x；法人高標隱含 {_nullize_text(target_high_implied_pe if 'target_high_implied_pe' in locals() else None)}x；判讀：{_nullize_text(implied_status if 'implied_status' in locals() else None)}

【3. TTM + Forward EPS 年期分層估值（17-C-9c-hotfix44）】
{_prompt_forward_eps_tier_core(forward_eps_tier_pack)}

【4. 核心財務與估值】
- 現價: {_nullize_text(curr_p)}
- Trailing P/E / Forward P/E / P/B / PEG: {panel_pe} / {panel_fpe} / {panel_pb} / {panel_peg}
- 毛利率 / 營益率: {panel_gmom}
- ROE / D/E: {panel_roe} / {panel_de}
- 營收 YoY / 預估獲利成長 YoY: {panel_rg} / {panel_eg}
- FCF / 流動比率 / 殖利率: {_nullize_text(fcf_str)} / {_nullize_text(cr_str)} / {_nullize_text(dy_str)}

【5. 分歧與資料品質】
- 系統 / AI 分歧警告:
{_prompt_warnings(divergence_warnings)}
- 資料品質摘要:
{_prompt_quality_summary(dq_report_df)}
- 欄位來源優先表:
{prompt_field_source_priority_summary(max_rows=14)}

【6. 法人目標價與可信度】
{_prompt_target_price_panel_summary()}

【7. 前瞻 PEG 詳細估值分層（系統公式 + FY1/FY2/FY3 base/soft/hard）】
{_prompt_peg_valuation_layers()}
- 可操作估值區間低/中/高: {_nullize_text(valuation_separation.get('operable_low') if isinstance(valuation_separation, dict) else 'NULL')} / {_nullize_text(valuation_separation.get('operable_mid') if isinstance(valuation_separation, dict) else 'NULL')} / {_nullize_text(valuation_separation.get('operable_high') if isinstance(valuation_separation, dict) else 'NULL')}
- 可操作估值提示: {_nullize_text(valuation_separation.get('action_hint') if isinstance(valuation_separation, dict) else 'NULL')}

【8. 模型落差風險提示（買進決策版專用）】
{_prompt_buy_decision_gap_risk_conditions()}

【9. 產業估值模型】
- 產業模型建置時間 / 版本: {_nullize_text(industry_profile.get('model_built_at') if isinstance(industry_profile, dict) else 'NULL')} / {_nullize_text(industry_profile.get('model_build_version') if isinstance(industry_profile, dict) else 'NULL')}
- 正式/匹配分類: {_nullize_text(industry_profile.get('model_label') if isinstance(industry_profile, dict) else 'NULL')}
- 分類來源 / 可信度 / 折扣: {_nullize_text(industry_profile.get('classification_source') if isinstance(industry_profile, dict) else 'NULL')} / {_nullize_text(industry_profile.get('classification_confidence') if isinstance(industry_profile, dict) else 'NULL')} / ×{_nullize_text(industry_profile.get('classification_confidence_factor') if isinstance(industry_profile, dict) else 'NULL')}
- 是否待人工確認: {_nullize_text(industry_profile.get('classification_needs_manual_review') if isinstance(industry_profile, dict) else 'NULL')}｜{_nullize_text(industry_profile.get('classification_warning') if isinstance(industry_profile, dict) else 'NULL')}
- AI 建議分類 / 題材: {_nullize_text(industry_profile.get('ai_suggested_taxon') if isinstance(industry_profile, dict) else 'NULL')} / {_nullize_text(industry_profile.get('ai_suggested_themes') if isinstance(industry_profile, dict) else 'NULL')}
- 題材標籤: {_nullize_text(industry_profile.get('themes_text') if isinstance(industry_profile, dict) else 'NULL')}
- 模型重評價狀態: {_nullize_text(industry_profile.get('re_rating_status_label') if isinstance(industry_profile, dict) else 'NULL')}｜{_nullize_text(industry_profile.get('re_rating_status') if isinstance(industry_profile, dict) else 'NULL')}
- 重評價操作規則: {_nullize_text(industry_profile.get('pricing_horizon_policy') if isinstance(industry_profile, dict) else 'NULL')}
- hard ceiling 政策: {_nullize_text(industry_profile.get('hard_ceiling_policy') if isinstance(industry_profile, dict) else 'NULL')}
- 主要估值方式: {_nullize_text(industry_profile.get('primary_valuation') if isinstance(industry_profile, dict) else 'NULL')}；是否循環股/P-E陷阱: {_nullize_text(industry_profile.get('cyclical') if isinstance(industry_profile, dict) else 'NULL')} / {_nullize_text(industry_profile.get('pe_trap_warning') if isinstance(industry_profile, dict) else 'NULL')}
- 主分類原始 floor / soft / hard: {_nullize_text(industry_profile.get('hybrid_original_caps_text') if isinstance(industry_profile, dict) else 'NULL')}
- 混合產業權重: {_nullize_text(industry_profile.get('hybrid_taxons_text') if isinstance(industry_profile, dict) else 'NULL')}
- 混合後 base / floor / soft / hard: {_nullize_text(industry_profile.get('hybrid_mixed_caps_text') if isinstance(industry_profile, dict) else 'NULL')}

【10. Dynamic Cap 2.0 決策摘要】
{_prompt_dynamic_cap_core(dynamic_cap_pack, mode="decision")}

【11. 產業模型稽核摘要】
{_prompt_snapshot_audit_summary(snapshot_audit, industry_profile, dynamic_cap_pack)}

【12. ETF / 防禦力 / 籌碼摘要】
- ETF 持有與曝險：
{_prompt_etf_panel_summary()}
- 防禦力/財務健康：
{_prompt_defense_panel_summary()}
- 籌碼/股權結構：
{_prompt_chip_panel_summary()}

【13. 提示詞與面板同步自檢】
{_prompt_panel_sync_audit()}

【14. AI 來源與驗證摘要】
- AI JSON 驗證: {_nullize_text(ai_validation_status_for_prompt)}；警告: {_nullize_text('；'.join([str(x) for x in ai_validation_warnings_for_prompt[:5]]) if ai_validation_warnings_for_prompt else 'NULL')}
- 估值採用 AI 欄位來源摘要:
{_prompt_ai_source_summary(ai_source_trace_df_for_prompt)}
"""


            full_prompt_for_copy = f"""你是台股研究總監 + 交易策略專家。請用繁體中文、條列、可執行結論，並嚴格使用下方 {APP_PAGE_TITLE} 數據。

重要原則：
1) 請優先尊重 {APP_PAGE_TITLE} 已產出的「月營收公告月份、EPS 拆欄、分歧警告、資料品質報告、法人目標價可信度、公式估值/可操作估值分離、產業估值模型、Dynamic Cap 2.0、最終操作燈號」。
2) 公式合理估值與公式極限價只代表模型輸出，不可直接當作買進目標；真正操作請以「可操作估值區間」與最終燈號為主。
3) 若系統 / AI 分歧警告存在，必須先說明分歧對估值可信度與操作可信度的影響，不可直接給樂觀目標價。
4) EPS 必須分清楚最新單季 EPS、TTM EPS、完整年度 EPS、系統 Forward EPS、AI Forward EPS、法人共識 Forward EPS，不可混用。
5) 月營收必須以公告月份為準，不可用查詢當月推定最新月營收。
6) 同一欄位若系統 / AI / 外部來源衝突，需依「欄位來源優先表」決定採用值，不可自行挑樂觀數據。
7) 若關鍵欄位為 NULL，需提出替代判斷法；若為資料異常-不可判斷，請明確說「暫不適合做買賣判斷」；若為資料分歧-降權判斷，請用保守估值並限制倉位。
8) 若產業分類來源為 AI 建議或 keyword_fallback，請先檢查分類是否合理；AI 建議分類屬待確認，不可視為正式 stock_mapping.py 分類。
9) 請閱讀「產業模型單次快照稽核與更新判斷」，判斷是否需人工檢查產業估值模型；但不可把單次快照直接當成必須更新模型。
10) 請閱讀「Forward EPS 年期分層估值」，判斷市場/法人是否可能已經用 FY2 或 FY3 EPS 定價；若是，請說明這是先行定價還是過度樂觀。
11) 研究完整版請額外輸出「模型庫回饋建議」：這不是買賣建議，而是協助日後修正 stock_mapping.py、industry_taxonomy.py、dynamic_cap_model.py 或法人目標價可信度規則；AI 回饋只能作為候選清單，不可直接覆蓋模型庫。

任務要求：
1) 先做「{APP_PAGE_TITLE} 資料品質盤點」：逐項說明哪些欄位是系統/AI/推估/NULL，並指出最影響結論的 3 個資料風險。
2) 解讀「分歧警告」：EPS / YoY / PEG / 合理價 / D/E 若有警告，請說明是否會讓估值降級。
3) 解讀「產業估值模型」：說明這檔股票適合用哪些估值指標，不適合用哪些指標。
4) 解讀「公式估值 vs 可操作估值」：請分開說明公式合理價、公式極限價、可操作估值區間，不可混成同一個目標價。
5) 交易決策：
   - 先引用系統最終燈號，再判斷是否同意。
   - 給「可買-小量分批 / 觀望 / 不建議 / 資料分歧-降權判斷 / 觀望-資料待確認 / 資料異常-不可判斷」之一。
   - 買點：給 2~3 個分批區間與理由。
   - 賣點：給 2~3 個減碼 / 停利 / 停損條件。
   - 倉位建議：保守 / 中性 / 積極三種配置比例。
6) 三情境目標價：牛市 / 基準 / 熊市，各列目標價區間、假設前提、觸發條件。
7) 下月追蹤清單：列出 8 個要追蹤的指標與警戒閾值，必須包含月營收 YoY、MoM、毛利率、EPS、法人目標價或 EPS 預估調整。
8) 模型庫回饋建議：請依【18. 模型庫回饋建議】輸出模型庫修正候選，並明確標示是否只是觀察，不得把模型回饋混成買賣結論。

輸出格式（必須照做）：
- [投資結論一句話]
- [{APP_PAGE_TITLE} 資料品質與分歧警告]
- [產業估值模型解讀]
- [公式估值 vs 可操作估值]
- [公司優缺點]
- [買點 / 賣點 / 停損停利]
- [三情境目標價]
- [風險與反證]
- [下月追蹤清單]
- [模型庫回饋建議｜研究用途，非買賣建議]

以下是 {APP_PAGE_TITLE} 精簡打包數據（只保留會影響外部 AI 判斷的採用值、分歧、估值層級、產業模型、Dynamic Cap 與燈號；無資料為 NULL）。若出現數據不合理，可上網查詢並說明不合理原因，但不可忽略系統已標示的分歧與資料品質警告：
{context_str}
"""

            research_prompt_for_copy = full_prompt_for_copy
            buy_decision_prompt_for_copy = f"""你是台股研究總監 + 交易策略專家。請用繁體中文、條列、可執行結論，協助我判斷這檔股票「現在是否值得買進」。

請優先尊重 {APP_PAGE_TITLE} 的判讀，尤其是：月營收公告月份、EPS 拆欄、分歧警告、資料品質、法人目標價可信度、公式估值/可操作估值分離、產業估值模型、Dynamic Cap 2.0、最終操作燈號。

重要規則：
- 不可把公式合理估值或公式極限價直接當買進目標。
- 買進判斷以可操作估值區間、資料可信度、估值可信度、操作可信度、最終燈號為主。
- EPS 必須分清楚最新單季 EPS、TTM EPS、完整年度 EPS、系統 Forward EPS、AI Forward EPS、法人共識 Forward EPS。
- 月營收必須以公告月份為準。
- 同一欄位若多來源衝突，必須依欄位來源優先表判斷採用值，不可挑選較樂觀來源。
- 若法人目標價分析師人數為 NULL 或少於 3 人，請降低目標價可信度。
- 若資料品質不足或關鍵欄位異常，請明確說「暫不適合做買進判斷」。
- 若同一欄位同時列出系統值與 AI 值，請說明採用哪一個，以及是否影響估值可信度。
- 若觸發「模型落差風險提示」，請優先判斷落差是否會傷害買進安全邊際；但不要在買進決策版提出模型庫修正建議。

請依序回答：
1. [投資結論一句話]：可買-小量分批 / 觀望 / 不建議 / 資料分歧-降權判斷 / 觀望-資料待確認 / 資料異常-不可判斷，並說明是否同意系統最終燈號。
2. [買進前資料檢查]：檢查月營收公告月份、EPS 口徑、Forward EPS、法人目標價可信度、公式估值是否被樂觀 EPS 放大，並列出最影響買進判斷的 3 個資料風險。
3. [產業與成長邏輯]：說明產業主線、未來 1～2 年成長動能，以及成長失速條件。
4. [估值判斷]：分開說明公式合理價、公式極限價、可操作估值區間、法人目標價，並判斷現價低估 / 合理 / 偏高 / 高估。不可只用 PEG 判斷便宜。
5. [模型落差風險]：若現價、法人目標價、系統可操作估值與 FY1/FY2/FY3 估值落差過大，請判斷是否只靠 FY2/FY3 才能解釋現價，以及這是否降低買進安全邊際。
6. [買進策略]：現價可不可以買？給 2～3 個分批買點與理由；若不建議買，說明跌到哪裡或出現什麼條件才可重新評估。
7. [賣出與風控]：給 2～3 個停利區與 2～3 個停損 / 減碼條件；高題材股需說明拉高是否先收一部分。
8. [倉位建議]：保守 / 中性 / 積極三種配置比例；資料可信度不足時限制最高倉位。
9. [三情境目標價]：牛市 / 基準 / 熊市，各列目標價區間、假設前提、觸發條件。
10. [下月追蹤清單]：列 8 個指標與警戒值，必須包含月營收 YoY、MoM、毛利率、EPS、Forward EPS 或法人 EPS 預估、法人目標價可信度、營益率或 ROE、重要訂單 / 產業事件。
11. [EPS 年期判斷]：請先用 TTM EPS 判斷目前實際獲利估值，再說明目前股價與法人目標價比較像用 FY1、FY2 還是 FY3 EPS 定價；FY1/FY2/FY3 是預估年度 EPS 序列，不是查詢日後1/2/3年。若用 FY2/FY3 才合理，請說明風險與是否能作為買進依據。
12. [產業模型是否需更新]：請根據「17-C-9c-hotfix44 單次快照稽核」回答：不建議更新模型 / 暫時觀察 / 建議檢查 hybrid 權重 / 建議檢查 primary_taxon / 建議檢查整個產業倍率。若建議檢查，請說明是市場過熱、法人過度樂觀、EPS/營收尚未落地，還是公司營運型態已改變；不可因單次現價高於 hard ceiling 就直接調高模型。

以下是 {APP_PAGE_TITLE}「買進決策版」系統資料。這不是完整研究資料包，只保留會直接影響買進判斷的採用值、系統值/AI值、分歧、估值層級、產業模型、Dynamic Cap 與燈號。若資料不合理，可上網查證，但不可忽略系統標示的資料品質與分歧警告：
{decision_context_str}
"""


            def _essential_num(value, digits=2, suffix=""):
                value = s_float(value)
                return f"{value:.{digits}f}{suffix}" if value is not None else None

            def _essential_pct(value):
                value = s_float(value)
                return f"{value * 100:.2f}%" if value is not None else None

            essential_prompt_fields = [
                ("現價", _essential_num(curr_p, 2, "元")),
                ("TTM EPS", _essential_num(eff_t_eps)),
                (f"FY1 EPS ({ai_forward_eps_fy1_year})" if ai_forward_eps_fy1_year else "FY1 EPS", _essential_num(ai_forward_eps_fy1)),
                (f"FY2 EPS ({ai_forward_eps_fy2_year})" if ai_forward_eps_fy2_year else "FY2 EPS", _essential_num(ai_forward_eps_fy2)),
                (f"FY3 EPS ({ai_forward_eps_fy3_year})" if ai_forward_eps_fy3_year else "FY3 EPS", _essential_num(ai_forward_eps_fy3)),
                ("毛利率", _essential_pct(eff_gm)),
                ("營益率", _essential_pct(eff_om)),
                ("最新月營收 YoY", _essential_pct(eff_rg)),
                ("Dynamic Cap Base", _essential_num(base_pe_cap_for_calc, 2, "x")),
                ("Dynamic Cap Soft", _essential_num(soft_pe_cap_for_calc, 2, "x")),
                ("Dynamic Cap Hard", _essential_num(hard_pe_cap_for_calc, 2, "x")),
                ("法人代表目標價", _essential_num(ai_target_price, 2, "元")),
                ("法人平均目標價", _essential_num(ai_me_val, 2, "元")),
                ("法人最低目標價", _essential_num(ai_lo_val, 2, "元")),
                ("法人最高目標價", _essential_num(ai_hi_val, 2, "元")),
                ("法人樣本數", f"{int(ai_analyst_count)}位" if s_float(ai_analyst_count) is not None else None),
                ("法人目標價來源", target_price_source if any(v is not None for v in (ai_target_price, ai_me_val, ai_lo_val, ai_hi_val)) else None),
                ("系統最終燈號", final_signal.get("signal") if isinstance(final_signal, dict) else None),
                ("系統操作建議", final_signal.get("advice") if isinstance(final_signal, dict) else None),
            ]
            for row in eps_price_rows:
                scenario_parts = []
                for cap_name, price_key in (("Base", "base_price"), ("Soft", "soft_price"), ("Hard", "hard_price")):
                    price_text = _essential_num(row.get(price_key), 2, "元")
                    if price_text:
                        scenario_parts.append(f"{cap_name} {price_text}")
                if scenario_parts:
                    essential_prompt_fields.append((f"{row.get('tier')} 計算價", " / ".join(scenario_parts)))

            essential_prompt_for_copy = build_essential_version_prompt(
                app_title=APP_PAGE_TITLE,
                stock_id=curr_id,
                stock_name=c_name,
                fields=essential_prompt_fields,
            )


            def _build_prompt_technical_suffix(mode: str) -> str:
                return prompt_technical_suffix(mode, hist=hist, curr_p=curr_p)
            
            # 第 17-C-2：打包提示詞分成「買進決策版 / 研究完整版」
            _render_prompt_pack_compat(
                curr_id=curr_id,
                prompt=essential_prompt_for_copy,
            )
            
            st.markdown("---")

            # ⚔️ 產業同業 PK
            render_peer_compare_panel(curr_id=curr_id, stock_name=c_name)

            # 🌊 雙河流圖 (Tabs)
            render_valuation_river_charts(hist=hist, df_per_bk=df_per_bk)

            # ==========================================
            # 🚀 專業技術線圖與 KD 指標
            # ==========================================
            render_technical_chart_panel(curr_id=curr_id, hist=hist)
        else:
            st.error(f"找不到代號 {curr_id} 的資料，請確認代號是否正確或重新整理。")
