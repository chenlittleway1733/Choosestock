import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
import re

# 設定網頁標題與寬度
st.set_page_config(page_title="台股智慧選股系統", layout="wide")

# --- 初始化 Session State (確保點擊按鈕可以切換股票) ---
if 'selected_stock' not in st.session_state:
    st.session_state.selected_stock = "2330"
if 'current_topic' not in st.session_state:
    st.session_state.current_topic = ""

# 用於按鈕點擊更新當前股票的函數
def change_stock(stock_code):
    st.session_state.selected_stock = stock_code

# --- 側邊欄：輸入區 ---
with st.sidebar:
    st.markdown("### 🔍 個股查詢")
    # 將輸入框與 session_state 綁定
    stock_input = st.text_input("請輸入台股代號 (例如: 2330)", key="selected_stock")
    ticker_symbol = f"{stock_input}.TW"
    
    st.markdown("---")
    
    st.markdown("### 🧠 議題智慧選股")
    st.markdown("<small>輸入時事議題，系統將找出關聯概念股</small>", unsafe_allow_html=True)
    topic_input = st.text_input("輸入議題 (如: 美伊戰爭、AI、綠能)")
    
    if st.button("AI 智慧關聯分析", type="primary", use_container_width=True):
        if topic_input:
            st.session_state.current_topic = topic_input
            
    st.markdown("---")
    if st.button("🔄 重新整理 / 清除暫存", use_container_width=True):
        st.cache_data.clear() # 清除快取
        st.rerun()

# --- 資料獲取函數 (快取) ---
@st.cache_data(ttl=3600)
def get_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1y") 
        info = ticker.info
        return hist, info
    except Exception:
        return None, None

@st.cache_data(ttl=86400) 
def get_chinese_name(stock_id):
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=5)
        match = re.search(r'<title>(.*?)\(', response.text)
        if match:
            name = match.group(1).strip()
            if "Yahoo" not in name: 
                return name
    except Exception:
        pass
    return None

# --- 議題關聯選股邏輯 (內部智慧引擎) ---
def get_topic_stocks(topic):
    topic = topic.lower()
    if any(kw in topic for kw in ["戰爭", "美伊", "中東", "軍工", "武力", "地緣政治"]):
        return [("2618", "長榮航太"), ("2634", "漢翔"), ("8046", "南電"), ("2330", "台積電"), ("2308", "台達電")], \
               [("8033", "雷虎"), ("8222", "寶一"), ("2208", "台船"), ("6753", "龍德造船"), ("5284", "jpp-KY")]
    elif any(kw in topic for kw in ["ai", "人工智慧", "輝達", "伺服器", "晶片", "算力"]):
        return [("2330", "台積電"), ("2382", "廣達"), ("3231", "緯創"), ("2376", "技嘉"), ("2356", "英業達")], \
               [("6669", "緯穎"), ("3017", "奇鋐"), ("3324", "雙鴻"), ("2368", "金像電"), ("8210", "勤誠")]
    elif any(kw in topic for kw in ["綠能", "缺電", "重電", "太陽能", "風電"]):
        return [("1519", "華城"), ("1513", "中興電"), ("1503", "士電"), ("1514", "亞力"), ("3708", "上緯投控")], \
               [("6806", "森崴能源"), ("8996", "高力"), ("6443", "元晶"), ("6477", "安集"), ("1519", "華城")]
    elif any(kw in topic for kw in ["疫情", "生技", "醫療", "病毒"]):
        return [("1795", "美時"), ("6446", "藥華藥"), ("1701", "中化"), ("4114", "健喬"), ("4105", "東洋")], \
               [("4133", "亞諾法"), ("1325", "恆大"), ("9919", "康那香"), ("6589", "台康生技"), ("4128", "中裕")]
    else:
        # 如果輸入未知的議題，提供大盤概況的熱門股
        return [("2330", "台積電"), ("2454", "聯發科"), ("2317", "鴻海"), ("2881", "富邦金"), ("2412", "中華電")], \
               [("3443", "創意"), ("3661", "世芯-KY"), ("1519", "華城"), ("3231", "緯創"), ("8033", "雷虎")]


# ==========================================
# 主畫面開始
# ==========================================
st.markdown("## 📈 台股智慧選股與個股評估系統")

# --- 區塊 A：議題智慧選股結果 (如有搜尋則顯示) ---
if st.session_state.current_topic:
    st.markdown(f"### 💡 議題【{st.session_state.current_topic}】關聯選股分析")
    st.info("系統已根據您的議題篩選出以下關聯標的。**點擊下方股票按鈕，即可立即查看該股的詳細圖表與評估！**")
    
    potentials, skyrockets = get_topic_stocks(st.session_state.current_topic)
    
    col_p, col_s = st.columns(2)
    with col_p:
        st.markdown("#### 🛡️ 相關潛力股 (受惠/避險)")
        for code, name in potentials:
            # 點擊按鈕時觸發 change_stock 函數更新選擇的股票
            st.button(f"{name} ({code})", on_click=change_stock, args=(code,), key=f"p_{code}", use_container_width=True)
            
    with col_s:
        st.markdown("#### 🚀 可能飆股 (資金集中炒作)")
        for code, name in skyrockets:
            st.button(f"{name} ({code})", on_click=change_stock, args=(code,), key=f"s_{code}", use_container_width=True)
            
    st.markdown("---")

# --- 區塊 B：個股綜合評估 ---
if stock_input:
    with st.spinner('正在獲取最新報價與分析資料...'):
        hist_data, stock_info = get_stock_data(ticker_symbol)
        chinese_name_result = get_chinese_name(stock_input)

    if hist_data is None or hist_data.empty:
        st.error(f"找不到代號 {stock_input} 的資料，請確認代號是否正確。")
    else:
        # 整理資訊與名稱
        english_name = stock_info.get('shortName', stock_info.get('longName', stock_input))
        display_name = f"{chinese_name_result} ({stock_input})" if chinese_name_result else f"{english_name} ({stock_input})"

        current_price = hist_data['Close'].iloc[-1]
        eps_trailing = stock_info.get('trailingEps', 0)
        eps_forward = stock_info.get('forwardEps', eps_trailing)
        
        pe_trailing = current_price / eps_trailing if eps_trailing and eps_trailing > 0 else 0
        pe_forward = current_price / eps_forward if eps_forward and eps_forward > 0 else 0

        # 顯示綜合評估
        st.markdown(f"### 📊 {display_name} 綜合評估報告", unsafe_allow_html=True)
        
        st.markdown("""
            <style>
            [data-testid="stMetricValue"] { font-size: 1.5rem !important; }
            [data-testid="stMetricLabel"] { font-size: 0.9rem !important; }
            </style>
            """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        col1.metric("最新收盤價", f"{current_price:.2f}")
        eps_display = f"{eps_trailing:.2f} | {eps_forward:.2f}" if eps_trailing else "N/A"
        col2.metric("EPS (歷史|預估)", eps_display)
        pe_display = f"{pe_trailing:.1f} | {pe_forward:.1f}" if pe_trailing > 0 else "N/A"
        col3.metric("本益比 (歷史|預估)", pe_display)
        
        # 財務預估價
        st.markdown("#### 💰 財務預估價分析", unsafe_allow_html=True)
        base_eps = eps_forward if eps_forward and eps_forward > 0 else eps_trailing
        st.markdown(f"<small style='color:gray;'>*計算基準：法人預估今年 EPS ({base_eps:.2f} 元)*</small>", unsafe_allow_html=True)

        if base_eps and base_eps > 0:
            val_col1, val_col2, val_col3 = st.columns(3)
            val_col1.markdown(f"<div style='background:#e8f5e9;padding:10px;border-radius:5px;text-align:center;color:#000;'><small>便宜價(15x)</small><br><b style='font-size:1.2rem;'>{base_eps*15:.1f}</b></div>", unsafe_allow_html=True)
            val_col2.markdown(f"<div style='background:#fff3e0;padding:10px;border-radius:5px;text-align:center;color:#000;'><small>合理價(20x)</small><br><b style='font-size:1.2rem;'>{base_eps*20:.1f}</b></div>", unsafe_allow_html=True)
            val_col3.markdown(f"<div style='background:#ffebee;padding:10px;border-radius:5px;text-align:center;color:#000;'><small>昂貴價(30x)</small><br><b style='font-size:1.2rem;'>{base_eps*30:.1f}</b></div>", unsafe_allow_html=True)
        else:
             st.warning("EPS 數據不足，無法計算預估價。")

        st.markdown("---")

        # 繪製 K 線圖
        st.markdown("#### 📈 股價趨勢與均線 (日K)", unsafe_allow_html=True)
        
        hist_data['5MA'] = hist_data['Close'].rolling(window=5).mean()
        hist_data['10MA'] = hist_data['Close'].rolling(window=10).mean()
        hist_data['60MA'] = hist_data['Close'].rolling(window=60).mean()

        fig = go.Figure()

        # K 線
        fig.add_trace(go.Candlestick(
            x=hist_data.index,
            open=hist_data['Open'], high=hist_data['High'],
            low=hist_data['Low'], close=hist_data['Close'],
            name='K線', increasing_line_color='#ff4d4d', decreasing_line_color='#00cc66'
        ))

        # 均線
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['5MA'], mode='lines', name='5日線', line=dict(color='blue', width=1)))
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['10MA'], mode='lines', name='10日線', line=dict(color='orange', width=1)))
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['60MA'], mode='lines', name='季線', line=dict(color='purple', width=1.5)))

        fig.update_xaxes(
            rangebreaks=[dict(bounds=["sat", "mon"])], 
            tickformat="%m/%d", 
            tickangle=0 
        )

        fig.update_layout(
            height=550,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis_rangeslider_visible=False,
            # 【重要修正】將圖例的 xanchor 改為 "left"，x 設為 0，這樣就不會跟右上角的工具列打架了！
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            template="plotly_dark", 
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)'
        )

        st.plotly_chart(fig, use_container_width=True)
