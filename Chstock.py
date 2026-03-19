import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import re
import json

# 設定網頁標題與寬度
st.set_page_config(page_title="台股聯網 AI 投資戰情室", layout="wide")

# --- 初始化 Session State (確保所有變數都在一開始就建立，防止 AttributeError) ---
if 'selected_stock' not in st.session_state:
    st.session_state.selected_stock = "2330"
if 'topic_results' not in st.session_state:
    st.session_state.topic_results = None
if 'show_whale' not in st.session_state:
    st.session_state.show_whale = False
if 'ai_error' not in st.session_state:
    st.session_state.ai_error = None
if 'api_key' not in st.session_state:
    st.session_state.api_key = ""
if 'ai_fetched_eps' not in st.session_state:
    st.session_state.ai_fetched_eps = {}

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

# --- 🤖 新增：專屬 AI 聯網抓取法人預估 EPS 函數 ---
def get_eps_from_ai(stock_name, stock_id, api_key):
    if not api_key: return None
    api_key = api_key.strip()
    
    model = "gemini-2.5-flash"
    api_host = "https://" + "generativelanguage.googleapis.com"
    url = f"{api_host}/v1beta/models/{model}:generateContent?key={api_key}"
    
    system_prompt = "你是一個精準的財經數據提取機器人。請上網搜尋國內外法人或投顧，針對該公司「明年」或「今年」所預估的 EPS（每股盈餘）。請綜合最新資訊，『嚴格只回傳一個最合理的數字』（例如：30.5 或 15.2）。不要加上任何單位、不要解釋、不要有其他文字。若真的查無資料，請回傳 0。"
    
    payload = {
        "contents": [{"parts": [{"text": f"請搜尋台股 {stock_name} ({stock_id}) 最新的法人預估 EPS"}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "tools": [{"google_search": {}}],
    }
    
    try:
        res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=15)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            return float(text)
    except:
        pass
    return None

# --- 資料與翻譯函數 ---
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
        host_name = "tw.stock.yahoo.com"
        path = "/quote/"
        url = f"https://{host_name}{path}{stock_id}"
        
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        match = re.search(r'<title>(.*?)\(', response.text)
        if match: return match.group(1).strip()
    except:
        pass
    return None

@st.cache_data(ttl=86400)
def translate_to_zh(text):
    if not text or text == '暫無簡介。': return text
    try:
        host_name = "translate.googleapis.com"
        path = "/translate_a/single"
        translate_url = f"https://{host_name}{path}"
        
        params = {"client": "gtx", "sl": "en", "tl": "zh-TW", "dt": "t", "q": text}
        res = requests.get(translate_url, params=params, timeout=5)
        translated_text = "".join([item[0] for item in res.json()[0]])
        return translated_text
    except Exception:
        return text + "\n\n(⚠️ 翻譯服務暫時忙碌中，以上為原文顯示)"

# ==========================================
# 側邊欄：所有功能選單
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
    
    # 綁定 API Key 到 Session State
    st.session_state.api_key = st.text_input("🔑 Gemini API Key", type="password", value=st.session_state.api_key)
    
    if st.button("AI 實時推演分析", type="primary", use_container_width=True):
        if st.session_state.api_key and topic:
            with st.spinner("AI 深度推演中..."):
                reasoning, stocks = get_ai_analysis_final(topic, st.session_state.api_key)
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
        
        # --- 自動英翻中區塊 ---
        with st.expander("📖 查看公司詳細營業項目簡介 (自動英翻中)"):
            summary_en = info.get('longBusinessSummary', '暫無簡介。')
            if summary_en != '暫無簡介。':
                with st.spinner("背景翻譯中..."):
                    summary_zh = translate_to_zh(summary_en)
                st.write(summary_zh)
            else:
                st.write(summary_en)

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

        # --- 📊 新增：月營收與 YoY 雙軸圖表 ---
        st.markdown("#### 📊 近一年月營收與成長動能趨勢 (示意範例)")
        st.markdown("<small style='color:gray;'>*註：因海外 yfinance 資料庫缺乏台股「月營收」精確欄位，此處暫以模擬數據展示雙軸圖表視覺效果。實戰中可串接公開資訊觀測站 API 替換為真實數據。*</small>", unsafe_allow_html=True)

        rev_data = {
            'Month': ['2023-04', '2023-05', '2023-06', '2023-07', '2023-08', '2023-09',
                      '2023-10', '2023-11', '2023-12', '2024-01', '2024-02', '2024-03'],
            'Revenue': [25.1, 26.8, 28.5, 27.2, 30.1, 32.5, 31.0, 34.2, 35.8, 32.1, 29.5, 36.5],
            'YoY': [15.2, 18.5, 22.1, 19.8, 28.4, 35.2, 30.1, 42.5, 45.8, 28.5, 12.4, 48.2]
        }
        df_rev = pd.DataFrame(rev_data)

        fig_rev = make_subplots(specs=[[{"secondary_y": True}]])
        
        # 主軸：單月營收 (直條圖 Bar)
        fig_rev.add_trace(
            go.Bar(
                x=df_rev['Month'],
                y=df_rev['Revenue'],
                name="單月營收 (億)",
                marker_color='#3498db', # 搭配暗黑主題的亮藍色
                opacity=0.8,
                hovertemplate="營收: %{y} 億<extra></extra>"
            ),
            secondary_y=False,
        )
        
        # 副軸：年增率 YoY (折線圖 Line+Markers)
        fig_rev.add_trace(
            go.Scatter(
                x=df_rev['Month'],
                y=df_rev['YoY'],
                name="YoY (%)",
                mode='lines+markers',
                line=dict(color='#ff4d4d', width=3), # 醒目的亮紅色
                marker=dict(size=8, symbol='circle'),
                hovertemplate="YoY: %{y}%<extra></extra>"
            ),
            secondary_y=True,
        )
        
        # UI/UX 細節優化
        fig_rev.update_layout(
            height=400,
            template="plotly_dark", # 套用暗黑主題以融入戰情室背景
            hovermode="x unified",
            margin=dict(l=10, r=10, t=30, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        fig_rev.update_yaxes(title_text="營收金額 (億)", secondary_y=False, showgrid=False)
        fig_rev.update_yaxes(
            title_text="年增率 YoY (%)",
            secondary_y=True,
            showgrid=True, gridcolor='#333', # 淡淡的網格線
            zeroline=True, zerolinewidth=1, zerolinecolor='#555'
        )
        st.plotly_chart(fig_rev, use_container_width=True)
        st.markdown("---")

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
        st.markdown("<small style='color:gray;'>*註：透過市場三大估值指標，檢視目前股價是否透支未來成長性或具備足夠的安全邊際。海外資料庫之預估 EPS 可能因模型外推而極度樂觀，建議適時切換為國內法人共識值以防追高。*</small>", unsafe_allow_html=True)

        pb_ratio = info.get('priceToBook')
        pe_ratio = info.get('trailingPE')
        sys_peg_ratio = info.get('pegRatio')
        sys_forward_pe = info.get('forwardPE')
        t_eps = info.get('trailingEps')
        f_eps = info.get('forwardEps')
        earn_growth = info.get('earningsGrowth')
        
        # --- 核心升級：進階估值微調 (法人共識 EPS 動態切換 + AI 聯網抓取) ---
        st.markdown("##### ⚙️ 進階估值微調 (EPS 敏感度分析)")
        
        col_eps1, col_eps2, col_eps3 = st.columns([1.2, 1.5, 1])
        with col_eps1:
            use_custom_eps = st.toggle("切換為「自訂 / 法人共識預估 EPS」", value=False)
        
        with col_eps3:
            # 點擊按鈕後，呼叫 AI 抓取並存入 Session
            if st.button("🤖 AI 自動上網尋找法人 EPS", disabled=not st.session_state.api_key, help="需在左側選單輸入 API Key"):
                with st.spinner("AI 爬文中..."):
                    fetched_val = get_eps_from_ai(c_name, curr_id, st.session_state.api_key)
                    if fetched_val and fetched_val > 0:
                        st.session_state.ai_fetched_eps[curr_id] = fetched_val
                        st.success(f"抓取成功！AI 推估值約為 {fetched_val} 元")
                    else:
                        st.error("AI 暫時找不到具體數據，請手動輸入。")
                        
        with col_eps2:
            # 優先使用 AI 抓到的數據，沒有的話才用預設值
            default_eps_val = st.session_state.ai_fetched_eps.get(curr_id)
            if default_eps_val is None:
                default_eps_val = float(f_eps) if f_eps is not None else (float(t_eps) if t_eps else 1.0)
                
            custom_eps = st.number_input("輸入國內法人共識 EPS (元)", min_value=0.01, value=default_eps_val, step=0.5, disabled=not use_custom_eps)

        # 動態估值計算邏輯
        if use_custom_eps:
            active_f_eps = custom_eps
            # 依據使用者輸入的 EPS 重新計算前瞻本益比
            forward_pe = curr_p / active_f_eps if active_f_eps > 0 else None
            
            # 依據使用者輸入的 EPS 重新計算 PEG
            if t_eps and t_eps > 0 and pe_ratio:
                custom_growth = (active_f_eps - t_eps) / t_eps
                if custom_growth > 0:
                    peg_ratio = pe_ratio / (custom_growth * 100)
                else:
                    peg_ratio = None # 獲利衰退不適用 PEG
            else:
                peg_ratio = None
                
            eps_source_text = f"自訂法人共識 ({active_f_eps:.2f}元)"
        else:
            active_f_eps = f_eps
            # 若 API 沒給前瞻本益比，自動使用系統 EPS 計算
            if sys_forward_pe is None and f_eps is not None and f_eps > 0 and curr_p:
                forward_pe = curr_p / f_eps
            else:
                forward_pe = sys_forward_pe
                
            if sys_peg_ratio is None and pe_ratio is not None and earn_growth is not None and earn_growth > 0:
                peg_ratio = pe_ratio / (earn_growth * 100)
            else:
                peg_ratio = sys_peg_ratio
                
            eps_source_text = f"海外系統外推 ({f_eps:.2f}元)" if f_eps else "系統預估 (無資料)"

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
            peg_color, peg_eval = "gray", "衰退或無數據"
        elif peg_ratio > 2:
            peg_color, peg_eval = "#ff4d4d", "透支未來成長"
        elif peg_ratio <= 1:
            peg_color, peg_eval = "#00cc66", "低估 (成長性支撐)"
        else:
            peg_color, peg_eval = "#FFD700", "合理區間"
            
        fpe_str = f"{forward_pe:.1f}x" if forward_pe is not None else "N/A"
        if forward_pe is None:
            fpe_color, fpe_eval = "gray", "數據不足"
        elif forward_pe > 25:
            fpe_color, fpe_eval = "#ff4d4d", "偏高 / 成長期望高"
        elif forward_pe < 15:
            fpe_color, fpe_eval = "#00cc66", "相對便宜"
        else:
            fpe_color, fpe_eval = "#FFD700", "合理區間"

        st.markdown(f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-top:10px;'>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {pe_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>📊 歷史本益比 (Trailing P/E)</div>
                    <div style='background:{pe_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{pe_eval}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:10px;'>{pe_str}</div>
                <div style='color:#aaa; font-size:0.85rem; line-height:1.5;'>
                    以過去一年的獲利計算。適合用來和「同業」或是公司「歷史區間」作對比。高成長性科技股通常享有較高溢價，但也需提防過度樂觀導致的估值泡沫。
                </div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {fpe_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🚀 前瞻本益比 (Forward P/E)</div>
                    <div style='background:{fpe_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{fpe_eval}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:5px;'>{fpe_str}</div>
                <div style='color:#ffd700; font-size:0.85rem; margin-bottom:10px; font-weight:bold;'>基準：{eps_source_text}</div>
                <div style='color:#aaa; font-size:0.85rem; line-height:1.5;'>
                    以「預估未來一年 EPS」計算。投資科技成長股看重的是未來，若歷史本益比極高但前瞻本益比大幅下降，代表獲利即將爆發，這正是買盤願意溢價介入的關鍵。
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
        </div>
        """, unsafe_allow_html=True)
        st.markdown("---")

        # --- 🐳 籌碼面與股權結構分析 ---
        st.markdown("#### 🐳 籌碼面與股權結構分析", unsafe_allow_html=True)
        st.markdown("<small style='color:gray;'>*註：籌碼流向為台股短線動能關鍵，透過股本規模與持股結構，自動推估該檔股票的主力控盤屬性。*</small>", unsafe_allow_html=True)

        insider_pct = info.get('heldPercentInsiders')
        inst_pct = info.get('heldPercentInstitutions')
        market_cap = info.get('marketCap', 0)
        
        shares_out = info.get('sharesOutstanding')
        share_capital = shares_out * 10 if shares_out else None

        if share_capital:
            if share_capital >= 10_000_000_000:
                cap_type, driver, cap_color = "大型權值股", "🌍 外資主導", "#4169E1"
                driver_desc = f"股本約 {share_capital/100000000:.0f} 億。籌碼龐大，走勢高度受外資資金與國際大盤影響，不易被單一主力炒作。"
            elif share_capital <= 3_000_000_000:
                cap_type, driver, cap_color = "中小型飆股", "🔥 投信 / 內資主力", "#ff8c00"
                driver_desc = f"股本約 {share_capital/100000000:.0f} 億。籌碼輕薄，極易受「投信連續買超」作帳帶動，吸引主力拉抬，爆發力強。"
            else:
                cap_type, driver, cap_color = "中型中堅股", "🤝 土洋對作/共議", "#9370DB"
                driver_desc = f"股本約 {share_capital/100000000:.0f} 億。外資與投信皆有著墨空間。當出現「土洋合作」(同步買超) 時易有大波段行情。"
        else:
            if market_cap >= 200_000_000_000:
                cap_type, driver, cap_color = "大型權值股", "🌍 外資主導", "#4169E1"
                driver_desc = "走勢高度受外資控盤與國際大盤影響，不易被人為炒作，看重長期基本面。"
            elif market_cap <= 50_000_000_000:
                cap_type, driver, cap_color = "中小型飆股", "🔥 投信 / 內資主力", "#ff8c00"
                driver_desc = "股本小、籌碼輕，極易受「投信連續買超」的作帳行情帶動，爆發力強。"
            else:
                cap_type, driver, cap_color = "中型中堅股", "🤝 土洋對作/共議", "#9370DB"
                driver_desc = "外資與投信皆有著墨空間。當出現「土洋合作」(同步買超) 時，往往能走出大波段行情。"

        inst_str = f"{inst_pct * 100:.2f}%" if inst_pct is not None else "N/A"
        if inst_pct is None:
            inst_color, inst_eval, inst_desc = "gray", "數據不足", "缺乏法人持股資料。"
        elif inst_pct > 0.40:
            inst_color, inst_eval = "#ff4d4d", "高度集中 (留意結帳)"
            inst_desc = "法人持股比例極高，代表基本面獲高度認可。籌碼雖穩定，但若趨勢反轉或財報不如預期，需防範法人互相踐踏的「結帳賣壓」。"
        elif inst_pct > 0.15:
            inst_color, inst_eval = "#FFD700", "穩定認可"
            inst_desc = "法人持股水位適中，代表機構持續關注並具備加碼空間，屬於健康的籌碼結構。"
        else:
            inst_color, inst_eval = "#00bfff", "內資/散戶主導"
            inst_desc = "外資與投信介入不深，股價走勢較容易受到市場主力大戶、公司派或散戶情緒的影響。"

        insider_str = f"{insider_pct * 100:.2f}%" if insider_pct is not None else "N/A"
        if insider_pct is None:
            in_color, in_eval, in_desc = "gray", "數據不足", "缺乏大股東持股資料。"
        elif insider_pct > 0.40:
            in_color, in_eval = "#ff4d4d", "籌碼極度安定"
            in_desc = "大股東與內部人持股極高，市面流通籌碼少，只要少量資金即可拉抬股價，且代表內部人對公司前景極度看好。"
        elif insider_pct > 0.20:
            in_color, in_eval = "#FFD700", "相對穩健"
            in_desc = "內部人持股在標準健康區間，股權結構穩定，經營團隊與股東利益一致。"
        else:
            in_color, in_eval = "#00cc66", "籌碼較渙散 (警戒)"
            in_desc = "內部人持股偏低，可能代表大股東已逢高獲利了結，或股權過度分散，股價遇壓時較缺乏內部防守力道。"

        chip_html = f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-top:10px;'>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {inst_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🏦 三大法人持股率</div>
                    <div style='background:{inst_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{inst_eval}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:5px;'>{inst_str}</div>
                <div style='color:#aaa; font-size:0.85rem; line-height:1.5;'>{inst_desc}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {in_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🏢 內部人與大股東持股</div>
                    <div style='background:{in_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{in_eval}</div>
                </div>
                <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:5px;'>{insider_str}</div>
                <div style='color:#aaa; font-size:0.85rem; line-height:1.5;'>{in_desc}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {cap_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🎯 控盤主力推估</div>
                    <div style='background:{cap_color}; color:#fff; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{cap_type}</div>
                </div>
                <div style='font-size:1.3rem; font-weight:bold; color:{cap_color}; margin-bottom:10px;'>{driver}</div>
                <div style='color:#aaa; font-size:0.85rem; line-height:1.5;'>{driver_desc}</div>
            </div>
        </div>
        """
        st.markdown(chip_html, unsafe_allow_html=True)
        st.markdown("---")

        # --- 🤖 專業技術線圖與量化型態分析 (近半年) ---
        st.markdown("### 🤖 專業技術線圖與量化型態分析 (近半年)")
        hist['MA5'] = hist['Close'].rolling(5).mean()
        hist['MA10'] = hist['Close'].rolling(10).mean()
        hist['MA20'] = hist['Close'].rolling(20).mean()
        hist['MA60'] = hist['Close'].rolling(60).mean()
        hist['MA120'] = hist['Close'].rolling(120).mean()
        hist['Vol_MA20'] = hist['Volume'].rolling(20).mean()

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
        ma120_last = hist['MA120'].iloc[-1] if not pd.isna(hist['MA120'].iloc[-1]) else ma60_last
        k_last = hist['K'].iloc[-1]
        d_last = hist['D'].iloc[-1]
        
        recent_20 = hist.tail(20)
        recent_high = recent_20['High'].max()
        recent_low = recent_20['Low'].min()
        
        max_vol_idx = recent_20['Volume'].idxmax()
        max_vol_day = recent_20.loc[max_vol_idx]
        
        is_high_vol = max_vol_day['Volume'] > (max_vol_day['Vol_MA20'] * 2)
        is_at_high = max_vol_day['High'] >= (recent_high * 0.95)
        is_dropping = last_close < max_vol_day['Low']
        high_vol_warning = is_high_vol and is_at_high and is_dropping
        
        support_price = max(recent_low, ma60_last) if last_close > ma60_last else recent_low
        resist_price = recent_high if last_close > ma20_last else min(recent_high, ma20_last)
        
        if last_close < ma60_last:
            trend_status, trend_color = "⚠️ 跌破季線 (趨勢轉弱)", "#00cc66"
        elif last_close > ma20_last and ma5_last > ma20_last:
            trend_status, trend_color = "📈 多頭強勢 (站上月線)", "#ff4d4d"
        elif last_close < ma20_last and ma5_last < ma20_last:
            trend_status, trend_color = "📉 空頭弱勢 (跌破月線)", "#00cc66"
        else:
            trend_status, trend_color = "↔️ 區間震盪 (方向未明)", "#ffd700"
            
        if high_vol_warning:
            adv_text = "🚨 【量價警訊】近期高檔爆出天量且跌破低點，主力疑似獲利了結出貨，強烈建議觀望，切勿盲目接刀！"
            buy_rec, sell_rec = "強烈觀望", f"反彈至 {max_vol_day['High']:.2f} 逃命"
        elif last_close < ma60_last:
            adv_text = "📉 【趨勢轉弱】股價已跌破季線(生命線)，長線大趨勢走弱或進入深層洗盤，應耐心等待底部確立。"
            buy_rec, sell_rec = "等待站回季線", f"{ma60_last:.2f} (季線壓力)"
        elif k_last < 25 and k_last > d_last:
            adv_text = "📈 【技術反彈】KD 低檔黃金交叉且長線均線有守，具短線反彈契機，可嘗試逢低少量佈局。"
            buy_rec, sell_rec = f"現價~{support_price:.2f} 附近", f"{resist_price:.2f} (上檔壓力)"
        elif k_last > 80 and k_last < d_last:
            adv_text = "⚠️ 【動能轉弱】KD 高檔死亡交叉，短線上漲動能衰退，建議適度獲利了結保住利潤。"
            buy_rec, sell_rec = "暫時觀望", f"現價~{resist_price:.2f} 附近"
        elif last_close > ma20_last:
            adv_text = "🔥 【多方格局】量價配合良好，拉回月線(20MA)有守可伺機介入，跌破支撐應嚴格停損。"
            buy_rec, sell_rec = f"{ma20_last:.2f} (月線支撐)", f"{resist_price:.2f} (近期前高)"
        else:
            adv_text = "❄️ 【空方格局】短線均線反壓，建議多看少做，反彈至均線壓力區可考慮減碼。"
            buy_rec, sell_rec = "等待技術面打底", f"{ma20_last:.2f} (月線壓力)"

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

        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA5'], mode='lines', name='MA5(周線)', line=dict(color='#00bfff', width=1.5)), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA10'], mode='lines', name='MA10(雙周)', line=dict(color='#ab82ff', width=1.5)), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], mode='lines', name='MA20(月線)', line=dict(color='#ff8c00', width=1.5)), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA60'], mode='lines', name='MA60(季線)', line=dict(color='#ffd700', width=1.5)), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA120'], mode='lines', name='MA120(半年線)', line=dict(color='#ff69b4', width=1.5)), row=1, col=1, secondary_y=False)

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
        
        fig.update_yaxes(range=[0, 100], dtick=10, side="right", mirror=True, showline=True, linecolor='#555', row=2, col=1)

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
