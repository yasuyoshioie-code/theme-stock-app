"""世界の株価・為替・商品・仮想通貨のリアルタイムデータ取得モジュール

データ元: nikkei225jp.com の AJAX エンドポイント
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

import requests
import streamlit as st

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://nikkei225jp.com/",
}

# AJAX エンドポイント
AJAX_URLS = {
    "TOP": "https://jss.nikkei225jp.com/ajaxindex/ajax_TOP.js",
    "dow": "https://jss.nikkei225jp.com/ajaxindex/ajax_dow.js",
    "oil": "https://jss.nikkei225jp.com/ajaxindex/ajax_oil.js",
    "bitcoin": "https://jss.nikkei225jp.com/ajaxindex/ajax_bitcoin.js",
}

# コード → 名前・地域マッピング
INDEX_MAP = {
    # === 日本 ===
    "111": ("日経平均", "日本", "🇯🇵"),
    "112": ("TOPIX", "日本", "🇯🇵"),
    "121": ("グロース250", "日本", "🇯🇵"),
    "136": ("日経先物(mini)", "日本", "🇯🇵"),
    "141": ("東証REIT指数", "日本", "🇯🇵"),
    "151": ("日本10年債利回り", "日本", "🇯🇵"),
    "191": ("日経CFD", "日本", "🇯🇵"),

    # === 米国 ===
    "211": ("NYダウ", "米国", "🇺🇸"),
    "212": ("NASDAQ", "米国", "🇺🇸"),
    "213": ("S&P500", "米国", "🇺🇸"),
    "214": ("NASDAQ100", "米国", "🇺🇸"),
    "216": ("FANG+", "米国", "🇺🇸"),
    "611": ("SOX半導体", "米国", "🇺🇸"),
    "613": ("ラッセル2000", "米国", "🇺🇸"),
    "621": ("VIX恐怖指数", "米国", "🇺🇸"),
    "811": ("米10年債利回り", "米国", "🇺🇸"),
    "731": ("NYダウCFD", "米国", "🇺🇸"),
    "737": ("NAS100CFD", "米国", "🇺🇸"),

    # === 欧州 ===
    "411": ("CAC40 (仏)", "欧州", "🇫🇷"),
    "412": ("DAX (独)", "欧州", "🇩🇪"),
    "413": ("FTSE100 (英)", "欧州", "🇬🇧"),
    "481": ("STOXX50", "欧州", "🇪🇺"),

    # === アジア ===
    "312": ("台湾 加権", "アジア", "🇹🇼"),
    "313": ("韓国 KOSPI", "アジア", "🇰🇷"),
    "321": ("上海総合", "アジア", "🇨🇳"),
    "331": ("香港 ハンセン", "アジア", "🇭🇰"),
    "341": ("シンガポール STI", "アジア", "🇸🇬"),
    "345": ("タイ SET", "アジア", "🇹🇭"),
    "347": ("インドネシア JCI", "アジア", "🇮🇩"),
    "352": ("インド Nifty50", "アジア", "🇮🇳"),

    # === 為替 ===
    "501": ("ドルインデックス", "為替", "💱"),
    "511": ("ドル円", "為替", "💴"),
    "514": ("ユーロ円", "為替", "💶"),
    "523": ("ユーロドル", "為替", "💶"),

    # === 商品 ===
    "921": ("WTI原油", "商品", "🛢️"),
    "931": ("NY金", "商品", "🥇"),
    "932": ("NY銀", "商品", "🥈"),
    "934": ("プラチナ", "商品", "⬜"),
    "912": ("CRB指数", "商品", "📦"),

    # === 仮想通貨 ===
    "1001": ("ビットコイン", "仮想通貨", "₿"),
    "1011": ("イーサリアム", "仮想通貨", "⟠"),
    "1021": ("リップル(XRP)", "仮想通貨", "✕"),
    "1031": ("ソラナ(SOL)", "仮想通貨", "◎"),

    # === 投信 ===
    "641": ("eMAXIS全世界", "投信", "🌍"),
    "642": ("eMAXIS S&P500", "投信", "🌍"),
    "643": ("eMAXIS先進国", "投信", "🌍"),
}

# 地域の表示順
REGION_ORDER = ["日本", "米国", "欧州", "アジア", "為替", "商品", "仮想通貨", "投信"]

# 地域ごとの色（みんかぶ風ネイビー基調）
REGION_COLORS = {
    "日本": ("#014099", "#FFFFFF"),
    "米国": ("#1565C0", "#FFFFFF"),
    "欧州": ("#2E7D32", "#FFFFFF"),
    "アジア": ("#D84315", "#FFFFFF"),
    "為替": ("#6A1B9A", "#FFFFFF"),
    "商品": ("#5D4037", "#FFFFFF"),
    "仮想通貨": ("#E65100", "#FFFFFF"),
    "投信": ("#00695C", "#FFFFFF"),
}


@dataclass
class IndexData:
    """指標1件分のデータ"""
    code: str
    name: str
    region: str
    flag: str
    value: float | None
    change: float | None
    change_pct: float | None
    time_str: str
    status: int  # 0=closed, 1=open

    @property
    def is_up(self) -> bool:
        return (self.change or 0) > 0

    @property
    def is_down(self) -> bool:
        return (self.change or 0) < 0

    @property
    def change_str(self) -> str:
        if self.change is None:
            return ""
        return f"{self.change:+,.2f}"

    @property
    def change_pct_str(self) -> str:
        if self.change_pct is None:
            return ""
        return f"{self.change_pct:+.2f}%"

    @property
    def value_str(self) -> str:
        if self.value is None:
            return "-"
        if abs(self.value) >= 1000:
            return f"{self.value:,.2f}"
        return f"{self.value:.4f}" if abs(self.value) < 10 else f"{self.value:,.2f}"


def _parse_ajax_line(code: str, raw: str) -> IndexData | None:
    """A[code]='value_change_pct_time_status__' をパース"""
    info = INDEX_MAP.get(code)
    if not info:
        return None

    name, region, flag = info
    parts = raw.split("_")

    try:
        value = float(parts[0].replace(",", "")) if parts[0] else None
    except (ValueError, IndexError):
        value = None
    try:
        change = float(parts[1].replace(",", "")) if len(parts) > 1 and parts[1] else None
    except (ValueError, IndexError):
        change = None
    try:
        change_pct = float(parts[2].replace(",", "")) if len(parts) > 2 and parts[2] else None
    except (ValueError, IndexError):
        change_pct = None

    time_str = parts[3] if len(parts) > 3 else ""
    try:
        status = int(parts[4]) if len(parts) > 4 and parts[4] else 0
    except ValueError:
        status = 0

    return IndexData(
        code=code,
        name=name,
        region=region,
        flag=flag,
        value=value,
        change=change,
        change_pct=change_pct,
        time_str=time_str,
        status=status,
    )


def fetch_world_indices(pages: list[str] | None = None) -> list[IndexData]:
    """世界の株価データを取得

    Args:
        pages: 取得するページリスト ['TOP', 'dow', 'oil', 'bitcoin']
               Noneなら全ページ取得

    Returns:
        IndexData のリスト（地域→コード順でソート）
    """
    if pages is None:
        pages = list(AJAX_URLS.keys())

    all_data: dict[str, IndexData] = {}

    for page in pages:
        url = AJAX_URLS.get(page)
        if not url:
            continue

        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            text = resp.text

            # A[code]="value_change_pct_time_status__"; パターンで抽出
            for m in re.finditer(r'A\[(\d+)\]="([^"]*)"', text):
                code = m.group(1)
                raw = m.group(2)
                if code in INDEX_MAP and code not in all_data:
                    item = _parse_ajax_line(code, raw)
                    if item:
                        all_data[code] = item

        except Exception as e:
            st.warning(f"世界の株価 ({page}) 取得エラー: {e}")

    # 地域順 → コード順でソート
    region_rank = {r: i for i, r in enumerate(REGION_ORDER)}
    items = sorted(
        all_data.values(),
        key=lambda x: (region_rank.get(x.region, 99), x.code),
    )
    return items


def get_region_color(region: str) -> tuple[str, str]:
    """地域名から (背景色, 文字色) を返す"""
    return REGION_COLORS.get(region, ("#757575", "#FFFFFF"))
