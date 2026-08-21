"""Pure HTML builders for the page-level section navigation bar."""

from html import escape


TOP_SECTION_NAV_ITEMS = (
    ("overview", "個股概覽"),
    ("etf", "ETF"),
    ("financial-news", "財報新聞"),
    ("stock-forecast", "股票預估價"),
    ("valuation-risk", "估值風控"),
    ("target-price", "法人目標價"),
    ("chips", "籌碼"),
    ("ai-analysis", "AI 分析"),
    ("peer-river", "同業河流"),
    ("technical", "技術分析"),
)


def build_top_section_nav_html(items=TOP_SECTION_NAV_ITEMS):
    links = "".join(
        f'<a href="#{escape(str(section_id), quote=True)}">{escape(str(label))}</a>'
        for section_id, label in items
    )
    return f"""
<style>
html {{ scroll-behavior: smooth; }}
.way-section-anchor {{ height: 0; scroll-margin-top: 8.5rem; }}
.way-top-nav {{
    display: flex;
    align-items: center;
    gap: 0.42rem;
    overflow-x: auto;
    white-space: nowrap;
    padding: 0.55rem 0.65rem;
    margin: 0.15rem 0 0.85rem 0;
    border: 1px solid rgba(56, 189, 248, 0.42);
    border-radius: 0.75rem;
    background: rgba(15, 23, 42, 0.96);
    box-shadow: 0 6px 18px rgba(2, 6, 23, 0.28);
}}
.way-top-nav-label {{
    color: #7DD3FC;
    font-weight: 800;
    padding: 0 0.25rem;
}}
.way-top-nav a {{
    color: #E2E8F0 !important;
    background: #1E293B;
    border: 1px solid #334155;
    border-radius: 999px;
    padding: 0.33rem 0.68rem;
    text-decoration: none !important;
    font-size: 0.88rem;
    line-height: 1.2;
}}
.way-top-nav a:hover {{
    color: #0F172A !important;
    background: #7DD3FC;
    border-color: #7DD3FC;
}}
div[data-testid="stElementContainer"]:has(.way-top-nav) {{
    position: sticky;
    top: 3.2rem;
    z-index: 999;
}}
@media (max-width: 768px) {{
    .way-top-nav {{ padding: 0.48rem 0.5rem; }}
    .way-top-nav a {{ font-size: 0.82rem; padding: 0.3rem 0.58rem; }}
}}
</style>
<nav class="way-top-nav" aria-label="頁面區塊導覽">
  <span class="way-top-nav-label">快速跳轉</span>
  {links}
</nav>
""".strip()


def build_section_anchor_html(section_id):
    safe_id = escape(str(section_id), quote=True)
    return f'<div id="{safe_id}" class="way-section-anchor" aria-hidden="true"></div>'


__all__ = ["TOP_SECTION_NAV_ITEMS", "build_section_anchor_html", "build_top_section_nav_html"]
