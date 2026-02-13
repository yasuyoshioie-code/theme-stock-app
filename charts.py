import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

# みんかぶ風カラーパレット（ネイビー基調）
COLORS = [
    "#014099",  # ネイビー
    "#1565C0",  # ブルー
    "#1B8A50",  # グリーン
    "#D84315",  # オレンジ
    "#6A1B9A",  # パープル
    "#00695C",  # ティール
    "#C62828",  # レッド
    "#EF6C00",  # アンバー
    "#37474F",  # ブルーグレー
    "#AD1457",  # ピンク
    "#4527A0",  # ディープパープル
    "#0277BD",  # ライトブルー
]

# 上昇=赤 / 下落=緑（日本式）
COLOR_UP = "#F54545"
COLOR_DOWN = "#1B8A50"


def sector_bar_chart(summary: pd.DataFrame) -> go.Figure:
    """セクター別売買代金合計の棒グラフ"""
    fig = go.Figure(
        go.Bar(
            x=summary.index,
            y=summary["売買代金合計(億円)"],
            marker_color=COLORS[: len(summary)],
            text=summary["売買代金合計(億円)"].apply(lambda x: f"{x:,.0f}"),
            textposition="outside",
        )
    )
    fig.update_layout(
        title="セクター別 売買代金合計",
        xaxis_title="セクター",
        yaxis_title="売買代金 (億円)",
        template="plotly_white",
        height=500,
    )
    return fig


def timeseries_chart(
    sector_df: pd.DataFrame,
    selected_sectors: list[str],
    highlight_sectors: list[str] | None = None,
) -> go.Figure:
    """セクター別売買代金の時系列推移（折れ線グラフ）

    highlight_sectors: 強調表示するセクターリスト。
      指定された場合、それ以外は薄く細い線で描画。
    """
    fig = go.Figure()

    for i, sector in enumerate(selected_sectors):
        if sector not in sector_df.columns:
            continue

        is_highlighted = highlight_sectors is None or sector in highlight_sectors
        color = COLORS[i % len(COLORS)]

        if is_highlighted:
            fig.add_trace(
                go.Scatter(
                    x=sector_df.index,
                    y=sector_df[sector] / 1e8,
                    mode="lines+markers",
                    name=sector,
                    line=dict(color=color, width=3),
                    marker=dict(size=5),
                    opacity=1.0,
                )
            )
        else:
            fig.add_trace(
                go.Scatter(
                    x=sector_df.index,
                    y=sector_df[sector] / 1e8,
                    mode="lines",
                    name=sector,
                    line=dict(color="lightgray", width=1, dash="dot"),
                    opacity=0.4,
                    showlegend=True,
                )
            )

    fig.update_layout(
        title="セクター別 売買代金推移",
        xaxis_title="日付",
        yaxis_title="売買代金 (億円)",
        template="plotly_white",
        height=550,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    return fig


def momentum_bar_chart(ranking_df: pd.DataFrame) -> go.Figure:
    """盛り上がりスコアの横棒グラフ"""
    if ranking_df.empty:
        fig = go.Figure()
        fig.update_layout(title="データなし")
        return fig

    df = ranking_df.copy()
    colors = [
        COLOR_UP if s > 0 else COLOR_DOWN for s in df["盛り上がりスコア"]
    ]

    fig = go.Figure(
        go.Bar(
            x=df["盛り上がりスコア"],
            y=df["セクター"],
            orientation="h",
            marker_color=colors,
            text=df["盛り上がりスコア"].apply(lambda x: f"{x:+.1f}%"),
            textposition="outside",
        )
    )
    fig.update_layout(
        title="セクター盛り上がりランキング",
        xaxis_title="盛り上がりスコア (%)",
        template="plotly_white",
        height=max(400, len(df) * 35),
        yaxis=dict(autorange="reversed"),
    )
    fig.add_vline(x=0, line_color="gray", line_width=1)
    return fig


def week_change_bar_chart(comparison_df: pd.DataFrame) -> go.Figure:
    """週間変化率の棒グラフ"""
    if comparison_df.empty:
        fig = go.Figure()
        fig.update_layout(title="データなし")
        return fig

    df = comparison_df.sort_values("週間変化率(%)", ascending=True)
    colors = [
        COLOR_UP if v > 0 else COLOR_DOWN for v in df["週間変化率(%)"]
    ]

    fig = go.Figure(
        go.Bar(
            x=df["週間変化率(%)"],
            y=df["セクター"],
            orientation="h",
            marker_color=colors,
            text=df["週間変化率(%)"].apply(lambda x: f"{x:+.1f}%"),
            textposition="outside",
        )
    )
    fig.update_layout(
        title="週間 売買代金変化率",
        xaxis_title="変化率 (%)",
        template="plotly_white",
        height=max(400, len(df) * 35),
    )
    fig.add_vline(x=0, line_color="gray", line_width=1)
    return fig


def period_change_bar_chart(comparison_df: pd.DataFrame) -> go.Figure:
    """期間変化率の棒グラフ"""
    if comparison_df.empty:
        fig = go.Figure()
        fig.update_layout(title="データなし")
        return fig

    df = comparison_df.sort_values("期間変化率(%)", ascending=True)
    colors = [
        COLOR_UP if v > 0 else COLOR_DOWN for v in df["期間変化率(%)"]
    ]

    fig = go.Figure(
        go.Bar(
            x=df["期間変化率(%)"],
            y=df["セクター"],
            orientation="h",
            marker_color=colors,
            text=df["期間変化率(%)"].apply(lambda x: f"{x:+.1f}%"),
            textposition="outside",
        )
    )
    fig.update_layout(
        title="期間 売買代金変化率（後半 vs 前半）",
        xaxis_title="変化率 (%)",
        template="plotly_white",
        height=max(400, len(df) * 35),
    )
    fig.add_vline(x=0, line_color="gray", line_width=1)
    return fig


def comparison_bar_chart(sector_df: pd.DataFrame, selected_sectors: list[str]) -> go.Figure:
    """セクター比較 グループ化棒グラフ"""
    fig = go.Figure()
    for i, sector in enumerate(selected_sectors):
        if sector in sector_df.columns:
            fig.add_trace(
                go.Bar(
                    x=sector_df.index.strftime("%m/%d") if hasattr(sector_df.index, "strftime") else sector_df.index,
                    y=sector_df[sector] / 1e8,
                    name=sector,
                    marker_color=COLORS[i % len(COLORS)],
                )
            )
    fig.update_layout(
        title="セクター比較（売買代金）",
        xaxis_title="日付",
        yaxis_title="売買代金 (億円)",
        barmode="group",
        template="plotly_white",
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def normalized_chart(sector_df: pd.DataFrame, selected_sectors: list[str]) -> go.Figure:
    """正規化チャート（初日を100として相対比較）"""
    fig = go.Figure()
    for i, sector in enumerate(selected_sectors):
        if sector in sector_df.columns:
            series = sector_df[sector]
            first_nonzero = series[series > 0].iloc[0] if (series > 0).any() else 1
            normalized = series / first_nonzero * 100
            fig.add_trace(
                go.Scatter(
                    x=sector_df.index,
                    y=normalized,
                    mode="lines",
                    name=sector,
                    line=dict(color=COLORS[i % len(COLORS)], width=2),
                )
            )
    fig.update_layout(
        title="セクター比較（正規化：初日=100）",
        xaxis_title="日付",
        yaxis_title="相対値",
        template="plotly_white",
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.add_hline(y=100, line_dash="dash", line_color="gray", opacity=0.5)
    return fig


def stock_detail_bar(detail_df: pd.DataFrame, top_n: int = 20) -> go.Figure:
    """銘柄別売買代金ランキング"""
    df = detail_df.head(top_n)
    fig = go.Figure(
        go.Bar(
            x=df["売買代金合計(億円)"],
            y=df["銘柄名"] + " (" + df["銘柄コード"] + ")",
            orientation="h",
            marker_color=[
                COLORS[list(detail_df["セクター"].unique()).index(s) % len(COLORS)]
                for s in df["セクター"]
            ],
            text=df["売買代金合計(億円)"].apply(lambda x: f"{x:,.0f}"),
            textposition="outside",
        )
    )
    fig.update_layout(
        title=f"銘柄別 売買代金ランキング (Top {top_n})",
        xaxis_title="売買代金 (億円)",
        template="plotly_white",
        height=max(400, top_n * 30),
        yaxis=dict(autorange="reversed"),
    )
    return fig


def stock_momentum_bar_chart(
    momentum_df: pd.DataFrame, top_n: int = 30
) -> go.Figure:
    """銘柄別 急騰スコアの横棒グラフ"""
    if momentum_df.empty:
        fig = go.Figure()
        fig.update_layout(title="データなし")
        return fig

    df = momentum_df.head(top_n).copy()
    # 表示用ラベル
    df["label"] = df["銘柄名"] + " (" + df["銘柄コード"] + ")"

    colors = [
        COLOR_UP if s > 0 else COLOR_DOWN for s in df["急騰スコア"]
    ]

    fig = go.Figure(
        go.Bar(
            x=df["急騰スコア"],
            y=df["label"],
            orientation="h",
            marker_color=colors,
            text=df["急騰スコア"].apply(lambda x: f"{x:+.1f}"),
            textposition="outside",
            customdata=df[["セクター", "前日比(%)", "週間変化(%)", "月間変化(%)", "直近(億円)"]].values,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "セクター: %{customdata[0]}<br>"
                "急騰スコア: %{x:+.1f}<br>"
                "前日比: %{customdata[1]:+.1f}%<br>"
                "週間変化: %{customdata[2]:+.1f}%<br>"
                "月間変化: %{customdata[3]:+.1f}%<br>"
                "直近売買代金: %{customdata[4]:.2f}億円"
                "<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title=f"銘柄別 売買代金急騰ランキング (Top {top_n})",
        xaxis_title="急騰スコア",
        template="plotly_white",
        height=max(500, top_n * 28),
        yaxis=dict(autorange="reversed"),
    )
    fig.add_vline(x=0, line_color="gray", line_width=1)
    return fig


def stock_change_heatmap(momentum_df: pd.DataFrame, top_n: int = 30) -> go.Figure:
    """銘柄別 変化率ヒートマップ"""
    if momentum_df.empty:
        fig = go.Figure()
        fig.update_layout(title="データなし")
        return fig

    df = momentum_df.head(top_n).copy()
    df["label"] = df["銘柄名"] + " (" + df["銘柄コード"] + ")"

    metrics = ["前日比(%)", "週間変化(%)", "月間変化(%)", "vs平均(%)"]
    z_data = df[metrics].values
    y_labels = df["label"].tolist()

    fig = go.Figure(
        go.Heatmap(
            z=z_data,
            x=["前日比", "週間変化", "月間変化", "vs平均"],
            y=y_labels,
            colorscale=[
                [0, COLOR_DOWN],
                [0.5, "#ffffff"],
                [1, COLOR_UP],
            ],
            zmid=0,
            text=[[f"{v:+.1f}%" for v in row] for row in z_data],
            texttemplate="%{text}",
            textfont=dict(size=10),
            hovertemplate="銘柄: %{y}<br>%{x}: %{z:+.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"銘柄別 変化率ヒートマップ (Top {top_n})",
        template="plotly_white",
        height=max(500, top_n * 28),
        yaxis=dict(autorange="reversed"),
    )
    return fig


# ----------------------------------------------------------------
# 市場ランキングチャート
# ----------------------------------------------------------------

def market_ranking_bar(
    df: pd.DataFrame,
    ranking_name: str,
    value_col: str = "前日比率(%)",
    top_n: int = 50,
) -> go.Figure:
    """市場ランキングの横棒グラフ（コード+銘柄名ラベル）"""
    if df.empty or "名称" not in df.columns:
        fig = go.Figure()
        fig.update_layout(title=f"{ranking_name} - データなし")
        return fig

    plot_df = df.head(top_n).copy()

    # ラベル: コード + 銘柄名
    if "コード" in plot_df.columns:
        plot_df["label"] = plot_df["コード"].astype(str) + " " + plot_df["名称"]
    else:
        plot_df["label"] = plot_df["名称"]

    # 値カラムを自動選択
    if value_col not in plot_df.columns:
        # ランキング種類に応じた値カラムを探す
        for candidate in ["前日比率(%)", "出来高", "売買代金", "配当利回り(%)", "PER", "PBR",
                          "出来高増加率(%)", "時価総額", "信用買残", "信用売残", "信用倍率"]:
            if candidate in plot_df.columns:
                value_col = candidate
                break
        else:
            value_col = "前日比率(%)"

    if value_col in plot_df.columns:
        values = pd.to_numeric(plot_df[value_col], errors="coerce").fillna(0)
    else:
        values = pd.Series(range(len(plot_df), 0, -1))

    colors = [
        COLOR_UP if v > 0 else COLOR_DOWN for v in values
    ]

    # テキストフォーマット
    if "(%)" in value_col or "率" in value_col:
        text_fmt = values.apply(lambda x: f"{x:+.2f}%")
    elif "売買代金" in value_col or "時価総額" in value_col:
        text_fmt = values.apply(lambda x: f"{x/1e8:,.0f}億" if x >= 1e8 else f"{x:,.0f}")
    elif "出来高" in value_col and "率" not in value_col:
        text_fmt = values.apply(lambda x: f"{x/10000:,.0f}万株" if x >= 10000 else f"{x:,.0f}株")
    else:
        text_fmt = values.apply(lambda x: f"{x:+.2f}" if abs(x) < 1000 else f"{x:,.0f}")

    # ホバー情報
    hover_cols = ["市場", "取引値", "前日比"]
    customdata_cols = [c for c in hover_cols if c in plot_df.columns]
    customdata = plot_df[customdata_cols].values if customdata_cols else None

    hover_parts = ["<b>%{y}</b><br>"]
    for ci, col in enumerate(customdata_cols):
        hover_parts.append(f"{col}: %{{customdata[{ci}]}}<br>")
    hover_parts.append(f"{value_col}: %{{x}}<extra></extra>")
    hovertemplate = "".join(hover_parts)

    fig = go.Figure(
        go.Bar(
            x=values,
            y=plot_df["label"],
            orientation="h",
            marker_color=colors,
            text=text_fmt,
            textposition="outside",
            customdata=customdata,
            hovertemplate=hovertemplate,
        )
    )
    n_display = min(top_n, len(plot_df))
    fig.update_layout(
        title=f"{ranking_name} (Top {n_display})",
        xaxis_title=value_col,
        template="plotly_white",
        height=max(500, n_display * 24),
        yaxis=dict(autorange="reversed"),
        margin=dict(l=280),
    )
    if "(%)" in value_col or "率" in value_col:
        fig.add_vline(x=0, line_color="gray", line_width=1)

    return fig