import io
import os
import re
import time as _time
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# デフォルトのセクターデータファイル（アプリ内蔵）
# Parquet が存在すればそちらを優先（1,578テーマのロードが数十秒 → 数百msに短縮）
_APP_DIR = os.path.dirname(__file__)
DEFAULT_XLSX = os.path.join(_APP_DIR, "default_sectors.xlsx")
DEFAULT_PARQUET = os.path.join(_APP_DIR, "default_sectors.parquet")
DEFAULT_DATA_PATH = DEFAULT_PARQUET if os.path.exists(DEFAULT_PARQUET) else DEFAULT_XLSX

from data_loader import load_sector_data, get_all_tickers, get_sector_tickers
from market_data import fetch_market_data_with_progress
from analysis import (
    aggregate_by_sector,
    get_sector_summary,
    get_stock_detail,
    get_momentum_ranking,
    get_period_comparison,
    get_hot_sectors,
    get_stock_momentum,
)
from charts import (
    sector_bar_chart,
    timeseries_chart,
    momentum_bar_chart,
    week_change_bar_chart,
    period_change_bar_chart,
    comparison_bar_chart,
    normalized_chart,
    stock_detail_bar,
    stock_momentum_bar_chart,
    stock_change_heatmap,
    market_ranking_bar,
    next_day_ranking_bar,
)
from next_day_ranking import get_next_day_ranking, filter_ranking_by_sector
from news_analyzer import analyze_news_item, build_stock_index
from etf2083_ui import render_etf2083_tab
from market_ranking import (
    RANKING_TYPES,
    MARKET_OPTIONS,
    TERM_OPTIONS,
    CATEGORY_ORDER,
    get_ranking_categories,
    fetch_ranking_via_read_html,
    fetch_multiple_rankings,
)
from news_feed import (
    NEWS_SOURCES,
    fetch_all_news,
    get_source_names,
    get_default_sources,
    get_source_icon,
    get_source_color,
)
from disclosure import (
    fetch_disclosure,
    get_category_color,
    check_new_disclosures,
)
from shikiho_csv import (
    CsvType,
    detect_csv_type,
    load_stock_price_csv,
    load_watchlist_csv,
    load_generic_csv,
    stock_price_candlestick,
    stock_price_summary,
    watchlist_profit_chart,
)
from world_indices import (
    fetch_world_indices,
    get_region_color,
    REGION_ORDER,
)
from sector_forecast import (
    make_us_snapshot,
    compute_sector_forecast,
    heat_emoji,
    US_INDICATOR_CODES,
)
from us_sector_perf import (
    fetch_us_sector_performance,
    get_sector_etf_rankings,
    US_SECTOR_ETFS,
)

st.set_page_config(
    page_title="テーマ株セクター 売買代金ダッシュボード",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ブラウザ翻訳プロンプトを抑制（複数手法で確実に）
st.markdown(
    """
    <meta name="google" content="notranslate">
    <meta http-equiv="Content-Language" content="ja">
    <script>
    (function(){
      var h=document.documentElement;
      h.setAttribute("lang","ja");
      h.setAttribute("translate","no");
      h.classList.add("notranslate");
      var m=document.querySelector('meta[name="google"]');
      if(!m){m=document.createElement("meta");m.name="google";document.head.appendChild(m);}
      m.content="notranslate";
    })();
    </script>
    """,
    unsafe_allow_html=True,
)
import streamlit.components.v1 as components

# ===== Terminal Pro デザイン: 2026年プレミアム・ダークモード =====
_GLOBAL_CSS = """<style>
/* ========== Chrome翻訳バー非表示 ========== */
.goog-te-banner-frame, #goog-gt-tt, .goog-te-balloon-frame,
.skiptranslate, #google_translate_element,
div[id^="goog-gt-"], iframe.goog-te-menu-frame {
  display: none !important;
  visibility: hidden !important;
  height: 0 !important;
  overflow: hidden !important;
}
body { top: 0 !important; }

/* ========== Design Tokens ========== */
:root {
  --bg: #0A0E17;
  --bg-grad: radial-gradient(ellipse at top, #0F1626 0%, #0A0E17 55%);
  --surface: #121826;
  --surface-2: #181F33;
  --surface-3: #1F2942;
  --border: rgba(148, 163, 196, 0.12);
  --border-strong: rgba(148, 163, 196, 0.22);
  --text: #F0F3FA;
  --text-2: #A8B3CD;
  --text-3: #6B7895;
  --accent: #00E5FF;
  --accent-2: #7C3AED;
  --accent-glow: 0 0 24px rgba(0, 229, 255, 0.35);
  --up: #FF5E6C;
  --up-soft: rgba(255, 94, 108, 0.14);
  --down: #00D9A3;
  --down-soft: rgba(0, 217, 163, 0.14);
  --warn: #FFB020;
  --info: #3B82F6;
  --radius: 10px;
  --radius-sm: 6px;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
  --shadow-md: 0 4px 16px rgba(0,0,0,0.35);
  --shadow-lg: 0 12px 40px rgba(0,0,0,0.5);
  --mono: 'JetBrains Mono', 'SF Mono', 'Monaco', 'Menlo', 'Consolas', monospace;
}

/* ========== Base ========== */
html, body, [class*="css"] {
  font-family: 'Inter', 'Hiragino Kaku Gothic ProN', 'Hiragino Sans', Meiryo, 'Yu Gothic', system-ui, -apple-system, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  font-feature-settings: "cv11", "ss01", "ss03";
}
[data-testid="stAppViewContainer"], .stApp {
  background: var(--bg-grad) !important;
  background-attachment: fixed !important;
}
.stApp::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(600px circle at 10% 0%, rgba(124, 58, 237, 0.08), transparent 40%),
    radial-gradient(800px circle at 90% 10%, rgba(0, 229, 255, 0.06), transparent 45%);
  z-index: 0;
}

/* ========== Header ========== */
header[data-testid="stHeader"] {
  background: rgba(10, 14, 23, 0.72) !important;
  backdrop-filter: blur(20px) saturate(1.4);
  -webkit-backdrop-filter: blur(20px) saturate(1.4);
  border-bottom: 1px solid var(--border) !important;
  box-shadow: 0 1px 0 rgba(255,255,255,0.03) inset;
}

/* ========== Title ========== */
h1 {
  color: var(--text) !important;
  font-size: 26px !important;
  font-weight: 800 !important;
  letter-spacing: -0.02em !important;
  padding-left: 0 !important;
  border-left: none !important;
  background: linear-gradient(135deg, #FFFFFF 0%, #A8B3CD 85%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  position: relative;
}
h1::before {
  content: "";
  display: inline-block;
  width: 4px;
  height: 22px;
  background: linear-gradient(180deg, var(--accent), var(--accent-2));
  border-radius: 2px;
  margin-right: 12px;
  vertical-align: middle;
  box-shadow: var(--accent-glow);
}
h2, h3 { color: var(--text) !important; font-weight: 700 !important; letter-spacing: -0.01em !important; }
h2 { font-size: 19px !important; }
h3 { font-size: 15px !important; }

/* ========== Tabs (pill + underline hybrid) ========== */
div[data-baseweb="tab-list"] {
  gap: 2px !important;
  border-bottom: 1px solid var(--border) !important;
  background: transparent !important;
  padding: 0 !important;
  margin-bottom: 12px !important;
  position: sticky;
  top: 0;
  z-index: 10;
  backdrop-filter: blur(12px);
  background: rgba(10, 14, 23, 0.6) !important;
}
button[data-baseweb="tab"] {
  font-weight: 600 !important;
  font-size: 13px !important;
  color: var(--text-3) !important;
  border-bottom: 2px solid transparent !important;
  padding: 12px 16px !important;
  transition: all 0.18s ease !important;
  background: transparent !important;
  border-radius: 0 !important;
}
button[data-baseweb="tab"]:hover {
  color: var(--text) !important;
  background: rgba(0, 229, 255, 0.05) !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
  color: var(--accent) !important;
  border-bottom: 2px solid var(--accent) !important;
  background: transparent !important;
  text-shadow: 0 0 12px rgba(0, 229, 255, 0.4);
}

/* ========== Main container ========== */
.stMainBlockContainer {
  max-width: 1280px !important;
  margin: 0 auto !important;
  padding: 1.2rem 2rem 3rem !important;
  position: relative;
  z-index: 1;
}

/* ========== Sidebar ========== */
section[data-testid="stSidebar"] {
  background: rgba(18, 24, 38, 0.85) !important;
  backdrop-filter: blur(16px);
  border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
  color: var(--text) !important;
}

/* ========== Buttons ========== */
button[kind="primary"], .stButton>button[kind="primary"] {
  background: linear-gradient(135deg, #00E5FF 0%, #00B8D4 60%, #7C3AED 130%) !important;
  color: #0A0E17 !important;
  border: none !important;
  border-radius: var(--radius-sm) !important;
  font-weight: 700 !important;
  letter-spacing: 0.01em !important;
  transition: all 0.2s !important;
  box-shadow: 0 2px 10px rgba(0, 229, 255, 0.25), inset 0 1px 0 rgba(255,255,255,0.3) !important;
}
button[kind="primary"]:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(0, 229, 255, 0.45), inset 0 1px 0 rgba(255,255,255,0.4) !important;
}
button[kind="primary"]:active { transform: translateY(0); }
.stButton>button:not([kind="primary"]) {
  background: var(--surface) !important;
  border: 1px solid var(--border-strong) !important;
  color: var(--text) !important;
  border-radius: var(--radius-sm) !important;
  font-weight: 500 !important;
  transition: all 0.18s !important;
}
.stButton>button:not([kind="primary"]):hover {
  background: var(--surface-2) !important;
  border-color: var(--accent) !important;
  color: var(--accent) !important;
}
.stButton>button:disabled {
  opacity: 0.4 !important;
  cursor: not-allowed !important;
}

/* ========== Inputs / Selects ========== */
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div {
  background: var(--surface) !important;
  border: 1px solid var(--border-strong) !important;
  border-radius: var(--radius-sm) !important;
  color: var(--text) !important;
  transition: border-color 0.15s, box-shadow 0.15s;
}
div[data-baseweb="select"] > div:hover,
div[data-baseweb="input"] > div:hover {
  border-color: rgba(0, 229, 255, 0.4) !important;
}
div[data-baseweb="select"] > div:focus-within,
div[data-baseweb="input"] > div:focus-within {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px rgba(0, 229, 255, 0.15) !important;
}
input, textarea { color: var(--text) !important; }
div[data-baseweb="popover"] { background: var(--surface-2) !important; }

/* ========== Metric cards ========== */
div[data-testid="stMetric"] {
  background: linear-gradient(135deg, var(--surface) 0%, var(--surface-2) 100%);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 18px;
  position: relative;
  overflow: hidden;
  transition: all 0.2s;
}
div[data-testid="stMetric"]::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, var(--accent), var(--accent-2));
  opacity: 0.6;
}
div[data-testid="stMetric"]:hover {
  border-color: var(--border-strong);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
  font-family: var(--mono) !important;
  font-weight: 700 !important;
  font-size: 24px !important;
  letter-spacing: -0.02em !important;
  color: var(--text) !important;
}
div[data-testid="stMetric"] [data-testid="stMetricLabel"] {
  color: var(--text-3) !important;
  font-size: 11px !important;
  text-transform: uppercase !important;
  letter-spacing: 0.08em !important;
  font-weight: 600 !important;
}
div[data-testid="stMetricDelta"] svg { display: none; }
div[data-testid="stMetricDelta"] { font-family: var(--mono) !important; font-weight: 600 !important; }

/* ========== Dataframes ========== */
div[data-testid="stDataFrame"] {
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-sm) !important;
  overflow: hidden;
  background: var(--surface) !important;
}
div[data-testid="stDataFrame"] th {
  background: var(--surface-2) !important;
  color: var(--text-2) !important;
  font-weight: 600 !important;
  font-size: 12px !important;
  text-transform: uppercase !important;
  letter-spacing: 0.05em !important;
  border-bottom: 1px solid var(--border-strong) !important;
}
div[data-testid="stDataFrame"] td {
  color: var(--text) !important;
  font-family: var(--mono) !important;
  font-size: 12px !important;
}

/* ========== Alerts ========== */
div[data-testid="stAlert"] {
  border-radius: var(--radius-sm) !important;
  font-size: 13px !important;
  backdrop-filter: blur(10px);
  border: 1px solid var(--border-strong) !important;
}

/* ========== Expander ========== */
details[data-testid="stExpander"] {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-sm) !important;
}
details[data-testid="stExpander"] summary {
  color: var(--text-2) !important;
}

/* ========== Divider ========== */
hr { border-color: var(--border) !important; margin: 1.2rem 0 !important; }

/* ========== Toggles / Radios ========== */
label[data-baseweb="radio"] span:first-child,
label[data-baseweb="checkbox"] span:first-child {
  background: var(--surface) !important;
  border-color: var(--border-strong) !important;
}

/* ========== Progress bar ========== */
div[data-testid="stProgress"] > div > div > div {
  background: linear-gradient(90deg, var(--accent), var(--accent-2)) !important;
}

/* ========== Captions ========== */
.stCaption, p[data-testid="stCaptionContainer"], small {
  color: var(--text-3) !important;
}

/* ========== Toast ========== */
div[data-testid="stToast"] {
  background: var(--surface-2) !important;
  border: 1px solid var(--border-strong) !important;
  color: var(--text) !important;
}

/* ========================================================== */
/* ========== Ticker Bar (LED-style glass) ========== */
/* ========================================================== */
.mk-ticker-bar {
  display: flex;
  gap: 0;
  overflow-x: auto;
  background: linear-gradient(180deg, rgba(24, 31, 51, 0.8), rgba(18, 24, 38, 0.8));
  backdrop-filter: blur(14px);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 18px;
  padding: 0;
  box-shadow: var(--shadow-md), inset 0 1px 0 rgba(255,255,255,0.03);
  position: relative;
}
.mk-ticker-bar::-webkit-scrollbar { height: 4px; }
.mk-ticker-bar::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 2px; }
.mk-ticker-item {
  flex: 1;
  min-width: 160px;
  padding: 12px 16px;
  text-align: left;
  border-right: 1px solid var(--border);
  transition: background 0.18s;
  position: relative;
}
.mk-ticker-item:last-child { border-right: none; }
.mk-ticker-item:hover { background: rgba(0, 229, 255, 0.04); }
.mk-ticker-name {
  font-size: 10px;
  font-weight: 700;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 4px;
}
.mk-ticker-value {
  font-family: var(--mono);
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.02em;
  margin-bottom: 2px;
}
.mk-ticker-sub {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-3);
  margin-left: 6px;
  font-weight: 500;
}
.mk-ticker-change {
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.mk-ticker-change.up { color: var(--up); text-shadow: 0 0 8px rgba(255,94,108,0.35); }
.mk-ticker-change.down { color: var(--down); text-shadow: 0 0 8px rgba(0,217,163,0.35); }
.mk-ticker-change.flat { color: var(--text-3); }

/* ========================================================== */
/* ========== News List ========== */
/* ========================================================== */
.mk-news-item {
  display: flex;
  align-items: flex-start;
  gap: 0;
  padding: 11px 14px;
  border-bottom: 1px solid var(--border);
  transition: all 0.18s;
  border-radius: 0;
}
.mk-news-item .mk-news-title { padding-top: 1px; }
.mk-news-item .mk-news-time { padding-top: 3px; }
.mk-news-item:hover {
  background: var(--surface);
  padding-left: 18px;
}
.mk-news-body { flex: 1; min-width: 0; }
.mk-news-title {
  font-size: 14px;
  font-weight: 500;
  line-height: 1.55;
  color: var(--text);
}
.mk-news-title a { color: var(--text); text-decoration: none; transition: color 0.15s; }
.mk-news-title a:hover { color: var(--accent); }
.mk-news-time {
  flex-shrink: 0;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-3);
  white-space: nowrap;
  margin-left: 16px;
  min-width: 110px;
  text-align: right;
  font-weight: 500;
}
.mk-news-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.mk-tag {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  background: var(--surface-2);
  color: var(--text-2);
  white-space: nowrap;
  border: 1px solid var(--border-strong);
  cursor: pointer;
  transition: all 0.15s;
}
.mk-tag:hover { background: var(--surface-3); color: var(--text); border-color: var(--accent); }
.mk-tag-source {
  background: rgba(0, 229, 255, 0.08);
  color: var(--accent);
  border-color: rgba(0, 229, 255, 0.25);
}
.mk-tag-source:hover { background: rgba(0, 229, 255, 0.16); }
.mk-news-headline {
  padding: 14px 16px 18px;
  margin-bottom: 10px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  background: linear-gradient(135deg, var(--surface) 0%, var(--surface-2) 100%);
  position: relative;
  overflow: hidden;
}
.mk-news-headline::before {
  content: "";
  position: absolute;
  top: 0; left: 0; bottom: 0;
  width: 3px;
  background: linear-gradient(180deg, var(--accent), var(--accent-2));
}
.mk-news-headline .mk-news-title {
  font-size: 18px;
  font-weight: 700;
  line-height: 1.5;
  letter-spacing: -0.01em;
}
.mk-news-headline .mk-news-title a { color: var(--text); }
.mk-news-headline .mk-news-title a:hover { color: var(--accent); }
.mk-news-hl-time {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-3);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 600;
}
.mk-news-summary {
  font-size: 13px;
  color: var(--text-2);
  line-height: 1.7;
  margin-top: 10px;
}
.mk-news-new {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 700;
  background: var(--up);
  color: #FFF;
  margin-left: 8px;
  vertical-align: middle;
  letter-spacing: 0.08em;
  animation: mk-pulse 2s ease-in-out infinite;
  box-shadow: 0 0 12px rgba(255,94,108,0.5);
}

/* ========== 銘柄材料チップ & センチメント ========== */
.mk-stock-material {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  padding: 8px 10px;
  background: linear-gradient(90deg, rgba(255,94,108,0.08) 0%, rgba(124,58,237,0.06) 100%);
  border-radius: 8px;
  border-left: 3px solid var(--up);
}
.mk-material-label {
  font-size: 10px;
  font-weight: 700;
  color: var(--up);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin-right: 4px;
  font-family: var(--mono);
}
.mk-stock-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  background: var(--surface-3);
  color: var(--text);
  border: 1px solid var(--border-strong);
  text-decoration: none;
  white-space: nowrap;
  transition: all 0.15s;
}
.mk-stock-chip:hover {
  background: rgba(0, 229, 255, 0.14);
  border-color: var(--accent);
  color: var(--accent);
  transform: translateY(-1px);
}
.mk-stock-chip-code {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--accent);
  font-weight: 700;
  letter-spacing: 0.04em;
}
.mk-stock-chip-sector {
  font-size: 10px;
  color: var(--text-3);
  font-weight: 500;
}
.mk-sentiment {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  font-family: var(--mono);
  margin-right: 6px;
}
.mk-sentiment-positive {
  background: var(--up-soft);
  color: var(--up);
  border: 1px solid rgba(255,94,108,0.35);
}
.mk-sentiment-negative {
  background: var(--down-soft);
  color: var(--down);
  border: 1px solid rgba(0,217,163,0.35);
}
.mk-sentiment-neutral {
  background: var(--surface-2);
  color: var(--text-3);
  border: 1px solid var(--border);
}
.mk-breaking-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 800;
  background: linear-gradient(90deg, #FF5E6C, #FF8C42);
  color: #FFF;
  letter-spacing: 0.12em;
  margin-right: 8px;
  box-shadow: 0 0 10px rgba(255,94,108,0.4);
  animation: mk-pulse 1.8s ease-in-out infinite;
}

/* ========== ブログタイトル提案ボックス ========== */
.mk-blog-box {
  margin-top: 10px;
  padding: 10px 12px;
  background: linear-gradient(135deg, rgba(0,229,255,0.05) 0%, rgba(124,58,237,0.05) 100%);
  border: 1px solid rgba(0,229,255,0.20);
  border-radius: 8px;
}
.mk-blog-box-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  font-family: var(--mono);
  margin-bottom: 6px;
}
.mk-blog-title-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.mk-blog-title-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: var(--surface);
  border: 1px solid var(--border);
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--text);
  font-weight: 500;
  transition: all 0.15s;
}
.mk-blog-title-item:hover {
  background: var(--surface-2);
  border-color: var(--accent);
}
.mk-blog-title-num {
  flex-shrink: 0;
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 700;
  color: var(--accent);
  background: rgba(0,229,255,0.1);
  border-radius: 4px;
  padding: 2px 6px;
  letter-spacing: 0.04em;
}

/* ========================================================== */
/* ========== Disclosure Cards ========== */
/* ========================================================== */
.mk-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 11px 14px;
  margin-bottom: 6px;
  background: var(--surface);
  transition: all 0.15s;
  position: relative;
}
.mk-card:hover {
  background: var(--surface-2);
  border-color: var(--border-strong);
  transform: translateX(2px);
}
.mk-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
  flex-wrap: wrap;
}
.mk-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  white-space: nowrap;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.mk-title {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.55;
  color: var(--text);
}
.mk-title a { color: var(--text); text-decoration: none; }
.mk-title a:hover { color: var(--accent); text-decoration: underline; }
.mk-meta {
  font-size: 11px;
  color: var(--text-3);
  font-family: var(--mono);
}
.mk-company {
  font-weight: 700;
  font-size: 13px;
  color: var(--text);
}
.mk-code {
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  background: rgba(0, 229, 255, 0.1);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(0, 229, 255, 0.2);
}
.mk-left-bar {
  border-left: 3px solid;
  padding-left: 12px;
}
.mk-summary {
  font-size: 12px;
  color: var(--text-2);
  line-height: 1.55;
  margin-top: 3px;
}

/* ========================================================== */
/* ========== World Indices Grid ========== */
/* ========================================================== */
.mk-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
.mk-index-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  background: linear-gradient(135deg, var(--surface) 0%, var(--surface-2) 100%);
  transition: all 0.18s;
  position: relative;
  overflow: hidden;
}
.mk-index-card::after {
  content: "";
  position: absolute;
  top: 0; right: 0; width: 60px; height: 60px;
  background: radial-gradient(circle, rgba(0,229,255,0.06), transparent 70%);
  pointer-events: none;
}
.mk-index-card:hover {
  border-color: var(--border-strong);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}
.mk-index-card.mk-up {
  border-left: 3px solid var(--up);
  box-shadow: inset 4px 0 12px rgba(255,94,108,0.1);
}
.mk-index-card.mk-down {
  border-left: 3px solid var(--down);
  box-shadow: inset 4px 0 12px rgba(0,217,163,0.1);
}
.mk-index-card.mk-flat { border-left: 3px solid var(--text-3); }
.mk-idx-name {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-2);
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.mk-idx-value {
  font-family: var(--mono);
  font-size: 24px;
  font-weight: 700;
  color: var(--text);
  margin: 4px 0;
  letter-spacing: -0.03em;
}
.mk-idx-change {
  font-family: var(--mono);
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.mk-idx-change.up { color: var(--up); }
.mk-idx-change.down { color: var(--down); }
.mk-idx-change.flat { color: var(--text-3); }
.mk-idx-time {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-3);
  margin-top: 6px;
}

.mk-section {
  font-size: 13px;
  font-weight: 700;
  margin: 18px 0 10px 0;
  padding: 5px 14px;
  border-radius: var(--radius-sm);
  display: inline-block;
  color: var(--accent);
  background: rgba(0, 229, 255, 0.08);
  border: 1px solid rgba(0, 229, 255, 0.2);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

/* ========== NEW tag (TDnet) ========== */
.mk-new-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 700;
  background: var(--up);
  color: #FFF;
  letter-spacing: 0.1em;
  animation: mk-pulse 1.8s ease-in-out infinite;
  box-shadow: 0 0 14px rgba(255,94,108,0.45);
}
@keyframes mk-pulse {
  0%,100% { opacity:1; transform: scale(1); }
  50% { opacity:0.75; transform: scale(0.96); }
}

/* ========== Page info ========== */
.mk-page-info {
  text-align: center;
  padding: 8px 0;
  font-family: var(--mono);
  font-weight: 600;
  font-size: 13px;
  color: var(--text-2);
}

/* ========== Section title ========== */
.mk-section-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  border-left: 3px solid var(--accent);
  padding-left: 12px;
  margin: 18px 0 12px 0;
  letter-spacing: -0.01em;
}

/* ========== Scrollbar ========== */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb {
  background: var(--surface-3);
  border-radius: 5px;
  border: 2px solid var(--bg);
}
::-webkit-scrollbar-thumb:hover { background: var(--border-strong); }

/* ========== Plotly chart wrapper tidy ========== */
div[data-testid="stPlotlyChart"] {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px;
}
</style>"""
st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)

st.title("テーマ株セクター 売買代金ダッシュボード")

# --- みんかぶ風 指数ティッカーバー ---
# 世界の株価データがあればヘッダー下にティッカー表示
if "world_items" in st.session_state:
    _ticker_indices = ["日経平均", "TOPIX", "NYダウ", "S&P500", "ドル/円", "ユーロ/円", "ビットコイン/円"]
    _ticker_data = []
    for wi in st.session_state["world_items"]:
        for tname in _ticker_indices:
            if tname in wi.name:
                _ticker_data.append(wi)
                break
    if _ticker_data:
        import html as _ticker_html
        _ticker_parts = []
        for ti in _ticker_data[:7]:
            if ti.is_up:
                chg_class = "up"
            elif ti.is_down:
                chg_class = "down"
            else:
                chg_class = "flat"
            _ticker_parts.append(
                f'<div class="mk-ticker-item">'
                f'<div class="mk-ticker-name">{_ticker_html.escape(ti.name)}</div>'
                f'<div class="mk-ticker-value">{_ticker_html.escape(ti.value_str)}'
                f'<span class="mk-ticker-sub">({_ticker_html.escape(ti.time_str)})</span></div>'
                f'<div class="mk-ticker-change {chg_class}">{_ticker_html.escape(ti.change_str)} ({_ticker_html.escape(ti.change_pct_str)})</div>'
                f'</div>'
            )
        st.markdown('<div class="mk-ticker-bar">' + "".join(_ticker_parts) + '</div>', unsafe_allow_html=True)

# --- サイドバー ---
with st.sidebar:
    st.header("設定")

    # デフォルトデータの有無を表示
    has_default = os.path.exists(DEFAULT_DATA_PATH)
    if has_default:
        st.success("✅ 内蔵データ: 1,578テーマ・約3,800銘柄")
        # xlsx があれば同時配布（ユーザーが Excel で開けるように）
        if os.path.exists(DEFAULT_XLSX):
            with open(DEFAULT_XLSX, "rb") as _f:
                st.download_button(
                    label="📥 内蔵データをダウンロード",
                    data=_f.read(),
                    file_name="default_sectors.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    help="1,578テーマ × 約3,800銘柄のテーマ株データ",
                )
    uploaded_file = st.file_uploader(
        "別のデータで上書き（任意）",
        type=["xlsx"],
        help="アップロードしなければ内蔵の40セクターデータを使用します",
    )

    st.divider()

    # 期間選択
    period_preset = st.selectbox(
        "期間プリセット",
        ["1週間", "1ヶ月", "3ヶ月", "6ヶ月", "1年", "カスタム"],
        index=1,
    )

    period_map = {
        "1週間": 7,
        "1ヶ月": 30,
        "3ヶ月": 90,
        "6ヶ月": 180,
        "1年": 365,
    }

    if period_preset == "カスタム":
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("開始日", datetime.now() - timedelta(days=30))
        with col2:
            end_date = st.date_input("終了日", datetime.now())
    else:
        days = period_map[period_preset]
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

    st.divider()

    # 集計単位
    freq = st.radio("集計単位", ["日次", "週次", "月次"], horizontal=True)
    freq_map = {"日次": "D", "週次": "W", "月次": "M"}

# --- テンプレート生成 ---
@st.cache_data
def generate_template() -> bytes:
    """サンプル入りテンプレートxlsxをメモリ上で生成"""
    themes = {
        "半導体": [
            ("6857", "アドバンテスト"),
            ("6920", "レーザーテック"),
            ("8035", "東京エレクトロン"),
            ("6146", "ディスコ"),
            ("6723", "ルネサスエレクトロニクス"),
        ],
        "AI関連": [
            ("9984", "ソフトバンクグループ"),
            ("6758", "ソニーグループ"),
            ("6501", "日立製作所"),
            ("6702", "富士通"),
            ("6861", "キーエンス"),
        ],
        "防衛": [
            ("7011", "三菱重工業"),
            ("7012", "川崎重工業"),
            ("7721", "東京計器"),
            ("6208", "石川製作所"),
            ("4274", "細谷火工"),
        ],
    }
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, stocks in themes.items():
            df = pd.DataFrame(stocks, columns=["証券コード", "銘柄名"])
            df.to_excel(writer, sheet_name=name, index=False)
    return buf.getvalue()


# --- メインコンテンツ ---
# データソース決定: アップロード優先、なければ内蔵データ
if uploaded_file is not None:
    data_source = uploaded_file
    data_label = "アップロードデータ"
elif os.path.exists(DEFAULT_DATA_PATH):
    data_source = DEFAULT_DATA_PATH
    data_label = "内蔵データ（1,578テーマ・約3,800銘柄）"
else:
    st.info("サイドバーからテーマ株スプレッドシート (.xlsx) をアップロードしてください。")
    st.markdown(
        """
        ### スプレッドシートの形式
        - **1シート = 1テーマセクター**（シート名がセクター名になります）
        - 各シートには「証券コード」「銘柄名」列を入れてください

        | 証券コード | 銘柄名 |
        |---|---|
        | 6857 | アドバンテスト |
        | 6920 | レーザーテック |
        | 8035 | 東京エレクトロン |
        """
    )
    st.download_button(
        label="📥 テンプレートをダウンロード",
        data=generate_template(),
        file_name="テーマ株テンプレート.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.stop()

st.caption(f"📂 データソース: {data_label}")

# データ読込
sectors = load_sector_data(data_source)
sector_tickers = get_sector_tickers(sectors)
all_tickers = get_all_tickers(sectors)

# サイドバー: セクター選択（データ読込後）
# 1,578テーマあるので、デフォルトは人気30テーマに絞る（存在するもののみ）
_DEFAULT_SELECTED_THEMES = [
    "半導体商社", "半導体製造装置", "AI(人工知能)", "データセンター", "セキュリティ",
    "量子コンピュータ", "5G", "SaaS", "自動運転", "EV(電気自動車)関連",
    "EV充電器", "防衛", "防衛産業", "ロボット", "水素",
    "核融合発電", "原子力発電", "再生医療", "バイオ医薬品", "金地金",
    "REIT", "メタバース(仮想空間)", "総合商社", "海運", "太陽光発電",
    "風力発電", "脱炭素", "円安メリット", "円高メリット", "インバウンド",
]
_default_sel = [t for t in _DEFAULT_SELECTED_THEMES if t in sectors]
# それでも空なら最初の10テーマ
if not _default_sel:
    _default_sel = list(sectors.keys())[:10]

with st.sidebar:
    st.divider()
    selected_sectors = st.multiselect(
        "表示セクター",
        options=list(sectors.keys()),
        default=_default_sel,
        help=f"全 {len(sectors):,} テーマから選択（デフォルトは人気30テーマ）",
    )

# 読込結果の表示（選択中のテーマのみ表示・多いと重いので）
with st.expander(f"📂 読み込んだセクター情報（全 {len(sectors):,} テーマ）", expanded=False):
    display_names = selected_sectors if selected_sectors else list(sectors.keys())[:20]
    st.caption(f"選択中の {len(display_names)} テーマを表示（全件は非表示）")
    for name in display_names:
        df = sectors.get(name)
        if df is None:
            continue
        st.markdown(f"**{name}**: {len(df)}銘柄")
        st.dataframe(df[["証券コード", "銘柄名"]].reset_index(drop=True), hide_index=True, height=150)

# データ取得ボタン
if st.button("📈 売買代金データを取得", type="primary", use_container_width=True):
    st.session_state["fetch_triggered"] = True
    st.session_state["start_date"] = pd.Timestamp(start_date).strftime("%Y-%m-%d")
    st.session_state["end_date"] = pd.Timestamp(end_date).strftime("%Y-%m-%d")
    st.session_state["freq"] = freq_map[freq]
    st.session_state["selected_sectors"] = selected_sectors
    # 前回キャッシュをクリアして再取得させる
    for _k in ["cached_data", "cached_sector_df", "cached_summary",
               "cached_detail", "cached_momentum", "cached_comparison",
               "cached_hot_sectors", "cached_stock_momentum"]:
        st.session_state.pop(_k, None)
    # 翌日予測ランキングのキャッシュもクリア
    for _k in list(st.session_state.keys()):
        if _k.startswith("next_day_"):
            st.session_state.pop(_k, None)

# 売買代金データの取得（トリガー済みの場合のみ）
has_market_data = False
if st.session_state.get("fetch_triggered"):
    start_str = st.session_state["start_date"]
    end_str = st.session_state["end_date"]
    current_freq = st.session_state["freq"]
    current_sectors = st.session_state["selected_sectors"]

    selected_tickers = set()
    for s in current_sectors:
        if s in sector_tickers:
            selected_tickers.update(sector_tickers[s])
    selected_tickers = sorted(selected_tickers)

    if selected_tickers:
        # キャッシュがあればそのまま使う（rerun のたびに再取得しない）
        if "cached_data" in st.session_state and not st.session_state["cached_data"].empty:
            data = st.session_state["cached_data"]
            available = sorted(set(data.columns.get_level_values(0))) if isinstance(data.columns, pd.MultiIndex) else []
            st.success(f"取得済み: {len(available)}銘柄 | データ形状: {data.shape}")
        else:
            st.info(f"取得対象: {len(selected_tickers)}銘柄 | 期間: {start_str} 〜 {end_str}")
            data = fetch_market_data_with_progress(
                tickers_tuple=tuple(selected_tickers),
                start_date=start_str,
                end_date=end_str,
            )
            if not data.empty:
                st.session_state["cached_data"] = data
                available = sorted(set(data.columns.get_level_values(0))) if isinstance(data.columns, pd.MultiIndex) else []
                st.success(f"取得完了: {len(available)}銘柄 | データ形状: {data.shape}")
            else:
                st.error("データの取得に失敗しました。期間やセクターを確認してください。")

        if "cached_data" in st.session_state and not st.session_state["cached_data"].empty:
            data = st.session_state["cached_data"]

            # 集計結果もキャッシュ
            if "cached_summary" not in st.session_state:
                filtered_sector_tickers = {k: v for k, v in sector_tickers.items() if k in current_sectors}
                sector_df = aggregate_by_sector(data, filtered_sector_tickers, freq=current_freq)
                summary = get_sector_summary(sector_df)
                detail = get_stock_detail(data, filtered_sector_tickers, sectors)
                momentum = get_momentum_ranking(sector_df)
                comparison = get_period_comparison(sector_df)
                hot_sectors = get_hot_sectors(sector_df, top_n=5)
                stock_momentum = get_stock_momentum(data, filtered_sector_tickers, sectors)
                # キャッシュに保存
                st.session_state["cached_sector_df"] = sector_df
                st.session_state["cached_summary"] = summary
                st.session_state["cached_detail"] = detail
                st.session_state["cached_momentum"] = momentum
                st.session_state["cached_comparison"] = comparison
                st.session_state["cached_hot_sectors"] = hot_sectors
                st.session_state["cached_stock_momentum"] = stock_momentum
            else:
                sector_df = st.session_state["cached_sector_df"]
                summary = st.session_state["cached_summary"]
                detail = st.session_state["cached_detail"]
                momentum = st.session_state["cached_momentum"]
                comparison = st.session_state["cached_comparison"]
                hot_sectors = st.session_state["cached_hot_sectors"]
                stock_momentum = st.session_state["cached_stock_momentum"]

            has_market_data = True
    else:
        st.warning("セクターが選択されていません。")

# --- タブ表示 ---
# ニュース・市場ランキングは常に表示、売買代金系はデータ取得後に表示
tab_main, tab8, tab_etf, tab9, tab11, tab10, tab7, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["🏠 ダッシュボード", "📰 ニュース", "📦 ETF 2083組入", "📋 適時開示", "🌏 世界の株価", "📙 四季報CSV", "🏆 市場ランキング", "🔥 盛り上がりランキング", "📈 時系列推移", "🔄 セクター比較", "🗂️ 銘柄別詳細", "🚀 銘柄別変化率"]
)

_NEED_DATA_MSG = "⬆️ 上の「📈 売買代金データを取得」ボタンを押してデータを取得してください。"

# ===== 🏠 メインダッシュボード（米国市場→明日セクター→注目銘柄→本日概況）=====
with tab_main:
    # --- Section 1: 米国市場の動向（前日の夜間 ≒ 翌日の先行指標）---
    st.markdown(
        '<div class="mk-section-title">🇺🇸 米国市場の動向（翌営業日の先行指標）</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "日本市場の翌日寄り付きは、前日夜間の米国市場で大きく左右されます。"
        "主要指標の変化をチェックし、買われやすいセクターを予測しましょう。"
    )

    # 米国市場データをキャッシュ
    if "us_snapshot_cache" not in st.session_state:
        with st.spinner("🌐 米国市場データ取得中..."):
            world_items = fetch_world_indices()
            st.session_state["us_snapshot_cache"] = make_us_snapshot(world_items)

    col_refresh, _ = st.columns([1, 5])
    with col_refresh:
        if st.button("🔄 米国市場を更新", key="refresh_us_snapshot"):
            with st.spinner("🌐 米国市場データ取得中..."):
                world_items = fetch_world_indices()
                st.session_state["us_snapshot_cache"] = make_us_snapshot(world_items)

    us_snapshot = st.session_state["us_snapshot_cache"]

    # 主要指標をメトリック表示
    display_codes = ["211", "212", "213", "611", "621", "511", "811", "921"]
    cols = st.columns(len(display_codes))
    for col, code in zip(cols, display_codes):
        item = us_snapshot.by_code.get(code)
        name = US_INDICATOR_CODES.get(code, code)
        with col:
            if item is None or item.value is None:
                st.metric(name, "—", "—")
            else:
                pct = item.change_pct if item.change_pct is not None else 0.0
                st.metric(
                    name,
                    item.value_str,
                    f"{pct:+.2f}%" if pct else "0.00%",
                )

    # 総合ムード
    mood_score, mood_label = us_snapshot.mood_score()
    st.markdown(
        f"**米国市場の総合ムード**: {mood_label}  （スコア: {mood_score:+.1f} / ±100）"
    )

    st.divider()

    # --- Section 1b: 米国セクターETF パフォーマンス（NY終値ベース）---
    st.markdown(
        '<div class="mk-section-title">📊 米国セクターETF パフォーマンス（朝7時更新）</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "🇺🇸 **NY市場終了後（JST 6:00〜7:00）に更新**。主要11セクター + 注目テーマETF の前日変化率。"
        "該当セクターが上がっていれば、同分野の日本株に買いが波及しやすい傾向。"
    )

    # 米国セクターETF を取得（yfinance 1h キャッシュ）
    col_etf_refresh, _ = st.columns([1, 5])
    with col_etf_refresh:
        if st.button("🔄 米国ETFを更新", key="refresh_us_etfs"):
            fetch_us_sector_performance.clear()

    with st.spinner("📈 米国セクターETF 取得中..."):
        etf_perfs = fetch_us_sector_performance()

    # 主要11セクターの ETF をメトリック表示
    tab_us_major, tab_us_theme = st.tabs(["🏛️ 主要11セクター", "🎯 テーマETF (注目)"])

    with tab_us_major:
        major_etfs = [p for p in etf_perfs.values() if p.category == "major"]
        major_etfs.sort(key=lambda x: x.change_pct if x.change_pct is not None else -999, reverse=True)
        if major_etfs:
            rows_per_col = 6
            n_cols = 4
            cols = st.columns(n_cols)
            for i, p in enumerate(major_etfs):
                with cols[i % n_cols]:
                    if p.change_pct is None:
                        st.metric(f"{p.name}\n({p.ticker})", "—", "—")
                    else:
                        st.metric(
                            f"{p.name}",
                            f"${p.close:,.2f}" if p.close else "—",
                            f"{p.change_pct:+.2f}%",
                        )

    with tab_us_theme:
        theme_etfs = [p for p in etf_perfs.values() if p.category == "theme"]
        theme_etfs.sort(key=lambda x: x.change_pct if x.change_pct is not None else -999, reverse=True)
        if theme_etfs:
            # 上昇Top10と下落Bottom5に分けて表示
            col_up, col_down = st.columns(2)
            with col_up:
                st.markdown("**🔥 上昇 Top 10**")
                up_data = pd.DataFrame([
                    {"ETF": p.ticker, "銘柄": p.name, "変化率": f"{p.change_pct:+.2f}%" if p.change_pct is not None else "—"}
                    for p in theme_etfs[:10]
                ])
                st.dataframe(up_data, use_container_width=True, hide_index=True, height=380)
            with col_down:
                st.markdown("**❄️ 下落 Bottom 5**")
                down = theme_etfs[-5:] if len(theme_etfs) >= 5 else []
                down_data = pd.DataFrame([
                    {"ETF": p.ticker, "銘柄": p.name, "変化率": f"{p.change_pct:+.2f}%" if p.change_pct is not None else "—"}
                    for p in reversed(down)
                ])
                st.dataframe(down_data, use_container_width=True, hide_index=True, height=200)

    # 最終取得時刻
    sample_p = next((p for p in etf_perfs.values() if p.fetched_at), None)
    if sample_p:
        st.caption(f"🕒 最終取得: {sample_p.fetched_at.strftime('%Y-%m-%d %H:%M:%S JST')}　（データ元: Yahoo Finance）")

    st.divider()

    # --- Section 2: 明日盛り上がりそうセクター Top 10 ---
    st.markdown(
        '<div class="mk-section-title">🔥 明日盛り上がりそうセクター ランキング</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "🧮 **明日温度** = NDXスコア平均 × 0.6 + (50 + 指数補正 + ETF補正) × 0.4　"
        "／ 前日の日本市場(NDX)+ 米国主要指数(SOX/NASDAQ等) + 米国セクターETF の3層で算出"
    )

    if has_market_data:
        # --- ここで pred_df を計算（Section 3 でも使う）---
        col_p1, col_p2, col_p3 = st.columns([2, 1, 1])
        with col_p1:
            pred_sector_filter = st.multiselect(
                "セクターで絞り込み",
                options=["すべて"] + list(current_sectors),
                default=["すべて"],
                key="pred_sector_filter",
            )
        with col_p2:
            pred_top_n = st.selectbox(
                "銘柄表示件数",
                [10, 20, 30, 50, 100],
                index=1,
                key="pred_top_n",
            )
        with col_p3:
            pred_min_turnover = st.selectbox(
                "最低売買代金(億円)",
                [0.5, 1.0, 3.0, 5.0, 10.0, 30.0],
                index=1,
                key="pred_min_turnover",
                help="この金額未満の薄商い銘柄は除外",
            )

        # --- ランキング計算（キャッシュ） ---
        pred_cache_key = f"next_day_{pred_min_turnover}"
        if pred_cache_key not in st.session_state:
            with st.spinner("🔍 テクニカル指標を計算中..."):
                filtered_sector_tickers = {
                    k: v for k, v in sector_tickers.items() if k in current_sectors
                }
                pred_df = get_next_day_ranking(
                    data,
                    filtered_sector_tickers,
                    sectors,
                    min_turnover_oku=pred_min_turnover,
                )
                st.session_state[pred_cache_key] = pred_df
        pred_df = st.session_state[pred_cache_key]

        forecast_df = compute_sector_forecast(pred_df, us_snapshot, etf_perfs=etf_perfs)

        if not forecast_df.empty:
            # Top 3 をカード表示
            top3 = forecast_df.head(3)
            card_cols = st.columns(3)
            for i, (col, (_, row)) in enumerate(zip(card_cols, top3.iterrows())):
                medal = ["🥇", "🥈", "🥉"][i]
                heat = heat_emoji(row["明日温度"])
                reason = row["補正理由"] if row["補正理由"] else "（補正なし）"
                total_us = row["指数補正"] + row["ETF補正"]
                card_html = (
                    '<div style="background: linear-gradient(135deg, #014099 0%, #1565C0 100%);'
                    'color: white; padding: 18px; border-radius: 12px;'
                    'box-shadow: 0 4px 8px rgba(0,0,0,0.1); min-height: 180px;">'
                    f'<div style="font-size: 18px; font-weight: 700;">{medal} {row["セクター"]} {heat}</div>'
                    f'<div style="font-size: 28px; font-weight: 800; margin: 8px 0;">{row["明日温度"]:.1f}</div>'
                    f'<div style="font-size: 12px; opacity: 0.9;">'
                    f'NDX平均 <b>{row["NDX平均"]:.1f}</b> ／ 強気 <b>{row["強気銘柄数"]}/{row["銘柄数"]}</b></div>'
                    f'<div style="font-size: 11px; margin-top: 8px; opacity: 0.85;">'
                    f'📈 US合計: <b>{total_us:+.1f}</b>'
                    f' (指数{row["指数補正"]:+.1f} / ETF{row["ETF補正"]:+.1f})<br/>{reason}</div>'
                    '</div>'
                )
                with col:
                    st.markdown(card_html, unsafe_allow_html=True)

            st.markdown("")
            st.markdown("**📋 明日温度ランキング Top 20**")
            st.dataframe(
                forecast_df.head(20),
                use_container_width=True,
                height=min(700, 50 + min(20, len(forecast_df)) * 35),
            )

            with st.expander("ℹ️ 明日温度スコアの読み方"):
                st.markdown("""
- 🔥🔥 **70以上**: 非常に盛り上がりやすい（強気銘柄集中 + US追い風）
- 🔥 **60-70**: 買いが集まりやすい
- 🟢 **50-60**: 平均的、注視対象
- 🟡 **40-50**: やや弱気
- 🔵 **40未満**: 弱含み／US逆風

**明日温度の算出式**:
```
明日温度 = NDXスコア平均 × 0.6 + (50 + 指数補正 + ETF補正) × 0.4
```

**3層の情報源**:
1. **NDXスコア** — 前日の日本市場のテクニカル（終値強さ・出来高・MA整列・RSI等）
2. **指数補正** — 米国主要指数の変化率（SOX/NASDAQ/VIX/ドル円/米10年債/WTI等）
3. **ETF補正** — 米国セクターETFの前日終値変化率（SMH/XBI/GDX/URA等、朝7時 JST 更新）

例:
- 半導体テーマ → SMH(半導体ETF)とSOX指数の両方で追い風判定
- バイオ医薬品 → XBI(バイオETF)と米ゲノム(ARKG)で追い風判定
- 金地金 → GDX(金鉱株ETF)で追い風判定
                """)

        st.divider()

        # --- Section 3: 翌営業日 注目銘柄ランキング（NDXスコア）---
        st.markdown(
            '<div class="mk-section-title">🎯 翌営業日 上昇期待銘柄ランキング</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "世界最高レベルのトレーダー/アナリスト視点で **10種のテクニカル指標を加重平均** した "
            "**NDXスコア**（Next-Day eXpected, 0〜100）で翌営業日に上がりやすい銘柄を可視化します。"
        )

        with st.expander("📖 スコアリング・ロジック（判断基準）", expanded=False):
            st.markdown("""
### 🔬 NDXスコア = 10指標の加重平均 (0〜100)

| 指標 | 重み | 判断理由 |
|---|---|---|
| **終値強さ** `(Close-Low)/(High-Low)` | **18%** | 高値引け=強い買い残存→翌日も継続されやすい |
| **出来高急増** `今日vol/20日avg` | **15%** | 平均2倍以上=機関投資家の注目集中サイン |
| **移動平均整列** `MA5>MA25>MA75` | **12%** | パーフェクトオーダー=強力な上昇トレンド |
| **5日モメンタム** | **12%** | 短期の勢いを捕捉 |
| **RSI(14)** | **10%** | 50-70が最適、>80は反落警戒（減点） |
| **MACDヒストグラム** | **10%** | ゼロライン上&拡大=強気、縮小=勢い鈍化 |
| **売買代金急増** | **8%** | 出来高×価格の総合的な注目度 |
| **20日高値ブレイク** | **8%** | 新高値更新=抵抗突破、継続力◎ |
| **前日比モメンタム** | **7%** | 当日の勢いを加味 |

### ⚠️ ペナルティ項目
- **1日+15%超の急騰** → 過熱ペナルティ（-3pt/%）
- **ATR>8%** → 異常ボラティリティ減点
- **薄商い銘柄** → 流動性フィルタで除外

### 💡 スコアの読み方
- 🔥 **75以上**: 強い買いサイン（複数指標が揃っている）
- 🟠 **60-75**: 買い候補（注視推奨）
- 🟢 **45-60**: 中立（判断保留）
- 🔴 **45未満**: 弱含み or 過熱リスク
            """)

        if not pred_df.empty:
            filtered_pred = filter_ranking_by_sector(pred_df, pred_sector_filter)

            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            with col_m1:
                st.metric("対象銘柄数", f"{len(filtered_pred):,}銘柄")
            with col_m2:
                strong_count = (filtered_pred["NDXスコア"] >= 75).sum()
                st.metric("🔥 強気シグナル", f"{strong_count}銘柄")
            with col_m3:
                avg_score = filtered_pred["NDXスコア"].mean()
                st.metric("平均NDXスコア", f"{avg_score:.1f}")
            with col_m4:
                breakout_count = (filtered_pred["ブレイク"] == "✅").sum()
                st.metric("20日高値更新", f"{breakout_count}銘柄")

            top_df = filtered_pred.head(pred_top_n)

            col_c1, col_c2 = st.columns([3, 4])
            with col_c1:
                st.plotly_chart(
                    next_day_ranking_bar(top_df, top_n=pred_top_n),
                    use_container_width=True,
                )
            with col_c2:
                st.markdown(f"**🏆 Top {len(top_df)} 詳細ランキング**")
                display_cols = [
                    "銘柄コード", "銘柄名", "セクター", "NDXスコア",
                    "終値", "前日比(%)", "終値強さ(%)", "出来高倍率",
                    "売買代金(億円)", "5日変化(%)", "RSI", "MACD",
                    "MA整列", "ブレイク", "トレーダー判断",
                ]
                st.dataframe(
                    top_df[display_cols],
                    use_container_width=True,
                    height=min(700, 50 + len(top_df) * 35),
                )

            st.markdown('<div class="mk-section-title">💎 本日のトップ3ピック</div>', unsafe_allow_html=True)
            top3_cols = st.columns(min(3, len(top_df)))
            for idx, (_, row) in enumerate(top_df.head(3).iterrows()):
                with top3_cols[idx]:
                    score = row["NDXスコア"]
                    if score >= 75:
                        bar_color = "#FF5E6C"
                    elif score >= 60:
                        bar_color = "#FFB020"
                    else:
                        bar_color = "#00E5FF"
                    change_color = "#FF5E6C" if row["前日比(%)"] > 0 else "#00D9A3"
                    pick_html = (
                        '<div style="background: linear-gradient(135deg, rgba(18,24,38,0.9) 0%, rgba(31,41,66,0.9) 100%);'
                        'border: 1px solid rgba(148,163,196,0.2);'
                        f'border-left: 4px solid {bar_color};'
                        'border-radius: 10px; padding: 16px; box-shadow: 0 4px 16px rgba(0,0,0,0.35);">'
                        f'<div style="font-size:10px;color:#6B7895;letter-spacing:0.1em;text-transform:uppercase;font-weight:700;">RANK #{idx+1}</div>'
                        f'<div style="font-size:18px;font-weight:700;color:#F0F3FA;margin-top:4px;">{row["銘柄名"]}</div>'
                        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:11px;color:#00E5FF;margin-top:2px;">'
                        f'{row["銘柄コード"]} · {row["セクター"]}</div>'
                        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:32px;font-weight:800;color:{bar_color};margin-top:12px;letter-spacing:-0.03em;text-shadow:0 0 20px {bar_color}66;">'
                        f'{score:.1f}</div>'
                        '<div style="font-size:10px;color:#A8B3CD;text-transform:uppercase;letter-spacing:0.1em;font-weight:600;">NDX Score</div>'
                        '<div style="margin-top:14px;padding-top:12px;border-top:1px solid rgba(148,163,196,0.15);">'
                        '<div style="font-size:11px;color:#A8B3CD;line-height:1.6;">'
                        f'<b>終値:</b> <span style="font-family:\'JetBrains Mono\',monospace;">{row["終値"]:,.1f}円</span><br>'
                        f'<b>前日比:</b> <span style="font-family:\'JetBrains Mono\',monospace;color:{change_color};">{row["前日比(%)"]:+.2f}%</span><br>'
                        f'<b>出来高:</b> <span style="font-family:\'JetBrains Mono\',monospace;">{row["出来高倍率"]:.2f}x</span><br>'
                        f'<b>売買代金:</b> <span style="font-family:\'JetBrains Mono\',monospace;">{row["売買代金(億円)"]:,.1f}億円</span>'
                        '</div></div>'
                        '<div style="margin-top:10px;font-size:12px;color:#F0F3FA;line-height:1.6;padding:8px 10px;background:rgba(0,229,255,0.05);border-radius:6px;border-left:2px solid #00E5FF;">'
                        f'💬 {row["トレーダー判断"]}</div>'
                        '</div>'
                    )
                    st.markdown(pick_html, unsafe_allow_html=True)

            st.caption(
                "⚠️ **重要**: NDXスコアはテクニカル指標のみに基づく統計的ランキングです。"
                "実際の投資判断は、企業ファンダメンタルズ・業績・ニュース・市況・マクロ環境を総合して行ってください。"
                "このツールは補助的な分析ツールとして活用し、投資は自己責任でお願いします。"
            )
        else:
            st.warning("⚠️ 計算対象の銘柄がありません。流動性フィルタを緩めるか、期間を長くしてデータを再取得してください。")

        st.divider()

        # --- Section 4: 本日のセクター概況（既存UIを維持）---
        st.markdown(
            '<div class="mk-section-title">📊 本日のセクター概況</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(sector_bar_chart(summary), use_container_width=True)
        with st.expander("📋 セクター別サマリー（詳細）", expanded=False):
            st.dataframe(summary, use_container_width=True)
    else:
        st.info(_NEED_DATA_MSG)
        st.markdown("""
        ##### 📌 使い方
        1. 左サイドバーで**期間を1ヶ月以上**に設定（テクニカル指標の精度のため）
        2. 📈 **売買代金データを取得** ボタンを押す
        3. このダッシュボードで **米国市場 → 明日注目セクター → 注目銘柄** が一覧できる
        4. **15:30 の日本市場引け後**にチェック
        """)

# ===== タブ2: 盛り上がりランキング（新機能） =====
with tab2:
    if has_market_data:
        st.subheader("🔥 セクター盛り上がりランキング")
        st.caption("💡 表の行をクリックするとセクター内の銘柄一覧が表示されます")

        if not momentum.empty:
            col1, col2 = st.columns([3, 2])
            with col1:
                st.plotly_chart(momentum_bar_chart(momentum), use_container_width=True)
            with col2:
                # 行選択可能なdataframe
                momentum_event = st.dataframe(
                    momentum,
                    use_container_width=True,
                    height=400,
                    on_select="rerun",
                    selection_mode="single-row",
                    key="momentum_table",
                )

            # --- 選択されたセクターの銘柄ドリルダウン ---
            selected_rows = momentum_event.selection.rows if momentum_event else []
            if selected_rows:
                # momentum は 1始まりindex なので iloc で取得
                selected_sector = momentum.iloc[selected_rows[0]]["セクター"]

                st.divider()
                st.markdown(
                    f'<div class="mk-section-title">📂 {selected_sector} — 構成銘柄</div>',
                    unsafe_allow_html=True,
                )

                # 1) セクター内銘柄リスト（元データ）
                sector_stocks = sectors.get(selected_sector, pd.DataFrame())

                # 2) 売買代金データがあれば急騰スコア付きで表示
                if not stock_momentum.empty:
                    sector_momentum = stock_momentum[
                        stock_momentum["セクター"] == selected_sector
                    ].copy()
                    sector_momentum = sector_momentum.sort_values(
                        "急騰スコア", ascending=False
                    ).reset_index(drop=True)
                    sector_momentum.index = sector_momentum.index + 1
                    sector_momentum.index.name = "順位"

                    if not sector_momentum.empty:
                        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                        with col_s1:
                            st.metric("構成銘柄数", f"{len(sector_momentum)}銘柄")
                        with col_s2:
                            total_val = sector_momentum["直近(億円)"].sum()
                            st.metric("直近売買代金合計", f"{total_val:,.1f}億円")
                        with col_s3:
                            avg_score = sector_momentum["急騰スコア"].mean()
                            st.metric("平均急騰スコア", f"{avg_score:+.1f}%")
                        with col_s4:
                            winners = (sector_momentum["急騰スコア"] > 0).sum()
                            st.metric(
                                "プラス銘柄",
                                f"{winners} / {len(sector_momentum)}",
                                delta=f"{winners/len(sector_momentum)*100:.0f}%",
                            )

                        st.markdown("**📊 銘柄別 急騰スコアランキング**")
                        st.dataframe(
                            sector_momentum.drop(columns=["セクター"]),
                            use_container_width=True,
                            height=min(600, 50 + len(sector_momentum) * 35),
                        )
                    else:
                        # momentum なし = fallback でセクター銘柄リストのみ
                        if not sector_stocks.empty:
                            st.dataframe(
                                sector_stocks[["証券コード", "銘柄名"]].reset_index(drop=True),
                                use_container_width=True,
                                hide_index=True,
                            )
                else:
                    # momentum 計算前 or 未取得 → 単純に構成銘柄
                    if not sector_stocks.empty:
                        st.dataframe(
                            sector_stocks[["証券コード", "銘柄名"]].reset_index(drop=True),
                            use_container_width=True,
                            hide_index=True,
                        )
            else:
                st.caption("👆 表の左側の行をクリックすると、そのセクターの構成銘柄が表示されます")

        st.divider()
        st.subheader("週間・期間 変化率")

        if not comparison.empty:
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(week_change_bar_chart(comparison), use_container_width=True)
            with col2:
                st.plotly_chart(period_change_bar_chart(comparison), use_container_width=True)

            st.subheader("比較データ詳細")
            st.dataframe(comparison, use_container_width=True, hide_index=True)
    else:
        st.info(_NEED_DATA_MSG)

# ===== タブ3: 時系列推移（改良版） =====
with tab3:
    if has_market_data:
        st.subheader("📈 売買代金 時系列推移")

        chart_mode = st.radio(
            "表示モード",
            ["すべて表示", "盛り上がりTop5を強調", "カスタム選択"],
            horizontal=True,
            key="chart_mode",
        )

        if chart_mode == "すべて表示":
            highlight = None
            chart_sectors = current_sectors
        elif chart_mode == "盛り上がりTop5を強調":
            highlight = hot_sectors
            chart_sectors = current_sectors
            st.caption(f"強調セクター: {', '.join(hot_sectors)}")
        else:
            highlight = st.multiselect(
                "強調表示するセクターを選択",
                options=current_sectors,
                default=hot_sectors[:3] if hot_sectors else current_sectors[:3],
                key="highlight_sectors",
            )
            chart_sectors = current_sectors

        st.plotly_chart(
            timeseries_chart(sector_df, chart_sectors, highlight_sectors=highlight),
            use_container_width=True,
        )
    else:
        st.info(_NEED_DATA_MSG)

# ===== タブ4: セクター比較 =====
with tab4:
    if has_market_data:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(
                comparison_bar_chart(sector_df, current_sectors), use_container_width=True
            )
        with col2:
            st.plotly_chart(
                normalized_chart(sector_df, current_sectors), use_container_width=True
            )
    else:
        st.info(_NEED_DATA_MSG)

# ===== タブ5: 銘柄別詳細 =====
with tab5:
    if has_market_data:
        st.plotly_chart(stock_detail_bar(detail), use_container_width=True)
        st.subheader("銘柄別売買代金一覧")
        st.dataframe(detail.reset_index(drop=True), use_container_width=True, hide_index=True)
    else:
        st.info(_NEED_DATA_MSG)

# ===== タブ6: 銘柄別変化率（新機能） =====
with tab6:
    if has_market_data:
        st.subheader("🚀 銘柄別 売買代金変化率ランキング")
        st.caption("前日比・週間変化・月間変化・vs期間平均 の加重平均で急騰スコアを算出")

        if not stock_momentum.empty:
            col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
            with col_f1:
                sector_filter = st.multiselect(
                    "セクターで絞り込み",
                    options=["すべて"] + sorted(stock_momentum["セクター"].unique().tolist()),
                    default=["すべて"],
                    key="stock_momentum_sector_filter",
                )
            with col_f2:
                top_n_select = st.selectbox(
                    "表示件数",
                    [10, 20, 30, 50, 100],
                    index=1,
                    key="stock_momentum_top_n",
                )
            with col_f3:
                sort_col = st.selectbox(
                    "ソート基準",
                    ["急騰スコア", "前日比(%)", "週間変化(%)", "月間変化(%)", "vs平均(%)"],
                    index=0,
                    key="stock_momentum_sort",
                )

            filtered_momentum = stock_momentum.copy()
            if "すべて" not in sector_filter:
                filtered_momentum = filtered_momentum[
                    filtered_momentum["セクター"].isin(sector_filter)
                ]

            filtered_momentum = filtered_momentum.sort_values(
                sort_col, ascending=False
            ).reset_index(drop=True)
            filtered_momentum.index = filtered_momentum.index + 1
            filtered_momentum.index.name = "順位"

            st.markdown(f"**対象銘柄数: {len(filtered_momentum)}**")

            col1, col2 = st.columns([3, 2])
            with col1:
                st.plotly_chart(
                    stock_momentum_bar_chart(filtered_momentum, top_n=top_n_select),
                    use_container_width=True,
                )
            with col2:
                st.dataframe(
                    filtered_momentum.head(top_n_select),
                    use_container_width=True,
                    height=600,
                )

            st.divider()
            st.subheader("変化率ヒートマップ")
            st.plotly_chart(
                stock_change_heatmap(filtered_momentum, top_n=min(top_n_select, 30)),
                use_container_width=True,
            )
        else:
            st.warning("銘柄別の変化率データを計算できませんでした。")
    else:
        st.info(_NEED_DATA_MSG)

# ===== タブ7: 市場ランキング =====
with tab7:
    st.subheader("🏆 市場ランキング（Yahoo Finance Japan）")
    st.caption("Yahoo Finance Japan からリアルタイムのランキングデータを取得します")

    # ランキング設定
    col_r1, col_r2, col_r3 = st.columns([2, 1, 1])

    categories = get_ranking_categories()

    with col_r1:
        # カテゴリ選択
        selected_category = st.selectbox(
            "カテゴリ",
            CATEGORY_ORDER,
            index=0,
            key="ranking_category",
        )
        # ランキング種類
        available_rankings = categories.get(selected_category, [])
        selected_ranking = st.selectbox(
            "ランキング種類",
            available_rankings,
            index=0,
            key="ranking_type",
        )

    with col_r2:
        selected_market = st.selectbox(
            "市場",
            list(MARKET_OPTIONS.keys()),
            index=0,
            key="ranking_market",
        )
        market_code = MARKET_OPTIONS[selected_market]

    with col_r3:
        selected_term = st.selectbox(
            "期間",
            list(TERM_OPTIONS.keys()),
            index=0,
            key="ranking_term",
        )
        term_code = TERM_OPTIONS[selected_term]

        ranking_pages = st.selectbox(
            "取得ページ数",
            [1, 2, 3],
            index=0,
            key="ranking_pages",
            help="1ページ = 約50銘柄",
        )

    # 取得ボタン
    if st.button("📡 ランキングを取得", key="fetch_ranking", use_container_width=True):
        with st.spinner(f"{selected_ranking} を取得中..."):
            ranking_df = fetch_ranking_via_read_html(
                ranking_name=selected_ranking,
                market=market_code,
                term=term_code,
                pages=ranking_pages,
            )
            st.session_state["ranking_data"] = ranking_df
            st.session_state["ranking_name"] = selected_ranking

    # 一括取得ボタン
    st.divider()
    col_batch1, col_batch2 = st.columns([1, 3])
    with col_batch1:
        if st.button("📡 主要ランキング一括取得", key="fetch_all_rankings"):
            quick_rankings = ["値上がり率", "値下がり率", "出来高", "売買代金上位", "ストップ高", "ストップ安"]
            progress_bar = st.progress(0, text="ランキングを取得中...")

            def update_progress(pct, text):
                progress_bar.progress(pct, text=text)

            results = fetch_multiple_rankings(
                ranking_names=quick_rankings,
                market=market_code,
                term=term_code,
                pages=1,
                progress_callback=update_progress,
            )
            st.session_state["batch_rankings"] = results
            progress_bar.empty()

    with col_batch2:
        st.caption("値上がり率・値下がり率・出来高・売買代金上位・ストップ高・ストップ安 を一括取得")

    # --- 個別ランキング表示 ---
    if "ranking_data" in st.session_state and st.session_state["ranking_data"] is not None:
        rdf = st.session_state["ranking_data"]
        rname = st.session_state.get("ranking_name", "ランキング")

        if not rdf.empty:
            st.subheader(f"{rname} ({selected_market} / {selected_term})")
            st.markdown(f"**取得件数: {len(rdf)}銘柄**")

            col1, col2 = st.columns([3, 2])
            with col1:
                st.plotly_chart(
                    market_ranking_bar(rdf, rname, top_n=50),
                    use_container_width=True,
                    key="single_ranking_chart",
                )
            with col2:
                st.dataframe(rdf, use_container_width=True, height=800, hide_index=True, key="single_ranking_df")
        else:
            st.warning(f"{rname} のデータを取得できませんでした。")

    # --- 一括ランキング表示 ---
    if "batch_rankings" in st.session_state:
        st.divider()
        st.subheader("📊 主要ランキング一覧")

        batch_data = st.session_state["batch_rankings"]

        # ランキングごとにフル表示
        ranking_names = [k for k, v in batch_data.items() if not v.empty]
        for idx, rname in enumerate(ranking_names):
            rdf = batch_data[rname]
            st.markdown(f"### {rname} ({len(rdf)}銘柄)")
            col1, col2 = st.columns([3, 2])
            with col1:
                st.plotly_chart(
                    market_ranking_bar(rdf, rname, top_n=50),
                    use_container_width=True,
                    key=f"batch_chart_{idx}_{rname}",
                )
            with col2:
                st.dataframe(rdf, use_container_width=True, height=600, hide_index=True, key=f"batch_df_{idx}_{rname}")
            if idx < len(ranking_names) - 1:
                st.divider()

# ===== タブ8: ニュース =====
with tab8:
    st.subheader("📰 株式ニュースフィード")
    st.caption("主要メディアの最新株式・経済ニュースをリアルタイムで取得")

    # ソース選択・設定
    col_n1, col_n2, col_n3 = st.columns([3, 1, 1])
    with col_n1:
        selected_sources = st.multiselect(
            "ニュースソース",
            options=get_source_names(),
            default=get_default_sources(),
            key="news_sources",
        )
    with col_n2:
        per_page = st.selectbox(
            "1ページ表示件数",
            [50, 100, 200],
            index=1,
            key="news_per_page",
        )
    with col_n3:
        auto_refresh_interval = st.selectbox(
            "自動更新間隔",
            [("OFF", 0), ("1分", 60), ("3分", 180), ("5分", 300), ("10分", 600)],
            index=3,  # デフォルト: 5分
            format_func=lambda x: x[0],
            key="news_auto_interval",
        )
        auto_interval_sec = auto_refresh_interval[1]

    # 自動更新ON/OFFトグル
    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        manual_fetch = st.button("📡 ニュースを取得", key="fetch_news", type="primary", use_container_width=True)
    with col_btn2:
        if auto_interval_sec > 0:
            auto_on = st.toggle("🔄 自動更新ON", value=st.session_state.get("news_auto_on", False), key="news_auto_toggle")
            st.session_state["news_auto_on"] = auto_on
        else:
            auto_on = False
            st.session_state["news_auto_on"] = False
            st.caption("自動更新: OFF")

    # --- ニュース取得関数 ---
    def _do_fetch_news(show_progress=True):
        if not selected_sources:
            st.warning("ソースを1つ以上選択してください。")
            return
        if show_progress:
            progress_bar = st.progress(0, text="ニュースを取得中...")
            def update_news_progress(pct, text):
                progress_bar.progress(pct, text=text)
        else:
            update_news_progress = None

        news_items = fetch_all_news(
            sources=selected_sources,
            progress_callback=update_news_progress,
        )
        if show_progress:
            progress_bar.empty()

        st.session_state["news_items"] = news_items
        st.session_state["news_fetched_at"] = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        st.session_state["news_last_fetch_ts"] = _time.time()
        st.session_state["news_page"] = 1  # 新規取得時はページ1に戻す
        # 古いニュース分析キャッシュをクリア
        for k in list(st.session_state.keys()):
            if isinstance(k, str) and k.startswith("news_analysis_"):
                del st.session_state[k]

    # 手動取得
    if manual_fetch:
        _do_fetch_news(show_progress=True)

    # 自動更新チェック: 前回取得から間隔が過ぎていたら自動取得
    if auto_on and auto_interval_sec > 0:
        last_ts = st.session_state.get("news_last_fetch_ts", 0)
        elapsed = _time.time() - last_ts
        if elapsed >= auto_interval_sec:
            _do_fetch_news(show_progress=True)

    # 自動更新タイマー表示
    if auto_on and auto_interval_sec > 0 and "news_last_fetch_ts" in st.session_state:
        last_ts = st.session_state["news_last_fetch_ts"]
        next_refresh = last_ts + auto_interval_sec
        remaining = int(next_refresh - _time.time())
        if remaining > 0:
            mins, secs = divmod(remaining, 60)
            st.info(f"🔄 自動更新ON（{auto_refresh_interval[0]}間隔） — 次回更新まで {mins}分{secs}秒")
        else:
            st.info(f"🔄 自動更新ON（{auto_refresh_interval[0]}間隔） — 更新中...")

    # ニュース表示
    if "news_items" in st.session_state:
        items = st.session_state["news_items"]
        fetched_at = st.session_state.get("news_fetched_at", "")

        if items:
            st.success(f"取得記事数: {len(items)}件 | 取得時刻: {fetched_at}")

            # --- 銘柄インデックス構築（セクターデータがある場合のみ・キャッシュ） ---
            known_stocks = []
            if sectors:
                cache_key = f"news_known_stocks_{len(sectors)}"
                if cache_key not in st.session_state:
                    st.session_state[cache_key] = build_stock_index(sectors)
                known_stocks = st.session_state[cache_key]

            # --- ニュース分析（アイテムIDでキャッシュ） ---
            analysis_cache_key = f"news_analysis_{st.session_state.get('news_fetched_at', '')}"
            if analysis_cache_key not in st.session_state:
                analysis_map = {}
                for item in items:
                    item_id = f"{item.url}"
                    analysis_map[item_id] = analyze_news_item(
                        item.title or "",
                        item.summary or "",
                        known_stocks,
                    )
                st.session_state[analysis_cache_key] = analysis_map
            analysis_map = st.session_state[analysis_cache_key]

            # フィルタ: ソース & 個別銘柄材料
            col_f1, col_f2 = st.columns([3, 1])
            with col_f1:
                all_sources_in_data = sorted(set(item.source for item in items))
                filter_source = st.multiselect(
                    "ソースで絞り込み",
                    options=["すべて"] + all_sources_in_data,
                    default=["すべて"],
                    key="news_filter_source",
                )
            with col_f2:
                only_stock_material = st.toggle(
                    "💎 個別株材料のみ",
                    value=False,
                    key="news_only_stock",
                    help="特定の銘柄名・証券コードが本文に含まれるニュースだけを表示",
                )

            filtered_items = items
            if "すべて" not in filter_source:
                filtered_items = [item for item in filtered_items if item.source in filter_source]
            if only_stock_material:
                filtered_items = [
                    item for item in filtered_items
                    if analysis_map.get(item.url) and analysis_map[item.url].has_stock_material
                ]

            # 材料あり件数サマリ
            stock_material_count = sum(
                1 for item in filtered_items
                if analysis_map.get(item.url) and analysis_map[item.url].has_stock_material
            )
            if stock_material_count > 0:
                st.caption(f"💎 個別株材料あり: {stock_material_count}件 / 全{len(filtered_items)}件中")

            # ページネーション
            total_items = len(filtered_items)
            total_pages = max(1, (total_items + per_page - 1) // per_page)

            # ページ番号の管理
            if "news_page" not in st.session_state:
                st.session_state["news_page"] = 1
            current_page = st.session_state["news_page"]
            current_page = min(current_page, total_pages)

            start_idx = (current_page - 1) * per_page
            end_idx = min(start_idx + per_page, total_items)
            display_items = filtered_items[start_idx:end_idx]

            # ページナビ（上部）
            col_pg1, col_pg2, col_pg3, col_pg4, col_pg5 = st.columns([1, 1, 2, 1, 1])
            with col_pg1:
                if st.button("⏮ 最初", key="news_pg_first", disabled=(current_page <= 1), use_container_width=True):
                    st.session_state["news_page"] = 1
                    st.rerun()
            with col_pg2:
                if st.button("◀ 前へ", key="news_pg_prev", disabled=(current_page <= 1), use_container_width=True):
                    st.session_state["news_page"] = current_page - 1
                    st.rerun()
            with col_pg3:
                st.markdown(
                    f"<div style='text-align:center;padding:8px 0;font-weight:600;'>"
                    f"📄 {current_page} / {total_pages} ページ "
                    f"（{start_idx+1}〜{end_idx}件 / 全{total_items}件）</div>",
                    unsafe_allow_html=True,
                )
            with col_pg4:
                if st.button("次へ ▶", key="news_pg_next", disabled=(current_page >= total_pages), use_container_width=True):
                    st.session_state["news_page"] = current_page + 1
                    st.rerun()
            with col_pg5:
                if st.button("最後 ⏭", key="news_pg_last", disabled=(current_page >= total_pages), use_container_width=True):
                    st.session_state["news_page"] = total_pages
                    st.rerun()

            # --- みんかぶ風ニュースリスト描画 ---
            import html as _html

            def _render_stock_material(analysis) -> str:
                """銘柄材料 + センチメント + 速報バッジ HTML"""
                if not analysis:
                    return ""
                parts = []

                # 上段: 速報 & センチメント
                top_parts = []
                if analysis.is_breaking:
                    top_parts.append('<span class="mk-breaking-badge">🚨 速報</span>')
                sent_cls = f"mk-sentiment-{analysis.sentiment}"
                top_parts.append(
                    f'<span class="mk-sentiment {sent_cls}">'
                    f'{analysis.sentiment_emoji} {analysis.sentiment_label}'
                    f'</span>'
                )

                # 銘柄チップ
                if analysis.mentioned_stocks:
                    chips = []
                    for s in analysis.mentioned_stocks:
                        safe_name = _html.escape(s.name)
                        safe_code = _html.escape(s.code)
                        safe_sector = _html.escape(s.sector) if s.sector else ""
                        sector_html = f'<span class="mk-stock-chip-sector">{safe_sector}</span>' if safe_sector else ""
                        chips.append(
                            f'<span class="mk-stock-chip">'
                            f'<span class="mk-stock-chip-code">{safe_code}</span>'
                            f'{safe_name}'
                            f'{sector_html}'
                            f'</span>'
                        )
                    parts.append(
                        f'<div class="mk-stock-material">'
                        f'<span class="mk-material-label">💎 個別株材料</span>'
                        f'{"".join(top_parts)}'
                        f'{"".join(chips)}'
                        f'</div>'
                    )
                elif analysis.is_breaking or analysis.sentiment != "neutral":
                    # 銘柄ヒットなしでも速報/センチメントは出す
                    parts.append(
                        f'<div class="mk-stock-material" style="border-left-color: var(--accent);">'
                        f'{"".join(top_parts)}'
                        f'</div>'
                    )
                return "".join(parts)

            def _render_blog_titles(analysis) -> str:
                """ブログタイトル提案 HTML"""
                if not analysis or not analysis.blog_titles:
                    return ""
                items_html = "".join(
                    f'<li class="mk-blog-title-item">'
                    f'<span class="mk-blog-title-num">案{i+1}</span>'
                    f'<span>{_html.escape(t)}</span>'
                    f'</li>'
                    for i, t in enumerate(analysis.blog_titles)
                )
                return (
                    f'<div class="mk-blog-box">'
                    f'<div class="mk-blog-box-header">✍️ ブログ記事タイトル案</div>'
                    f'<ul class="mk-blog-title-list">{items_html}</ul>'
                    f'</div>'
                )

            # ヘッドライン（最初の1件は大きめ表示 — みんかぶ風）
            if display_items:
                item = display_items[0]
                safe_title = _html.escape(item.title)
                safe_url = _html.escape(item.url)
                safe_source = _html.escape(item.source)
                safe_summary = ""
                if item.summary:
                    s = item.summary[:200] + ("..." if len(item.summary) > 200 else "")
                    safe_summary = _html.escape(s)
                safe_category = _html.escape(item.category) if item.category else ""
                time_str = _html.escape(item.published_str()) if item.published_str() else _html.escape(item.age_str())

                cat_tags = ""
                if safe_category:
                    cat_tags += f'<span class="mk-tag">{safe_category}</span>'
                cat_tags += f'<span class="mk-tag mk-tag-source">{safe_source}</span>'
                summary_html = f'<div class="mk-news-summary">{safe_summary}</div>' if safe_summary else ""

                analysis = analysis_map.get(item.url)
                material_html = _render_stock_material(analysis)
                blog_html = _render_blog_titles(analysis)

                st.markdown(
                    f'<div class="mk-news-headline">'
                    f'<div class="mk-news-hl-time">{time_str}</div>'
                    f'<div class="mk-news-title"><a href="{safe_url}" target="_blank" rel="noopener noreferrer">{safe_title}</a></div>'
                    f'{summary_html}'
                    f'<div class="mk-news-tags">{cat_tags}</div>'
                    f'{material_html}'
                    f'{blog_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            # 残りのニュース（みんかぶ風: タイトル左 — 時刻右端 + 材料あり記事は拡張表示）
            for idx, item in enumerate(display_items[1:]):
                safe_title = _html.escape(item.title)
                safe_url = _html.escape(item.url)
                age = _html.escape(item.age_str())
                time_str = _html.escape(item.published_str()) if item.published_str() else age
                time_display = f"今日 {time_str.split(' ')[-1]}" if ' ' in time_str else time_str

                # 新着は5分以内
                new_tag = '<span class="mk-news-new">NEW</span>' if age in ("たった今", "1分前", "2分前", "3分前", "4分前", "5分前") else ""

                analysis = analysis_map.get(item.url)
                material_html = _render_stock_material(analysis)
                blog_html = _render_blog_titles(analysis) if analysis and analysis.has_stock_material else ""

                st.markdown(
                    f'<div class="mk-news-item">'
                    f'<div class="mk-news-body">'
                    f'<div class="mk-news-title"><a href="{safe_url}" target="_blank" rel="noopener noreferrer">{safe_title}</a>{new_tag}</div>'
                    f'{material_html}'
                    f'{blog_html}'
                    f'</div>'
                    f'<div class="mk-news-time">{time_display}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            # ページナビ（下部）
            if total_pages > 1:
                col_bpg1, col_bpg2, col_bpg3, col_bpg4, col_bpg5 = st.columns([1, 1, 2, 1, 1])
                with col_bpg1:
                    if st.button("⏮ 最初", key="news_bpg_first", disabled=(current_page <= 1), use_container_width=True):
                        st.session_state["news_page"] = 1
                        st.rerun()
                with col_bpg2:
                    if st.button("◀ 前へ", key="news_bpg_prev", disabled=(current_page <= 1), use_container_width=True):
                        st.session_state["news_page"] = current_page - 1
                        st.rerun()
                with col_bpg3:
                    st.markdown(
                        f"<div style='text-align:center;padding:8px 0;font-weight:600;'>"
                        f"📄 {current_page} / {total_pages} ページ</div>",
                        unsafe_allow_html=True,
                    )
                with col_bpg4:
                    if st.button("次へ ▶", key="news_bpg_next", disabled=(current_page >= total_pages), use_container_width=True):
                        st.session_state["news_page"] = current_page + 1
                        st.rerun()
                with col_bpg5:
                    if st.button("最後 ⏭", key="news_bpg_last", disabled=(current_page >= total_pages), use_container_width=True):
                        st.session_state["news_page"] = total_pages
                        st.rerun()
        else:
            st.warning("ニュースが取得できませんでした。ソースを変更してみてください。")

    # 自動更新: st_autorefresh で定期的にページをリロード
    if auto_on and auto_interval_sec > 0:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(
            interval=auto_interval_sec * 1000,
            limit=None,
            key="news_autorefresh",
        )

# ===== タブ: ETF 2083 組入銘柄トラッカー =====
with tab_etf:
    render_etf2083_tab(sectors=sectors if sectors else None)

# ===== タブ9: 適時開示 =====
with tab9:
    st.subheader("📋 適時開示速報（TDnet）")
    st.caption("東証TDnetから最新の適時開示情報をリアルタイムで取得")

    # 設定行
    col_d1, col_d2, col_d3 = st.columns([1, 1, 1])
    with col_d1:
        disclosure_pages = st.selectbox(
            "取得ページ数",
            [1, 2, 3, 5, 10],
            index=1,
            key="disclosure_pages",
            help="1ページ = 約100件（TDnet）",
        )
    with col_d2:
        disc_auto_interval = st.selectbox(
            "自動更新間隔",
            [("OFF", 0), ("1分", 60), ("3分", 180), ("5分", 300), ("10分", 600)],
            index=3,  # デフォルト: 5分
            format_func=lambda x: x[0],
            key="disc_auto_interval",
        )
        disc_auto_sec = disc_auto_interval[1]
    with col_d3:
        disc_notify = st.toggle(
            "🔔 新着通知ON",
            value=st.session_state.get("disc_notify", True),
            key="disc_notify_toggle",
        )
        st.session_state["disc_notify"] = disc_notify

    # ボタン行
    col_db1, col_db2 = st.columns([1, 1])
    with col_db1:
        disc_manual = st.button("📡 適時開示を取得", key="fetch_disc", type="primary", use_container_width=True)
    with col_db2:
        if disc_auto_sec > 0:
            disc_auto_on = st.toggle("🔄 自動更新ON", value=st.session_state.get("disc_auto_on", False), key="disc_auto_toggle")
            st.session_state["disc_auto_on"] = disc_auto_on
        else:
            disc_auto_on = False
            st.session_state["disc_auto_on"] = False
            st.caption("自動更新: OFF")

    # --- 取得関数 ---
    def _do_fetch_disclosure():
        with st.spinner("適時開示を取得中..."):
            items = fetch_disclosure(pages=disclosure_pages)

        # 新着チェック
        prev_keys = st.session_state.get("disc_prev_keys", set())
        if prev_keys and disc_notify:
            new_items = check_new_disclosures(items, prev_keys)
            if new_items:
                st.toast(f"🔔 新着開示 {len(new_items)}件!", icon="🔔")
                for ni in new_items[:5]:
                    st.toast(f"📄 {ni.company}: {ni.title[:40]}")
                st.session_state["disc_new_keys"] = {ni.unique_key for ni in new_items}
            else:
                st.session_state["disc_new_keys"] = set()
        else:
            st.session_state["disc_new_keys"] = set()

        # キーを保存
        st.session_state["disc_prev_keys"] = {item.unique_key for item in items}
        st.session_state["disc_items"] = items
        st.session_state["disc_fetched_at"] = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        st.session_state["disc_last_fetch_ts"] = _time.time()
        st.session_state["disc_page"] = 1  # ページリセット

    # 手動取得
    if disc_manual:
        _do_fetch_disclosure()

    # 自動更新
    if disc_auto_on and disc_auto_sec > 0:
        last_ts = st.session_state.get("disc_last_fetch_ts", 0)
        elapsed = _time.time() - last_ts
        if elapsed >= disc_auto_sec:
            _do_fetch_disclosure()

    # タイマー表示
    if disc_auto_on and disc_auto_sec > 0 and "disc_last_fetch_ts" in st.session_state:
        last_ts = st.session_state["disc_last_fetch_ts"]
        next_refresh = last_ts + disc_auto_sec
        remaining = int(next_refresh - _time.time())
        if remaining > 0:
            mins, secs = divmod(remaining, 60)
            st.info(f"🔄 自動更新ON（{disc_auto_interval[0]}間隔） — 次回更新まで {mins}分{secs}秒")
        else:
            st.info(f"🔄 自動更新ON（{disc_auto_interval[0]}間隔） — 更新中...")

    # --- 開示カード表示 ---
    if "disc_items" in st.session_state:
        items = st.session_state["disc_items"]
        fetched_at = st.session_state.get("disc_fetched_at", "")
        new_keys = st.session_state.get("disc_new_keys", set())

        if items:
            st.success(f"取得件数: {len(items)}件 | 取得時刻: {fetched_at}")

            # カテゴリフィルタ
            all_cats = sorted(set(item.category for item in items))
            filter_cat = st.multiselect(
                "資料区分で絞り込み",
                options=["すべて"] + all_cats,
                default=["すべて"],
                key="disc_filter_cat",
            )

            # 企業名検索
            search_company = st.text_input(
                "🔍 企業名で検索",
                value="",
                key="disc_search_company",
                placeholder="企業名 or 証券コードを入力...",
            )

            filtered = items
            if "すべて" not in filter_cat:
                filtered = [it for it in filtered if it.category in filter_cat]
            if search_company.strip():
                q = search_company.strip()
                filtered = [it for it in filtered if q in it.company or q in it.title or q in it.code]

            # --- ページネーション設定 ---
            disc_per_page = st.selectbox(
                "1ページ表示件数", [50, 100, 200], index=1, key="disc_per_page",
            )
            total_disc_items = len(filtered)
            total_disc_pages = max(1, -(-total_disc_items // disc_per_page))  # ceil

            # フィルタ変更時にページリセット
            disc_filter_key = f"{filter_cat}_{search_company}"
            if st.session_state.get("_disc_filter_key") != disc_filter_key:
                st.session_state["disc_page"] = 1
                st.session_state["_disc_filter_key"] = disc_filter_key

            disc_current_page = st.session_state.get("disc_page", 1)
            disc_current_page = max(1, min(disc_current_page, total_disc_pages))
            st.session_state["disc_page"] = disc_current_page

            disc_start = (disc_current_page - 1) * disc_per_page
            disc_end = min(disc_start + disc_per_page, total_disc_items)
            display_disc = filtered[disc_start:disc_end]

            st.markdown(f"**表示中: {disc_start+1}〜{disc_end}件 / 全{total_disc_items}件（{len(items)}件中）**")

            # ページナビ（上部）
            if total_disc_pages > 1:
                col_dp1, col_dp2, col_dp3, col_dp4, col_dp5 = st.columns([1, 1, 2, 1, 1])
                with col_dp1:
                    if st.button("⏮ 最初", key="disc_pg_first", disabled=(disc_current_page <= 1), use_container_width=True):
                        st.session_state["disc_page"] = 1
                        st.rerun()
                with col_dp2:
                    if st.button("◀ 前へ", key="disc_pg_prev", disabled=(disc_current_page <= 1), use_container_width=True):
                        st.session_state["disc_page"] = disc_current_page - 1
                        st.rerun()
                with col_dp3:
                    st.markdown(
                        f"<div style='text-align:center;padding:8px 0;font-weight:600;'>"
                        f"📄 {disc_current_page} / {total_disc_pages} ページ</div>",
                        unsafe_allow_html=True,
                    )
                with col_dp4:
                    if st.button("次へ ▶", key="disc_pg_next", disabled=(disc_current_page >= total_disc_pages), use_container_width=True):
                        st.session_state["disc_page"] = disc_current_page + 1
                        st.rerun()
                with col_dp5:
                    if st.button("最後 ⏭", key="disc_pg_last", disabled=(disc_current_page >= total_disc_pages), use_container_width=True):
                        st.session_state["disc_page"] = total_disc_pages
                        st.rerun()

            import html as _html

            cards = []
            for item in display_disc:
                bg, fg = get_category_color(item.category)
                is_new = item.unique_key in new_keys

                safe_title = _html.escape(item.title)
                safe_company = _html.escape(item.company)
                safe_code = _html.escape(item.code) if item.code else ""
                safe_cat = _html.escape(item.category)
                safe_url = _html.escape(item.url) if item.url else ""
                time_label = _html.escape(item.time_str)

                new_tag = '<span class="mk-new-tag">🔔 NEW</span>' if is_new else ""
                new_bg = "background:#FFF8E1;border-color:#FFB300;border-width:2px;" if is_new else ""
                code_tag = f'<span class="mk-code">{safe_code}</span>' if safe_code else ""

                title_html = f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">{safe_title}</a>' if safe_url else safe_title

                cards.append(
                    f'<div class="mk-card mk-left-bar" style="border-left-color:{bg};{new_bg}">'
                    f'<div class="mk-card-header">'
                    f'<span class="mk-badge" style="background:{bg};color:{fg};">{safe_cat}</span>'
                    f'{code_tag}'
                    f'<span class="mk-company">{safe_company}</span>'
                    f'{new_tag}'
                    f'<span class="mk-meta">{time_label}</span>'
                    f'</div>'
                    f'<div class="mk-title">{title_html}</div>'
                    f'</div>'
                )

            # 1件ずつ st.markdown で出力
            for card in cards:
                st.markdown(card, unsafe_allow_html=True)

            # ページナビ（下部）
            if total_disc_pages > 1:
                col_dbp1, col_dbp2, col_dbp3, col_dbp4, col_dbp5 = st.columns([1, 1, 2, 1, 1])
                with col_dbp1:
                    if st.button("⏮ 最初", key="disc_bpg_first", disabled=(disc_current_page <= 1), use_container_width=True):
                        st.session_state["disc_page"] = 1
                        st.rerun()
                with col_dbp2:
                    if st.button("◀ 前へ", key="disc_bpg_prev", disabled=(disc_current_page <= 1), use_container_width=True):
                        st.session_state["disc_page"] = disc_current_page - 1
                        st.rerun()
                with col_dbp3:
                    st.markdown(
                        f"<div style='text-align:center;padding:8px 0;font-weight:600;'>"
                        f"📄 {disc_current_page} / {total_disc_pages} ページ</div>",
                        unsafe_allow_html=True,
                    )
                with col_dbp4:
                    if st.button("次へ ▶", key="disc_bpg_next", disabled=(disc_current_page >= total_disc_pages), use_container_width=True):
                        st.session_state["disc_page"] = disc_current_page + 1
                        st.rerun()
                with col_dbp5:
                    if st.button("最後 ⏭", key="disc_bpg_last", disabled=(disc_current_page >= total_disc_pages), use_container_width=True):
                        st.session_state["disc_page"] = total_disc_pages
                        st.rerun()
        else:
            st.warning("適時開示データを取得できませんでした。")

    # 自動更新: st_autorefresh
    if disc_auto_on and disc_auto_sec > 0:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(
            interval=disc_auto_sec * 1000,
            limit=None,
            key="disc_autorefresh",
        )

# ===== タブ11: 世界の株価 =====
with tab11:
    st.subheader("🌏 世界の株価・為替・商品")
    st.caption("日経平均・NYダウ・為替・商品・仮想通貨のリアルタイムデータ")

    # 設定行
    col_w1, col_w2 = st.columns([1, 1])
    with col_w1:
        world_manual = st.button("🔄 今すぐ更新", key="fetch_world", type="primary", use_container_width=True)
    with col_w2:
        world_auto_interval = st.selectbox(
            "自動更新間隔",
            [("OFF", 0), ("1分", 60), ("3分", 180), ("5分", 300)],
            index=0,  # デフォルト: OFF（10秒間隔だと他タブを巻き込んで頻繁にrerunされニュース取得が中断されるため）
            format_func=lambda x: x[0],
            key="world_auto_interval",
        )
        world_auto_sec = world_auto_interval[1]

    # 地域フィルタ
    selected_regions = st.multiselect(
        "表示する地域",
        options=REGION_ORDER,
        default=REGION_ORDER,
        key="world_regions",
    )

    # 取得処理
    def _do_fetch_world():
        items = fetch_world_indices()
        st.session_state["world_items"] = items
        st.session_state["world_fetched_at"] = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        st.session_state["world_last_fetch_ts"] = _time.time()

    # 手動更新
    if world_manual:
        _do_fetch_world()

    # 初回アクセス時に自動取得（ボタン不要）
    if "world_items" not in st.session_state:
        _do_fetch_world()

    # 自動更新
    if world_auto_sec > 0 and "world_last_fetch_ts" in st.session_state:
        last_ts = st.session_state["world_last_fetch_ts"]
        if _time.time() - last_ts >= world_auto_sec:
            _do_fetch_world()

    # 表示
    if "world_items" in st.session_state:
        items = st.session_state["world_items"]
        fetched_at = st.session_state.get("world_fetched_at", "")

        if items:
            filtered = [it for it in items if it.region in selected_regions]
            auto_label = f"🔄 {world_auto_interval[0]}で自動更新中" if world_auto_sec > 0 else "自動更新OFF"
            st.success(f"📡 {len(filtered)}件 | {fetched_at} 更新 | {auto_label}")

            import html as _html

            # 地域ごとにグループ化
            from itertools import groupby
            for region, group_items in groupby(filtered, key=lambda x: x.region):
                st.markdown(
                    f'<div class="mk-section">{_html.escape(region)}</div>',
                    unsafe_allow_html=True,
                )

                cards = []
                for item in group_items:
                    if item.is_up:
                        card_class = "mk-index-card mk-up"
                        change_class = "up"
                        arrow = "▲"
                    elif item.is_down:
                        card_class = "mk-index-card mk-down"
                        change_class = "down"
                        arrow = "▼"
                    else:
                        card_class = "mk-index-card mk-flat"
                        change_class = "flat"
                        arrow = "─"

                    safe_name = _html.escape(item.name)
                    safe_flag = _html.escape(item.flag)

                    cards.append(
                        f'<div class="{card_class}">'
                        f'<div class="mk-idx-name"><span>{safe_flag}</span> <span>{safe_name}</span></div>'
                        f'<div class="mk-idx-value">{_html.escape(item.value_str)}</div>'
                        f'<div class="mk-idx-change {change_class}">{arrow} {_html.escape(item.change_str)} ({_html.escape(item.change_pct_str)})</div>'
                        f'<div class="mk-idx-time">{_html.escape(item.time_str)}</div>'
                        f'</div>'
                    )

                grid_html = '<div class="mk-grid">' + "".join(cards) + '</div>'
                st.markdown(grid_html, unsafe_allow_html=True)
        else:
            st.warning("データを取得できませんでした。")
    else:
        st.info("⏳ データを読み込み中...")

    # 自動更新: st_autorefresh（常時有効）
    if world_auto_sec > 0:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(
            interval=world_auto_sec * 1000,
            limit=None,
            key="world_autorefresh",
        )

# ===== タブ10: 四季報CSV分析 =====
with tab10:
    st.subheader("📙 四季報オンライン CSV分析")
    st.caption("四季報オンライン プレミアムからダウンロードしたCSVを読み込んで分析")

    # CSVアップローダー
    st.markdown("""
    **対応CSV:**
    - 📈 **株価CSV** — ローソク足チャート・移動平均線・出来高
    - 📋 **ウォッチリスト一覧CSV** — 損益分析・ポートフォリオ一覧
    - 📊 **指標CSV / 業績CSV** — Chrome拡張からの指標・業績データ
    """)

    shikiho_files = st.file_uploader(
        "四季報CSVをアップロード",
        type=["csv"],
        accept_multiple_files=True,
        key="shikiho_csv_upload",
        help="複数ファイルを同時にアップロード可能",
    )

    if shikiho_files:
        for file_idx, uploaded_csv in enumerate(shikiho_files):
            st.divider()
            file_name = uploaded_csv.name

            try:
                # まず汎用読み込みで種類判定
                raw_df = pd.read_csv(uploaded_csv, encoding="utf-8-sig", nrows=5)
                uploaded_csv.seek(0)
                csv_type = detect_csv_type(raw_df)

                st.markdown(f"### 📄 {file_name}")
                st.caption(f"自動判定: **{csv_type.value}** | サイズ: {uploaded_csv.size:,} bytes")

                if csv_type == CsvType.STOCK_PRICE:
                    # --- 株価CSV ---
                    df = load_stock_price_csv(uploaded_csv)

                    if not df.empty:
                        # サマリーカード
                        stats = stock_price_summary(df)
                        cols = st.columns(len(stats))
                        for i, (label, value) in enumerate(stats.items()):
                            with cols[i % len(cols)]:
                                st.metric(label, value)

                        # ローソク足チャート
                        ticker_name = re.sub(r"_daily.*\.csv$", "", file_name, flags=re.IGNORECASE)
                        fig = stock_price_candlestick(df, title=f"{ticker_name} 株価チャート")
                        st.plotly_chart(fig, use_container_width=True, key=f"shikiho_candle_{file_idx}")

                        # データテーブル
                        with st.expander("📊 生データを表示", expanded=False):
                            st.dataframe(
                                df.reset_index(),
                                use_container_width=True,
                                height=400,
                                key=f"shikiho_price_df_{file_idx}",
                            )
                    else:
                        st.warning("株価データの読み込みに失敗しました。")

                elif csv_type == CsvType.WATCHLIST:
                    # --- ウォッチリスト ---
                    df = load_watchlist_csv(uploaded_csv)

                    if not df.empty:
                        st.success(f"ウォッチリスト: {len(df)}銘柄")

                        # 損益チャート
                        chart = watchlist_profit_chart(df)
                        if chart:
                            st.plotly_chart(chart, use_container_width=True, key=f"shikiho_wl_chart_{file_idx}")

                        # テーブル表示
                        st.dataframe(
                            df,
                            use_container_width=True,
                            height=min(600, len(df) * 35 + 50),
                            hide_index=True,
                            key=f"shikiho_wl_df_{file_idx}",
                        )

                        # 基本統計
                        pnl_col = next((c for c in df.columns if "損益(%)" in c or "損益(%" in c), None)
                        if pnl_col and df[pnl_col].notna().any():
                            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                            with col_s1:
                                st.metric("銘柄数", f"{len(df)}")
                            with col_s2:
                                winners = (df[pnl_col] > 0).sum()
                                st.metric("含み益銘柄", f"{winners}銘柄", delta=f"{winners/len(df)*100:.0f}%")
                            with col_s3:
                                st.metric("最大利益", f"{df[pnl_col].max():+.1f}%")
                            with col_s4:
                                st.metric("最大損失", f"{df[pnl_col].min():+.1f}%")
                    else:
                        st.warning("ウォッチリストの読み込みに失敗しました。")

                elif csv_type in (CsvType.INDICATORS, CsvType.FINANCIAL):
                    # --- 指標/業績CSV ---
                    df = load_generic_csv(uploaded_csv)

                    if not df.empty:
                        label = "指標データ" if csv_type == CsvType.INDICATORS else "業績データ"
                        st.success(f"{label}: {len(df)}銘柄 × {len(df.columns)}項目")

                        # テーブル表示
                        st.dataframe(
                            df,
                            use_container_width=True,
                            height=min(600, len(df) * 35 + 50),
                            hide_index=True,
                            key=f"shikiho_gen_df_{file_idx}",
                        )

                        # 数値列のサマリー
                        numeric_cols = df.select_dtypes(include="number").columns.tolist()
                        if numeric_cols:
                            with st.expander("📊 統計サマリー", expanded=False):
                                st.dataframe(
                                    df[numeric_cols].describe().T.round(2),
                                    use_container_width=True,
                                    key=f"shikiho_gen_stats_{file_idx}",
                                )

                            # ソート機能
                            sort_col = st.selectbox(
                                "並び替え列",
                                options=numeric_cols,
                                index=0,
                                key=f"shikiho_sort_{file_idx}",
                            )
                            sort_order = st.radio(
                                "順序",
                                ["降順", "昇順"],
                                horizontal=True,
                                key=f"shikiho_order_{file_idx}",
                            )
                            sorted_df = df.sort_values(
                                sort_col, ascending=(sort_order == "昇順")
                            ).reset_index(drop=True)
                            sorted_df.index = sorted_df.index + 1
                            sorted_df.index.name = "順位"
                            st.dataframe(
                                sorted_df,
                                use_container_width=True,
                                height=600,
                                key=f"shikiho_sorted_df_{file_idx}",
                            )
                    else:
                        st.warning("データの読み込みに失敗しました。")

                else:
                    # --- 不明なCSV → 汎用表示 ---
                    df = load_generic_csv(uploaded_csv)
                    if not df.empty:
                        st.info(f"CSV種類を自動判定できませんでした。汎用表示します（{len(df)}行 × {len(df.columns)}列）")
                        st.dataframe(
                            df,
                            use_container_width=True,
                            height=min(600, len(df) * 35 + 50),
                            hide_index=True,
                            key=f"shikiho_unk_df_{file_idx}",
                        )
                    else:
                        st.error("CSVの読み込みに失敗しました。")

            except Exception as e:
                st.error(f"❌ {file_name} の読み込みエラー: {e}")

    else:
        # ガイダンス表示
        st.info("👆 四季報オンラインからダウンロードしたCSVファイルをアップロードしてください。")

        st.markdown("""
        #### 📥 CSVの取得方法

        **株価CSV（プレミアム限定）:**
        1. 四季報オンラインで銘柄ページを開く
        2. 「時系列株価」セクションの「株価CSVダウンロード」ボタンをクリック
        3. ダウンロードされたCSVをここにアップロード

        **ウォッチリストCSV:**
        1. ウォッチリストページの「一覧」タブを開く
        2. 「CSVダウンロード」ボタンをクリック

        **指標・業績CSV（Chrome拡張）:**
        1. Chrome拡張「四季報オンライン BrowserExtension」をインストール
        2. ウォッチリストの「指標」or「業績」タブを開く
        3. 拡張機能のCSVボタンでダウンロード

        > 💡 **複数ファイルを同時にアップロード可能です！**
        """)

# フッター
st.divider()
if has_market_data:
    st.caption(f"データ期間: {start_str} 〜 {end_str} | 集計単位: {freq} | データソース: Yahoo Finance (yfinance)")
else:
    st.caption("データソース: Yahoo Finance (yfinance) | ニュース・市場ランキングは売買代金データ取得不要で利用できます")
