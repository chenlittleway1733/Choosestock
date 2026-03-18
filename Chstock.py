import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 設定網頁標題與寬度
st.set_page_config(page_title="台股智慧選股系統", layout="wide")

st.title("📈 台股智慧選股與個股評估系統")

# --- 側邊欄：輸入區 ---
with st.sidebar:
    st.header("選股條件與個股查詢")
    stock_input = st.text_input("請輸入台股代號 (例如: 2330)", "2330")
    
    # 判斷上市或上櫃 (簡單預設為上市 .TW，若需精準可做清單比對)
    # 這裡為方便演示，統一加上 .TW
    ticker_symbol = f"{stock_input}.TW"
    
    if st.button("🔄 重新整理 / 獲取最新資料"):
        st.cache_data.clear() # 清除快取，強制重新抓資料
        st.success("已清除暫存！正在重新獲取最新資料...")

# --- 資料獲取函數 (加入快取機制減少等待) ---
@st.cache_data(ttl=3600) # 快取 1 小時
def get_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1y") # 抓取近一年資料畫圖
        info = ticker.info
        return hist, info
    except Exception as e:
        return None, None

# --- 執行資料抓取 ---
if stock_input:
    with st.spinner('正在從網路獲取最新報價與財報資料...'):
        hist_data, stock_info = get_stock_data(ticker_symbol)

    if hist_data is None or hist_data.empty:
        st.error(f"找不到代號 {stock_input} 的資料，請確認代號是否正確。")
    else:
        # --- 整理股票基本資訊 ---
        # 獲取中文名稱 (Yahoo Finance 通常在 shortName 或 longName 會有中文)
        stock_name = stock_info.get('shortName', stock_info.get('longName', stock_input))
        current_price = hist_data['Close'].iloc[-1]
        
        # 獲取 EPS 資訊
        # trailingEps: 近四季(TTM) EPS
        # forwardEps: 法人/分析師預估未來一年 EPS 平均值
        eps_trailing = stock_info.get('trailingEps', 0)
        eps_forward = stock_info.get('forwardEps', 0) 
        
        # 若無法人預估，則使用近四季 EPS 替代
        if eps_forward is None or eps_forward == 0:
            eps_forward = eps_trailing

        # 計算本益比
        pe_trailing = current_price / eps_trailing if eps_trailing > 0 else 0
        pe_forward = current_price / eps_forward if eps_forward > 0 else 0

        # --- 顯示綜合評估報告 ---
        st.subheader(f"📊 {stock_name} ({stock_input}) 綜合評估報告")
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("最新收盤價", f"{current_price:.2f}")
        col2.metric("近四季 EPS / 預估 EPS", f"{eps_trailing:.2f} / {eps_forward:.2f}")
        col3.metric("歷史本益比 / 預估本益比", f"{pe_trailing:.2f} / {pe_forward:.2f}")
        
        # 簡單估值系統評定
        if pe_forward > 0:
            if pe_forward < 15:
                val_status = "便宜"
                val_color = "green"
            elif pe_forward < 25:
                val_status = "合理"
                val_color = "orange"
            else:
                val_status = "昂貴"
                val_color = "red"
        else:
            val_status = "無法評估"
            val_color = "gray"
            
        col4.markdown(f"系統估值評價：<h2 style='color:{val_color}; margin-top:0px;'>{val_status}</h2>", unsafe_allow_html=True)

        st.markdown("---")

        # --- 財務預估價分析 ---
        st.subheader("💰 財務預估價分析 (基於法人預估平均 EPS)")
        st.markdown(f"*目前計算預估價採用之標準：**法人預估今年 EPS ({eps_forward:.2f} 元)*** \n*(註：此為 Yahoo 財經統整之市場分析師共識平均值)*")
        
        val_col1, val_col2, val_col3 = st.columns(3)
        val_col1.info(f"**便宜價 (15倍本益比)**\n### {(eps_forward * 15):.2f} 元")
        val_col2.warning(f"**合理價 (20倍本益比)**\n### {(eps_forward * 20):.2f} 元")
        val_col3.error(f"**昂貴價 (30倍本益比)**\n### {(eps_forward * 30):.2f} 元")

        st.markdown("---")

        # --- 繪製 K 線圖與均線 (使用 Plotly) ---
        st.subheader("📈 股價趨勢與均線 (5日, 10日, 季線)")
        
        # 計算均線
        hist_data['5MA'] = hist_data['Close'].rolling(window=5).mean()
        hist_data['10MA'] = hist_data['Close'].rolling(window=10).mean()
        hist_data['60MA'] = hist_data['Close'].rolling(window=60).mean() # 季線約 60 個交易日

        # 建立 Plotly 圖表
        fig = go.Figure()

        # 加入 K 線圖
        fig.add_trace(go.Candlestick(
            x=hist_data.index,
            open=hist_data['Open'],
            high=hist_data['High'],
            low=hist_data['Low'],
            close=hist_data['Close'],
            name='K線',
            increasing_line_color='red', decreasing_line_color='green' # 台股習慣：紅漲綠跌
        ))

        # 加入均線
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['5MA'], mode='lines', name='5日線 (5MA)', line=dict(color='blue', width=1)))
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['10MA'], mode='lines', name='10日線 (10MA)', line=dict(color='orange', width=1)))
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['60MA'], mode='lines', name='季線 (60MA)', line=dict(color='purple', width=2)))

        # 隱藏週末的空白日期
        fig.update_xaxes(
            rangebreaks=[dict(bounds=["sat", "mon"])] # 隱藏週六到週一早上的區間
        )

        fig.update_layout(
            height=600,
            margin=dict(l=0, r=0, t=30, b=0),
            xaxis_rangeslider_visible=False, # 隱藏下方預設的拉桿讓畫面更簡潔
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        # 在 Streamlit 顯示互動圖表
        st.plotly_chart(fig, use_container_width=True)
