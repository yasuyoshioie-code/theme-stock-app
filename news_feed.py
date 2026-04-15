"""株式関連ニュースフィードを複数ソースから取得するモジュール

対応ソース（主要）:
  - moomoo証券 ニュース速報/ヘッドライン: スクレイピング
  - CNBC World: RSS
  - WSJ日本版 / 四季報オンライン / ロイター日本語 / ブルームバーグ日本語 / 日経: Google News経由
  - 東洋経済オンライン: RSS
  - 株探 (Kabutan): Google News経由 + 直接スクレイピング併用
  - みんかぶ: スクレイピング
  - Google News (株式市場): RSS

拡張ソース:
  - 楽天証券 トウシル (Rakuten Toushin): Google News経由
  - マネックス マネクリ: Google News経由
  - フィスコ (Fisco): Google News経由
  - TRADERS WEB: Google News経由
  - Yahoo!ファイナンス (Japan): Google News経由
  - JPX マーケットニュース: Google News経由
  - 四季報オンラインプレミアム: 認証Cookie経由スクレイピング（st.secrets["shikiho_premium_cookie"]）
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
        items = unique[:80]

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
        for entry in feed.entries[:50]:
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

def fetch_google_news_query(query: str, source_label: str, category: str = "株式", max_items: int = 50) -> list[NewsItem]:
    """Google News RSS で特定クエリのニュースを取得"""
    encoded = requests.utils.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=ja&gl=JP&ceid=JP:ja"
    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:max_items]:
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
    """株探（Google News + 直接スクレイピング併用）"""
    items = []

    # 1) Google News 経由
    gn_items = fetch_google_news_query(
        "site:kabutan.jp",
        source_label="株探",
        category="株式",
    )
    items.extend(gn_items)

    # 2) 直接スクレイピング（table.s_news_list から最新ニュース）
    for page in range(1, 4):  # 3ページ = 約30件
        try:
            url = f"https://kabutan.jp/news/marketnews/?b=n&page={page}"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            table = soup.select_one("table.s_news_list")
            if not table:
                break

            for row in table.find_all("tr"):
                tds = row.find_all("td")
                if len(tds) < 3:
                    continue

                time_text = tds[0].get_text(strip=True)  # "02/12 13:18"
                cat_text = tds[1].get_text(strip=True)    # "材料"
                title_td = tds[2]
                title = title_td.get_text(strip=True)
                link = title_td.find("a", href=True)

                item_url = ""
                if link:
                    href = link.get("href", "")
                    item_url = "https://kabutan.jp" + href if not href.startswith("http") else href

                # 日時パース: "02/12 13:18" → datetime
                pub_dt = None
                tm = re.match(r"(\d{2})/(\d{2})\s+(\d{1,2}):(\d{2})", time_text)
                if tm:
                    try:
                        now = datetime.now(JST)
                        mon, day = int(tm.group(1)), int(tm.group(2))
                        hour, minute = int(tm.group(3)), int(tm.group(4))
                        year = now.year
                        pub_dt = datetime(year, mon, day, hour, minute, tzinfo=JST)
                        if pub_dt > now:
                            pub_dt = pub_dt.replace(year=year - 1)
                    except ValueError:
                        pass

                items.append(NewsItem(
                    title=title,
                    url=item_url,
                    source="株探",
                    published=pub_dt,
                    category=cat_text or "株式",
                ))

        except Exception:
            break

        if page < 3:
            time.sleep(0.3)

    # 重複除去
    seen = set()
    unique = []
    for item in items:
        key = re.sub(r"\s+", "", item.title)
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


# ----------------------------------------------------------------
# 東洋経済 RSS
# ----------------------------------------------------------------

def fetch_toyokeizai() -> list[NewsItem]:
    """東洋経済オンライン RSS"""
    url = "https://toyokeizai.net/list/feed/rss"
    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:50]:
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

        # /news/数字 のパターンで正確にニュース記事リンクを取得
        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "")
            if not re.match(r"^/news/\d+$", href):
                continue

            title = a_tag.get_text(strip=True)
            if not title or len(title) < 8:
                continue
            # 「続きを読む」等のリンクテキストはスキップ
            if title in ("続きを読む", "もっと見る", "一覧を見る"):
                continue

            full_url = "https://minkabu.jp" + href

            # 近くの time タグから日時取得
            parent = a_tag.parent
            time_tag = None
            if parent:
                time_tag = parent.find("time")
            if not time_tag:
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
                url=full_url,
                source="みんかぶ",
                published=pub_dt,
                category="株式",
            ))

        # 重複除去（同一タイトルの「続きを読む」リンクなど）
        seen = set()
        unique = []
        for item in items:
            key = re.sub(r"\s+", "", item.title)
            if key not in seen:
                seen.add(key)
                unique.append(item)
        items = unique[:50]

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
        max_items=50,
    )


# ----------------------------------------------------------------
# 追加ソース（高PVメディア）
# ----------------------------------------------------------------

def fetch_rakuten_toushin() -> list[NewsItem]:
    """楽天証券 トウシル（個人投資家向け人気メディア）"""
    return fetch_google_news_query(
        "site:media.rakuten-sec.net OR site:toushil.rakuten-sec.co.jp",
        source_label="トウシル",
        category="投資情報",
    )


def fetch_monex_manekuri() -> list[NewsItem]:
    """マネックス証券 マネクリ（マネクリニュース・投資戦略レポート）"""
    return fetch_google_news_query(
        "site:media.monex.co.jp OR site:info.monex.co.jp",
        source_label="マネクリ",
        category="投資情報",
    )


def fetch_fisco() -> list[NewsItem]:
    """フィスコ（Fisco）マーケット・個別銘柄レポート"""
    items = fetch_google_news_query(
        "site:fisco.jp OR site:web.fisco.jp",
        source_label="フィスコ",
        category="市場レポート",
    )
    # Fiscoの一般記事（fisco.jp/news/ 直下）も補完
    if len(items) < 10:
        extra = fetch_google_news_query(
            "フィスコ 株 OR 市場 OR 決算",
            source_label="フィスコ",
            category="市場レポート",
            max_items=30,
        )
        items.extend(extra)
    return items


def fetch_traders_web() -> list[NewsItem]:
    """TRADERS WEB（個別銘柄・為替・商品全般）"""
    return fetch_google_news_query(
        "site:traders.co.jp",
        source_label="TRADERS WEB",
        category="マーケット",
    )


def fetch_yahoo_finance_jp() -> list[NewsItem]:
    """Yahoo!ファイナンス（Japan）"""
    return fetch_google_news_query(
        "site:finance.yahoo.co.jp",
        source_label="Yahoo!ファイナンス",
        category="株式",
    )


def fetch_jpx_news() -> list[NewsItem]:
    """日本取引所グループ（JPX）公式ニュース"""
    return fetch_google_news_query(
        "site:jpx.co.jp",
        source_label="JPX",
        category="公式",
    )


def fetch_shikiho_premium() -> list[NewsItem]:
    """四季報オンライン プレミアム（要ログインCookie）

    利用方法:
        Streamlit secrets.toml に以下を追加:
            shikiho_premium_cookie = "<ブラウザで取得した Cookie ヘッダ全文>"

        取得手順:
            1. ブラウザで shikiho.toyokeizai.net にログイン
            2. DevTools > Network > 任意のリクエスト > Request Headers > `cookie:` の値をコピー
            3. .streamlit/secrets.toml に上記のキーで保存

    Cookie が未設定の場合は空リストを返す（Google News 経由の無料版はすでに fetch_shikiho で取得済み）。
    """
    cookie = ""
    try:
        cookie = st.secrets.get("shikiho_premium_cookie", "") or ""
    except Exception:
        cookie = ""

    if not cookie:
        return []

    items: list[NewsItem] = []
    # プレミアム限定のニュース/コラム一覧ページ（構造はサイト側都合で変わるため失敗許容）
    candidate_urls = [
        "https://shikiho.toyokeizai.net/news",
        "https://shikiho.toyokeizai.net/news/list",
        "https://shikiho.toyokeizai.net/news/premium",
    ]
    headers = dict(HEADERS)
    headers["Cookie"] = cookie

    for url in candidate_urls:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                href = a_tag.get("href", "")
                # プレミアム記事の /news/{id} 形式を拾う
                if not re.search(r"/news/\d+", href):
                    continue
                title = a_tag.get_text(strip=True)
                if not title or len(title) < 10:
                    continue
                if not href.startswith("http"):
                    href = "https://shikiho.toyokeizai.net" + href
                items.append(NewsItem(
                    title=title,
                    url=href,
                    source="四季報プレミアム",
                    published=None,
                    category="プレミアム",
                ))
            if items:
                break
        except Exception:
            continue

    # 重複除去
    seen = set()
    unique = []
    for it in items:
        key = re.sub(r"\s+", "", it.title)
        if key and key not in seen:
            seen.add(key)
            unique.append(it)
    return unique[:60]


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
    # --- 拡張ソース ---
    "楽天証券 トウシル": {
        "func": fetch_rakuten_toushin,
        "icon": "🔺",
        "default": True,
    },
    "マネックス マネクリ": {
        "func": fetch_monex_manekuri,
        "icon": "🟦",
        "default": True,
    },
    "フィスコ": {
        "func": fetch_fisco,
        "icon": "🟩",
        "default": True,
    },
    "TRADERS WEB": {
        "func": fetch_traders_web,
        "icon": "🟨",
        "default": True,
    },
    "Yahoo!ファイナンス": {
        "func": fetch_yahoo_finance_jp,
        "icon": "🟪",
        "default": True,
    },
    "JPX": {
        "func": fetch_jpx_news,
        "icon": "🏛",
        "default": False,
    },
    "四季報プレミアム": {
        "func": fetch_shikiho_premium,
        "icon": "💎",
        "default": False,  # Cookie必須。st.secrets["shikiho_premium_cookie"] 設定時のみ有効
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


# ソース別カラー定義 (badge背景色, badge文字色) — みんかぶ風
_SOURCE_COLORS = {
    "moomoo":       ("#6A1B9A", "#FFFFFF"),  # 紫
    "cnbc":         ("#014099", "#FFFFFF"),  # ネイビー
    "wsj":          ("#1565C0", "#FFFFFF"),  # 青
    "四季報プレミアム": ("#B71C1C", "#FFFFFF"),  # 深紅（プレミアム）
    "四季報":       ("#D84315", "#FFFFFF"),  # オレンジ
    "東洋経済":     ("#C62828", "#FFFFFF"),  # 赤
    "ロイター":     ("#EF6C00", "#FFFFFF"),  # オレンジ
    "reuters":      ("#EF6C00", "#FFFFFF"),
    "ブルームバーグ": ("#1565C0", "#FFFFFF"),  # 青
    "bloomberg":    ("#1565C0", "#FFFFFF"),
    "日経":         ("#C62828", "#FFFFFF"),  # 赤
    "nikkei":       ("#C62828", "#FFFFFF"),
    "株探":         ("#1B8A50", "#FFFFFF"),  # 緑
    "kabutan":      ("#1B8A50", "#FFFFFF"),
    "かぶたん":     ("#1B8A50", "#FFFFFF"),
    "みんかぶ":     ("#EF6C00", "#FFFFFF"),  # オレンジ
    "minkabu":      ("#EF6C00", "#FFFFFF"),
    "google":       ("#616161", "#FFFFFF"),  # グレー
    "時事通信":     ("#4A148C", "#FFFFFF"),  # 紫暗
    "共同通信":     ("#0D47A1", "#FFFFFF"),  # 紺暗
    "fisco":        ("#1B8A50", "#FFFFFF"),  # 緑
    "フィスコ":     ("#1B8A50", "#FFFFFF"),
    "trader":       ("#0277BD", "#FFFFFF"),  # 水色
    "traders":      ("#0277BD", "#FFFFFF"),
    "トウシル":     ("#BF0000", "#FFFFFF"),  # 楽天カラー
    "rakuten":      ("#BF0000", "#FFFFFF"),
    "マネクリ":     ("#0097A7", "#FFFFFF"),  # マネックスカラー
    "monex":        ("#0097A7", "#FFFFFF"),
    "yahoo":        ("#6001D2", "#FFFFFF"),  # Yahoo紫
    "ファイナンス": ("#6001D2", "#FFFFFF"),
    "jpx":          ("#0D47A1", "#FFFFFF"),  # 紺
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
    if "トウシル" in source_name or "rakuten" in source_lower:
        return "🔺"
    if "マネクリ" in source_name or "monex" in source_lower:
        return "🟦"
    if "フィスコ" in source_name or "fisco" in source_lower:
        return "🟩"
    if "trader" in source_lower:
        return "🟨"
    if "yahoo" in source_lower or "ファイナンス" in source_name:
        return "🟪"
    if "jpx" in source_lower:
        return "🏛"
    if "プレミアム" in source_name:
        return "💎"
    return "📰"


def get_source_color(source_name: str) -> tuple[str, str]:
    """ソース名から (背景色, 文字色) を返す"""
    name_lower = source_name.lower()
    for key, colors in _SOURCE_COLORS.items():
        if key in source_name or key in name_lower:
            return colors
    return ("#757575", "#FFFFFF")
