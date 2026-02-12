"""株式関連ニュースフィードを複数ソースから取得するモジュール

対応ソース:
  - moomoo証券 ニュース速報/ヘッドライン: スクレイピング
  - CNBC World: RSS
  - WSJ日本版: Google News経由
  - 四季報オンライン: Google News経由
  - 東洋経済オンライン: RSS
  - ロイター日本語: Google News経由
  - ブルームバーグ日本語: Google News経由
  - 日経: Google News経由
  - 株探 (Kabutan): Google News経由
  - みんかぶ: スクレイピング
  - Google News (株式市場): RSS
"""

import re
import time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

import feedparser
import requests
from bs4 import BeautifulSoup
import streamlit as st

# ----------------------------------------------------------------
# 定数
# ----------------------------------------------------------------

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# ----------------------------------------------------------------
# データモデル
# ----------------------------------------------------------------

@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published: datetime | None = None
    summary: str = ""
    category: str = ""

    def published_str(self) -> str:
        if self.published is None:
            return ""
        return self.published.strftime("%Y/%m/%d %H:%M")

    def age_str(self) -> str:
        """○分前 / ○時間前 / ○日前 を返す"""
        if self.published is None:
            return ""
        now = datetime.now(JST)
        pub = self.published
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=JST)
        diff = now - pub
        secs = int(diff.total_seconds())
        if secs < 0:
            return "たった今"
        if secs < 60:
            return "たった今"
        if secs < 3600:
            return f"{secs // 60}分前"
        if secs < 86400:
            return f"{secs // 3600}時間前"
        return f"{secs // 86400}日前"


# ----------------------------------------------------------------
# ユーティリティ
# ----------------------------------------------------------------

def _parse_rss_date(entry) -> datetime | None:
    """feedparserのentryからdatetimeを抽出"""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            dt = datetime(*parsed[:6], tzinfo=timezone.utc)
            return dt.astimezone(JST)
        except Exception:
            pass
    date_str = entry.get("published") or entry.get("updated") or ""
    if date_str:
        for fmt in [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
        ]:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(JST)
            except ValueError:
                continue
    return None


def _clean_html(text: str) -> str:
    """HTMLタグを除去"""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_relative_time(text: str) -> datetime | None:
    """moomooの相対時刻(例: '15:30', '07:50')をJST datetimeに変換"""
    m = re.search(r"(\d{1,2}):(\d{2})\s*$", text)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        now = datetime.now(JST)
        dt = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        # 未来なら前日にする
        if dt > now:
            dt -= timedelta(days=1)
        return dt
    return None


# ----------------------------------------------------------------
# moomoo証券 ニュース
# ----------------------------------------------------------------

def fetch_moomoo_news() -> list[NewsItem]:
    """moomoo証券 ニュース速報・ヘッドライン（SSRページをスクレイピング）"""
    url = "https://www.moomoo.com/ja/news/main"
    items = []

    # 既知のサブソース名
    KNOWN_SOURCES = [
        "moomooニュース", "みんかぶ", "時事通信社", "Reuters",
        "Trader's Web", "Fisco", "株探ニュース", "フィスコ",
        "ロイター", "Bloomberg", "共同通信",
    ]

    def _split_title_source(text: str):
        """タイトル末尾の 'ソース名·HH:MM' を分離"""
        for src in KNOWN_SOURCES:
            # "ソース名·HH:MM" パターン
            pattern = re.escape(src) + r"[·・](\d{1,2}:\d{2})\s*$"
            m = re.search(pattern, text)
            if m:
                title = text[:m.start()].strip()
                pub_dt = _parse_relative_time(m.group(1))
                return title, src, pub_dt
            # "ソース名·数字" パターン (時のみ)
            pattern2 = re.escape(src) + r"[·・](\d{1,2})\s*$"
            m2 = re.search(pattern2, text)
            if m2:
                title = text[:m2.start()].strip()
                return title, src, None
            # ソース名のみ (末尾)
            if text.endswith(src):
                title = text[:-len(src)].strip()
                if title:
                    return title, src, None
        return text, "moomoo", None

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "")
            if "/ja/news/post/" not in href:
                continue

            text = a_tag.get_text(strip=True)
            if not text or len(text) < 10:
                continue

            title, sub_source, pub_dt = _split_title_source(text)

            if not href.startswith("http"):
                href = "https://www.moomoo.com" + href

            items.append(NewsItem(
                title=title,
                url=href,
                source=f"moomoo ({sub_source})",
                published=pub_dt,
                category="マーケット",
            ))

        # 重複除去
        seen = set()
        unique = []
        for item in items:
            key = re.sub(r"\s+", "", item.title)
            if key not in seen:
                seen.add(key)
                unique.append(item)
        items = unique[:50]

    except Exception as e:
        st.warning(f"moomoo証券 取得エラー: {e}")
    return items


# ----------------------------------------------------------------
# CNBC World
# ----------------------------------------------------------------

def fetch_cnbc_world() -> list[NewsItem]:
    """CNBC World RSS"""
    url = "https://www.cnbc.com/id/100727362/device/rss/rss.html"
    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:30]:
            items.append(NewsItem(
                title=entry.get("title", ""),
                url=entry.get("link", ""),
                source="CNBC",
                published=_parse_rss_date(entry),
                summary=_clean_html(entry.get("summary", "")),
                category="World",
            ))
    except Exception as e:
        st.warning(f"CNBC RSS 取得エラー: {e}")
    return items


# ----------------------------------------------------------------
# Google News 経由の各メディア
# ----------------------------------------------------------------

def fetch_google_news_query(query: str, source_label: str, category: str = "株式") -> list[NewsItem]:
    """Google News RSS で特定クエリのニュースを取得"""
    encoded = requests.utils.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=ja&gl=JP&ceid=JP:ja"
    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:20]:
            title = entry.get("title", "")
            actual_source = source_label
            if " - " in title:
                parts = title.rsplit(" - ", 1)
                title = parts[0]
                actual_source = parts[1] if len(parts) > 1 else source_label

            items.append(NewsItem(
                title=title,
                url=entry.get("link", ""),
                source=actual_source,
                published=_parse_rss_date(entry),
                summary=_clean_html(entry.get("summary", "")),
                category=category,
            ))
    except Exception as e:
        st.warning(f"Google News ({source_label}) 取得エラー: {e}")
    return items


def fetch_wsj_japan() -> list[NewsItem]:
    """WSJ日本版（Google News経由）"""
    return fetch_google_news_query(
        "site:jp.wsj.com",
        source_label="WSJ日本版",
        category="市場",
    )


def fetch_shikiho() -> list[NewsItem]:
    """四季報オンライン（Google News経由）"""
    return fetch_google_news_query(
        "site:shikiho.toyokeizai.net",
        source_label="四季報オンライン",
        category="株式",
    )


def fetch_reuters_japan() -> list[NewsItem]:
    """ロイター日本語版（Google News経由）"""
    return fetch_google_news_query(
        "site:jp.reuters.com 株 OR 市場 OR 経済",
        source_label="ロイター",
        category="市場",
    )


def fetch_bloomberg_japan() -> list[NewsItem]:
    """ブルームバーグ日本語版（Google News経由）"""
    return fetch_google_news_query(
        "site:bloomberg.co.jp 株 OR 市場 OR 経済",
        source_label="ブルームバーグ",
        category="市場",
    )


def fetch_nikkei() -> list[NewsItem]:
    """日経新聞（Google News経由）"""
    return fetch_google_news_query(
        "site:nikkei.com 株式 OR 市場 OR 経済",
        source_label="日経",
        category="経済",
    )


def fetch_kabutan() -> list[NewsItem]:
    """株探（Google News経由）"""
    return fetch_google_news_query(
        "site:kabutan.jp",
        source_label="株探",
        category="株式",
    )


# ----------------------------------------------------------------
# 東洋経済 RSS
# ----------------------------------------------------------------

def fetch_toyokeizai() -> list[NewsItem]:
    """東洋経済オンライン RSS"""
    url = "https://toyokeizai.net/list/feed/rss"
    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:30]:
            title = entry.get("title", "")
            # " | カテゴリ | 東洋経済オンライン" を除去
            title = re.sub(r"\s*\|.*東洋経済.*$", "", title)
            items.append(NewsItem(
                title=title,
                url=entry.get("link", ""),
                source="東洋経済",
                published=_parse_rss_date(entry),
                summary=_clean_html(entry.get("summary", "")),
                category="経済",
            ))
    except Exception as e:
        st.warning(f"東洋経済 RSS 取得エラー: {e}")
    return items


# ----------------------------------------------------------------
# みんかぶ
# ----------------------------------------------------------------

def fetch_minkabu() -> list[NewsItem]:
    """みんかぶ ニュース（スクレイピング）"""
    url = "https://minkabu.jp/news"
    items = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for a_tag in soup.select("a[href*='/news/']"):
            title = a_tag.get_text(strip=True)
            href = a_tag.get("href", "")

            if not title or len(title) < 8:
                continue
            if not href.startswith("http"):
                href = "https://minkabu.jp" + href

            time_tag = a_tag.find_next("time") or a_tag.find_previous("time")
            pub_dt = None
            if time_tag:
                dt_str = time_tag.get("datetime", "")
                if dt_str:
                    try:
                        pub_dt = datetime.fromisoformat(dt_str)
                        if pub_dt.tzinfo is None:
                            pub_dt = pub_dt.replace(tzinfo=JST)
                        pub_dt = pub_dt.astimezone(JST)
                    except Exception:
                        pass

            items.append(NewsItem(
                title=title,
                url=href,
                source="みんかぶ",
                published=pub_dt,
                category="株式",
            ))

        seen = set()
        unique = []
        for item in items:
            if item.title not in seen:
                seen.add(item.title)
                unique.append(item)
        items = unique[:30]

    except Exception as e:
        st.warning(f"みんかぶ 取得エラー: {e}")
    return items


# ----------------------------------------------------------------
# Google News 一般
# ----------------------------------------------------------------

def fetch_google_news_market() -> list[NewsItem]:
    """Google News 日本株式市場 一般クエリ"""
    return fetch_google_news_query(
        "日本株 OR 東証 OR 日経平均 OR 株式市場",
        source_label="Google News",
        category="株式市場",
    )


# ----------------------------------------------------------------
# ソース定義
# ----------------------------------------------------------------

NEWS_SOURCES = {
    "moomoo証券": {
        "func": fetch_moomoo_news,
        "icon": "🟣",
        "default": True,
    },
    "CNBC World": {
        "func": fetch_cnbc_world,
        "icon": "🔷",
        "default": True,
    },
    "WSJ日本版": {
        "func": fetch_wsj_japan,
        "icon": "📘",
        "default": True,
    },
    "四季報オンライン": {
        "func": fetch_shikiho,
        "icon": "📙",
        "default": True,
    },
    "東洋経済": {
        "func": fetch_toyokeizai,
        "icon": "📕",
        "default": True,
    },
    "ロイター": {
        "func": fetch_reuters_japan,
        "icon": "🟠",
        "default": True,
    },
    "ブルームバーグ": {
        "func": fetch_bloomberg_japan,
        "icon": "🔵",
        "default": True,
    },
    "日経": {
        "func": fetch_nikkei,
        "icon": "🔴",
        "default": True,
    },
    "株探": {
        "func": fetch_kabutan,
        "icon": "🟢",
        "default": True,
    },
    "みんかぶ": {
        "func": fetch_minkabu,
        "icon": "🟡",
        "default": True,
    },
    "Google News (株式市場)": {
        "func": fetch_google_news_market,
        "icon": "⚪",
        "default": False,
    },
}


# ----------------------------------------------------------------
# 高レベルAPI
# ----------------------------------------------------------------

def fetch_all_news(
    sources: list[str] | None = None,
    progress_callback=None,
) -> list[NewsItem]:
    """複数ソースからニュースを一括取得し、日時順でソートして返す"""

    if sources is None:
        sources = [name for name, info in NEWS_SOURCES.items() if info["default"]]

    all_items: list[NewsItem] = []
    total = len(sources)

    for i, source_name in enumerate(sources):
        if progress_callback:
            progress_callback(i / total, f"{source_name} を取得中...")

        source_info = NEWS_SOURCES.get(source_name)
        if source_info is None:
            continue

        try:
            items = source_info["func"]()
            all_items.extend(items)
        except Exception as e:
            st.warning(f"{source_name} の取得に失敗: {e}")

        if i < total - 1:
            time.sleep(0.3)

    if progress_callback:
        progress_callback(1.0, "完了")

    # 日時順ソート（新しい順）
    def sort_key(item: NewsItem):
        if item.published is None:
            return datetime.min.replace(tzinfo=JST)
        dt = item.published
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return dt

    all_items.sort(key=sort_key, reverse=True)

    # タイトルの重複除去
    seen_titles = set()
    unique = []
    for item in all_items:
        normalized = re.sub(r"\s+", "", item.title)
        if normalized not in seen_titles:
            seen_titles.add(normalized)
            unique.append(item)

    return unique


def get_source_names() -> list[str]:
    """利用可能なソース名一覧"""
    return list(NEWS_SOURCES.keys())


def get_default_sources() -> list[str]:
    """デフォルトで有効なソース名一覧"""
    return [name for name, info in NEWS_SOURCES.items() if info["default"]]


# ソース別カラー定義 (badge背景色, badge文字色)
_SOURCE_COLORS = {
    "moomoo":       ("#7C3AED", "#FFFFFF"),  # 紫
    "cnbc":         ("#005594", "#FFFFFF"),  # 紺
    "wsj":          ("#0274B6", "#FFFFFF"),  # 青
    "四季報":       ("#E67E22", "#FFFFFF"),  # オレンジ
    "東洋経済":     ("#C0392B", "#FFFFFF"),  # 赤
    "ロイター":     ("#FF8200", "#FFFFFF"),  # オレンジ
    "reuters":      ("#FF8200", "#FFFFFF"),
    "ブルームバーグ": ("#2F54EB", "#FFFFFF"),  # 青
    "bloomberg":    ("#2F54EB", "#FFFFFF"),
    "日経":         ("#D32F2F", "#FFFFFF"),  # 赤
    "nikkei":       ("#D32F2F", "#FFFFFF"),
    "株探":         ("#27AE60", "#FFFFFF"),  # 緑
    "kabutan":      ("#27AE60", "#FFFFFF"),
    "かぶたん":     ("#27AE60", "#FFFFFF"),
    "みんかぶ":     ("#F1C40F", "#333333"),  # 黄
    "minkabu":      ("#F1C40F", "#333333"),
    "google":       ("#757575", "#FFFFFF"),  # グレー
    "時事通信":     ("#5B2C6F", "#FFFFFF"),  # 紫暗
    "共同通信":     ("#1A5276", "#FFFFFF"),  # 紺暗
    "fisco":        ("#2ECC71", "#FFFFFF"),  # 明緑
    "フィスコ":     ("#2ECC71", "#FFFFFF"),
    "trader":       ("#3498DB", "#FFFFFF"),  # 水色
}


def get_source_icon(source_name: str) -> str:
    """ソース名からアイコンを取得"""
    for name, info in NEWS_SOURCES.items():
        if name == source_name:
            return info["icon"]
    source_lower = source_name.lower()
    if "moomoo" in source_lower:
        return "🟣"
    if "cnbc" in source_lower:
        return "🔷"
    if "wsj" in source_lower:
        return "📘"
    if "四季報" in source_name or "shikiho" in source_lower:
        return "📙"
    if "東洋経済" in source_name or "toyokeizai" in source_lower:
        return "📕"
    if "ロイター" in source_name or "reuters" in source_lower:
        return "🟠"
    if "ブルームバーグ" in source_name or "bloomberg" in source_lower:
        return "🔵"
    if "日経" in source_name or "nikkei" in source_lower:
        return "🔴"
    if "株探" in source_name or "kabutan" in source_lower:
        return "🟢"
    if "みんかぶ" in source_name or "minkabu" in source_lower:
        return "🟡"
    return "📰"


def get_source_color(source_name: str) -> tuple[str, str]:
    """ソース名から (背景色, 文字色) を返す"""
    name_lower = source_name.lower()
    for key, colors in _SOURCE_COLORS.items():
        if key in source_name or key in name_lower:
            return colors
    return ("#757575", "#FFFFFF")
