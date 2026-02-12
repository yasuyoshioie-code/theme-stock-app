"""適時開示情報を日経電子版から取得するモジュール

取得元: https://www.nikkei.com/markets/kigyo/disclose/
テーブル構造: 発表日 | 時刻 | 企業名 | 資料区分 | 表題
"""

import re
import time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
import streamlit as st

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# 資料区分ごとの色
CATEGORY_COLORS = {
    "決算":     ("#1565C0", "#FFFFFF"),  # 青
    "配当":     ("#2E7D32", "#FFFFFF"),  # 緑
    "業績":     ("#E65100", "#FFFFFF"),  # オレンジ
    "株式":     ("#6A1B9A", "#FFFFFF"),  # 紫
    "自社株":   ("#6A1B9A", "#FFFFFF"),  # 紫
    "MBO":      ("#B71C1C", "#FFFFFF"),  # 赤
    "TOB":      ("#B71C1C", "#FFFFFF"),  # 赤
    "合併":     ("#B71C1C", "#FFFFFF"),  # 赤
    "提携":     ("#00838F", "#FFFFFF"),  # シアン
    "役員":     ("#4E342E", "#FFFFFF"),  # 茶
    "その他":   ("#757575", "#FFFFFF"),  # グレー
    "追加訂正": ("#FF8F00", "#FFFFFF"),  # 琥珀
}


@dataclass
class DisclosureItem:
    """適時開示1件"""
    date_str: str        # "26/2/12"
    time_str: str        # "13:00"
    company: str         # "新日本空調"
    category: str        # "決算 ３Ｑ"
    title: str           # "2026年3月期 第3四半期決算短信 ..."
    url: str             # PDF/リダイレクトURL
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
        return f"{self.company}|{self.title}|{self.time_str}"


def _parse_datetime(date_str: str, time_str: str) -> datetime | None:
    """'26/2/12' + '13:00' → datetime(JST)"""
    try:
        # 年が2桁の場合
        parts = date_str.split("/")
        if len(parts) == 3:
            y, m, d = parts
            year = int(y)
            if year < 100:
                year += 2000
            month = int(m)
            day = int(d)
        else:
            return None

        # 時刻
        tp = time_str.split(":")
        hour = int(tp[0]) if len(tp) >= 1 else 0
        minute = int(tp[1]) if len(tp) >= 2 else 0

        return datetime(year, month, day, hour, minute, tzinfo=JST)
    except (ValueError, IndexError):
        return None


def fetch_disclosure(pages: int = 1) -> list[DisclosureItem]:
    """日経 適時開示速報を取得

    Args:
        pages: 取得ページ数 (1ページ = 約50件)

    Returns:
        DisclosureItem のリスト（新しい順）
    """
    all_items: list[DisclosureItem] = []

    for page in range(1, pages + 1):
        url = f"https://www.nikkei.com/markets/kigyo/disclose/?PageIndex={page}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            table = soup.find("table", class_="cmn-table_style2")
            if not table:
                continue

            rows = table.find_all("tr")
            for row in rows:
                # 発表日は <th>、残り4列 (時刻,企業名,資料区分,表題) は <td>
                th = row.find("th")
                tds = row.find_all("td")
                if th is None or len(tds) < 4:
                    continue

                date_str = th.get_text(strip=True)             # "26/2/12"
                time_str = tds[0].get_text(strip=True)         # "13:00"
                company = tds[1].get_text(strip=True)          # "新日本空調"
                category = tds[2].get_text(strip=True)         # "決算 ３Ｑ"
                title_cell = tds[3]
                title = title_cell.get_text(strip=True)

                # リンク取得
                link = title_cell.find("a", href=True)
                item_url = ""
                if link:
                    item_url = link.get("href", "")
                    if item_url and not item_url.startswith("http"):
                        item_url = "https://www.nikkei.com" + item_url

                pub_dt = _parse_datetime(date_str, time_str)

                all_items.append(DisclosureItem(
                    date_str=date_str,
                    time_str=time_str,
                    company=company,
                    category=category,
                    title=title,
                    url=item_url,
                    published=pub_dt,
                ))

        except Exception as e:
            st.warning(f"適時開示 ページ{page} 取得エラー: {e}")

        if page < pages:
            time.sleep(0.5)

    return all_items


def get_category_color(category: str) -> tuple[str, str]:
    """資料区分から (背景色, 文字色) を返す"""
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
