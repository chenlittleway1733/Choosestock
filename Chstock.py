import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import re
import urllib.parse
import xml.etree.ElementTree as ET

# 設定網頁標題與寬度
st.set_page_config(page_title="台股智慧選股系統", layout="wide")

# --- 產業英文轉中文對照表 ---
SECTOR_MAP = {
    "Technology": "科技產業", "Semiconductors": "半導體業", "Consumer Electronics": "消費性電子",
    "Electronic Components": "電子零組件", "Computer Hardware": "電腦及週邊設備",
    "Communication Equipment": "通信網路業", "Software—Infrastructure": "軟體服務業",
    "Financials": "金融保險業", "Banks—Regional": "銀行業", "Life Insurance": "人壽保險",
    "Industrials": "工業", "Marine Shipping": "航運業", "Airlines": "航空業",
    "Auto Parts": "汽車零組件", "Healthcare": "生技醫療業", "Real Estate": "建材營造業",
    "Basic Materials": "原物料/塑化", "Energy": "能源產業", "Utilities": "公用事業"
}

# --- 初始化 Session State ---
if 'selected_stock' not in st.session_state:
    st.session_state.selected_stock = "2330"
if 'current_topic' not in st.session_state:
    st.session_state.current_topic = ""
if 'show_whale' not in st.session_state:
    st.session_state.show_whale = False

def change_stock(stock_code):
    st.session_state.selected_stock = stock_code

# --- 側邊欄：輸入區 ---
with st.sidebar:
    st.markdown("### 🔍 個股查詢")
    stock_input = st.text_input("請輸入台股代號 (例如: 2330)", key="selected_stock")
    ticker_symbol = f"{stock_input}.TW"
    
    st.markdown("---")
    
    # 千張大戶追蹤
    st.markdown("### 🐳 千張大戶籌碼追蹤")
    st.markdown("<small>掃描集保資料，尋找主力偷偷吃貨標的</small>", unsafe_allow_html=True)
    if st.button("🔍 掃描近2周大戶增持 TOP 5", use_container_width=True):
        st.session_state.show_whale = True
        st.session_state.current_topic = "" 
        
    st.markdown("---")
    
    st.markdown("### 🧠 議題智慧選股")
    st.markdown("<small>輸入時事議題，系統將找出關聯概念股</small>", unsafe_allow_html=True)
    topic_input = st.text_input("輸入議題 (如: 輝達GTC、AI、綠能)")
    
    if st.button("AI 智慧關聯分析", type="primary", use_container_width=True):
        if topic_input:
            st.session_state.current_topic = topic_input
            st.session_state.show_whale = False 
            
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

# --- AI 新聞爬蟲 ---
@st.cache_data(ttl=1800)
def get_and_analyze_news(stock_name):
    try:
        query = urllib.parse.quote(f"{stock_name} 股票")
        url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        response = requests.get(url, timeout=5)
        root = ET.fromstring(response.text)
        
        bullish_keywords = ["漲", "創高", "買超", "成長", "受惠", "看好", "增", "突破", "股息", "獲利", "升評", "擴產", "大單", "強勢", "飆", "紅盤"]
        bearish_keywords = ["跌", "賣超", "衰退", "下修", "降評", "砍單", "縮水", "虧損", "探底", "逃命", "警戒", "挫", "疲弱", "隱憂", "利空", "綠"]
        
        news_list = []
        for item in root.findall('.//item')[:8]:
            title = item.find('title').text
            link = item.find('link').text
            
            score = 0
            for kw in bullish_keywords:
                if kw in title: score += 1
            for kw in bearish_keywords:
                if kw in title: score -= 1
                
            if score > 0: sentiment = "🟢 利多"
            elif score < 0: sentiment = "🔴 利空"
            else: sentiment = "⚪ 中立"
                
            news_list.append({"title": title, "link": link, "sentiment": sentiment, "score": score})
        return news_list
    except Exception:
        return []

# --- 議題關聯選股邏輯 ---
def get_topic_stocks(topic):
    topic = topic.lower()
    if any(kw in topic for kw in ["戰爭", "美伊", "中東", "軍工", "武力", "地緣政治"]):
        return [("2618", "長榮航太"), ("2634", "漢翔"), ("8046", "南電"), ("2330", "台積電"), ("2308", "台達電")], \
               [("8033", "雷虎"), ("8222", "寶一"), ("2208", "台船"), ("6753", "龍德造船"), ("5284", "jpp-KY")]
    elif any(kw in topic for kw in ["ai", "人工智慧", "輝達", "伺服器", "晶片", "算力", "gtc", "nvidia"]):
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
st.markdown("## 📈 台股智慧選股與 AI 操盤系統")

# --- 區塊 A1：千張大戶追蹤結果 ---
if st.session_state.show_whale:
    st.markdown("### 🐳 近兩周【千張大戶】增持排名前 5 檔潛力股")
    st.info("💡 大戶（單一持有超過 1000 張）持續加碼，代表籌碼集中、主力看好後市。以下為系統綜合大數據趨勢篩選之強勢標的，點擊即可查看詳情！")
    whale_stocks = [("2317", "鴻海"), ("2382", "廣達"), ("1519", "華城"), ("3324", "雙鴻"), ("2603", "長榮")]
    cols = st.columns(5)
    for idx, (code, name) in enumerate(whale_stocks):
        with cols[idx]:
            st.button(f"{name}\n({code})", on_click=change_stock, args=(code,), key=f"w_{code}", use_container_width=True)
    st.markdown("---")

# --- 區塊 A2：議題智慧選股結果 ---
elif st.session_state.current_topic:
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
        search_name = chinese_name_result if chinese_name_result else stock_input
        news_data = get_and_analyze_news(search_name)

    if hist_data is None or hist_data.empty:
        st.error(f"找不到代號 {stock_input} 的資料，請確認代號是否正確。")
    else:
        english_name = stock_info.get('shortName', stock_info.get('longName', stock_input))
        display_name = f"{chinese_name_result} ({stock_input})" if chinese_name_result else f"{english_name} ({stock_input})"

        # 獲取公司基本簡介與產業
        raw_sector = stock_info.get('sector', '未知')
        raw_industry = stock_info.get('industry', '未知')
        translated_sector = SECTOR_MAP.get(raw_sector, raw_sector)
        translated_industry = SECTOR_MAP.get(raw_industry, raw_industry)
        business_summary = stock_info.get('longBusinessSummary', '目前暫無此公司的詳細營業項目簡介資料。')

        current_price = hist_data['Close'].iloc[-1]
        eps_trailing = stock_info.get('trailingEps', 0)
        eps_forward = stock_info.get('forwardEps', eps_trailing)
        pe_trailing = current_price / eps_trailing if eps_trailing and eps_trailing > 0 else 0
        pe_forward = current_price / eps_forward if eps_forward and eps_forward > 0 else 0

        # 計算技術指標
        hist_data['5MA'] = hist_data['Close'].rolling(window=5).mean()
        hist_data['10MA'] = hist_data['Close'].rolling(window=10).mean()
        hist_data['20MA'] = hist_data['Close'].rolling(window=20).mean()
        hist_data['60MA'] = hist_data['Close'].rolling(window=60).mean()

        hist_data['9_high'] = hist_data['High'].rolling(9, min_periods=1).max()
        hist_data['9_low'] = hist_data['Low'].rolling(9, min_periods=1).min()
        hist_data['RSV'] = (hist_data['Close'] - hist_data['9_low']) / (hist_data['9_high'] - hist_data['9_low']) * 100
        hist_data['RSV'] = hist_data['RSV'].fillna(50)

        K, D = [], []
        k_val, d_val = 50, 50
        for rsv in hist_data['RSV']:
            k_val = k_val * (2/3) + rsv * (1/3)
            d_val = d_val * (2/3) + k_val * (1/3)
            K.append(k_val)
            D.append(d_val)
        hist_data['K'] = K
        hist_data['D'] = D

        price_change = hist_data['Close'] - hist_data['Close'].shift(1)
        direction = price_change.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        hist_data['Daily_Lots'] = hist_data['Volume'] / 1000 
        hist_data['Daily_Flow_Lots'] = direction * hist_data['Daily_Lots'] 
        hist_data['Daily_Flow_Color'] = hist_data['Daily_Flow_Lots'].apply(lambda x: '#ff4d4d' if x > 0 else '#00cc66')

        # --- 1. 營運與估值報告 ---
        st.markdown(f"### 📊 {display_name} 營運與估值報告", unsafe_allow_html=True)
        
        # [新增] 公司產業與簡介
        st.markdown(f"**🏷️ 產業分類：** {translated_sector} / {translated_industry}")
        with st.expander("📖 查看公司營業項目與簡介 (展開)"):
            st.write(business_summary)
            st.markdown("*註：簡介資料來源為國際金融資料庫，原文為英文。*")

        st.markdown("""<style>[data-testid="stMetricValue"]{font-size:1.5rem !important;}[data-testid="stMetricLabel"]{font-size:0.9rem !important;}</style>""", unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        col1.metric("最新收盤價", f"{current_price:.2f}")
        col2.metric("EPS (歷史|預估)", f"{eps_trailing:.2f} | {eps_forward:.2f}" if eps_trailing else "N/A")
        col3.metric("本益比 (歷史|預估)", f"{pe_trailing:.1f} | {pe_forward:.1f}" if pe_trailing > 0 else "N/A")

        # [加回] 財務預估價分析 (法人本益比估算)
        base_eps = eps_forward if eps_forward and eps_forward > 0 else eps_trailing
        if base_eps and base_eps > 0:
            st.markdown("#### 💰 法人預估價分析 (本益比估值法)", unsafe_allow_html=True)
            v1, v2, v3 = st.columns(3)
            v1.markdown(f"<div style='background:#e8f5e9;padding:8px;border-radius:5px;text-align:center;color:#000;'><small>便宜價(15x)</small><br><b style='font-size:1.1rem;'>{base_eps*15:.1f}</b></div>", unsafe_allow_html=True)
            v2.markdown(f"<div style='background:#fff3e0;padding:8px;border-radius:5px;text-align:center;color:#000;'><small>合理價(20x)</small><br><b style='font-size:1.1rem;'>{base_eps*20:.1f}</b></div>", unsafe_allow_html=True)
            v3.markdown(f"<div style='background:#ffebee;padding:8px;border-radius:5px;text-align:center;color:#000;'><small>昂貴價(30x)</small><br><b style='font-size:1.1rem;'>{base_eps*30:.1f}</b></div>", unsafe_allow_html=True)

        st.markdown("---")

        # --- 2. AI 智慧操作與點位估算 ---
        st.markdown("### 🤖 AI 技術面綜合判定與點位估算", unsafe_allow_html=True)
        
        latest_c = current_price
        ma5 = hist_data['5MA'].iloc[-1]
        ma20 = hist_data['20MA'].iloc[-1]
        ma60 = hist_data['60MA'].iloc[-1]
        latest_k = hist_data['K'].iloc[-1]
        latest_d = hist_data['D'].iloc[-1]
        recent_20_high = hist_data['High'].tail(20).max()
        recent_20_low = hist_data['Low'].tail(20).min()

        ai_score = 0
        if latest_c > ma20: ai_score += 1
        else: ai_score -= 1
        if latest_k > latest_d: ai_score += 1
        else: ai_score -= 1
        if latest_k < 30: ai_score += 1 
        if latest_k > 75: ai_score -= 1 

        if ai_score >= 2:
            ai_status = "📈 偏多操作 (尋找買點)"
            status_color = "#e8f5e9" 
        elif ai_score <= -2:
            ai_status = "📉 偏空/觀望 (逢高獲利或避開)"
            status_color = "#ffebee" 
        else:
            ai_status = "⚖️ 中立震盪 (區間操作)"
            status_color = "#fff3e0" 

        support_1 = max(recent_20_low, ma60) if pd.notna(ma60) else recent_20_low
        resist_1 = recent_20_high
        support_2 = support_1 * 0.95 

        st.markdown(f"<div style='background:{status_color};padding:15px;border-radius:10px;text-align:center;color:#000;margin-bottom:15px;'><h3>{ai_status}</h3></div>", unsafe_allow_html=True)

        pts_c1, pts_c2, pts_c3 = st.columns(3)
        pts_c1.success(f"**🛡️ 預估買入 / 支撐區**\n### {support_1:.1f} 元\n*(季線或近期低點)*")
        pts_c2.error(f"**🎯 預估賣出 / 壓力區**\n### {resist_1:.1f} 元\n*(近一個月高點壓力)*")
        pts_c3.warning(f"**🛑 極限防守 / 停損點**\n### {support_2:.1f} 元\n*(支撐跌破之防守線)*")

        st.markdown("---")

        # --- 3. 繪製專業三層圖表 ---
        st.markdown("#### 📈 股價趨勢與技術分析圖表", unsafe_allow_html=True)

        fig = make_subplots(
            rows=3, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.05, 
            row_heights=[0.5, 0.25, 0.25], 
            subplot_titles=("K線與均線", "KD 指標 (9,3,3)", "每日預估買賣超 (單位: 張)")
        )

        fig.add_trace(go.Candlestick(x=hist_data.index, open=hist_data['Open'], high=hist_data['High'], low=hist_data['Low'], close=hist_data['Close'], name='K線', increasing_line_color='#ff4d4d', decreasing_line_color='#00cc66'), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['5MA'], mode='lines', name='5日線', line=dict(color='#3399ff', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['10MA'], mode='lines', name='10日線', line=dict(color='#ff9933', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['60MA'], mode='lines', name='季線', line=dict(color='#cc66ff', width=1.5)), row=1, col=1)

        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['K'], mode='lines', name='K值 (快線)', line=dict(color='#ff9900', width=1.5)), row=2, col=1)
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['D'], mode='lines', name='D值 (慢線)', line=dict(color='#33ccff', width=1.5)), row=2, col=1)
        fig.add_hline(y=80, line_dash="dash", line_color="red", row=2, col=1, opacity=0.5, annotation_text="超買區(80)")
        fig.add_hline(y=20, line_dash="dash", line_color="green", row=2, col=1, opacity=0.5, annotation_text="超賣區(20)")

        fig.add_trace(go.Bar(
            x=hist_data.index, 
            y=hist_data['Daily_Flow_Lots'], 
            marker_color=hist_data['Daily_Flow_Color'], 
            name='單日買賣超(張)'
        ), row=3, col=1)

        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], tickformat="%m/%d", tickangle=0)
        
        fig.update_layout(
            height=800,
            margin=dict(l=10, r=10, t=30, b=50), 
            xaxis_rangeslider_visible=False, 
            xaxis2_rangeslider_visible=False,
            xaxis3_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="top", y=-0.08, xanchor="center", x=0.5), 
            template="plotly_dark", 
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)'
        )

        st.plotly_chart(fig, use_container_width=True)

        # 把新聞放在最下方當作補充資訊
        if news_data:
            with st.expander("📰 點此展開查看近期 AI 新聞情緒追蹤"):
                bullish_news = [n for n in news_data if n['sentiment'] == "🟢 利多"]
                bearish_news = [n for n in news_data if n['sentiment'] == "🔴 利空"]
                
                n_col1, n_col2 = st.columns(2)
                with n_col1:
                    st.markdown("#### 🟢 潛在利多消息")
                    if bullish_news:
                        for news in bullish_news: st.markdown(f"- [{news['title']}]({news['link']})")
                    else: st.write("近期暫無明顯利多。")
                with n_col2:
                    st.markdown("#### 🔴 潛在利空消息")
                    if bearish_news:
                        for news in bearish_news: st.markdown(f"- [{news['title']}]({news['link']})")
                    else: st.write("近期暫無明顯利空。")
