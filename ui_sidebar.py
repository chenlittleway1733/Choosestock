"""
側邊欄 UI 模組：
包含個股查詢、自選股管理器與系統設定。
"""
from ui_common import *


def render_sidebar():
    """渲染左側欄，並回傳主畫面需要共用的 sidebar 狀態。"""
    # ==========================================
    # 4. 側邊欄：功能選單與系統設定
    # ==========================================
    with st.sidebar:
        st.markdown("### 🔍 個股查詢")
        st.text_input("輸入台股代號", value=st.session_state.selected_stock, key="stock_input_widget", on_change=on_stock_input_change)
        st.markdown("<div style='color:#ff8c00; font-size:0.8rem; margin-top:-10px; margin-bottom:10px;'>💡 提示：輸入完畢請務必按 <b>Enter 鍵</b> 確認送出</div>", unsafe_allow_html=True)
    
        options = ["-- 快速切換標的 --"]
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
                        else:
                            options.append(f"🏷️ {line}")
            except Exception as e:
                st.warning(f"⚠️ 快速選股名單讀取失敗，已改用最小模式。({str(e)[:80]})")
            
        st.selectbox("⚡ 快速選股名單", options, key="quick_select", on_change=on_quick_select_change)
        if st.button("🗂️ 自選股管理器", use_container_width=True):
            st.session_state.show_watchlist_manager = not st.session_state.get('show_watchlist_manager', False)

        if st.session_state.get('show_watchlist_manager', False):
            with st.container():
                st.markdown("#### 🛠️ 自選股管理器")
                cat_order, cat_map, parse_errors = load_stocklist_structure()
                if parse_errors:
                    st.warning("⚠️ 偵測到檔案格式問題：" + "；".join(parse_errors[:3]))

                issues = validate_stocklist_structure(cat_order, cat_map)
                if issues:
                    st.error("❌ 格式驗證未通過：" + "；".join(issues[:3]))
                else:
                    st.success("✅ 檔案格式驗證通過")

                with st.expander("➕ 新增分類", expanded=False):
                    new_cat = st.text_input("分類名稱", key="mgr_new_cat")
                    if st.button("新增分類", key="mgr_add_cat_btn", use_container_width=True):
                        ok, msg = add_category_to_stocklist(new_cat)
                        (st.success if ok else st.error)(msg)
                        if ok: st.rerun()

                with st.expander("➕ 新增股票", expanded=False):
                    mcol1, mcol2 = st.columns(2)
                    with mcol1:
                        new_code = st.text_input("股票代號", key="mgr_new_code")
                    with mcol2:
                        new_name = st.text_input("股票名稱", key="mgr_new_name")
                    cat_choices = cat_order if cat_order else ["未分類"]
                    new_cat_target = st.selectbox("加入到分類", cat_choices, key="mgr_target_cat")
                    if st.button("新增股票", key="mgr_add_stock_btn", use_container_width=True):
                        ok, msg = add_stock_to_category(new_code, new_name, new_cat_target)
                        (st.success if ok else st.error)(msg)
                        if ok: st.rerun()

                all_stocks = [(c, n, cat) for cat in cat_order for c, n in cat_map.get(cat, [])]
                if all_stocks:
                    with st.expander("🔀 搬移股票", expanded=False):
                        stock_labels = [f"{c} {n}（{cat}）" for c, n, cat in all_stocks]
                        picked = st.selectbox("選擇股票", stock_labels, key="mgr_move_pick")
                        target_cat = st.selectbox("目標分類", cat_order if cat_order else ["未分類"], key="mgr_move_target")
                        pick_code = picked.split(" ")[0]
                        if st.button("搬移到新分類", key="mgr_move_btn", use_container_width=True):
                            ok, msg = move_stock_to_category(pick_code, target_cat)
                            (st.success if ok else st.error)(msg)
                            if ok: st.rerun()

                    with st.expander("🧹 刪除股票", expanded=False):
                        del_pick = st.selectbox("選擇要刪除的股票", stock_labels, key="mgr_del_pick")
                        del_code = del_pick.split(" ")[0]
                        if st.button("刪除股票", key="mgr_del_btn", use_container_width=True):
                            ok, msg = remove_stock_from_stocklist(del_code)
                            (st.success if ok else st.error)(msg)
                            if ok: st.rerun()

                    with st.expander("↕️ 分類內排序（拖曳替代）", expanded=False):
                        sort_cat = st.selectbox("排序分類", cat_order, key="mgr_sort_cat")
                        sort_arr = cat_map.get(sort_cat, [])
                        for i, (sc, sn) in enumerate(sort_arr):
                            c1, c2, c3 = st.columns([0.64, 0.18, 0.18])
                            with c1:
                                st.caption(f"{i+1}. {sc} {sn}")
                            with c2:
                                if st.button("⬆️", key=f"mgr_up_{sort_cat}_{sc}_{i}", use_container_width=True):
                                    ok, msg = move_stock_order_within_category(sort_cat, sc, "up")
                                    (st.success if ok else st.warning)(msg)
                                    if ok: st.rerun()
                            with c3:
                                if st.button("⬇️", key=f"mgr_dn_{sort_cat}_{sc}_{i}", use_container_width=True):
                                    ok, msg = move_stock_order_within_category(sort_cat, sc, "down")
                                    (st.success if ok else st.warning)(msg)
                                    if ok: st.rerun()
                else:
                    st.info("目前尚無股票資料，可先新增分類或股票。")

        st.markdown("---")
        st.markdown("### 🔐 一鍵匯入金鑰")
        uploaded_key_file = st.file_uploader("📂 上傳 key.txt 自動填入", type=["txt"], help="請上傳包含 GEMINI_KEY, FUGLE_KEY, FINMIND_KEY 的純文字檔")
        if uploaded_key_file is not None:
            content = uploaded_key_file.getvalue().decode("utf-8")
            clean_content = re.sub(r'\s+', '', content)
            keys_loaded = 0
            m_gemini = re.search(r'GEMINI_KEY=(.*?)(?:FUGLE_KEY|FINMIND_KEY|$)', clean_content, re.IGNORECASE)
            m_fugle = re.search(r'FUGLE_KEY=(.*?)(?:GEMINI_KEY|FINMIND_KEY|$)', clean_content, re.IGNORECASE)
            m_finmind = re.search(r'FINMIND_KEY=(.*?)(?:GEMINI_KEY|FUGLE_KEY|$)', clean_content, re.IGNORECASE)
        
            if m_gemini and m_gemini.group(1):
                st.session_state.api_key = m_gemini.group(1)
                keys_loaded += 1
            if m_fugle and m_fugle.group(1):
                st.session_state.fugle_key = m_fugle.group(1)
                keys_loaded += 1
            if m_finmind and m_finmind.group(1):
                st.session_state.finmind_key = m_finmind.group(1)
                keys_loaded += 1
            
            if keys_loaded > 0:
                st.success(f"✅ 成功載入 {keys_loaded} 組金鑰！密碼框已自動填滿，請點擊下方「🔄 重新整理快取」套用。")
            else:
                st.error("❌ 找不到有效的金鑰，請確認檔案格式是否正確。")

        if st.button("🔄 重新整理快取", use_container_width=True):
            st.cache_data.clear(); st.rerun()
        st.markdown("---")
        st.markdown("### 🤖 AI 功能設定")
        st.session_state.api_key = st.text_input("🔑 Gemini API Key", type="password", value=st.session_state.api_key)
        st.caption("供個股財報補查、ETF 持股補查與產業同業分析使用；模型固定為 Gemini 3.1 Pro Preview。")

        st.markdown("---")
        st.markdown("### ⚔️ 產業同業 PK")
        if st.button("🤖 尋找同業競爭對手並 PK", use_container_width=True):
            if not st.session_state.api_key: st.warning("請先輸入您的 API Key。")
            else: st.session_state.show_pk = True; st.rerun()

        st.markdown("---")
        st.markdown("### 📈 進階資料源設定")
        st.session_state.fugle_key = st.text_input("🔑 Fugle (富果) API Key (選填)", type="password", value=st.session_state.fugle_key)
        st.session_state.finmind_key = st.text_input("🔑 FinMind API Key (選填)", type="password", value=st.session_state.finmind_key)

        f_ok, m_ok = validate_api_keys(st.session_state.fugle_key, st.session_state.finmind_key)
    
        if st.session_state.fugle_key:
            if f_ok: st.success("✅ 富果 API 連線成功")
            else: st.error("❌ 富果金鑰無效或已過期")
        
        if st.session_state.finmind_key:
            if m_ok: st.success("✅ FinMind API 連線成功")
            else: st.error("❌ FinMind 金鑰無效")
        st.markdown("---")
        st.markdown("### 🩺 Data Health Panel")
        health = st.session_state.get("data_health_stats", {})
        def fmt_health_status(raw_status):
            rs = str(raw_status).upper() if raw_status is not None else "N/A"
            if rs == "N/A":
                return "— 尚未呼叫"
            if rs in ["200", "OK"]:
                return f"✅ 成功 ({raw_status})"
            if rs == "ERR":
                return "❌ 連線錯誤 (ERR)"
            return f"⚠️ 失敗 ({raw_status})"

        if health:
            for src in ["Yahoo", "Fugle", "FinMind", "Gemini"]:
                s = health.get(src, {"last_success": None, "error_count": 0, "last_status": "N/A"})
                last_ok = s.get("last_success") or "尚無"
                err_cnt = s.get("error_count", 0)
                last_st = s.get("last_status", "N/A")
                st.markdown(
                    f"- **{src}**｜最近狀態: `{fmt_health_status(last_st)}`｜錯誤次數: `{err_cnt}`\n"
                    f"  - 最後成功時間: `{last_ok}`"
                )
        else:
            st.info("尚無來源健康資料。")

        error_events = st.session_state.get("error_events", [])
        if error_events:
            with st.expander("🧯 最近非致命錯誤紀錄", expanded=False):
                for ev in reversed(error_events[-10:]):
                    st.markdown(
                        f"- `{ev.get('time', '')}` **{ev.get('source', '')}** / "
                        f"{ev.get('context', '')}：`{ev.get('error', '')}`"
                    )
        st.markdown("---")

    return {
        "f_ok": locals().get("f_ok", None),
        "m_ok": locals().get("m_ok", None),
    }
