"""テーマ別騰落率計算エンジン

売買代金ランキング（300銘柄）の前日比と、各テーマへのマッピングから
テーマ別騰落率を算出する。stock-themes.com と同等の「テーマ騰落率 = 構成銘柄の単純平均」方式。

加えて、ツリーマップ用のデータも生成する。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from market_ranking import fetch_ranking_via_read_html


# ------------------------------------------------------------------
# ランキングデータ取得（値上がり率 + 値下がり率 + 売買代金）
# ------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner=False)
def fetch_all_ranking_data() -> pd.DataFrame:
    """全市場の売買代金 + 値上がり + 値下がりランキングを統合し、
    ユニークな銘柄リスト（コード/名称/市場/前日比%/売買代金）を返す。

    10分キャッシュ。
    """
    frames = []

    # 売買代金: 全市場200件 + STD/GRT各100件
    for mkey in ("all", "tokyo2", "tokyog"):
        pages = 4 if mkey == "all" else 2
        df = fetch_ranking_via_read_html("売買代金上位", market=mkey, pages=pages)
        if not df.empty:
            frames.append(df)

    # 値上がり率: 各市場100件
    for mkey in ("all", "tokyo2", "tokyog"):
        df = fetch_ranking_via_read_html("値上がり率", market=mkey, pages=2)
        if not df.empty:
            frames.append(df)

    # 値下がり率: 各市場100件
    for mkey in ("all", "tokyo2", "tokyog"):
        df = fetch_ranking_via_read_html("値下がり率", market=mkey, pages=2)
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    # 必須列確保
    for col in ("売買代金", "前日比率(%)", "市場"):
        if col not in combined.columns:
            combined[col] = 0.0 if col != "市場" else ""

    # 重複排除: 同一コードは売買代金最大のレコードを残す
    combined["売買代金"] = pd.to_numeric(combined["売買代金"], errors="coerce").fillna(0)
    combined["前日比率(%)"] = pd.to_numeric(combined["前日比率(%)"], errors="coerce").fillna(0)
    combined = combined.sort_values("売買代金", ascending=False)
    combined = combined.drop_duplicates(subset=["コード"], keep="first").reset_index(drop=True)

    return combined


# ------------------------------------------------------------------
# テーマ別騰落率の計算
# ------------------------------------------------------------------

def compute_theme_performance(
    ranking_df: pd.DataFrame,
    ticker_to_themes: dict[str, list[str]],
) -> pd.DataFrame:
    """テーマ別騰落率を計算（構成銘柄の前日比%の単純平均）

    Returns:
        columns: [テーマ, 騰落率(%), 銘柄数, 上昇, 下落, 売買代金(億円), 代表銘柄]
        sorted by 騰落率 desc
    """
    theme_data: dict[str, dict] = {}

    for _, row in ranking_df.iterrows():
        code = str(row["コード"]).strip()
        themes = ticker_to_themes.get(code, [])
        chg = float(row.get("前日比率(%)", 0) or 0)
        tv = float(row.get("売買代金", 0) or 0)
        name = str(row.get("名称", ""))
        n_themes = len(ticker_to_themes.get(code, []))

        for th in themes:
            if th not in theme_data:
                theme_data[th] = {
                    "changes": [],
                    "tv_sum": 0.0,
                    "up": 0,
                    "down": 0,
                    "best_rep": ("", 999, 0.0),  # (name, n_themes, tv)
                }
            d = theme_data[th]
            d["changes"].append(chg)
            d["tv_sum"] += tv
            if chg > 0:
                d["up"] += 1
            elif chg < 0:
                d["down"] += 1
            # 代表銘柄: 所属テーマ数が少ない方を優先
            cur = d["best_rep"]
            if n_themes < cur[1] or (n_themes == cur[1] and tv > cur[2]):
                d["best_rep"] = (name, n_themes, tv)

    rows = []
    for th, d in theme_data.items():
        n = len(d["changes"])
        avg_chg = sum(d["changes"]) / n if n > 0 else 0.0
        rows.append({
            "テーマ": th,
            "騰落率(%)": round(avg_chg, 2),
            "銘柄数": n,
            "上昇": d["up"],
            "下落": d["down"],
            "売買代金(億円)": int(d["tv_sum"] / 1e8),
            "代表銘柄": d["best_rep"][0],
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("騰落率(%)", ascending=False).reset_index(drop=True)
    return df


# ------------------------------------------------------------------
# ツリーマップ用データ
# ------------------------------------------------------------------

def build_treemap_data(
    theme_perf: pd.DataFrame,
    top_n: int = 80,
) -> pd.DataFrame:
    """ツリーマップ用のデータを構築

    Returns:
        columns: [テーマ, 騰落率(%), 銘柄数, 売買代金(億円), カテゴリ, 色]
    """
    if theme_perf.empty:
        return pd.DataFrame()

    # 売買代金上位N テーマに絞る（多すぎると見づらい）
    df = theme_perf.nlargest(top_n, "売買代金(億円)").copy()

    # カテゴリ分類（騰落率レンジ）
    def _categorize(chg: float) -> str:
        if chg >= 3.0:
            return "急騰 (+3%↑)"
        elif chg >= 1.0:
            return "上昇 (+1〜3%)"
        elif chg >= 0:
            return "小幅高 (0〜1%)"
        elif chg >= -1.0:
            return "小幅安 (0〜-1%)"
        elif chg >= -3.0:
            return "下落 (-1〜-3%)"
        else:
            return "急落 (-3%↓)"

    df["カテゴリ"] = df["騰落率(%)"].apply(_categorize)
    return df


def get_theme_detail(
    theme_name: str,
    ranking_df: pd.DataFrame,
    ticker_to_themes: dict[str, list[str]],
) -> pd.DataFrame:
    """特定テーマの構成銘柄詳細を返す

    Returns:
        columns: [コード, 銘柄名, 市場, 取引値, 前日比(%), 売買代金(億円)]
    """
    # そのテーマに属するコードを取得
    theme_codes = set()
    for code, themes in ticker_to_themes.items():
        if theme_name in themes:
            theme_codes.add(code)

    if not theme_codes or ranking_df.empty:
        return pd.DataFrame()

    # ランキング内で該当するもの
    matched = ranking_df[ranking_df["コード"].astype(str).isin(theme_codes)].copy()
    if matched.empty:
        return pd.DataFrame()

    result = pd.DataFrame({
        "コード": matched["コード"],
        "銘柄名": matched["名称"],
        "市場": matched["市場"],
        "取引値": matched["取引値"],
        "前日比(%)": matched["前日比率(%)"].round(2),
        "売買代金(億円)": (matched["売買代金"] / 1e8).round(0).astype(int),
    })
    result = result.sort_values("売買代金(億円)", ascending=False).reset_index(drop=True)
    return result
