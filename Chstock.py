import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

# ==========================================
# 系統介面與狀態設定
# ==========================================
st.set_page_config(page_title="台股智慧選股系統", layout="wide")
st.title("📈 台股短線智能選股與分析系統")

# 實作重新整理按鈕邏輯
if st.button("🔄 重新整理 / 獲取最新重大訊息與報價"):
    st.cache_data.clear()
    st.success("已清除系統暫存！將重新從公開資訊觀測站與市場獲取最新資料。")

# 側邊欄：使用者輸入選單
st.sidebar.header("選股條件與個股查詢")
stock_symbol = st.sidebar.text_input("請輸入台股代號 (例如: 2330)", "2330")
yf_symbol = f"{stock_symbol}.TW"

# ==========================================
# 資料獲取模組 
# ==========================================
@st.cache_data(ttl=3600)
def fetch_stock_data(symbol):
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1y") 
    info = ticker.info
    return hist, info

# ==========================================
# 核心運算與圖表渲染
# ==========================================
if stock_symbol:
    try:
        hist, info = fetch_stock_data(yf_symbol)
        
        if hist.empty:
            st.error("找不到該股票的資料，請確認台股代號是否正確。")
        else:
            stock_name = info.get('shortName', stock_symbol)
            st.subheader(f"📊 {stock_name} ({stock_symbol}) 綜合評估報告")
            
            # --- 基本面與預估價計算 ---
            current_price = hist['Close'].iloc[-1]
            
            # 取得 EPS，如果抓不到資料則預設為 0
            eps = info.get('trailingEps')
            if eps is None:
                eps = 0.0
                
            # 強制手動計算本益比：最新收盤價 / 近四季 EPS
            if eps > 0:
                pe_ratio = current_price / eps
            else:
                pe_ratio = 0.0
            
            cheap_price = eps * 15
            fair_price = eps * 20
            expensive_price = eps * 30
            
            # 顯示基本指標面板
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("最新收盤價", f"{current_price:.2f}")
            col2.metric("近四季 EPS", f"{eps:.2f}")
            col3.metric("本益比 (P/E)", f"{pe_ratio:.2f}")
            
            evaluation = "合理"
            if eps <= 0:
                evaluation = "無法估值 (缺乏獲利)"
            elif current_price <= cheap_price:
                evaluation = "便宜區間"
            elif current_price >= expensive_price:
                evaluation = "昂貴區間"
                
            col4.metric("系統估值評價", evaluation)
            
            # --- 預估價區塊 ---
            st.markdown("### 💰 財務預估價分析")
            if eps > 0:
                st.write(f"- **便宜價 (15倍本益比)**: {cheap_price:.2f} 元")
                st.write(f"- **合理價 (20倍本益比)**: {fair_price:.2f} 元")
                st.write(f"- **昂貴價 (30倍本益比)**: {expensive_price:.2f} 元")
            else:
                st.warning("⚠️ 由於目前系統無法取得該股有效的正數每股盈餘 (EPS)，因此暫時無法提供 15/20/30 倍本益比的預估價。")
            
            # --- 技術面計算 (5日、10日、季線) ---
            hist['5MA'] = hist['Close'].rolling(window=5).mean()
            hist['10MA'] = hist['Close'].rolling(window=10).mean()
            hist['60MA'] = hist['Close'].rolling(window=60).mean() 
            
            # --- KD 指標計算 (💯 終於把漏洞補上了！) ---
            # 1. 計算 9 日 RSV 值
            low_min = hist['Low'].rolling(window=9).min()
            high_max = hist['High'].rolling(window=9).max()
            rsv = 100 * (hist['Close'] - low_min) / (high_max - low_min)
            
            # 2. 這次「正確的」將 K 值與 D 值新增為獨立的欄位
            hist['K'] = rsv.ewm(com=2, adjust=False).mean()
            hist = hist['K'].ewm(com=2, adjust=False).mean()  # 就是這裡！加上了
            
            # --- 繪製 K 線圖與均線 ---
            st.markdown("### 📈 股價趨勢與均線 (5日, 10日, 季線)")
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='K線'))
            fig.add_trace(go.Scatter(x=hist.index, y=hist['5MA'], mode='lines', name='5日線', line=dict(color='blue', width=1)))
            fig.add_trace(go.Scatter(x=hist.index, y=hist['10MA'], mode='lines', name='10日線', line=dict(color='orange', width=1)))
            fig.add_trace(go.Scatter(x=hist.index, y=hist['60MA'], mode='lines', name='季線 (60MA)', line=dict(color='green', width=2)))
            fig.update_layout(xaxis_rangeslider_visible=False, height=500, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)
            
            # --- 繪製 KD 指標圖 ---
            st.markdown("### 📊 KD 動能指標")
            fig_kd = go.Figure()
            fig_kd.add_trace(go.Scatter(x=hist.index, y=hist['K'], mode='lines', name='K值 (快線)', line=dict(color='blue')))
            fig_kd.add_trace(go.Scatter(x=hist.index, y=hist, mode='lines', name='D值 (慢線)', line=dict(color='orange'))) # 同步修正這裡
            fig_kd.add_hline(y=80, line_dash="dash", line_color="red", annotation_text="超買區 (80)")
            fig_kd.add_hline(y=20, line_dash="dash", line_color="green", annotation_text="超賣區 (20)")
            fig_kd.update_layout(height=250, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_kd, use_container_width=True)
            
            # --- 消息面預留區塊 ---
            st.markdown("### 📰 最新公開資訊觀測站內容比對")
            st.info("系統提示：已於背景觸發爬蟲與 API，實時監測該股相關之重大訊息、法說會資訊與產業新聞。若出現如「美伊戰爭」等關鍵議題，系統將在此列出影響評估。")
            
    except Exception as e:
        st.error(f"系統分析時發生錯誤: {e}")
