import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests  # 新增：用於輕量抓取網頁
import re        # 新增：用於正規表達式解析

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

# --- 獲取中文名稱函數 (改用輕量級網頁抓取，徹底解決 twstock 與 lxml 報錯問題) ---
@st.cache_data(ttl=86400) 
def get_chinese_name(stock_id):
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        # 直接從 Yahoo 財經的網頁標題擷取中文名稱，不依賴任何外部套件
        match = re.search(r'<title>(.*?)\(', response.text)
        if match: 
            return match.group(1).strip()
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

        # --- 3.5 產業前景與競爭優勢 (專家系統量化推導) ---
        st.markdown("#### 🌟 產業前景與競爭優勢評估", unsafe_allow_html=True)
        st.markdown("<small style='color:gray;'>*註：此區塊非使用 AI，而是根據全球產業分類與財報毛利率、營益率特徵，進行客觀的競爭力推導。*</small>", unsafe_allow_html=True)

        # 獲取評估所需數據
        sector = stock_info.get('sector', '')
        industry = stock_info.get('industry', '')
        gross_margin = stock_info.get('grossMargins')
        op_margin = stock_info.get('operatingMargins')
        
        # 1. 市場趨勢判定 (基於產業鏈類別)
        hot_industries = ['Semiconductor', 'Software', 'Hardware', 'Electronic', 'IT Services', 'Communication', 'Technology']
        is_hot = any(hot in sector for hot in hot_industries) or any(hot in industry for hot in hot_industries)
        
        if is_hot:
            trend_icon, trend_title, trend_desc = "🚀", "長線成長大趨勢", f"所屬板塊 ({industry}) 涵蓋高階運算、AI 應用或資料中心等剛性需求，具備長期市場成長潛力。"
            trend_color = "#ff4d4d" # 亮紅色
        else:
            trend_icon, trend_title, trend_desc = "🏭", "穩定或景氣循環產業", f"所屬板塊 ({industry}) 發展相對成熟，需特別留意整體景氣波動或公司的特殊利基點。"
            trend_color = "#FFD700" # 金黃色

        # 2. 護城河判定 (基於毛利率 - 專利與技術門檻的財務體現)
        if gross_margin is None:
            moat_icon, moat_title, moat_desc, moat_color = "❓", "數據不足", "缺乏毛利率數據無法精確評估。", "gray"
        elif gross_margin >= 0.40:
            moat_icon, moat_title, moat_desc, moat_color = "🏰", "極寬廣 (強大護城河)", f"毛利率高達 {gross_margin*100:.1f}%！顯示公司具備極高的技術門檻、專利佈局或客戶轉換成本，對手極難搶奪市佔率。", "#ff4d4d"
        elif gross_margin >= 0.20:
            moat_icon, moat_title, moat_desc, moat_color = "🛡️", "中等壁壘", f"毛利率 {gross_margin*100:.1f}%。具備一定的技術領先或營運規模，存在競爭壁壘。", "#FFD700"
        else:
            moat_icon, moat_title, moat_desc, moat_color = "⚔️", "競爭激烈 (低護城河)", f"毛利率僅 {gross_margin*100:.1f}%。產品同質性偏高，容易落入價格戰，無法輕易阻擋對手跨入。", "#00cc66" # 綠色警戒

        # 3. 供應鏈地位判定 (基於營業利益率 - 定價權與附加價值的財務體現)
        if op_margin is None:
            pos_icon, pos_title, pos_desc, pos_color = "❓", "數據不足", "缺乏營益率數據無法精確評估。", "gray"
        elif op_margin >= 0.15:
            pos_icon, pos_title, pos_desc, pos_color = "👑", "核心主導者 (具定價權)", f"營益率高達 {op_margin*100:.1f}%。在產業鏈中掌握關鍵零組件、設備或 IP 設計，景氣波動時具備高度抗跌能力與話語權。", "#ff4d4d"
        elif op_margin >= 0.05:
            pos_icon, pos_title, pos_desc, pos_color = "⚙️", "關鍵供應商", f"營益率 {op_margin*100:.1f}%。在整體供應鏈中扮演不可或缺的一環，營運與定價能力相對穩健。", "#FFD700"
        else:
            pos_icon, pos_title, pos_desc, pos_color = "📦", "弱勢地位 (低階代工/組裝)", f"營益率僅 {op_margin*100:.1f}%。毛利微薄且被成本擠壓，在供應鏈中缺乏定價權，極易受原物料上漲與終端砍單衝擊。", "#00cc66"

        # 輸出專家系統分析 UI
        st.markdown(f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-top:10px;'>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {trend_color};'>
                <div style='font-size:1.1rem; font-weight:bold; color:#fff; margin-bottom:8px;'>{trend_icon} 市場趨勢</div>
                <div style='color:{trend_color}; font-weight:bold; margin-bottom:5px;'>{trend_title}</div>
                <div style='color:#aaa; font-size:0.9rem; line-height:1.5;'>{trend_desc}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {moat_color};'>
                <div style='font-size:1.1rem; font-weight:bold; color:#fff; margin-bottom:8px;'>{moat_icon} 護城河 (競爭壁壘)</div>
                <div style='color:{moat_color}; font-weight:bold; margin-bottom:5px;'>{moat_title}</div>
                <div style='color:#aaa; font-size:0.9rem; line-height:1.5;'>{moat_desc}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {pos_color};'>
                <div style='font-size:1.1rem; font-weight:bold; color:#fff; margin-bottom:8px;'>{pos_icon} 供應鏈地位</div>
                <div style='color:{pos_color}; font-weight:bold; margin-bottom:5px;'>{pos_title}</div>
                <div style='color:#aaa; font-size:0.9rem; line-height:1.5;'>{pos_desc}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

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
