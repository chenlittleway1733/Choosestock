"""
UI 模組共用匯入。
此檔案保留原 ui.py 需要的外部依賴，避免各模組重複維護 import。
"""
import datetime
import inspect
import math
import os
import re
import time
import json
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import streamlit.components.v1 as components
from services import *
from utils import *

from industry_model import get_industry_valuation_profile, build_industry_valuation_model_report

from dynamic_cap_model import calculate_dynamic_cap_v2


def st_dataframe(data=None, *, width="stretch", **kwargs):
    """Render dataframe with Streamlit 1.50+ width API and legacy fallback."""
    caller = inspect.currentframe().f_back
    st_target = caller.f_globals.get("st", st) if caller is not None else st
    try:
        return st_target.dataframe(data, width=width, **kwargs)
    except TypeError as exc:
        if "width" not in str(exc):
            raise
        use_container_width = width == "stretch"
        return st_target.dataframe(data, use_container_width=use_container_width, **kwargs)
