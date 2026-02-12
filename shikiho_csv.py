"""四季報オンライン プレミアムCSVの読み込み・分析モジュール

対応CSV:
  1. 株価CSV: 日付,始値(円),高値(円),安値(円),終値(円),前日比(円),前日比(%),出来高(株),売買代金(千円)
  2. ウォッチリスト一覧CSV: コード,銘柄名,株価,株価の前日比(%),取得価格,保有株数,損益額,損益(%),メモ
  3. Chrome拡張 指標CSV: コード,銘柄名,株価,...,PER,PBR,配当利回り,...
  4. Chrome拡張 業績CSV: コード,銘柄名,決算期,売上高,営業利益,...
"""

import io
import re
from enum import Enum

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class CsvType(Enum):
    STOCK_PRICE = "株価CSV"
    WATCHLIST = "ウォッチリスト"
    INDICATORS = "指標CSV"
    FINANCIAL = "業績CSV"
    UNKNOWN = "不明"


def detect_csv_type(df: pd.DataFrame) -> CsvType:
    """CSVのカラム名から種類を自動判定"""
    cols = set(df.columns)
    col_str = " ".join(df.columns).lower()

    # 株価CSV: 日付, 始値, 終値 がある
    if "日付" in cols and any("始値" in c for c in cols) and any("終値" in c for c in cols):
        return CsvType.STOCK_PRICE

    # ウォッチリスト: コード, 銘柄名, 取得価格 or 損益
    if any("コード" in c for c in cols) and any("銘柄名" in c for c in cols):
        if any("取得価格" in c or "損益" in c for c in cols):
            return CsvType.WATCHLIST
        if any("per" in col_str or "pbr" in col_str or "配当利回り" in c for c in cols):
            return CsvType.INDICATORS
        if any("売上" in c or "営業利益" in c or "決算" in c for c in cols):
            return CsvType.FINANCIAL

    return CsvType.UNKNOWN


def load_stock_price_csv(file) -> pd.DataFrame:
    """株価CSVを読み込み、Pandasデータフレームに変換"""
    df = pd.read_csv(file, encoding="utf-8-sig")

    # カラム名を正規化（括弧や単位を除去した短縮名も追加）
    rename_map = {}
    for col in df.columns:
        clean = col.strip().strip('"')
        rename_map[col] = clean

    df.rename(columns=rename_map, inplace=True)

    # 日付列をdatetimeに
    date_col = None
    for c in df.columns:
        if "日付" in c:
            date_col = c
            break

    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df.sort_values(date_col, inplace=True)
        df.set_index(date_col, inplace=True)

    # 数値列を数値化
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "").str.strip('"'),
                errors="coerce",
            )

    return df


def load_watchlist_csv(file) -> pd.DataFrame:
    """ウォッチリスト一覧CSVを読み込み"""
    df = pd.read_csv(file, encoding="utf-8-sig")
    # カラム名クリーン
    df.columns = [c.strip().strip('"') for c in df.columns]

    # 数値列を変換
    for col in df.columns:
        if any(kw in col for kw in ["株価", "価格", "損益", "前日比", "保有株数"]):
            if df[col].dtype == object:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace(",", "").str.strip('"').str.rstrip("%"),
                    errors="coerce",
                )
    return df


def load_generic_csv(file) -> pd.DataFrame:
    """汎用CSV読み込み（指標・業績など）"""
    # まず UTF-8-BOM を試し、失敗したら shift_jis
    try:
        df = pd.read_csv(file, encoding="utf-8-sig")
    except UnicodeDecodeError:
        file.seek(0) if hasattr(file, "seek") else None
        df = pd.read_csv(file, encoding="shift_jis")

    df.columns = [c.strip().strip('"') for c in df.columns]

    # 数値っぽい列を変換
    for col in df.columns:
        if df[col].dtype == object:
            try:
                converted = pd.to_numeric(
                    df[col].astype(str).str.replace(",", "").str.strip('"').str.rstrip("%"),
                    errors="coerce",
                )
                if converted.notna().sum() > len(df) * 0.5:
                    df[col] = converted
            except Exception:
                pass

    return df


# ================================================================
# チャート生成
# ================================================================

def stock_price_candlestick(df: pd.DataFrame, title: str = "株価チャート") -> go.Figure:
    """株価CSVからローソク足+出来高チャートを生成"""
    # カラム名を検出
    open_col = next((c for c in df.columns if "始値" in c), None)
    high_col = next((c for c in df.columns if "高値" in c), None)
    low_col = next((c for c in df.columns if "安値" in c), None)
    close_col = next((c for c in df.columns if "終値" in c), None)
    vol_col = next((c for c in df.columns if "出来高" in c), None)
    value_col = next((c for c in df.columns if "売買代金" in c), None)

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3],
        subplot_titles=[title, "出来高 / 売買代金"],
    )

    if open_col and high_col and low_col and close_col:
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df[open_col],
                high=df[high_col],
                low=df[low_col],
                close=df[close_col],
                name="株価",
                increasing_line_color="#EF5350",
                decreasing_line_color="#26A69A",
            ),
            row=1, col=1,
        )

        # 移動平均線
        if len(df) >= 25:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df[close_col].rolling(25).mean(),
                    name="25日移動平均",
                    line=dict(color="#FF9800", width=1.5),
                ),
                row=1, col=1,
            )
        if len(df) >= 75:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df[close_col].rolling(75).mean(),
                    name="75日移動平均",
                    line=dict(color="#2196F3", width=1.5),
                ),
                row=1, col=1,
            )

    # 出来高 or 売買代金
    bar_col = vol_col or value_col
    bar_label = "出来高" if vol_col else "売買代金"
    if bar_col:
        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df[bar_col],
                name=bar_label,
                marker_color="#90CAF9",
                opacity=0.6,
            ),
            row=2, col=1,
        )

    fig.update_layout(
        height=600,
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(dtick="M1", tickformat="%Y/%m", row=2, col=1)

    return fig


def stock_price_summary(df: pd.DataFrame) -> dict:
    """株価CSVからサマリー統計を計算"""
    close_col = next((c for c in df.columns if "終値" in c), None)
    vol_col = next((c for c in df.columns if "出来高" in c), None)
    value_col = next((c for c in df.columns if "売買代金" in c), None)
    change_pct_col = next((c for c in df.columns if "前日比(%)" in c or "前日比(%" in c), None)

    stats = {}
    if close_col and not df[close_col].dropna().empty:
        prices = df[close_col].dropna()
        stats["最新終値"] = f"{prices.iloc[-1]:,.0f}円"
        stats["期間高値"] = f"{prices.max():,.0f}円"
        stats["期間安値"] = f"{prices.min():,.0f}円"

        if len(prices) >= 2:
            period_change = (prices.iloc[-1] / prices.iloc[0] - 1) * 100
            stats["期間変化率"] = f"{period_change:+.2f}%"

        if len(prices) >= 5:
            week_change = (prices.iloc[-1] / prices.iloc[-5] - 1) * 100
            stats["直近5日変化率"] = f"{week_change:+.2f}%"

    if vol_col and not df[vol_col].dropna().empty:
        stats["平均出来高"] = f"{df[vol_col].mean():,.0f}株"

    if value_col and not df[value_col].dropna().empty:
        avg_val = df[value_col].mean()
        if avg_val >= 1_000_000:
            stats["平均売買代金"] = f"{avg_val/1_000_000:,.1f}十億円"
        elif avg_val >= 1_000:
            stats["平均売買代金"] = f"{avg_val/1_000:,.1f}百万円"
        else:
            stats["平均売買代金"] = f"{avg_val:,.0f}千円"

    stats["データ日数"] = f"{len(df)}日"
    if not df.index.empty:
        stats["期間"] = f"{df.index[0].strftime('%Y/%m/%d')} 〜 {df.index[-1].strftime('%Y/%m/%d')}"

    return stats


def watchlist_profit_chart(df: pd.DataFrame) -> go.Figure | None:
    """ウォッチリストCSVから損益チャートを生成"""
    name_col = next((c for c in df.columns if "銘柄名" in c), None)
    pnl_col = next((c for c in df.columns if "損益額" in c or "損益" in c and "%" not in c), None)
    pnl_pct_col = next((c for c in df.columns if "損益(%)" in c or "損益(%" in c), None)

    if not name_col:
        return None

    # 損益額チャート
    chart_col = pnl_pct_col or pnl_col
    chart_label = "損益(%)" if pnl_pct_col else "損益額"

    if not chart_col:
        return None

    plot_df = df[[name_col, chart_col]].dropna().copy()
    plot_df = plot_df.sort_values(chart_col, ascending=True)

    colors = ["#EF5350" if v < 0 else "#26A69A" for v in plot_df[chart_col]]

    fig = go.Figure(
        go.Bar(
            x=plot_df[chart_col],
            y=plot_df[name_col],
            orientation="h",
            marker_color=colors,
            text=[f"{v:+.1f}" for v in plot_df[chart_col]],
            textposition="outside",
        )
    )
    fig.update_layout(
        title=f"ウォッチリスト {chart_label}",
        xaxis_title=chart_label,
        height=max(400, len(plot_df) * 28),
        template="plotly_white",
        margin=dict(l=150),
    )
    return fig
