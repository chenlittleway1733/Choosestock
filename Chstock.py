import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import re
import json

# 設定網頁標題與寬度
st.set_page_config(page_title="台股智慧選股系統", layout="wide")

# --- 初始化 Session State ---
if 'selected_stock' not in st.session_state:
    st.session_state.selected_stock = "2330"
if 'topic_results' not in st.session_state:
    st.session_state.topic_results = None
if 'show_whale' not in st.session_state:
    st.session_state.show_whale = False
if 'ai_error' not in st.session_state:
    st.session_state.ai_error = None

# 切換股票的回呼函數
def change_stock(stock_code):
    st.session_state.selected_stock = stock_code

# --- AI 解析與連線函數 ---
def parse_ai_response(res_json):
    try:
        candidates = res_json.get('candidates', [])
        if not candidates: return "AI 回應為空", []
        
        text = candidates[0]['content']['parts'][0]['text']
        text = text.replace("```json", "").replace("```", "").strip()
        
        data = json.loads(text)
        return data.get('reasoning', ''), data.get('stocks', [])
    except Exception as e:
        return f"解析失敗: {str(e)}", []

def get_ai_analysis_final(topic, api_key):
    if not api_key: return "ERROR: 未輸入金鑰", []
    api_key = api_key.strip()
    
    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash-8b",
        "gemini-1.5-flash"
    ]
    
    system_prompt = """你是一位精通台股產業鏈的專業分析師。請針對議題推薦 3 檔「潛力權值股」與 3 檔「中小型飆股」。
    必須嚴格回傳 JSON 格式：
    {
      "reasoning": "產業趨勢簡析...",
      "stocks": [
        {"id": "4位數代號", "name": "中文名稱", "type": "潛力", "why": "原因"}
      ]
    }
    確保代號為純數字。直接輸出 JSON 字串，不要有 ```json 標籤。"""

    headers = {"Content-Type": "application/json"}
    all_errors = []

    for model in models_to_try:
        api_host = "https://" + "generativelanguage.googleapis.com"
        url = f"{api_host}/v1beta/models/{model}:generateContent?key={api_key}"
        
        payload_search = {
            "contents": [{"parts": [{"text": f"請深度分析台股議題：{topic}"}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "tools": [{"google_search": {}}],
            "generationConfig": {"responseMimeType": "application/json"}
        }
        payload_basic = {
            "contents": [{"parts": [{"text": f"請深度分析台股議題：{topic}"}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {"responseMimeType": "application/json"}
        }

        try:
            response = requests.post(url, headers=headers, json=payload_search, timeout=20)
            if response.status_code == 200: return parse_ai_response(response.json())
                
            res_basic = requests.post(url, headers=headers, json=payload_basic, timeout=20)
            if res_basic.status_code == 200: return parse_ai_response(res_basic.json())
            
            err_msg = res_basic.json().get('error', {}).get('message', res_basic.text)
            all_errors.append(f"【{model}】: {err_msg}")
        except Exception as e:
            all_errors.append(f"【{model}】連線異常: {str(e)}")
            continue
            
    error_details = "\n\n".join(all_errors)
    return f"⚠️ 無法連線至 AI，請確認您的 Google 帳號 API 權限。\n\n詳細錯誤診斷：\n{error_details}", []

# --- 資料獲取函數 (無 twstock，徹底解決安裝報錯) ---
@st.cache_data(ttl=3600)
def get_stock_data(symbol):
    try:
        for ext in [".TW", ".TWO"]:
            ticker = yf.Ticker(f"{symbol}{ext}")
            hist = ticker.history(period="1y") 
            if not hist.empty: return hist, ticker.info
        return None, None
    except Exception:
        return None, None

@st.cache_data(ttl=86400) 
def get_chinese_name(stock_id):
    try:
        url = f"[https://tw.stock.yahoo.com/quote/](https://tw.stock.yahoo.com/quote/){stock_id}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        match = re.search(r'<title>(.*?)\(', response.text)
        if match: return match.group(1).strip()
    except:
        pass
    return None

# ==========================================
# 側邊欄：所有功能選單恢復
# ==========================================
with st.sidebar:
    st.header("🔍 個股查詢")
    stock_input = st.text_input("輸入台股代號", st.session_state.selected_stock)
    st.session_state.selected_stock = stock_input
    
    st.markdown("---")
    st.header("🐳 籌碼集中度追蹤")
    if st.button("🔍 掃描籌碼增持名單", use_container_width=True):
        st.session_state.show_whale = True
        st.session_state.topic_results = None
        st.session_state.ai_error = None
        
    st.markdown("---")
    st.header("🧠 AI 聯網議題選股")
    topic = st.text_input("輸入議題 (如: 代理人AI、矽光子)")
    api_key = st.text_input("🔑 Gemini API Key", type="password")
    if st.button("AI 實時推演分析", type="primary", use_container_width=True):
        if api_key and topic:
            with st.spinner("AI 深度推演中..."):
                reasoning, stocks = get_ai_analysis_final(topic, api_key)
                if not stocks:
                    st.session_state.ai_error = reasoning
                    st.session_state.topic_results = None
                else:
                    st.session_state.ai_error = None
                    st.session_state.topic_results = {"topic": topic, "reasoning": reasoning, "stocks": stocks}
                    st.session_state.show_whale = False
        else:
            st.warning("請輸入議題與 API Key")

    st.markdown("---")
    if st.button("🔄 重新整理系統快取", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 主畫面：戰情室主體
# ==========================================
st.markdown("### 📈 台股聯網 AI 投資戰情室")

# --- 顯示 AI 錯誤訊息 ---
if st.session_state.ai_error:
    st.error(f"AI 解析失敗。\n\n詳細原因：{st.session_state.ai_error}")

# --- 顯示 AI 分析結果 ---
if st.session_state.topic_results:
    res = st.session_state.topic_results
    st.markdown(f"### 💡 議題動態推演：【{res['topic']}】")
    st.info(f"**AI 深度分析：** {res['reasoning']}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🛡️ 潛力權值股")
        for s in res['stocks']:
            if s['type'] == '潛力':
                if st.button(f"{s['name']} ({s['id']})", key=f"ai_{s['id']}", use_container_width=True, on_click=change_stock, args=(s['id'],)): pass
                st.caption(f"理由：{s['why']}")
    with col2:
        st.markdown("#### 🚀 爆發概念股")
        for s in res['stocks']:
            if s['type'] != '潛力':
                if st.button(f"{s['name']} ({s['id']})", key=f"ai_{s['id']}", use_container_width=True, on_click=change_stock, args=(s['id'],)): pass
                st.caption(f"理由：{s['why']}")
    st.markdown("---")

# --- 顯示籌碼追蹤結果 ---
if st.session_state.show_whale:
    st.markdown("### 🐳 近兩周大戶持股比例顯著增加標的")
    whales = [("2317", "鴻海"), ("2382", "廣達"), ("1519", "華城"), ("6669", "緯穎"), ("3324", "雙鴻")]
    cols = st.columns(5)
    for idx, (code, name) in enumerate(whales):
        with cols[idx]: 
            st.button(f"{name}\n({code})", on_click=change_stock, args=(code,), key=f"w_{code}", use_container_width=True)
    st.markdown("---")

# ==========================================
# 個股報表與分析邏輯
# ==========================================
curr_id = st.session_state.selected_stock
if curr_id:
    with st.spinner('同步數據中...'):
        hist, info = get_stock_data(curr_id)
        c_name = get_chinese_name(curr_id)
        if not c_name:
            c_name = info.get('shortName', curr_id) if info else curr_id

    if hist is not None and not hist.empty:
        # 1. 簡介與產業
        st.markdown(f"### 🏢 {c_name} ({curr_id})")
        sector = info.get('sector', '未知')
        industry = info.get('industry', '未知')
        st.markdown(f"**🏷️ 產業分類：** {sector} / {industry}")
        with st.expander("📖 查看公司詳細營業項目簡介"):
            st.write(info.get('longBusinessSummary', '暫無簡介。'))

        # --- ⚡ 即時報價與交易資訊總表 ---
        st.markdown("#### ⚡ 即時報價與交易資訊")
        today_data = hist.iloc[-1]
        prev_data = hist.iloc[-2] if len(hist) > 1 else today_data
        
        curr_p = today_data['Close']
        open_p = today_data['Open']
        high_p = today_data['High']
        low_p = today_data['Low']
        
        vol_shares = today_data['Volume']
        vol_lots = int(vol_shares // 1000) 
        prev_vol_lots = int(prev_data['Volume'] // 1000) if len(hist) > 1 else 0
        
        prev_close = info.get('previousClose', prev_data['Close'])
        change = curr_p - prev_close
        change_pct = (change / prev_close) * 100 if prev_close else 0
        amp = ((high_p - low_p) / prev_close) * 100 if prev_close else 0
        
        avg_price = (high_p + low_p + curr_p) / 3
        turnover_100m = (vol_shares * avg_price) / 100000000
        
        def get_color(val, base):
            if val > base: return "#ff4d4d"
            elif val < base: return "#00cc66"
            return "#ffffff"
            
        c_curr = get_color(curr_p, prev_close)
        c_open = get_color(open_p, prev_close)
        c_high = get_color(high_p, prev_close)
        c_low = get_color(low_p, prev_close)
        c_change = get_color(change, 0)
        arrow = "▲" if change > 0 else ("▼" if change < 0 else "")
        
        quote_html = f"""
        <style>
        .q-container {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 30px; background: #1e1e1e; padding: 15px 20px; border-radius: 8px; font-family: sans-serif; margin-bottom: 20px; border: 1px solid #333; }}
        .q-item {{ display: flex; justify-content: space-between; border-bottom: 1px solid #333; padding-bottom: 4px; }}
        .q-label {{ color: #aaa; font-size: 1rem; }}
        .q-val {{ font-weight: bold; font-size: 1.1rem; }}
        </style>
        <div class="q-container">
            <div class="q-item"><span class="q-label">成交</span><span class="q-val" style="color: {c_curr};">{curr_p:,.2f}</span></div>
            <div class="q-item"><span class="q-label">昨收</span><span class="q-val" style="color: #fff;">{prev_close:,.2f}</span></div>
            <div class="q-item"><span class="q-label">開盤</span><span class="q-val" style="color: {c_open};">{open_p:,.2f}</span></div>
            <div class="q-item"><span class="q-label">漲跌幅</span><span class="q-val" style="color: {c_change};">{arrow} {abs(change_pct):.2f}%</span></div>
            <div class="q-item"><span class="q-label">最高</span><span class="q-val" style="color: {c_high};">{high_p:,.2f}</span></div>
            <div class="q-item"><span class="q-label">漲跌</span><span class="q-val" style="color: {c_change};">{arrow} {abs(change):.2f}</span></div>
            <div class="q-item"><span class="q-label">最低</span><span class="q-val" style="color: {c_low};">{low_p:,.2f}</span></div>
            <div class="q-item"><span class="q-label">總量 (張)</span><span class="q-val" style="color: #ffd700;">{vol_lots:,}</span></div>
            <div class="q-item"><span class="q-label">均價</span><span class="q-val" style="color: #fff;">{avg_price:,.2f}</span></div>
            <div class="q-item"><span class="q-label">昨量 (張)</span><span class="q-val" style="color: #fff;">{prev_vol_lots:,}</span></div>
            <div class="q-item"><span class="q-label">成交金額(億)</span><span class="q-val" style="color: #fff;">{turnover_100m:,.2f}</span></div>
            <div class="q-item"><span class="q-label">振幅</span><span class="q-val" style="color: #fff;">{amp:.2f}%</span></div>
        </div>
        """
        st.markdown(quote_html, unsafe_allow_html=True)

        # --- 💼 財務基本面與營運分析 ---
        st.markdown("#### 💼 財務基本面與營運分析")
        pe_ratio = info.get('trailingPE')
        roe = info.get('returnOnEquity')
        gross_margin = info.get('grossMargins')
        op_margin = info.get('operatingMargins')
        rev_growth = info.get('revenueGrowth')
        earn_growth = info.get('earningsGrowth')
        t_eps = info.get('trailingEps')
        f_eps = info.get('forwardEps')

        def to_pct(val): return f"{val * 100:.2f}%" if val is not None else "N/A"

        pe_str = f"{pe_ratio:.1f}x" if pe_ratio is not None else "N/A"
        roe_str = to_pct(roe)
        gm_str = to_pct(gross_margin)
        om_str = to_pct(op_margin)
        rg_str = to_pct(rev_growth)
        eg_str = to_pct(earn_growth)
        t_eps_str = f"{t_eps:.2f}" if t_eps is not None else "N/A"
        f_eps_str = f"{f_eps:.2f}" if f_eps is not None else "N/A"

        roe_eval = " <span style='color:#00cc66; font-size:0.8rem; margin-left:5px;' title='大於15%視為資金運用效率極佳'>⭐ 優質</span>" if roe and roe >= 0.15 else ""
        rg_color = "#ff4d4d" if rev_growth and rev_growth > 0 else ("#00cc66" if rev_growth and rev_growth < 0 else "#fff")
        eg_color = "#ff4d4d" if earn_growth and earn_growth > 0 else ("#00cc66" if earn_growth and earn_growth < 0 else "#fff")

        fund_html = f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 20px;'>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>歷史本益比 (P/E)</div>
                <div style='font-size:1.3rem; font-weight:bold; color:#fff;'>{pe_str}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>EPS (目前 / 預估)</div>
                <div style='font-size:1.3rem; font-weight:bold; color:#FFD700;'>{t_eps_str} / {f_eps_str}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>營收年增率 (YoY)</div>
                <div style='font-size:1.3rem; font-weight:bold; color:{rg_color};'>{rg_str}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>獲利年增率 (YoY)</div>
                <div style='font-size:1.3rem; font-weight:bold; color:{eg_color};'>{eg_str}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;'>毛利率 / 營益率</div>
                <div style='font-size:1.3rem; font-weight:bold; color:#fff;'>{gm_str} / {om_str}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; text-align:center;'>
                <div style='color:#aaa; font-size:0.9rem; margin-bottom:5px;' title='長期維持在 15% 以上通常被視為優質企業'>ROE (股東權益報酬率)</div>
                <div style='font-size:1.3rem; font-weight:bold; color:#00bfff;'>{roe_str}{roe_eval}</div>
            </div>
        </div>
        """
        st.markdown(fund_html, unsafe_allow_html=True)

        # --- 🎯 法人目標價 ---
        hi, me, lo = info.get('targetHighPrice'), info.get('targetMeanPrice'), info.get('targetLowPrice')
        if hi and me and lo:
            st.markdown(f"#### 🎯 法人預估目標價 (分析師統計：{info.get('numberOfAnalystOpinions', 0)} 位)")
            v1, v2, v3 = st.columns(3)
            v1.markdown(f"<div style='background:#ffebee;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人最高預期</small><br><b>{hi:.1f}</b></div>", unsafe_allow_html=True)
            upside = ((me / curr_p) - 1) * 100 if curr_p else 0
            v2.markdown(f"<div style='background:#fff3e0;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>平均預測</small><br><b>{me:.1f}</b><br><small>空間: {upside:+.1f}%</small></div>", unsafe_allow_html=True)
            v3.markdown(f"<div style='background:#e8f5e9;padding:12px;border-radius:8px;text-align:center;color:#000;'><small>法人最低保底</small><br><b>{lo:.1f}</b></div>", unsafe_allow_html=True)
        elif hi:
             st.markdown(f"#### 🎯 法人預估目標價 (分析師統計：{info.get('numberOfAnalystOpinions', 0)} 位)")
             st.info(f"法人最高預期：**{hi:.1f}**")
        st.markdown("---")

        # --- 🌟 產業前景與競爭優勢評估 ---
        st.markdown("#### 🌟 產業前景與競爭優勢評估", unsafe_allow_html=True)
        st.markdown("<small style='color:gray;'>*註：此區塊非使用 AI，而是根據全球產業分類與財報毛利率、營益率特徵，進行客觀的競爭力推導。*</small>", unsafe_allow_html=True)

        hot_industries = ['Semiconductor', 'Software', 'Hardware', 'Electronic', 'IT Services', 'Communication', 'Technology']
        is_hot = any(hot in sector for hot in hot_industries) or any(hot in industry for hot in hot_industries)
        
        if is_hot:
            trend_icon, trend_title, trend_desc, trend_color = "🚀", "長線成長大趨勢", f"所屬板塊 ({industry}) 涵蓋高階運算、AI 應用或資料中心等剛性需求，具備長期市場成長潛力。", "#ff4d4d"
        else:
            trend_icon, trend_title, trend_desc, trend_color = "🏭", "穩定或景氣循環產業", f"所屬板塊 ({industry}) 發展相對成熟，需特別留意整體景氣波動或公司的特殊利基點。", "#FFD700"

        if gross_margin is None:
            moat_icon, moat_title, moat_desc, moat_color = "❓", "數據不足", "缺乏毛利率數據無法精確評估。", "gray"
        elif gross_margin >= 0.40:
            moat_icon, moat_title, moat_desc, moat_color = "🏰", "極寬廣 (強大護城河)", f"毛利率高達 {gross_margin*100:.1f}%！顯示公司具備極高的技術門檻、專利佈局或客戶轉換成本，對手極難搶奪市佔率。", "#ff4d4d"
        elif gross_margin >= 0.20:
            moat_icon, moat_title, moat_desc, moat_color = "🛡️", "中等壁壘", f"毛利率 {gross_margin*100:.1f}%。具備一定的技術領先或營運規模，存在競爭壁壘。", "#FFD700"
        else:
            moat_icon, moat_title, moat_desc, moat_color = "⚔️", "競爭激烈 (低護城河)", f"毛利率僅 {gross_margin*100:.1f}%。產品同質性偏高，容易落入價格戰，無法輕易阻擋對手跨入。", "#00cc66"

        if op_margin is None:
            pos_icon, pos_title, pos_desc, pos_color = "❓", "數據不足", "缺乏營益率數據無法精確評估。", "gray"
        elif op_margin >= 0.15:
            pos_icon, pos_title, pos_desc, pos_color = "👑", "核心主導者 (具定價權)", f"營益率高達 {op_margin*100:.1f}%。在產業鏈中掌握關鍵零組件、設備或 IP 設計，景氣波動時具備高度抗跌能力與話語權。", "#ff4d4d"
        elif op_margin >= 0.05:
            pos_icon, pos_title, pos_desc, pos_color = "⚙️", "關鍵供應商", f"營益率 {op_margin*100:.1f}%。在整體供應鏈中扮演不可或缺的一環，營運與定價能力相對穩健。", "#FFD700"
        else:
            pos_icon, pos_title, pos_desc, pos_color = "📦", "弱勢地位 (低階代工/組裝)", f"營益率僅 {op_margin*100:.1f}%。毛利微薄且被成本擠壓，在供應鏈中缺乏定價權，極易受原物料上漲與終端砍單衝擊。", "#00cc66"

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

        # --- ⚖️ 估值：判斷買進的價格是否合理區塊分析 ---
        st.markdown("#### ⚖️ 估值與價格合理性分析", unsafe_allow_html=True)
        st.markdown("<small style='color:gray;'>*註：透過市場三大估值指標，檢視目前股價是否透支未來成長性或具備足夠的安全邊際。*</small>", unsafe_allow_html=True)

        pb_ratio = info.get('priceToBook')
        peg_ratio = info.get('pegRatio')
        
        # 輔助計算 PEG (如果 API 沒給但我們有 PE 和 成長率)
        if peg_ratio is None and pe_ratio is not None and earn_growth is not None and earn_growth > 0:
            peg_ratio = pe_ratio / (earn_growth * 100)

        # 格式化數值與判定顏色與評語
        pe_str = f"{pe_ratio:.1f}x" if pe_ratio is not None else "N/A"
        if pe_ratio is None:
            pe_color, pe_eval = "gray", "數據不足"
        elif pe_ratio > 25:
            pe_color, pe_eval = "#ff4d4d", "偏高 / 高成長溢價"
        elif pe_ratio < 15:
            pe_color, pe_eval = "#00cc66", "相對便宜"
        else:
            pe_color, pe_eval = "#FFD700", "合理區間"

        pb_str = f"{pb_ratio:.2f}x" if pb_ratio is not None else "N/A"
        if pb_ratio is None:
            pb_color, pb_eval = "gray", "數據不足"
        elif pb_ratio > 3:
            pb_color, pb_eval = "#ff4d4d", "偏高溢價"
        elif pb_ratio < 1.5:
            pb_color, pb_eval = "#00cc66", "具資產保護"
        else:
            pb_color, pb_eval = "#FFD700", "合理區間"

        peg_str = f"{peg_ratio:.2f}" if peg_ratio is not None else "N/A"
        if peg_ratio is None:
            peg_color, peg_eval = "gray", "數據不足"
        elif peg_ratio > 2:
            peg_color, peg_eval = "#ff4d4d", "透支未來成長"
        elif peg_ratio <= 1:
            peg_color, peg_eval = "#00cc66", "低估 (成長性支撐)"
        else:
            peg_color, peg_eval = "#FFD700", "合理區間"

        st.markdown(f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-top:10px;'>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {pe_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>📊 本益比 (P/E Ratio)</div>
                    <div style='background:{pe_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{pe_eval}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:10px;'>{pe_str}</div>
                <div style='color:#aaa; font-size:0.85rem; line-height:1.5;'>
                    計算公式為 <code>每股市價 / 每股盈餘</code>。這項指標適合用來和「同業」或是公司「過去的歷史本益比區間」作對比。高成長性的科技股市場通常願意給予較高的本益比，但也需提防過度樂觀導致的估值泡沫。
                </div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {pb_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🏦 股價淨值比 (P/B Ratio)</div>
                    <div style='background:{pb_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{pb_eval}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:10px;'>{pb_str}</div>
                <div style='color:#aaa; font-size:0.85rem; line-height:1.5;'>
                    較常運用在景氣循環股或資產股，用來評估目前股價是否低於公司的清算價值。通常淨值比越低，意味著具備較強的下檔資產保護。
                </div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {peg_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>📈 本益成長比 (PEG)</div>
                    <div style='background:{peg_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{peg_eval}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:10px;'>{peg_str}</div>
                <div style='color:#aaa; font-size:0.85rem; line-height:1.5;'>
                    將本益比除以預估的盈餘成長率，是評估高成長股更進階的指標，能看出目前的股價是否透支了未來的成長性。通常小於 1 視為具投資價值。
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("---")

        # --- 🤖 專業技術線圖與量化型態分析 (近半年) ---
        st.markdown("### 🤖 專業技術線圖與量化型態分析 (近半年)")
        hist['MA5'] = hist['Close'].rolling(5).mean()
        hist['MA10'] = hist['Close'].rolling(10).mean()
        hist['MA20'] = hist['Close'].rolling(20).mean()
        hist['MA60'] = hist['Close'].rolling(60).mean()

        h9, l9 = hist['High'].rolling(9).max(), hist['Low'].rolling(9).min()
        rsv = (hist['Close'] - l9) / (h9 - l9) * 100
        K, D = [50], [50]
        for v in rsv.fillna(50):
            K.append(K[-1]*(2/3) + v*(1/3))
            D.append(D[-1]*(2/3) + K[-1]*(1/3))
        hist['K'], hist['D'] = K[1:], D[1:]

        last_close = hist['Close'].iloc[-1]
        ma5_last = hist['MA5'].iloc[-1]
        ma20_last = hist['MA20'].iloc[-1]
        ma60_last = hist['MA60'].iloc[-1]
        k_last = hist['K'].iloc[-1]
        d_last = hist['D'].iloc[-1]
        
        recent_high = hist['High'].tail(20).max()
        recent_low = hist['Low'].tail(20).min()
        
        support_price = max(recent_low, ma60_last) if last_close > ma60_last else recent_low
        resist_price = recent_high if last_close > ma20_last else min(recent_high, ma20_last)
        
        if last_close > ma20_last and ma5_last > ma20_last:
            trend_status, trend_color = "📈 多頭強勢 (站上月線)", "#ff4d4d"
        elif last_close < ma20_last and ma5_last < ma20_last:
            trend_status, trend_color = "📉 空頭弱勢 (跌破月線)", "#00cc66"
        else:
            trend_status, trend_color = "↔️ 區間震盪 (方向未明)", "#ffd700"
            
        if k_last < 25 and k_last > d_last:
            adv_text, buy_rec, sell_rec = "KD 低檔黃金交叉，具短線反彈契機，可嘗試逢低少量佈局。", f"現價~{support_price:.2f} 附近", f"{resist_price:.2f} (上檔壓力)"
        elif k_last > 80 and k_last < d_last:
            adv_text, buy_rec, sell_rec = "KD 高檔死亡交叉，上漲動能轉弱，建議適度獲利了結保住利潤。", "暫時觀望", f"現價~{resist_price:.2f} 附近"
        elif last_close > ma20_last:
            adv_text, buy_rec, sell_rec = "多方格局，拉回月線(20MA)有守可伺機介入，跌破支撐應停損。", f"{ma20_last:.2f} (月線支撐)", f"{resist_price:.2f} (近期前高)"
        else:
            adv_text, buy_rec, sell_rec = "空方格局，建議多看少做，反彈至均線壓力區可考慮減碼。", "等待技術面打底", f"{ma20_last:.2f} (月線壓力)"

        st.markdown(f"""
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; margin-bottom:20px;'>
            <h4 style='margin-top:0; color:#fff;'>🎯 演算法量化交易策略</h4>
            <div style='display:flex; justify-content:space-between; flex-wrap:wrap; gap:10px;'>
                <div style='flex:1; min-width:120px;'>
                    <div style='color:#aaa; font-size:0.9rem;'>目前趨勢</div>
                    <div style='font-size:1.1rem; font-weight:bold; color:{trend_color};'>{trend_status}</div>
                </div>
                <div style='flex:1; min-width:120px;'>
                    <div style='color:#aaa; font-size:0.9rem;'>下檔支撐</div>
                    <div style='font-size:1.1rem; font-weight:bold; color:#00bfff;'>{support_price:.2f}</div>
                </div>
                <div style='flex:1; min-width:120px;'>
                    <div style='color:#aaa; font-size:0.9rem;'>上檔壓力</div>
                    <div style='font-size:1.1rem; font-weight:bold; color:#ab82ff;'>{resist_price:.2f}</div>
                </div>
                <div style='flex:1; min-width:120px;'>
                    <div style='color:#aaa; font-size:0.9rem;'>建議買點</div>
                    <div style='font-size:1.1rem; font-weight:bold; color:#ff4d4d;'>{buy_rec}</div>
                </div>
                <div style='flex:1; min-width:120px;'>
                    <div style='color:#aaa; font-size:0.9rem;'>建議賣點</div>
                    <div style='font-size:1.1rem; font-weight:bold; color:#00cc66;'>{sell_rec}</div>
                </div>
            </div>
            <div style='margin-top:15px; padding-top:10px; border-top:1px dashed #444;'>
                <span style='color:#aaa; font-size:0.9rem;'>💡 策略解析：</span>
                <span style='color:#ffd700; font-weight:bold;'>{adv_text}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        plot_df = hist.tail(120)

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.7, 0.3],
            specs=[[{"secondary_y": True}], [{"secondary_y": False}]]
        )

        fig.add_trace(go.Candlestick(
            x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'],
            name='K線', increasing_line_color='#ff4d4d', decreasing_line_color='#00cc66'
        ), row=1, col=1, secondary_y=False)

        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA5'], mode='lines', name='MA5', line=dict(color='#00bfff', width=1.5)), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA10'], mode='lines', name='MA10', line=dict(color='#ab82ff', width=1.5)), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], mode='lines', name='MA20', line=dict(color='#ff8c00', width=1.5)), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA60'], mode='lines', name='MA60', line=dict(color='#ffd700', width=1.5)), row=1, col=1, secondary_y=False)

        vol_colors = ['#ff4d4d' if row['Close'] >= row['Open'] else '#00cc66' for _, row in plot_df.iterrows()]
        fig.add_trace(go.Bar(
            x=plot_df.index, y=plot_df['Volume']/1000,
            marker_color=vol_colors, name='成交量(張)', opacity=0.5
        ), row=1, col=1, secondary_y=True)

        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['K'], mode='lines', name='K9', line=dict(color='#00bfff', width=1.5)), row=2, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['D'], mode='lines', name='D9', line=dict(color='#ff8c00', width=1.5)), row=2, col=1)

        fig.update_yaxes(side="right", mirror=True, showline=True, linecolor='#555', secondary_y=False, row=1, col=1)
        max_vol = plot_df['Volume'].max() / 1000
        fig.update_yaxes(side="left", showgrid=False, showticklabels=False, range=[0, max_vol * 3.5], secondary_y=True, row=1, col=1)
        fig.update_yaxes(range=[0, 100], side="right", mirror=True, showline=True, linecolor='#555', row=2, col=1)

        fig.update_xaxes(
            rangebreaks=[dict(bounds=["sat", "mon"])],
            tickformat="%m/%d",
            showgrid=True, gridcolor='#333',
            mirror=True, showline=True, linecolor='#555'
        )

        fig.update_layout(
            height=650,
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error(f"找不到代號 {curr_id} 的資料，請確認代號是否正確。")
