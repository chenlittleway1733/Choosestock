"""
UI 入口門面：
為降低單一 ui.py 過大與後續維護困難，本檔只保留對外匯出的兩個入口函式。
實際畫面邏輯已拆到：
- ui_sidebar.py：側邊欄、自選股、策略掃描
- ui_main.py：主畫面、圖表、AI/財務/ETF 面板
- ui_common.py：共用 import
"""

from ui_sidebar import render_sidebar
from ui_main import render_main_page

__all__ = ["render_sidebar", "render_main_page"]
