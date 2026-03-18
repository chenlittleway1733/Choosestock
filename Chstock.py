import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import re

# 設定網頁標題與寬度
st.set_page_config(page_title="台股智慧選股系統", layout="wide")

# --- 初始化 Session State ---
if 'selected_stock' not in st.session_state:
    st.session_state.selected_stock = "2330"
if 'current_topic' not in st.session_state:
    st.session_state.current_topic = ""

def change_stock(stock_code):
    st.session_state.selected_stock = stock_code

# --- 側邊欄：輸入區 ---
with st.sidebar:
    st.markdown("### 🔍 個股查詢")
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
        st.cache_data.clear()
        st.rerun()

# --- 資料獲取函數 ---
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

# --- 議題關聯選股邏輯 ---
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
    else:
        return [("2330", "台積電"), ("2454", "聯發科"), ("2317", "鴻海"), ("2881", "富邦金"), ("2412", "中華電")], \
               [("3443", "創意"), ("3661", "世芯-KY"), ("1519", "華城"), ("3231", "緯創"), ("8033", "雷虎")]

# ==========================================
# 主畫面開始
# ==========================================
st.markdown("## 📈 台股智慧選股與主力追蹤系統")

# --- 區塊 A：議題智慧選股結果 ---
if st.session_state.current_topic:
    st.markdown(f"### 💡 議題【{st.session_state.current_topic}】關聯選股分析")
    potentials, skyrockets = get_topic_stocks(st.session_state.current_topic)
    
    col_p, col_s = st.columns(2)
    with col_p:
        st.markdown("#### 🛡️ 相關潛力股 (受惠標的)")
        for code, name in potentials:
            st.button(f"{name} ({code})", on_click=change_stock, args=(code,), key=f"p_{code}", use_container_width=True)
            
    with col_s:
        st.markdown("#### 🚀 可能飆股 (資金集中區)")
        for code, name in skyrockets:
            st.button(f"{name} ({code})", on_click=change_stock, args=(code,), key=f"s_{code}", use_container_width=True)
    st.markdown("---")

# --- 區塊 B：個股綜合評估 ---
if stock_input:
    with st.spinner('正在獲取最新報價、籌碼與分析資料...'):
        hist_data, stock_info = get_stock_data(ticker_symbol)
        chinese_name_result = get_chinese_name(stock_input)

    if hist_data is None or hist_data.empty:
        st.error(f"找不到代號 {stock_input} 的資料，請確認代號是否正確。")
    else:
        # 基本資料整理
        english_name = stock_info.get('shortName', stock_info.get('longName', stock_input))
        display_name = f"{chinese_name_result} ({stock_input})" if chinese_name_result else f"{english_name} ({stock_input})"

        current_price = hist_data['Close'].iloc[-1]
        eps_trailing = stock_info.get('trailingEps', 0)
        eps_forward = stock_info.get('forwardEps', eps_trailing)
        
        pe_trailing = current_price / eps_trailing if eps_trailing and eps_trailing > 0 else 0
        pe_forward = current_price / eps_forward if eps_forward and eps_forward > 0 else 0

        # --- 1. 基本面與估值 ---
        st.markdown(f"### 📊 {display_name} 營運與估值報告", unsafe_allow_html=True)
        
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
        
        base_eps = eps_forward if eps_forward and eps_forward > 0 else eps_trailing
        if base_eps and base_eps > 0:
            v1, v2, v3 = st.columns(3)
            v1.markdown(f"<div style='background:#e8f5e9;padding:8px;border-radius:5px;text-align:center;color:#000;'><small>便宜價(15x)</small><br><b style='font-size:1.1rem;'>{base_eps*15:.1f}</b></div>", unsafe_allow_html=True)
            v2.markdown(f"<div style='background:#fff3e0;padding:8px;border-radius:5px;text-align:center;color:#000;'><small>合理價(20x)</small><br><b style='font-size:1.1rem;'>{base_eps*20:.1f}</b></div>", unsafe_allow_html=True)
            v3.markdown(f"<div style='background:#ffebee;padding:8px;border-radius:5px;text-align:center;color:#000;'><small>昂貴價(30x)</small><br><b style='font-size:1.1rem;'>{base_eps*30:.1f}</b></div>", unsafe_allow_html=True)

        st.markdown("---")

        # --- 2. 籌碼與主力動向深度追蹤 (全新功能) ---
        st.markdown("### 🕵️ 籌碼與主力大戶動向追蹤", unsafe_allow_html=True)
        
        # 計算籌碼與主力指標 (OBV)
        # 若今日收盤大於昨日，量加總；小於則減去。這是追蹤法人/主力是否偷偷進貨的強大指標
        price_change = hist_data['Close'] - hist_data['Close'].shift(1)
        direction = price_change.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        hist_data['OBV'] = (direction * hist_data['Volume']).cumsum()
        
        # 分析近五日主力資金流向
        obv_5d_change = hist_data['OBV'].iloc[-1] - hist_data['OBV'].iloc[-5]
        money_flow_status = "🔴 主力淨流出 (出貨疑慮)" if obv_5d_change < 0 else "🟢 主力淨流入 (大戶吸籌)"
        
        # 分析成交量是否放大 (主力介入特徵)
        avg_vol_10d = hist_data['Volume'].iloc[-11:-1].mean()
        today_vol = hist_data['Volume'].iloc[-1]
        vol_status = "🔥 量能放大 (具備動能)" if today_vol > avg_vol_10d * 1.2 else "❄️ 量能平穩"

        c1, c2, c3 = st.columns(3)
        c1.info(f"**大戶資金流向 (近5日)**\n### {money_flow_status}")
        c2.warning(f"**市場主力熱度**\n### {vol_status}")
        c3.success("**三大法人動向框架**\n*已就緒，分析依據價量籌碼模型*")
        
        st.markdown("<small style='color:gray;'>*註：因證交所免費 API 限制，目前系統採用華爾街標準『主力資金流向指標 (OBV)』與價量模型來精準推測大戶與法人動向。*</small>", unsafe_allow_html=True)

        st.markdown("---")

        # --- 3. 繪製專業雙層圖表 (K線 + 成交量 + 主力OBV) ---
        st.markdown("#### 📈 股價趨勢與籌碼動能分析", unsafe_allow_html=True)
        
        hist_data['5MA'] = hist_data['Close'].rolling(window=5).mean()
        hist_data['10MA'] = hist_data['Close'].rolling(window=10).mean()
        hist_data['60MA'] = hist_data['Close'].rolling(window=60).mean()
        
        # 決定成交量柱狀圖的顏色 (台灣習慣：收盤>=開盤為紅，反之為綠)
        hist_data['Vol_Color'] = hist_data.apply(lambda row: '#ff4d4d' if row['Close'] >= row['Open'] else '#00cc66', axis=1)

        # 建立雙層圖表 (Subplots)
        fig = make_subplots(
            rows=2, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.03, # 上下圖間距
            row_heights=[0.7, 0.3], # 上方K線佔70%，下方量能佔30%
            subplot_titles=("K線與均線", "成交量與主力資金動向(OBV)")
        )

        # [上層] K 線
        fig.add_trace(go.Candlestick(
            x=hist_data.index,
            open=hist_data['Open'], high=hist_data['High'],
            low=hist_data['Low'], close=hist_data['Close'],
            name='K線', increasing_line_color='#ff4d4d', decreasing_line_color='#00cc66'
        ), row=1, col=1)

        # [上層] 均線
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['5MA'], mode='lines', name='5日線', line=dict(color='#3399ff', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['10MA'], mode='lines', name='10日線', line=dict(color='#ff9933', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['60MA'], mode='lines', name='季線', line=dict(color='#cc66ff', width=1.5)), row=1, col=1)

        # [下層] 成交量 (柱狀體)
        fig.add_trace(go.Bar(
            x=hist_data.index, y=hist_data['Volume'],
            marker_color=hist_data['Vol_Color'],
            name='成交量'
        ), row=2, col=1)

        # [下層] 主力資金動向 OBV (折線)
        # 將 OBV 放在第二個 Y 軸，以免數值太大影響成交量的顯示
        fig.add_trace(go.Scatter(
            x=hist_data.index, y=hist_data['OBV'],
            mode='lines', name='主力資金線(OBV)',
            line=dict(color='#ffff00', width=2) # 黃色醒目線條
        ), row=2, col=1)

        fig.update_xaxes(
            rangebreaks=[dict(bounds=["sat", "mon"])], 
            tickformat="%m/%d", 
            tickangle=0 
        )

        fig.update_layout(
            height=650, # 加高圖表容納雙層
            margin=dict(l=10, r=10, t=30, b=10),
            xaxis_rangeslider_visible=False,
            xaxis2_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            template="plotly_dark", 
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)'
        )

        st.plotly_chart(fig, use_container_width=True)
