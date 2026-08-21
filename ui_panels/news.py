"""News panel for ui_main.render_main_page."""

from ui_common import *


def render_financial_news_panel(*, curr_id):
    st.markdown("#### 📰 近期財報與法說會新聞")
    news_list = get_stock_news(curr_id)
    if news_list:
        for item in news_list[:5]:
            publish_time = datetime.datetime.fromtimestamp(item["timestamp"]).strftime("%Y-%m-%d %H:%M") if item["timestamp"] else "未知時間"
            st.markdown(
                f"🔸 [{item['title']}]({item['link']}) <span style='color:gray; font-size:0.8rem;'>- {item['publisher']} ({publish_time})</span>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("目前無符合條件的基本面或財報新聞。")
    st.markdown("---")
