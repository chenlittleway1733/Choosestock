import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
# 重新引入 twstock 來獲取中文名稱，因為 requirements.txt 已經有 lxml，現在應該可以正常運作了
import twstock 

# 設定網頁標題與寬度
st.set_page_config(page_title="台股智慧選股系統", layout="wide")

# 使用較小的標題
st.markdown("### 📈 台股智慧選股與個股評估系統")

# --- 側邊欄：輸入區 ---
with st.sidebar:
    st.header("個股查詢")
    stock_input = st.text_input("請輸入台股代號 (例如: 2330)", "2330")
    
    # 這裡為方便演示，統一加上 .TW
    ticker_symbol = f"{stock_input}.TW"
    
    st.markdown("---")
    if st.button("🔄 重新整理 / 獲取最新資料", type="primary"):
        st.cache_data.clear() # 清除快取
        st.rerun() # 重新執行 App

# --- 資料獲取函數 (加入快取) ---
@st.cache_data(ttl=3600)
def get_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1y") # 抓近一年畫圖
        info = ticker.info
        return hist, info
    except Exception:
        return None, None

# --- 獲取中文名稱函數 ---
@st.cache_data(ttl=86400) # 中文名稱很久才變一次，快取久一點
def get_chinese_name(stock_id):
    try:
        # twstock.codes 是一個包含所有台股代號資訊的字典
        if stock_id in twstock.codes:
            return twstock.codes[stock_id].name
    except:
        pass
    return None

# --- 主程式邏輯 ---
if stock_input:
    with st.spinner('正在獲取最新報價與分析資料...'):
        hist_data, stock_info = get_stock_data(ticker_symbol)
        chinese_name_result = get_chinese_name(stock_input)

    if hist_data is None or hist_data.empty:
        st.error(f"找不到代號 {stock_input} 的資料，請確認代號是否正確。")
    else:
        # --- 1. 整理資訊與名稱 ---
        english_name = stock_info.get('shortName', stock_info.get('longName', stock_input))
        
        # 優先顯示中文名稱，如果找不到就顯示英文
        if chinese_name_result:
            display_name = f"{chinese_name_result} ({stock_input})"
        else:
            display_name = f"{english_name} ({stock_input})"

        current_price = hist_data['Close'].iloc[-1]
        eps_trailing = stock_info.get('trailingEps', 0)
        eps_forward = stock_info.get('forwardEps', eps_trailing) # 若無預估則用歷史替代
        
        # 避免 EPS 為 0 或 None 導致除數錯誤
        if eps_trailing and eps_trailing > 0:
            pe_trailing = current_price / eps_trailing
        else:
            pe_trailing = 0
            
        if eps_forward and eps_forward > 0:
            pe_forward = current_price / eps_forward
        else:
             pe_forward = 0

        # --- 2. 顯示評估報告 (使用自訂 HTML 縮小字體) ---
        # 使用 markdown 搭配 HTML 來控制標題大小
        st.markdown(f"#### 📊 {display_name} 綜合評估", unsafe_allow_html=True)
        
        # 自定義 CSS 樣式來縮小 metric 的字體
        st.markdown("""
            <style>
            [data-testid="stMetricValue"] {
                font-size: 1.5rem !important;
            }
            [data-testid="stMetricLabel"] {
                font-size: 0.9rem !important;
            }
            </style>
            """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        col1.metric("最新收盤價", f"{current_price:.2f}")
        # 顯示格式：近四季 | 預估今年
        eps_display = f"{eps_trailing:.2f} | {eps_forward:.2f}" if eps_trailing else "N/A"
        col2.metric("EPS (歷史|預估)", eps_display)
        
        pe_display = f"{pe_trailing:.1f} | {pe_forward:.1f}" if pe_trailing > 0 else "N/A"
        col3.metric("本益比 (歷史|預估)", pe_display)
        
        st.markdown("---")

        # --- 3. 財務預估價 (縮小版面) ---
        st.markdown("#### 💰 財務預估價分析", unsafe_allow_html=True)
        # 使用較小的字體顯示基準
        base_eps = eps_forward if eps_forward and eps_forward > 0 else eps_trailing
        st.markdown(f"<small style='color:gray;'>*計算基準：法人預估今年 EPS ({base_eps:.2f} 元)*</small>", unsafe_allow_html=True)

        if base_eps and base_eps > 0:
            val_col1, val_col2, val_col3 = st.columns(3)
            # 使用 HTML 創建較小的價格顯示區塊
            val_col1.markdown(f"<div style='background:#e8f5e9;padding:10px;border-radius:5px;text-align:center;'><small>便宜價(15x)</small><br><b>{base_eps*15:.1f}</b></div>", unsafe_allow_html=True)
            val_col2.markdown(f"<div style='background:#fff3e0;padding:10px;border-radius:5px;text-align:center;'><small>合理價(20x)</small><br><b>{base_eps*20:.1f}</b></div>", unsafe_allow_html=True)
            val_col3.markdown(f"<div style='background:#ffebee;padding:10px;border-radius:5px;text-align:center;'><small>昂貴價(30x)</small><br><b>{base_eps*30:.1f}</b></div>", unsafe_allow_html=True)
        else:
             st.warning("EPS 數據不足，無法計算預估價。")

        st.markdown("---")

        # --- 4. 繪製 K 線圖 (加入日期格式化) ---
        st.markdown("#### 📈 股價趨勢與均線 (日K)", unsafe_allow_html=True)
        
        # 計算均線
        hist_data['5MA'] = hist_data['Close'].rolling(window=5).mean()
        hist_data['10MA'] = hist_data['Close'].rolling(window=10).mean()
        hist_data['60MA'] = hist_data['Close'].rolling(window=60).mean()

        # 建立 Plotly 圖表
        fig = go.Figure()

        # K 線
        fig.add_trace(go.Candlestick(
            x=hist_data.index,
            open=hist_data['Open'], high=hist_data['High'],
            low=hist_data['Low'], close=hist_data['Close'],
            name='K線', increasing_line_color='#ff4d4d', decreasing_line_color='#00cc66'
        ))

        # 均線 (線條調細一點)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['5MA'], mode='lines', name='5日線', line=dict(color='blue', width=1)))
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['10MA'], mode='lines', name='10日線', line=dict(color='orange', width=1)))
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['60MA'], mode='lines', name='季線', line=dict(color='purple', width=1.5)))

        # *** 關鍵修改：設定 X 軸日期格式 ***
        fig.update_xaxes(
            rangebreaks=[dict(bounds=["sat", "mon"])], # 隱藏假日
            tickformat="%m/%d",  # <--- 這裡設定為 "月/日" 格式，例如 03/18
            dtick="M1", # 這裡設定刻度間距，M1 代表一個月一跳，避免日期太擠
            tickangle=-45, # 日期轉個角度比較不會重疊
        )

        # 調整圖表版面
        fig.update_layout(
            height=500, # 高度稍微調小適應平板
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            # 設定深色模式背景，讓圖表在深色主題下更好看
            template="plotly_dark", 
            paper_bgcolor='rgba(0,0,0,0)', # 透明背景融入 Streamlit 主題
            plot_bgcolor='rgba(0,0,0,0)'
        )

        st.plotly_chart(fig, use_container_width=True)
