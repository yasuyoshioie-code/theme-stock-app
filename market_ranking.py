"""Yahoo Finance Japan からランキングデータを取得するモジュール

__PRELOADED_STATE__ JSON から構造化データを直接取得する方式。
"""

import json
import re
import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup

# ----------------------------------------------------------------
# ランキング定義
# ----------------------------------------------------------------

RANKING_TYPES = {
    # --- 値動き系 ---
    "値上がり率": {"key": "up", "category": "値動き"},
    "値下がり率": {"key": "down", "category": "値動き"},
    "ストップ高": {"key": "stopHigh", "category": "値動き"},
    "ストップ安": {"key": "stopLow", "category": "値動き"},
    "年初来高値": {"key": "yearToDateHigh", "category": "値動き"},
    "年初来安値": {"key": "yearToDateLow", "category": "値動き"},
    # --- 出来高・売買代金 ---
    "出来高": {"key": "volume", "category": "出来高・売買代金"},
    "出来高増加率": {"key": "volumeIncrease", "category": "出来高・売買代金"},
    "売買代金上位": {"key": "tradingValueHigh", "category": "出来高・売買代金"},
    # --- バリュエーション ---
    "高PER": {"key": "highPer", "category": "バリュエーション"},
    "低PER": {"key": "lowPer", "category": "バリュエーション"},
    "高PBR": {"key": "highPbr", "category": "バリュエーション"},
    "低PBR": {"key": "lowPbr", "category": "バリュエーション"},
    "配当利回り": {"key": "dividendYield", "category": "バリュエーション"},
    # --- 時価総額 ---
    "時価総額上位": {"key": "marketCapitalHigh", "category": "時価総額"},
    "時価総額下位": {"key": "marketCapitalLow", "category": "時価総額"},
    # --- 信用取引 ---
    "信用買残増加": {"key": "creditBuybackIncrease", "category": "信用取引"},
    "信用買残減少": {"key": "creditBuybackDecrease", "category": "信用取引"},
    "信用売残増加": {"key": "creditShortfallIncrease", "category": "信用取引"},
    "信用売残減少": {"key": "creditShortfallDecrease", "category": "信用取引"},
    "信用倍率上位": {"key": "creditRatioHigh", "category": "信用取引"},
    "信用倍率下位": {"key": "creditRatioLow", "category": "信用取引"},
}

MARKET_OPTIONS = {
    "全市場": "all",
    "プライム": "tokyo1",
    "スタンダード": "tokyo2",
    "グロース": "tokyog",
}

TERM_OPTIONS = {
    "デイリー": "daily",
    "週間": "weekly",
    "月間": "monthly",
}

CATEGORY_ORDER = ["値動き", "出来高・売買代金", "バリュエーション", "時価総額", "信用取引"]


# ----------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------

BASE_URL = "https://finance.yahoo.co.jp/stocks/ranking/{ranking_key}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


def _clean_num(text: str) -> float:
    """カンマ付き数値文字列をfloatに変換"""
    if not text:
        return 0.0
    text = str(text).replace(",", "").replace("株", "").replace("円", "").replace("倍", "").replace("%", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


# ----------------------------------------------------------------
# メイン取得関数（JSON方式）
# ----------------------------------------------------------------

def _extract_preloaded_state(html: str) -> dict | None:
    """HTML から __PRELOADED_STATE__ JSON を抽出する（ブレースバランス方式）"""
    idx = html.find("__PRELOADED_STATE__")
    if idx < 0:
        return None

    start = html.find("{", idx)
    if start < 0:
        return None

    # ブレースのバランスで終了位置を見つける
    depth = 0
    end = start
    for j in range(start, min(start + 200000, len(html))):
        if html[j] == "{":
            depth += 1
        elif html[j] == "}":
            depth -= 1
            if depth == 0:
                end = j + 1
                break

    if depth != 0:
        return None

    json_str = html[start:end]
    json_str = json_str.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def _parse_ranking_item(item: dict) -> dict:
    """JSON の1アイテムをパースする"""
    code = item.get("stockCode", "")
    name = item.get("stockName", "")
    # (株) を除去してスッキリさせる
    name = name.replace("（株）", "").replace("(株)", "").strip()
    market = item.get("marketName", "")
    price = item.get("savePrice", "")
    rank = item.get("rank", "")
    date = item.get("date", "")

    row = {
        "順位": int(rank) if rank else 0,
        "コード": code,
        "名称": name,
        "市場": market,
        "取引値": _clean_num(price),
        "日付": date,
    }

    # rankingResult から非nullデータを取り出す
    rr = item.get("rankingResult", {}) or {}

    # 値上がり / 値下がり率
    cpr = rr.get("changePriceRate")
    if cpr:
        row["前日比"] = cpr.get("changePrice", "")
        row["前日比率(%)"] = _clean_num(cpr.get("changePriceRate", "0"))
        row["出来高"] = _clean_num(cpr.get("volume", "0"))

    # ストップ高/安
    sp = rr.get("stopPrice")
    if sp:
        row["前日比"] = sp.get("changePrice", "")
        row["前日比率(%)"] = _clean_num(sp.get("changePriceRate", "0"))
        row["高値/安値"] = sp.get("highPrice", sp.get("lowPrice", ""))

    # 年初来高値/安値
    yp = rr.get("yearPrice")
    if yp:
        row["前日比"] = yp.get("changePrice", "")
        row["前日比率(%)"] = _clean_num(yp.get("changePriceRate", "0"))
        row["高値/安値"] = yp.get("highPrice", yp.get("lowPrice", ""))

    # 出来高
    vol = rr.get("volume")
    if vol:
        row["前日比"] = vol.get("changePrice", "")
        row["前日比率(%)"] = _clean_num(vol.get("changePriceRate", "0"))
        row["出来高"] = _clean_num(vol.get("volume", "0"))

    # 出来高増加率 / 減少率
    pvr = rr.get("previousVolumeRate")
    if pvr:
        row["前日比"] = pvr.get("changePrice", "")
        row["前日比率(%)"] = _clean_num(pvr.get("changePriceRate", "0"))
        row["出来高増加率(%)"] = _clean_num(pvr.get("previousVolumeRate", "0"))

    # 売買代金
    tv = rr.get("tradingValue")
    if tv:
        row["前日比"] = tv.get("changePrice", "")
        row["前日比率(%)"] = _clean_num(tv.get("changePriceRate", "0"))
        row["売買代金"] = _clean_num(tv.get("tradingValue", "0"))

    # 時価総額
    tpo = rr.get("totalPriceObj")
    if tpo:
        row["前日比"] = tpo.get("changePrice", "")
        row["前日比率(%)"] = _clean_num(tpo.get("changePriceRate", "0"))
        row["時価総額"] = tpo.get("totalPrice", "")

    # 配当利回り
    sdy = rr.get("shareDividendYield")
    if sdy:
        row["前日比"] = sdy.get("changePrice", "")
        row["前日比率(%)"] = _clean_num(sdy.get("changePriceRate", "0"))
        row["配当利回り(%)"] = _clean_num(sdy.get("shareDividendYield", "0"))

    # PER
    per = rr.get("per")
    if per:
        row["前日比"] = per.get("changePrice", "")
        row["前日比率(%)"] = _clean_num(per.get("changePriceRate", "0"))
        row["PER"] = _clean_num(per.get("per", "0"))

    # PBR
    pbr = rr.get("pbr")
    if pbr:
        row["前日比"] = pbr.get("changePrice", "")
        row["前日比率(%)"] = _clean_num(pbr.get("changePriceRate", "0"))
        row["PBR"] = _clean_num(pbr.get("pbr", "0"))

    # 信用買残
    mtb = rr.get("marginTransactionBuy")
    if mtb:
        row["前日比"] = mtb.get("changePrice", "")
        row["前日比率(%)"] = _clean_num(mtb.get("changePriceRate", "0"))
        row["信用買残"] = _clean_num(mtb.get("marginTransactionBuy", "0"))

    # 信用売残
    mts = rr.get("marginTransactionSell")
    if mts:
        row["前日比"] = mts.get("changePrice", "")
        row["前日比率(%)"] = _clean_num(mts.get("changePriceRate", "0"))
        row["信用売残"] = _clean_num(mts.get("marginTransactionSell", "0"))

    # 信用倍率
    mcm = rr.get("marginCreditMagnification")
    if mcm:
        row["前日比"] = mcm.get("changePrice", "")
        row["前日比率(%)"] = _clean_num(mcm.get("changePriceRate", "0"))
        row["信用倍率"] = _clean_num(mcm.get("marginCreditMagnification", "0"))

    # 掲示板投稿数
    bbs = rr.get("bbsContents")
    if bbs:
        row["投稿数"] = _clean_num(bbs.get("bbsCount", "0"))

    return row


def fetch_ranking_via_read_html(
    ranking_name: str,
    market: str = "all",
    term: str = "daily",
    pages: int = 1,
) -> pd.DataFrame:
    """Yahoo Finance Japan からランキングデータを取得する（JSON方式）"""
    if ranking_name not in RANKING_TYPES:
        return pd.DataFrame()

    ranking_info = RANKING_TYPES[ranking_name]
    ranking_key = ranking_info["key"]

    all_rows = []

    for page in range(1, pages + 1):
        url = BASE_URL.format(ranking_key=ranking_key)
        params = {"market": market, "term": term}
        if page > 1:
            params["page"] = page

        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            st.warning(f"ランキング取得エラー ({ranking_name}, page {page}): {e}")
            break

        state = _extract_preloaded_state(resp.text)
        if not state:
            st.warning(f"{ranking_name}: JSONデータの抽出に失敗しました (page {page})")
            break

        results = state.get("mainRankingList", {}).get("results", [])
        if not results:
            break

        for item in results:
            row = _parse_ranking_item(item)
            if row.get("コード"):
                all_rows.append(row)

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates(subset=["コード"], keep="first")

    # 不要カラムを除去（全部NaN/空のカラム）
    for col in df.columns:
        if df[col].isna().all() or (df[col] == 0).all() or (df[col] == "").all():
            if col not in ("順位", "コード", "名称", "市場", "取引値", "前日比", "前日比率(%)"):
                df = df.drop(columns=[col])

    return df.reset_index(drop=True)


# ----------------------------------------------------------------
# 高レベルAPI（Streamlit用）
# ----------------------------------------------------------------

def get_ranking_categories() -> dict[str, list[str]]:
    """カテゴリ → ランキング名リストの辞書を返す"""
    categories = {}
    for name, info in RANKING_TYPES.items():
        cat = info["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(name)
    return categories


def fetch_multiple_rankings(
    ranking_names: list[str],
    market: str = "all",
    term: str = "daily",
    pages: int = 1,
    progress_callback=None,
) -> dict[str, pd.DataFrame]:
    """複数のランキングを一括取得する"""
    results = {}
    total = len(ranking_names)

    for i, name in enumerate(ranking_names):
        if progress_callback:
            progress_callback(i / total, f"{name} を取得中...")

        df = fetch_ranking_via_read_html(
            ranking_name=name,
            market=market,
            term=term,
            pages=pages,
        )
        results[name] = df

    if progress_callback:
        progress_callback(1.0, "完了")

    return results
