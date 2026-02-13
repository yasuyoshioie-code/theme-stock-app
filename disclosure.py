"""適時開示情報をTDnet（東証）から取得するモジュール

取得元: https://www.release.tdnet.info/inbs/I_list_001_{YYYYMMDD}.html
テーブル構造: 時刻 | コード | 企業名 | 表題 | XBRL | 場所 | 更新
"""

import re
import time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
import streamlit as st

JST = timezone(timedelta(hours=9))

TDNET_BASE = "https://www.release.tdnet.info/inbs"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# タイトルからカテゴリを推定するルール（優先順）
_CATEGORY_RULES: list[tuple[str, str]] = [
    (r"決算短信", "決算"),
    (r"四半期報告書", "決算"),
    (r"第[１-４1-4]四半期", "決算"),
    (r"中間期.*決算", "決算"),
    (r"決算補足", "決算"),
    (r"決算説明", "決算"),
    (r"業績予想.*修正", "業績修正"),
    (r"通期.*予想", "業績修正"),
    (r"業績予想.*開示", "業績修正"),
    (r"配当.*修正|配当.*決定|配当.*変更|剰余金の配当|配当予想", "配当"),
    (r"自己株式.*取得|自社株", "自社株"),
    (r"株式分割|株式併合|株式の消却", "株式"),
    (r"新株予約権|ストックオプション", "株式"),
    (r"公開買付|TOB", "TOB"),
    (r"MBO|マネジメント.?バイアウト", "MBO"),
    (r"合併|会社分割|株式交換|株式移転|経営統合", "合併・再編"),
    (r"業務提携|資本提携|資本業務提携|協業", "提携"),
    (r"代表.*異動|役員.*異動|取締役.*選任|人事", "役員"),
    (r"追加訂正|訂正報告", "追加訂正"),
    (r"コーポレート・ガバナンス", "CG報告"),
    (r"支配株主|独立役員", "CG報告"),
    (r"PR情報", "PR"),
]

# 資料区分ごとの色
CATEGORY_COLORS = {
    "決算":     ("#1565C0", "#FFFFFF"),
    "配当":     ("#2E7D32", "#FFFFFF"),
    "業績修正": ("#E65100", "#FFFFFF"),
    "株式":     ("#6A1B9A", "#FFFFFF"),
    "自社株":   ("#6A1B9A", "#FFFFFF"),
    "MBO":      ("#B71C1C", "#FFFFFF"),
    "TOB":      ("#B71C1C", "#FFFFFF"),
    "合併・再編": ("#B71C1C", "#FFFFFF"),
    "提携":     ("#00838F", "#FFFFFF"),
    "役員":     ("#4E342E", "#FFFFFF"),
    "追加訂正": ("#FF8F00", "#FFFFFF"),
    "CG報告":   ("#37474F", "#FFFFFF"),
    "PR":       ("#78909C", "#FFFFFF"),
    "その他":   ("#757575", "#FFFFFF"),
}


def _guess_category(title: str) -> str:
    """タイトルから資料区分を推定"""
    for pattern, category in _CATEGORY_RULES:
        if re.search(pattern, title):
            return category
    return "その他"


@dataclass
class DisclosureItem:
    """適時開示1件"""
    date_str: str        # "2026/02/13"
    time_str: str        # "15:40"
    company: str         # "電通グループ"
    category: str        # "決算"
    title: str           # "2026年3月期 第3四半期決算短信..."
    url: str             # PDF URL
    code: str = ""       # "43240" (証券コード)
    exchange: str = ""   # "東" (取引所)
    published: datetime | None = None

    def age_str(self) -> str:
        if self.published is None:
            return ""
        now = datetime.now(JST)
        diff = now - self.published
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

    @property
    def unique_key(self) -> str:
        """重複チェック用キー"""
        return f"{self.code}|{self.title}|{self.time_str}"


def _parse_time(date_str: str, time_str: str) -> datetime | None:
    """'2026/02/13' + '15:40' → datetime(JST)"""
    try:
        tp = time_str.split(":")
        hour = int(tp[0]) if len(tp) >= 1 else 0
        minute = int(tp[1]) if len(tp) >= 2 else 0

        parts = date_str.replace("-", "/").split("/")
        if len(parts) == 3:
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
        else:
            return None

        return datetime(year, month, day, hour, minute, tzinfo=JST)
    except (ValueError, IndexError):
        return None


def fetch_disclosure(pages: int = 1, target_date: str | None = None) -> list[DisclosureItem]:
    """TDnet 適時開示速報を取得

    Args:
        pages: 取得ページ数 (1ページ = 100件)
        target_date: 対象日 (YYYYMMDD形式)。Noneなら今日

    Returns:
        DisclosureItem のリスト（新しい順）
    """
    if target_date is None:
        target_date = datetime.now(JST).strftime("%Y%m%d")

    # 表示用の日付文字列 "2026/02/13"
    display_date = f"{target_date[:4]}/{target_date[4:6]}/{target_date[6:8]}"

    all_items: list[DisclosureItem] = []

    for page_num in range(1, pages + 1):
        page_str = str(page_num).zfill(3)  # "001", "002", ...
        url = f"{TDNET_BASE}/I_list_{page_str}_{target_date}.html"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 404:
                break  # もうページがない
            resp.raise_for_status()
            resp.encoding = "utf-8"

            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table", id="main-list-table")
            if not table:
                break

            rows = table.find_all("tr")
            if not rows:
                break

            for row in rows:
                time_td = row.find("td", class_="kjTime")
                code_td = row.find("td", class_="kjCode")
                name_td = row.find("td", class_="kjName")
                title_td = row.find("td", class_="kjTitle")
                place_td = row.find("td", class_="kjPlace")

                if not time_td or not title_td:
                    continue

                time_val = time_td.get_text(strip=True)
                code_val = code_td.get_text(strip=True) if code_td else ""
                name_val = name_td.get_text(strip=True) if name_td else ""
                title_val = title_td.get_text(strip=True)
                place_val = place_td.get_text(strip=True) if place_td else ""

                # PDF リンク
                item_url = ""
                a_tag = title_td.find("a", href=True)
                if a_tag:
                    href = a_tag.get("href", "")
                    if href:
                        if href.startswith("http"):
                            item_url = href
                        else:
                            item_url = f"{TDNET_BASE}/{href}"

                # カテゴリ推定
                category = _guess_category(title_val)

                pub_dt = _parse_time(display_date, time_val)

                all_items.append(DisclosureItem(
                    date_str=display_date,
                    time_str=time_val,
                    company=name_val,
                    category=category,
                    title=title_val,
                    url=item_url,
                    code=code_val,
                    exchange=place_val,
                    published=pub_dt,
                ))

        except Exception as e:
            st.warning(f"TDnet ページ{page_num} 取得エラー: {e}")

        if page_num < pages:
            time.sleep(0.3)

    return all_items


def get_category_color(category: str) -> tuple[str, str]:
    """資料区分から (背景色, 文字色) を返す"""
    if category in CATEGORY_COLORS:
        return CATEGORY_COLORS[category]
    # 部分一致でもチェック
    for key, colors in CATEGORY_COLORS.items():
        if key in category:
            return colors
    return ("#757575", "#FFFFFF")


def check_new_disclosures(
    current_items: list[DisclosureItem],
    previous_keys: set[str],
) -> list[DisclosureItem]:
    """前回取得時から新しく追加された開示を検出"""
    if not previous_keys:
        return []
    new_items = []
    for item in current_items:
        if item.unique_key not in previous_keys:
            new_items.append(item)
    return new_items
