"""Financial statement and valuation panels for ui_main.render_main_page."""

from ui_common import *


def _nullize_text_local(value):
    text = str(value) if value is not None else ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("N/A", "NULL").replace("無資料", "NULL").replace("未捕捉到", "NULL")
    text = re.sub(r"\s+", " ", text)
    return text.strip() if text.strip() else "NULL"


def _format_pct_local(value):
    try:
        x = s_float(value)
    except Exception:
        x = None
    if x is None:
        return "NULL"
    if abs(x) <= 3:
        x *= 100
    return f"{x:.1f}%"


def _build_m10_margin_benchmark_report(summary):
    if not isinstance(summary, dict) or not summary.get("available"):
        return None
    rows = [
        {"項目": "M10 分類", "內容": _nullize_text_local(summary.get("category_name"))},
        {"項目": "狀態", "內容": _nullize_text_local(summary.get("status_label"))},
        {"項目": "品質 / 規則", "內容": f"{_nullize_text_local(summary.get('margin_quality'))} / {_nullize_text_local(summary.get('margin_rule_label'))}"},
        {
            "項目": "毛利率 base / low / high",
            "內容": f"{_format_pct_local(summary.get('base_gross_margin_pct'))} / {_format_pct_local(summary.get('gross_margin_low_pct'))} / {_format_pct_local(summary.get('gross_margin_high_pct'))}",
        },
        {
            "項目": "營益率 base / low / high",
            "內容": f"{_format_pct_local(summary.get('base_operating_margin_pct'))} / {_format_pct_local(summary.get('operating_margin_low_pct'))} / {_format_pct_local(summary.get('operating_margin_high_pct'))}",
        },
        {"項目": "估值用途", "內容": _nullize_text_local(summary.get("usage_label"))},
    ]
    if _nullize_text_local(summary.get("margin_reference_stocks")) != "NULL":
        rows.append({"項目": "參考公司", "內容": _nullize_text_local(summary.get("margin_reference_stocks"))})
    if _nullize_text_local(summary.get("warning")) != "NULL":
        rows.append({"項目": "提醒", "內容": _nullize_text_local(summary.get("warning"))})
    return pd.DataFrame(rows)


def _render_m10_margin_benchmark_summary(summary):
    if not isinstance(summary, dict):
        return
    status = str(summary.get("status") or "")
    color_map = {
        "usable": "#10B981",
        "tracking_only": "#F59E0B",
        "stock_not_valuation_ready": "#F97316",
        "not_applicable": "#94A3B8",
        "missing_stock_model_data": "#64748B",
    }
    color = color_map.get(status, "#94A3B8")
    if not summary.get("available"):
        st.caption("M10 margin benchmark：本股尚未建立分類毛利率 / 營益率 benchmark，Dynamic Cap 沿用既有品質係數設定。")
        return
    st.markdown(
        "<div style='background:#0F172A;color:#E5E7EB;border-left:6px solid "
        f"{color};padding:12px 14px;border-radius:8px;margin-bottom:10px;line-height:1.7;'>"
        f"<div style='font-weight:bold;color:{color};'>M10 margin benchmark：{_nullize_text_local(summary.get('status_label'))}</div>"
        f"<div>分類：{_nullize_text_local(summary.get('category_name'))}｜品質：{_nullize_text_local(summary.get('margin_quality'))}｜規則：{_nullize_text_local(summary.get('margin_rule_label'))}</div>"
        f"<div>毛利率 base/low/high：{_format_pct_local(summary.get('base_gross_margin_pct'))} / {_format_pct_local(summary.get('gross_margin_low_pct'))} / {_format_pct_local(summary.get('gross_margin_high_pct'))}</div>"
        f"<div>營益率 base/low/high：{_format_pct_local(summary.get('base_operating_margin_pct'))} / {_format_pct_local(summary.get('operating_margin_low_pct'))} / {_format_pct_local(summary.get('operating_margin_high_pct'))}</div>"
        f"<div style='color:#FCD34D;'>估值用途：{_nullize_text_local(summary.get('usage_label'))}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_candidate_review_panel(*, curr_id, temp_ai_fin):
    candidate_data = temp_ai_fin.get("_candidate_data") or []
    if not candidate_data:
        return []

    if "financial_candidate_reviews" not in st.session_state:
        st.session_state.financial_candidate_reviews = load_financial_candidate_review_cache().get("reviews", {})
    cached_reviews = load_financial_candidate_review_cache()
    session_reviews = st.session_state.get("financial_candidate_reviews", {})
    merged_candidates = apply_financial_candidate_reviews(candidate_data, cached_reviews, stock_id=curr_id)
    merged_candidates = apply_financial_candidate_reviews(merged_candidates, {"reviews": session_reviews}, stock_id=curr_id)
    temp_ai_fin["_candidate_data"] = merged_candidates
    if isinstance(st.session_state.get("ai_fetched_financials"), dict) and curr_id in st.session_state.ai_fetched_financials:
        st.session_state.ai_fetched_financials[curr_id]["_candidate_data"] = merged_candidates

    candidate_df = build_candidate_data_report(merged_candidates)
    if candidate_df is None or candidate_df.empty:
        return merged_candidates

    st.markdown("##### 🧾 AI 候選資料與審核狀態")
    st.caption("審核狀態會寫入本機 JSON cache；目前不會自動覆蓋正式採用值。")
    st_dataframe(candidate_df, hide_index=True)

    with st.expander("逐欄候選資料審核", expanded=False):
        visible_candidates = merged_candidates[:20]
        for item in visible_candidates:
            if not isinstance(item, dict):
                continue
            candidate_id = item.get("candidate_id", "")
            if not candidate_id:
                continue
            field_label = item.get("field_label") or item.get("field_name") or "未命名欄位"
            status = normalize_candidate_review_status(item.get("review_status"))
            status_label = REVIEW_STATUS_LABELS.get(status, status)
            source_tier = item.get("source_tier", "—")
            source_name = item.get("source_name", "—")
            st.markdown(
                f"**{field_label}**｜候選值 `{_nullize_text_local(item.get('value'))}`｜來源 Level {source_tier} `{source_name}`｜狀態 `{status_label}`"
            )
            safe_key = re.sub(r"[^A-Za-z0-9_]+", "_", str(candidate_id))
            action_cols = st.columns(4)
            actions = [
                ("採用 AI", "accepted", "使用者採用 AI 候選值"),
                ("保留原值", "kept_original", "使用者保留系統原值"),
                ("拒絕", "rejected", "使用者拒絕 AI 候選值"),
                ("需追查", "needs_followup", "使用者標示需追查"),
            ]
            for col, (label, next_status, note) in zip(action_cols, actions):
                with col:
                    if st.button(label, key=f"candidate_review_{curr_id}_{safe_key}_{next_status}", use_container_width=True):
                        record = update_financial_candidate_review(
                            stock_id=curr_id,
                            candidate_id=candidate_id,
                            review_status=next_status,
                            decision_note=note,
                            candidate_snapshot=item,
                        )
                        review_key = financial_candidate_review_key(record["stock_id"], record["candidate_id"])
                        st.session_state.financial_candidate_reviews[review_key] = record
                        refreshed = apply_financial_candidate_reviews(
                            merged_candidates,
                            {"reviews": st.session_state.financial_candidate_reviews},
                            stock_id=curr_id,
                        )
                        temp_ai_fin["_candidate_data"] = refreshed
                        st.session_state.ai_fetched_financials[curr_id]["_candidate_data"] = refreshed
                        st.success(f"{field_label} 已更新為：{REVIEW_STATUS_LABELS.get(next_status, next_status)}")
                        st.rerun()
        if len(merged_candidates) > len(visible_candidates):
            st.caption(f"尚有 {len(merged_candidates) - len(visible_candidates)} 筆候選資料未展開；可先處理前 20 筆核心欄位。")

    return merged_candidates


def _build_programmatic_analyst_fill_scope(info):
    """Return protected programmatic values and the analyst fields still needing AI fill."""
    info = info if isinstance(info, dict) else {}
    field_map = {
        "target_price_high": "targetHighPrice",
        "target_price_avg": "targetMeanPrice",
        "target_price_low": "targetLowPrice",
        "target_price_analyst_count": "numberOfAnalystOpinions",
        "forward_eps_fy1": "forwardEpsFY1",
        "forward_eps_fy1_year": "forwardEpsFY1Year",
        "forward_eps_fy2": "forwardEpsFY2",
        "forward_eps_fy2_year": "forwardEpsFY2Year",
        "forward_eps_fy3": "forwardEpsFY3",
        "forward_eps_fy3_year": "forwardEpsFY3Year",
    }
    snapshot = {}
    missing_fields = []
    for ai_key, info_key in field_map.items():
        raw_value = info.get(info_key)
        if ai_key.endswith("_year"):
            value = raw_value if str(raw_value or "").strip() else None
        else:
            value = s_float(raw_value)
        if value is None:
            missing_fields.append(ai_key)
        else:
            snapshot[ai_key] = value

    if info.get("targetPriceSource"):
        snapshot["target_price_source"] = str(info.get("targetPriceSource"))
    if info.get("forwardEpsFYBasis"):
        snapshot["forward_eps_fy_basis"] = str(info.get("forwardEpsFYBasis"))
    return snapshot, missing_fields


def render_ai_financial_audit_control(*, curr_id, stock_name, info=None):
    """Render the AI financial audit control and return current AI financial state."""
    programmatic_snapshot, missing_analyst_fields = _build_programmatic_analyst_fill_scope(info)
    col_fin_title, col_fin_btn = st.columns([0.6, 0.4])
    with col_fin_title:
        st.markdown("#### 💼 股票預估價")
        if programmatic_snapshot:
            st.caption(
                f"程式已取得 {len([key for key in programmatic_snapshot if key.startswith(('target_price_', 'forward_eps_fy')) and not key.endswith(('_source', '_basis'))])} 個法人目標價 / FY EPS 欄位；"
                f"AI 功能僅補剩餘 {len(missing_analyst_fields)} 個缺值並校對。"
            )
        else:
            st.caption("程式未取得法人目標價 / FY EPS；可用 AI 全方位校對功能補齊缺值。")
    with col_fin_btn:
        if st.button(
            "🪄 啟動 AI 全方位校對與補齊財報",
            disabled=not st.session_state.api_key,
            use_container_width=True,
            help="程式資料優先保留；AI 上網搜尋只補齊缺值並進行交叉校對",
        ):
            with st.spinner("AI 正在聯網為您強行抓取最新財報數據，請稍候...（Pro Only 最多重試 3 次，約需 30-90 秒）"):
                selected_model = get_selected_model_id()
                fetched_data = get_financials_from_ai(
                    stock_name,
                    curr_id,
                    st.session_state.api_key,
                    selected_model,
                    missing_fields=missing_analyst_fields,
                    programmatic_snapshot=programmatic_snapshot,
                )

                if isinstance(fetched_data, dict) and "error" not in fetched_data:
                    core_fin_keys = [
                        "pe",
                        "trailing_eps",
                        "ttm_eps",
                        "latest_month_eps",
                        "latest_quarter_eps",
                        "previous_quarter_eps",
                        "last_two_quarter_eps",
                        "forward_eps",
                        "forward_eps_ai",
                        "forward_eps_consensus",
                        "forward_eps_fy1",
                        "forward_eps_fy2",
                        "forward_eps_fy3",
                        "pb",
                        "gross_margin",
                        "operating_margin",
                        "roe",
                        "yoy",
                        "target_price",
                        "mom",
                        "dividend_yield",
                    ]
                    has_effective_fin_data = any(fetched_data.get(k) not in (None, "", "null") for k in core_fin_keys)
                    if not has_effective_fin_data:
                        st.warning("⚠️ AI 本次有回應，但未抓到可用財報欄位（可能是來源暫無資料或回傳皆為 null）。請稍後重試或切換標的。")
                        st.session_state.ai_fetched_financials.pop(curr_id, None)
                        st.stop()

                    model_label_map = {
                        "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview (付費版)",
                    }
                    model_id = fetched_data.get("model_used", selected_model)
                    model_label = model_label_map.get(model_id, model_id)
                    fallback_reason = fetched_data.get("fallback_reason") or ""
                    search_enabled = fetched_data.get("ai_search_enabled", True)
                    if fallback_reason:
                        model_label = f"{model_label}｜{fallback_reason}"
                    fetched_data["model_used"] = model_label
                    fetched_data["_stock_id"] = str(curr_id)
                    fetched_data["_stock_name"] = str(stock_name)
                    if not search_enabled:
                        st.warning("⚠️ 本次 AI 財報補齊未啟用 Google Search，資料不得納入公式極限價。")
                    elif fallback_reason:
                        st.warning(f"⚠️ {fallback_reason}")
                    st.session_state.ai_fetched_financials[curr_id] = fetched_data
                    st.session_state[f"dynamic_cap_refresh_token_{curr_id}"] = str(int(time.time()))
                    st.rerun()
                elif isinstance(fetched_data, dict) and "error" in fetched_data:
                    st.error(f"🚨 AI 抓取失敗：{fetched_data['error']}")
                    if fetched_data.get("last_error"):
                        st.caption(f"最後錯誤：{fetched_data.get('last_error')}")
                    if fetched_data.get("attempts"):
                        with st.expander("🧾 查看 Pro Only 同模型重試紀錄", expanded=False):
                            st.json(fetched_data.get("attempts"))
                else:
                    st.error("🚨 AI 暫時無法找到確切數據，或請求遭拒。")

        temp_ai_fin = st.session_state.ai_fetched_financials.get(curr_id, {})
        if not isinstance(temp_ai_fin, dict):
            temp_ai_fin = {}
        if isinstance(temp_ai_fin, dict) and temp_ai_fin:
            bound_stock_id = str(temp_ai_fin.get("_stock_id") or curr_id)
            if bound_stock_id != str(curr_id):
                st.session_state.ai_fetched_financials.pop(curr_id, None)
                temp_ai_fin = {}
        has_ai_fin_fetch = bool(temp_ai_fin)
        if temp_ai_fin.get("model_used"):
            st.markdown(
                f"<div style='text-align:right; color:#FFD700; font-size:0.85rem; margin-top:5px;'>🤖 驅動核心: <b>{temp_ai_fin['model_used']}</b></div>",
                unsafe_allow_html=True,
            )
            if temp_ai_fin.get("_ai_validation_warnings"):
                st.warning("🧪 AI 財報 JSON 已觸發合理性校驗；部分欄位已自動校正或設為 NULL，詳情可展開原始回報面板查看。")
            raw_state_key = f"show_ai_raw_panel_{curr_id}"
            if raw_state_key not in st.session_state:
                st.session_state[raw_state_key] = False

            btn_label = "🧾 隱藏本次 AI 查詢與回報資料" if st.session_state[raw_state_key] else "🧾 顯示本次 AI 查詢與回報資料"
            if st.button(btn_label, key=f"toggle_ai_raw_btn_{curr_id}", use_container_width=True):
                st.session_state[raw_state_key] = not st.session_state[raw_state_key]

            if st.session_state[raw_state_key]:
                st.caption("以下為本次 AI 全方位校對與補齊財報的查詢內容與原始回報：")
                query_preview = temp_ai_fin.get("query_payload")
                if query_preview:
                    st.code(query_preview, language="json")
                ai_source_df = build_ai_source_trace_report(temp_ai_fin)
                if ai_source_df is not None and not ai_source_df.empty:
                    st.markdown("##### 🔗 AI 逐欄來源追蹤")
                    st_dataframe(ai_source_df, hide_index=True)
                _render_candidate_review_panel(curr_id=curr_id, temp_ai_fin=temp_ai_fin)
                ai_validation_warnings = temp_ai_fin.get("_ai_validation_warnings") or []
                if ai_validation_warnings:
                    st.markdown("##### 🧪 AI JSON 合理性驗證")
                    st.warning(temp_ai_fin.get("_ai_validation_status", "⚠️ AI 欄位已校正"))
                    for warning in ai_validation_warnings[:20]:
                        st.caption(f"- {warning}")
                elif temp_ai_fin.get("_ai_validation_status"):
                    st.success(temp_ai_fin.get("_ai_validation_status"))
                st.json(temp_ai_fin)
    return temp_ai_fin, has_ai_fin_fetch


def render_eps_breakdown_panel(eps_report_df):
    with st.expander("🧾 EPS 口徑拆欄（單季 / TTM / 年度 / Forward）", expanded=False):
        st.caption("避免把最新單季 EPS、TTM EPS、完整年度 EPS、Forward EPS 混稱為『目前 EPS』。目前估值仍以系統 Forward EPS 優先，AI EPS 作為補齊與交叉校對。")
        st_dataframe(eps_report_df, hide_index=True)


def render_financial_quality_report_panel(dq_report_df):
    with st.expander("🩺 統一資料品質報告（系統 / AI / 採用值）", expanded=False):
        st.caption("此表用來檢查每個估值欄位的來源、採用值、來源優先序、期間、AI來源網址與品質狀態。估值模型依欄位優先表取捨，AI 作為補齊與交叉校對。")
        st_dataframe(dq_report_df, hide_index=True)


def render_valuation_detail_panel(
    *,
    val_html,
    target_price_html,
    target_confidence,
    valuation_separation,
    forward_eps_tier_pack,
    industry_profile,
    snapshot_audit,
    dynamic_cap_pack,
    ai_analyst_count,
    ai_hi_val,
    ai_me_val,
    ai_lo_val,
    ai_target_rationale,
):
    st.markdown(clean_html(val_html), unsafe_allow_html=True)

    if target_price_html:
        st.markdown(clean_html(target_price_html), unsafe_allow_html=True)

    with st.expander("🧭 法人目標價可信度 + 公式估值 / 可操作估值分離", expanded=True):
        tc = target_confidence or {}
        st.markdown(
            f"<div style='background:#111827;color:#F3F4F6;border-left:5px solid {tc.get('color', '#FFD700')};padding:12px 14px;border-radius:8px;margin-bottom:10px;line-height:1.7;'>"
            f"<div style='color:#F3F4F6;'><b>法人目標價可信度：</b><span style='color:{tc.get('color', '#FFD700')};font-weight:bold;'>{tc.get('label', '低可信')}</span>｜<span style='color:#D1D5DB;'>{tc.get('message', '')}</span></div>"
            f"<div style='margin-top:4px;color:#F3F4F6;'><b>可操作估值提示：</b><span style='color:#E5E7EB;'>{valuation_separation.get('action_hint', '觀望 / 資料不足')}</span></div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.caption("公式合理估值與公式極限價只顯示模型輸出；可操作估值區間會額外考慮保守 EPS、法人樣本數、系統/AI 分歧警告與產業估值模型。")
        st_dataframe(valuation_separation.get("report"), hide_index=True)

        with st.expander("📆 Dynamic Cap v18.2 EPS 口徑與年期估值", expanded=True):
            ft_summary = forward_eps_tier_pack.get("summary", {}) if isinstance(forward_eps_tier_pack, dict) else {}
            if not isinstance(ft_summary, dict):
                ft_summary = {}
            fy_calendar_notice_html = ""
            if ft_summary.get("fy_calendar_ui_notice"):
                fy_calendar_notice_html = (
                    "<div style='background:#2A2407;color:#FDE68A;border:1px solid #6B5E12;"
                    "padding:7px 9px;border-radius:6px;margin-top:7px;'>"
                    f"{_nullize_text_local(ft_summary.get('fy_calendar_ui_notice'))}"
                    "</div>"
                )
            st.markdown(
                "<div style='background:#111827;color:#F3F4F6;border-left:6px solid #60A5FA;padding:12px 14px;border-radius:8px;margin-bottom:10px;line-height:1.7;'>"
                f"<div style='font-weight:bold;color:#93C5FD;'>市場 EPS 年期判讀：{ft_summary.get('market_view', '資料不足，無法判斷市場 EPS 年期')}</div>"
                f"<div><b>FY 定義：</b>{ft_summary.get('fy_definition', 'FY1/FY2/FY3 為預估年度 EPS 序列')}</div>"
                f"<div><b>FY 年度提示：</b>{_nullize_text_local(ft_summary.get('fy_sequence_text'))}</div>"
                f"{fy_calendar_notice_html}"
                f"<div><b>年度估值倍率 base / soft / hard：</b>{_nullize_text_local(ft_summary.get('base_cap'))}x / {_nullize_text_local(ft_summary.get('soft_cap'))}x / {_nullize_text_local(ft_summary.get('hard_cap'))}x｜{_nullize_text_local(ft_summary.get('cap_definition'))}</div>"
                f"<div>TTM EPS：{_nullize_text_local(ft_summary.get('ttm_eps'))}｜近四季已實現 EPS，用於目前實際獲利估值</div>"
                f"<div>FY1 EPS：{_nullize_text_local(ft_summary.get('fy1_eps'))}｜{_nullize_text_local(ft_summary.get('fy1_label'))}</div>"
                f"<div>FY2 EPS：{_nullize_text_local(ft_summary.get('fy2_eps'))}｜{_nullize_text_local(ft_summary.get('fy2_label'))}</div>"
                f"<div>FY3 EPS：{_nullize_text_local(ft_summary.get('fy3_eps'))}｜{_nullize_text_local(ft_summary.get('fy3_label'))}</div>"
                f"<div>現價隱含 P/E（TTM/FY1/FY2/FY3）：{_nullize_text_local(ft_summary.get('market_pe_ttm'))}x / {_nullize_text_local(ft_summary.get('market_pe_fy1'))}x / {_nullize_text_local(ft_summary.get('market_pe_fy2'))}x / {_nullize_text_local(ft_summary.get('market_pe_fy3'))}x</div>"
                f"<div>EPS 年期基準 / 來源：{_nullize_text_local(ft_summary.get('eps_basis'))}｜{_nullize_text_local(ft_summary.get('eps_source_note'))}</div>"
                "<div style='color:#FCD34D;'>提醒：v18.2 TTM 參考倍率僅搭配 TTM EPS；前瞻倍率僅搭配同年度 FY1 EPS。FY2/FY3 不得套用 TTM-only 倍率。</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            ft_report = forward_eps_tier_pack.get("report") if isinstance(forward_eps_tier_pack, dict) else None
            if ft_report is not None:
                st_dataframe(ft_report, hide_index=True)
            else:
                st.caption("Forward EPS 年期分層估值資料不足。")

        with st.expander("🏭 產業估值模型明細", expanded=False):
            model_built_at = industry_profile.get("model_built_at", "—") if isinstance(industry_profile, dict) else "—"
            model_version = industry_profile.get("model_build_version", "—") if isinstance(industry_profile, dict) else "—"
            model_note = industry_profile.get("model_build_note", "—") if isinstance(industry_profile, dict) else "—"
            st.markdown(
                "<div style='background:#0F172A;color:#E5E7EB;border-left:6px solid #38BDF8;"
                "padding:12px 14px;border-radius:8px;margin-bottom:10px;line-height:1.7;'>"
                f"<div style='font-weight:bold;color:#7DD3FC;'>產業估值模型建立日期：{model_built_at}</div>"
                f"<div>模型版本：{model_version}</div>"
                f"<div style='color:#CBD5E1;'>{model_note}</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            st_dataframe(build_industry_valuation_model_report(industry_profile), hide_index=True)

        with st.expander("🧪 Dynamic Cap v18.2 單次快照稽核表", expanded=True):
            audit_summary = snapshot_audit.get("summary", {}) if isinstance(snapshot_audit, dict) else {}
            audit_color_map = {
                "green": "#10B981",
                "yellow": "#F59E0B",
                "orange": "#F97316",
                "red": "#EF4444",
                "gray": "#9CA3AF",
            }
            audit_color = audit_color_map.get(audit_summary.get("severity", "gray"), "#9CA3AF")
            st.markdown(
                f"<div style='background:#111827;color:#F3F4F6;border-left:6px solid {audit_color};padding:12px 14px;border-radius:8px;margin-bottom:10px;line-height:1.7;'>"
                f"<div style='font-size:1.1rem;font-weight:bold;color:{audit_color};'>稽核結果：{audit_summary.get('audit_label', '—')}｜分數 {audit_summary.get('audit_score', '—')}</div>"
                f"<div><b>建議動作：</b>{audit_summary.get('action', '—')}</div>"
                f"<div><b>產業模型建置：</b>{audit_summary.get('model_built_at', '—')}｜版本 {industry_profile.get('model_build_version', '—')}</div>"
                f"<div><b>目前分類：</b>{audit_summary.get('primary_taxon', '—')}｜hybrid：{audit_summary.get('hybrid_taxons', '—')}</div>"
                f"<div><b>混合後倍率：</b>{audit_summary.get('mixed_caps', '—')}</div>"
                f"<div style='color:#FCD34D;margin-top:4px;'><b>歷史限制：</b>{audit_summary.get('history_note', '')}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.caption("此表只做本次快照稽核，不會自動更新產業分類、hybrid 權重或產業倍率；若要判斷連續幾次，需等雲端歷史資料庫功能。")
            st_dataframe(snapshot_audit.get("report"), hide_index=True)

        if isinstance(dynamic_cap_pack, dict) and dynamic_cap_pack.get("report") is not None:
            with st.expander("⚙️ Dynamic Cap v18.2 逐股倍率明細", expanded=True):
                if dynamic_cap_pack.get("valuation_mode") == "pb_cycle":
                    st.warning("本分類採 P/B 週期模型：P/E Cap 僅作輔助，不直接作買進倍率。")
                else:
                    st.caption("v18.2：直接採用逐股 Company Base / Soft / Hard；不回退舊版、不重複加成，市場熱度也不上修 Hard。")
                m10_margin_summary = dynamic_cap_pack.get("m10_margin_benchmark") or {}
                _render_m10_margin_benchmark_summary(m10_margin_summary)
                m10_margin_report = _build_m10_margin_benchmark_report(m10_margin_summary)
                if m10_margin_report is not None:
                    st_dataframe(m10_margin_report, hide_index=True)
                st_dataframe(dynamic_cap_pack.get("report"), hide_index=True)
                dc_warnings = dynamic_cap_pack.get("warnings") or []
                if dc_warnings:
                    st.warning("Dynamic Cap 模型提醒：" + "；".join(str(x) for x in dc_warnings))

        with st.expander("法人目標價可信度明細", expanded=False):
            st_dataframe(
                build_target_price_confidence_report(ai_analyst_count, ai_hi_val, ai_me_val, ai_lo_val, ai_target_rationale),
                hide_index=True,
            )


def render_final_signal_panel(final_signal):
    with st.expander("🚦 最終操作燈號", expanded=True):
        st.markdown(
            f"<div style='background:#1e1e1e;border-left:7px solid {final_signal.get('color', '#FFD700')};padding:14px;border-radius:10px;margin-bottom:10px;'>"
            f"<div style='font-size:1.35rem;font-weight:bold;color:{final_signal.get('color', '#FFD700')};'>"
            f"{final_signal.get('signal', '觀望')}</div>"
            f"<div style='color:#ddd;margin-top:6px;'><b>操作含義：</b>{final_signal.get('advice', '')}</div>"
            f"<div style='color:#aaa;margin-top:6px;font-size:0.9rem;'>"
            f"資料可信度：{final_signal.get('data_confidence')}｜估值可信度：{final_signal.get('valuation_confidence')}｜操作可信度：{final_signal.get('operation_confidence')}"
            f"</div></div>",
            unsafe_allow_html=True,
        )
        st.caption("燈號會綜合資料分歧、可操作估值區間、法人樣本數、產業估值模型與基本面防呆；只有資料異常-不可判斷才停用買賣判斷，資料分歧則採降權與小量限制。")
        st_dataframe(final_signal.get("report"), hide_index=True)


def render_financial_metric_cards(
    *,
    pe_str,
    f_eps_display,
    latest_rev_display_label,
    rg_color,
    rg_str,
    latest_mom_val,
    latest_mom_str,
    eg_color,
    eg_str_disp,
    gm_om_str,
    roe_str,
    roe_eval,
    de_str,
    de_eval,
):
    mom_color = "#ff4d4d" if latest_mom_val is not None and latest_mom_val > 0 else ("#00cc66" if latest_mom_val is not None and latest_mom_val < 0 else "#fff")
    mom_str_disp = f"<br><span style='font-size:1rem; color:{mom_color};'>MoM: {latest_mom_str}</span>" if latest_mom_str != "N/A" else ""
    fund_html = f"""
    <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 20px;'>
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>歷史本益比 (P/E)</div><div style='font-size:1.3rem; font-weight:bold; color:#fff;'>{pe_str}</div></div>
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>EPS (TTM / Forward)</div><div style='font-size:1.3rem; font-weight:bold; color:#FFD700;'>{f_eps_display}</div></div>
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>營收成長率<br><span style='font-size:0.75rem; color:#888;'>({latest_rev_display_label})</span></div><div style='font-size:1.3rem; font-weight:bold; color:{rg_color};'>{rg_str}{mom_str_disp}</div></div>
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>預估獲利成長 (YoY)</div><div style='font-size:1.3rem; font-weight:bold; color:{eg_color};'>{eg_str_disp}</div></div>
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>毛利率 / 營益率</div><div style='font-size:1.3rem; font-weight:bold; color:#fff;'>{gm_om_str}</div></div>
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>ROE (恆等式校正)</div><div style='font-size:1.3rem; font-weight:bold; color:#00bfff;'>{roe_str}{roe_eval}</div></div>
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'><div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>負債權益比 (D/E)</div><div style='font-size:1.3rem; font-weight:bold; color:#fff;'>{de_str}{de_eval}</div></div>
    </div>
    """
    st.markdown(clean_html(fund_html), unsafe_allow_html=True)
    st.markdown("---")


def render_anomaly_detection_panel(*, eff_pb, df_rev_bk, hist, curr_p):
    st.markdown("#### 🚨 系統異常風險偵測 (Anomaly Detection)", unsafe_allow_html=True)
    anomaly_html = ""
    if eff_pb is not None and eff_pb > 10:
        anomaly_html += f"<div style='background:linear-gradient(90deg, #8b0000 0%, #ff4d4d 100%); color:white; padding:12px; border-radius:8px; margin-bottom:10px; font-weight:bold;'>🔥【極度溢價警示】 股價淨值比 (P/B) 高達 {eff_pb:.1f} 倍，已脫離台股歷史常態評價，隨時有均值回歸的暴跌風險！</div>"

    if df_rev_bk is not None and len(df_rev_bk) >= 2:
        last_mom = df_rev_bk["MoM"].iloc[-1]
        prev_mom = df_rev_bk["MoM"].iloc[-2]
        recent_high_120 = hist["High"].tail(120).max() if len(hist) >= 120 else hist["High"].max()
        price_near_high = curr_p >= (recent_high_120 * 0.9)
        if last_mom < 0 and prev_mom < 0 and price_near_high:
            anomaly_html += f"<div style='background:linear-gradient(90deg, #b8860b 0%, #ff8c00 100%); color:white; padding:12px; border-radius:8px; margin-bottom:10px; font-weight:bold;'>🚸【量價背離風險】 近兩月營收連續衰退 (最新 MoM: {last_mom:.2f}%)，但股價仍高掛在近半年高檔區，請嚴防主力拉高出貨！</div>"

    if anomaly_html == "":
        anomaly_html = "<div style='background:#1e1e1e; color:#00cc66; padding:12px; border-radius:8px; border:1px solid #333;'>✅ 目前未偵測到極端高估 (P/B>10) 或營收背離風險，數據處於相對常態範圍。</div>"

    st.markdown(clean_html(anomaly_html), unsafe_allow_html=True)
    st.markdown("---")


def render_defense_health_cards(
    *,
    dy_color,
    dy_eval,
    dy_str,
    fcf_color,
    fcf_eval,
    fcf_str,
    cr_color,
    cr_eval,
    cr_str,
    fs_color,
    fs_eval,
    fs_str,
):
    st.markdown("#### 🛡️ 防禦力與財務健康檢測 (長線/存股必看)", unsafe_allow_html=True)
    defense_html = f"""
    <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom:20px;'>
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {dy_color};'>
            <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>💰 預估殖利率</div><div style='background:{dy_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{dy_eval}</div>
            </div>
            <div style='font-size:1.6rem; font-weight:bold; color:#fff;'>{dy_str}</div>
        </div>
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {fcf_color};'>
            <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>💵 自由/營業現金流</div><div style='background:{fcf_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{fcf_eval}</div>
            </div>
            <div style='font-size:1.6rem; font-weight:bold; color:#fff;'>{fcf_str}</div>
        </div>
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {cr_color};'>
            <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>⚖️ 流動比率</div><div style='background:{cr_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{cr_eval}</div>
            </div>
            <div style='font-size:1.6rem; font-weight:bold; color:#fff;'>{cr_str}</div>
        </div>
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {fs_color};'>
            <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🩺 F-Score 健康跑分</div><div style='background:{fs_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{fs_eval}</div>
            </div>
            <div style='font-size:1.6rem; font-weight:bold; color:#fff;'>{fs_str}</div>
        </div>
    </div>
    """
    st.markdown(clean_html(defense_html), unsafe_allow_html=True)
    st.markdown("---")


def render_target_price_panel(
    *,
    curr_p,
    ai_hi_val,
    ai_me_val,
    ai_lo_val,
    ai_analyst_count,
    ai_target_rationale,
    target_confidence,
    ai_label,
    ai_period_val,
    target_price_source="",
):
    target_price_source = str(target_price_source or "").strip()
    target_panel_for_prompt = {
        "high": ai_hi_val,
        "mean": ai_me_val,
        "low": ai_lo_val,
        "analyst_count": ai_analyst_count,
        "confidence": target_confidence or classify_target_price_confidence(ai_analyst_count),
        "source": target_price_source or ("無可用法人目標價" if ai_me_val is None else "程式抓取 / AI 全方位校對補缺"),
        "rationale": ai_target_rationale,
    }

    analyst_count_display = ai_analyst_count if ai_analyst_count not in (None, "", "null") else "無"
    target_confidence = target_confidence or classify_target_price_confidence(ai_analyst_count)
    conf_color = target_confidence.get("color", "#FFD700")
    conf_label = target_confidence.get("label", "低可信")
    st.markdown(
        f"#### 🎯 法人預估目標價 (分析師統計：{analyst_count_display} 位｜可信度：<span style='color:{conf_color};'>{conf_label}</span>)",
        unsafe_allow_html=True,
    )
    st.caption(target_confidence.get("message", "分析師樣本數不足時，不宜視為強共識。"))
    if target_price_source and target_price_source != "無可用法人目標價":
        st.caption(f"資料來源：{target_price_source}；程式值優先，AI 僅補缺值。")

    if ai_hi_val is not None and ai_me_val is not None and ai_lo_val is not None:
        v1, v2, v3 = st.columns(3)
        v1.markdown(f"<div style='background:#ffebee;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>最高價</small><br><b>{ai_hi_val:.1f}</b></div>", unsafe_allow_html=True)
        upside = ((ai_me_val / curr_p) - 1) * 100 if curr_p else 0
        v2.markdown(f"<div style='background:#fff3e0;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>平均價</small><br><b>{ai_me_val:.1f}</b><br><small>空間: {upside:+.1f}%</small></div>", unsafe_allow_html=True)
        v3.markdown(f"<div style='background:#e8f5e9;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>最低價</small><br><b>{ai_lo_val:.1f}</b></div>", unsafe_allow_html=True)
        if ai_target_rationale:
            st.caption(f"📌 法人目標價核心理由：{ai_target_rationale}")
        st.markdown("---")
    elif ai_me_val is not None:
        upside_ai = ((ai_me_val / curr_p) - 1) * 100 if curr_p else 0
        st.markdown(
            f"<div style='background:#fff3e0;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>程式 / AI 補缺平均目標價 ({ai_period_val})</small><br><b>{ai_me_val:.1f}</b><br><small>潛在空間: {upside_ai:+.1f}%</small></div>",
            unsafe_allow_html=True,
        )
        if ai_target_rationale:
            st.caption(f"📌 法人目標價核心理由：{ai_target_rationale}")
        st.markdown("---")
    else:
        st.markdown("<span style='color:gray;'>程式與 AI 校對目前皆未取得法人目標價資料。</span>", unsafe_allow_html=True)
        st.markdown("---")

    return target_panel_for_prompt, target_confidence
