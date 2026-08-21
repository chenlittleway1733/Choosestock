""" 
台股聯網 AI 投資戰情室 - Streamlit 入口檔
執行方式：
    streamlit run app.py
""" 

import streamlit as st

from app_version import APP_DISPLAY_VERSION, APP_PAGE_TITLE
from ui import render_main_page, render_sidebar
from utils import init_session_state

# ==========================================
# 0. 網頁基本設定
# ==========================================
st.set_page_config(page_title=APP_PAGE_TITLE, layout="wide")
st.markdown('<meta name="google" content="notranslate">', unsafe_allow_html=True)

# ==========================================
# 0.1 密碼登入驗證機制
# ==========================================
def check_password():
    """驗證使用者是否輸入了正確的密碼"""
    # 如果 session_state 中已經記錄了密碼正確，就直接放行
    if st.session_state.get("password_correct", False):
        return True

    # 繪製置中的登入畫面
    st.markdown(
        f"<h1 style='text-align: center; margin-top: 10vh;'>🔒 WAY AI 投資戰情室 {APP_DISPLAY_VERSION}</h1>",
        unsafe_allow_html=True,
    )
    st.markdown("<h4 style='text-align: center; color: gray;'>此為專屬系統，請輸入密碼以繼續</h4>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        def password_entered():
            # 從 Streamlit Secrets 讀取密碼，避免將密碼寫死在程式碼中
            app_password = st.secrets.get("APP_PASSWORD", "")

            # 若尚未設定 APP_PASSWORD，直接拒絕登入並提示到部署後台設定
            if not app_password:
                st.session_state["password_correct"] = False
                st.session_state["password_config_missing"] = True
                return

            st.session_state["password_config_missing"] = False
            if st.session_state["password_input"] == app_password:
                st.session_state["password_correct"] = True
                del st.session_state["password_input"]  # 驗證成功後清除密碼暫存，提升安全性
            else:
                st.session_state["password_correct"] = False

        st.text_input(
            "密碼", 
            type="password", 
            on_change=password_entered, 
            key="password_input", 
            label_visibility="collapsed", 
            placeholder="請輸入密碼後按 Enter 鍵確認"
        )
        
        # 如果有輸入過密碼且錯誤，顯示提示
        if st.session_state.get("password_config_missing", False):
            st.error("❌ 尚未設定 APP_PASSWORD，請到 Streamlit Secrets 新增 APP_PASSWORD。")
        elif "password_correct" in st.session_state and not st.session_state["password_correct"]:
            st.error("❌ 密碼錯誤！請重新輸入。")
            
    return False

# 如果密碼驗證未通過，強制停止程式執行，不渲染後續的主畫面
if not check_password():
    st.stop()

# ==========================================
# 以下為原有的主程式渲染邏輯
# ==========================================
init_session_state()

sidebar_state = render_sidebar()
render_main_page(sidebar_state)
