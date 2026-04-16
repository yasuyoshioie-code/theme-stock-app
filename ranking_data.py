"""売買代金ランキングベースのセクター資金フロー分析モジュール

Yahoo Finance Japan の売買代金ランキング (Top100 × 3市場) を取得し、
1,578テーマへマッピングして「どのセクターに資金が流れているか」を追跡する。

データフロー:
    売買代金ランキング取得 (2-3秒)
    → テーマ逆引きマッピング
    → セクター別集計 (売買代金合計/銘柄数/平均変化率)
    → 日次スナップショット蓄積 (Parquet)
    → トレンド分析 (過去N日の資金フロー推移)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from market_ranking import fetch_ranking_via_read_html

JST = timezone(timedelta(hours=9))
_APP_DIR = Path(os.path.dirname(__file__))
SNAPSHOT_DIR = _APP_DIR / "data" / "daily"

MARKETS = {
    "プライム": "tokyo1",
    "スタンダード": "tokyo2",
    "グロース": "tokyog",
}


# ------------------------------------------------------------------
# 1. 売買代金ランキング取得
# ------------------------------------------------------------------

# 市場コード → 表示名マッピング
_MARKET_LABEL_MAP = {
    "東証PRM": "プライム",
    "東証STD": "スタンダード",
    "東証GRT": "グロース",
    "東証ETF": "ETF",
}


@st.cache_data(ttl=600, show_spinner=False)
def fetch_trading_value_ranking() -> pd.DataFrame:
    """売買代金ランキングを取得し、「市場」列で正確に分類（10分キャッシュ）

    Yahoo Finance Japan は市場パラメータを指定しても他市場銘柄が混入するため、
    全市場200件 + スタンダード100件 + グロース100件 を取得して
    「市場」列（東証PRM/STD/GRT/ETF）で正しく分類・重複排除する。

    Returns:
        columns: [順位, コード, 名称, 市場, 取引値, 前日比率(%), 売買代金, market_label]
    """
    frames = []

    # 全市場から200件（プライム上位が大半を占める）
    df_all = fetch_ranking_via_read_html("売買代金上位", market="all", pages=4)
    if not df_all.empty:
        frames.append(df_all)

    # スタンダード・グロースは個別に100件取得（全市場ランキングに入らない銘柄を補完）
    for mkey in ("tokyo2", "tokyog"):
        df_sub = fetch_ranking_via_read_html("売買代金上位", market=mkey, pages=2)
        if not df_sub.empty:
            frames.append(df_sub)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    # 必須列の確保
    for col in ("売買代金", "前日比率(%)", "市場"):
        if col not in combined.columns:
            combined[col] = 0.0 if col != "市場" else ""

    # 「市場」列で正確に market_label を設定
    combined["market_label"] = combined["市場"].map(_MARKET_LABEL_MAP).fillna("その他")

    # 重複排除（同じ銘柄コードは売買代金が大きい方を残す）
    combined = combined.sort_values("売買代金", ascending=False)
    combined = combined.drop_duplicates(subset=["コード"], keep="first")

    # 市場ごとに順位を振り直し
    combined = combined.sort_values("売買代金", ascending=False).reset_index(drop=True)
    combined["順位"] = combined.index + 1

    return combined


# ------------------------------------------------------------------
# 2. テーママッピング
# ------------------------------------------------------------------

def build_ticker_to_themes(sectors: dict[str, pd.DataFrame]) -> dict[str, list[str]]:
    """証券コード → テーマ名リスト の逆引き辞書を構築"""
    t2t: dict[str, list[str]] = {}
    for theme, sdf in sectors.items():
        for code in sdf["証券コード"].tolist():
            t2t.setdefault(code, []).append(theme)
    return t2t


def map_ranking_to_themes(
    ranking_df: pd.DataFrame,
    ticker_to_themes: dict[str, list[str]],
) -> pd.DataFrame:
    """ランキング → テーマ別売買代金集計

    代表銘柄はテーマ固有度（= 売買代金 / 所属テーマ数）が最大の銘柄を選ぶ。
    これにより、多数のテーマに属する超大型株（キオクシア等）ではなく
    そのテーマに特化した銘柄が代表として表示される。

    Returns:
        columns: [テーマ, 売買代金合計, 銘柄数, 平均変化率(%), 代表銘柄]
        sorted by 売買代金合計 desc
    """
    # 各銘柄のテーマ所属数を事前計算
    _theme_count: dict[str, int] = {
        code: len(themes) for code, themes in ticker_to_themes.items()
    }

    theme_stats: dict[str, dict] = {}

    for _, row in ranking_df.iterrows():
        code = str(row["コード"]).strip()
        themes = ticker_to_themes.get(code, [])
        tv = float(row.get("売買代金", 0) or 0)
        chg = float(row.get("前日比率(%)", 0) or 0)
        name = str(row.get("名称", ""))
        n_themes = _theme_count.get(code, 999)

        for th in themes:
            if th not in theme_stats:
                theme_stats[th] = {
                    "売買代金合計": 0.0,
                    "銘柄数": 0,
                    "_chg_sum": 0.0,
                    # (name, n_themes, tv) — n_themesが小さいほど特化度が高い
                    "_top_stock": ("", 999, 0.0),
                }
            s = theme_stats[th]
            s["売買代金合計"] += tv
            s["銘柄数"] += 1
            s["_chg_sum"] += chg
            cur = s["_top_stock"]
            # 特化度優先: 所属テーマ数が少ない方を優先、同数なら売買代金で決定
            if n_themes < cur[1] or (n_themes == cur[1] and tv > cur[2]):
                s["_top_stock"] = (name, n_themes, tv)

    rows = []
    for th, s in theme_stats.items():
        n = s["銘柄数"]
        rows.append({
            "テーマ": th,
            "売買代金合計": s["売買代金合計"],
            "銘柄数": n,
            "平均変化率(%)": s["_chg_sum"] / n if n > 0 else 0.0,
            "代表銘柄": s["_top_stock"][0],
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("売買代金合計", ascending=False).reset_index(drop=True)
    df["売買代金(億円)"] = (df["売買代金合計"] / 1e8).round(0).astype(int)
    return df


# ------------------------------------------------------------------
# 3. 日次スナップショット蓄積
# ------------------------------------------------------------------

def save_daily_snapshot(
    ranking_df: pd.DataFrame,
    theme_df: pd.DataFrame,
    date: str | None = None,
) -> tuple[Path, Path]:
    """本日のランキング + テーマ集計をParquetで保存"""
    if date is None:
        date = datetime.now(JST).strftime("%Y-%m-%d")

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    ranking_path = SNAPSHOT_DIR / f"{date}_ranking.parquet"
    theme_path = SNAPSHOT_DIR / f"{date}_themes.parquet"

    ranking_df["snapshot_date"] = date
    theme_df["snapshot_date"] = date

    ranking_df.to_parquet(ranking_path, engine="pyarrow", compression="zstd", index=False)
    theme_df.to_parquet(theme_path, engine="pyarrow", compression="zstd", index=False)

    return ranking_path, theme_path


def load_theme_history(days: int = 30) -> pd.DataFrame:
    """過去N日分のテーマ集計スナップショットを読み込む"""
    if not SNAPSHOT_DIR.exists():
        return pd.DataFrame()

    files = sorted(SNAPSHOT_DIR.glob("*_themes.parquet"))
    if not files:
        return pd.DataFrame()

    # 直近N日分に絞る
    cutoff = (datetime.now(JST) - timedelta(days=days)).strftime("%Y-%m-%d")
    recent = [f for f in files if f.name >= cutoff]
    if not recent:
        return pd.DataFrame()

    frames = [pd.read_parquet(f, engine="pyarrow") for f in recent]
    return pd.concat(frames, ignore_index=True)


def load_ranking_history(days: int = 30) -> pd.DataFrame:
    """過去N日分のランキングスナップショットを読み込む"""
    if not SNAPSHOT_DIR.exists():
        return pd.DataFrame()

    files = sorted(SNAPSHOT_DIR.glob("*_ranking.parquet"))
    if not files:
        return pd.DataFrame()

    cutoff = (datetime.now(JST) - timedelta(days=days)).strftime("%Y-%m-%d")
    recent = [f for f in files if f.name >= cutoff]
    if not recent:
        return pd.DataFrame()

    frames = [pd.read_parquet(f, engine="pyarrow") for f in recent]
    return pd.concat(frames, ignore_index=True)


# ------------------------------------------------------------------
# 4. トレンド分析
# ------------------------------------------------------------------

def compute_sector_flow_trend(
    theme_history: pd.DataFrame,
    top_n: int = 20,
) -> pd.DataFrame:
    """セクターの日次売買代金推移（ピボット形式）

    Returns:
        index = snapshot_date, columns = テーマ名, values = 売買代金(億円)
    """
    if theme_history.empty:
        return pd.DataFrame()

    # 直近日の売買代金Top N テーマを軸にする
    latest = theme_history["snapshot_date"].max()
    latest_df = theme_history[theme_history["snapshot_date"] == latest]
    top_themes = latest_df.nlargest(top_n, "売買代金合計")["テーマ"].tolist()

    filtered = theme_history[theme_history["テーマ"].isin(top_themes)]
    pivot = filtered.pivot_table(
        index="snapshot_date",
        columns="テーマ",
        values="売買代金合計",
        aggfunc="sum",
    )
    pivot = (pivot / 1e8).round(0)  # 億円に変換
    pivot = pivot.sort_index()
    return pivot


def compute_flow_change(
    theme_history: pd.DataFrame,
    compare_days: int = 5,
) -> pd.DataFrame:
    """直近 vs N日前の売買代金変化率を計算して「資金流入加速」テーマを検出

    Returns:
        columns: [テーマ, 直近売買代金(億円), N日前売買代金(億円), 変化率(%), 方向]
    """
    if theme_history.empty:
        return pd.DataFrame()

    dates = sorted(theme_history["snapshot_date"].unique())
    if len(dates) < 2:
        return pd.DataFrame()

    latest_date = dates[-1]
    # compare_days前に最も近い日を探す
    target_idx = max(0, len(dates) - 1 - compare_days)
    prev_date = dates[target_idx]

    latest = theme_history[theme_history["snapshot_date"] == latest_date]
    prev = theme_history[theme_history["snapshot_date"] == prev_date]

    merged = pd.merge(
        latest[["テーマ", "売買代金合計"]].rename(columns={"売買代金合計": "直近"}),
        prev[["テーマ", "売買代金合計"]].rename(columns={"売買代金合計": "前回"}),
        on="テーマ",
        how="outer",
    ).fillna(0)

    merged["直近売買代金(億円)"] = (merged["直近"] / 1e8).round(0).astype(int)
    merged["前回売買代金(億円)"] = (merged["前回"] / 1e8).round(0).astype(int)
    merged["変化率(%)"] = ((merged["直近"] - merged["前回"]) / merged["前回"].replace(0, 1) * 100).round(1)
    merged["方向"] = merged["変化率(%)"].apply(lambda x: "🔺 流入加速" if x > 20 else ("🔻 流出" if x < -20 else "→ 横ばい"))

    result = merged[["テーマ", "直近売買代金(億円)", "前回売買代金(億円)", "変化率(%)", "方向"]]
    return result.sort_values("直近売買代金(億円)", ascending=False).reset_index(drop=True)
