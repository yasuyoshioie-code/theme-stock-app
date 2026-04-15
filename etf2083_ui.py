"""ETF 2083 タブの Streamlit 描画モジュール

提供セクション:
  - 📊 サマリ（総資産・組入数・受益権口数）
  - 📥 データ取得（手動PCF取得・CSVアップロード）
  - 🏆 組入上位 Top20（棒グラフ+テーブル）
  - 🔄 差分分析（日付A→B の新規/除外/増減）
  - 📈 銘柄別タイムライン（株数・評価額・構成比の推移）
  - 🆕 月次新規組入
"""
from __future__ import annotations

import io
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from etf2083 import (
    PCF_URL,
    fetch_latest_pcf,
    import_csv_manual,
    list_dates,
    get_holdings,
    get_diff,
    get_timeline,
    get_summary,
    get_period_trend,
    get_period_movers,
    to_jp_name,
)

# charts.pyのダークテーマ定数を再利用
try:
    from charts import _DARK_LAYOUT, _apply_dark, COLORS, COLOR_UP, COLOR_DOWN
except ImportError:
    COLORS = ["#00E5FF", "#7C3AED", "#00D9A3", "#FF5E6C", "#FFB020"]
    COLOR_UP = "#FF5E6C"
    COLOR_DOWN = "#00D9A3"
    _DARK_LAYOUT = {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": dict(color="#F0F3FA", size=12),
    }
    def _apply_dark(fig):
        fig.update_layout(**_DARK_LAYOUT)
        return fig


def _fmt_oku(v: float) -> str:
    """円→億円表記"""
    if not v:
        return "0"
    return f"{v / 1e8:.2f}億"


def _fmt_num(v) -> str:
    """数値にカンマ"""
    if v is None:
        return "-"
    try:
        return f"{int(v):,}"
    except (ValueError, TypeError):
        return str(v)


def render_etf2083_tab(sectors: dict | None = None):
    """ETF 2083タブのメイン描画関数

    Parameters
    ----------
    sectors : dict (optional)
        テーマ株セクターデータ。組入銘柄がどのテーマに所属するか表示するため
    """
    st.subheader("📦 NF・日本成長株アクティブETF (2083) 組入銘柄トラッカー")
    st.caption(
        "東証PCF日次データから組入銘柄を自動収集・蓄積し、新規組入/除外/買い増し/売却を可視化します。"
        f" データソース: `{PCF_URL}` (平日 7:50-23:55 のみ配信)"
    )

    # ==================================================
    # サマリ
    # ==================================================
    summary = get_summary()
    if summary["status"] == "empty":
        st.warning("まだデータがありません。下の「📡 今日のPCFを取得」ボタンを押してください。")
        _render_fetch_controls()
        return

    # サマリメトリクス
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📅 データ期間", f"{summary['total_snapshots']}日分")
        st.caption(f"{summary['date_first']} 〜 {summary['date_last']}")
    with col2:
        st.metric("🎯 現在の組入銘柄数", summary["holdings_last"])
        delta = summary["holdings_last"] - summary["holdings_first"]
        st.caption(f"初日比: {delta:+d}銘柄")
    with col3:
        st.metric("🆕 期間中の新規組入", len(summary["new_since_start"]))
        st.caption(f"初日({summary['holdings_first']})→最新")
    with col4:
        st.metric("❌ 期間中の除外", len(summary["removed_since_start"]))
        st.caption(f"初日→最新({summary['holdings_last']})")

    st.divider()

    # ==================================================
    # 機能タブ
    # ==================================================
    sub_tabs = st.tabs([
        "🏆 組入上位",
        "🔄 差分分析",
        "📈 銘柄タイムライン",
        "🆕 新規・除外",
        "📥 データ取得",
    ])

    # ───── 🏆 組入上位 ─────
    with sub_tabs[0]:
        _render_top_holdings(summary, sectors)

    # ───── 🔄 差分分析 ─────
    with sub_tabs[1]:
        _render_diff_panel(summary)

    # ───── 📈 銘柄タイムライン ─────
    with sub_tabs[2]:
        _render_timeline(summary)

    # ───── 🆕 新規・除外 ─────
    with sub_tabs[3]:
        _render_new_and_removed(summary)

    # ───── 📥 データ取得 ─────
    with sub_tabs[4]:
        _render_fetch_controls()


# ==========================================================
# サブセクション
# ==========================================================
def _render_fetch_controls():
    """PCF取得・アップロード"""
    st.markdown("#### 📥 データ取得")
    st.caption(
        "PCFは**前営業日時点**の情報です。**平日7:50-23:55のみ配信**され、過去分のアーカイブは存在しません。"
        " 日次で自動蓄積する必要があります。"
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("📡 今日のPCFを取得", type="primary", use_container_width=True, key="etf2083_fetch"):
            with st.spinner("東証PCFをダウンロード中..."):
                result = fetch_latest_pcf()
            if result["status"] == "ok":
                st.success(f"✅ {result['date']} のデータを保存: {result['count']}銘柄")
                st.rerun()
            elif result["status"] == "skip":
                st.info(f"ℹ️ {result['date']} は既に取得済みです")
            elif result["status"] == "unavailable":
                st.warning("⚠️ 時間外です（平日 7:50-23:55 のみ配信）。CSVを手動アップロードしてください。")
            else:
                st.error(f"❌ {result.get('message', 'エラー')}")

    with col2:
        st.caption("**手動アップロード**（時間外用）")
        uploaded = st.file_uploader(
            "PCF CSV",
            type=["csv"],
            key="etf2083_uploader",
            label_visibility="collapsed",
        )

    if uploaded is not None:
        import_date = st.date_input(
            "このCSVの日付",
            value=pd.Timestamp.now().date(),
            key="etf2083_import_date",
        )
        if st.button("📥 インポート実行", type="secondary", key="etf2083_do_import"):
            raw = uploaded.read().decode("utf-8", errors="replace")
            result = import_csv_manual(raw, import_date.strftime("%Y-%m-%d"))
            if result["status"] == "ok":
                st.success(f"✅ {result['date']} を保存: {result['count']}銘柄")
                st.rerun()
            else:
                st.error(f"❌ {result.get('message', 'エラー')}")

    # 取得済み日付一覧
    dates = list_dates()
    if dates:
        st.markdown("#### 📅 蓄積済みスナップショット")
        df = pd.DataFrame(dates)
        df.columns = ["日付", "銘柄数", "受益権口数", "取得方法"]
        st.dataframe(df, use_container_width=True, hide_index=True)


def _render_top_holdings(summary: dict, sectors: dict | None):
    """組入上位Top20"""
    st.markdown(f"#### 🏆 組入上位 Top20（{summary['date_last']}時点）")

    top20 = summary["top20"]
    if not top20:
        st.info("データがありません")
        return

    df = pd.DataFrame(top20)
    df["rank"] = range(1, len(df) + 1)

    # 所属セクター推定（組入銘柄がどのテーマに入っているか）
    if sectors:
        sector_map = {}
        for sector_name, sec_df in sectors.items():
            if sec_df.empty or "証券コード" not in sec_df.columns:
                continue
            for _, row in sec_df.iterrows():
                code = str(row["証券コード"]).strip()
                sector_map.setdefault(code, []).append(sector_name)
        df["テーマ"] = df["code"].map(lambda c: ", ".join(sector_map.get(c, [])[:2]) if sector_map.get(c) else "-")
    else:
        df["テーマ"] = "-"

    # ===== 棒グラフ（構成比） =====
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=df["name"].tolist()[::-1],
        x=df["weight"].tolist()[::-1],
        orientation="h",
        text=[f"{w:.2f}%" for w in df["weight"][::-1]],
        textposition="outside",
        marker=dict(
            color=df["weight"].tolist()[::-1],
            colorscale=[[0, "#1F2942"], [0.5, "#00E5FF"], [1.0, "#7C3AED"]],
            line=dict(color="rgba(0,229,255,0.3)", width=1),
        ),
        hovertemplate="<b>%{y}</b><br>構成比: %{x:.3f}%<extra></extra>",
    ))
    fig.update_layout(
        height=max(400, 30 * len(df) + 80),
        xaxis_title="構成比 (%)",
        yaxis_title="",
        showlegend=False,
        margin=dict(l=10, r=50, t=10, b=30),
    )
    _apply_dark(fig)
    st.plotly_chart(fig, use_container_width=True)

    # ===== テーブル =====
    display_df = df[["rank", "code", "name", "shares", "stock_price", "market_value", "weight", "テーマ"]].copy()
    display_df.columns = ["順位", "コード", "銘柄名", "株数", "株価", "評価額(円)", "構成比(%)", "テーマ"]
    display_df["評価額(億)"] = display_df["評価額(円)"].apply(lambda v: f"{v / 1e8:.2f}億")
    display_df = display_df[["順位", "コード", "銘柄名", "株数", "株価", "評価額(億)", "構成比(%)", "テーマ"]]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "順位": st.column_config.NumberColumn(width="small"),
            "コード": st.column_config.TextColumn(width="small"),
            "株数": st.column_config.NumberColumn(format="%d"),
            "株価": st.column_config.NumberColumn(format="%d"),
            "構成比(%)": st.column_config.ProgressColumn(format="%.3f%%", min_value=0, max_value=float(df["weight"].max())),
        },
    )


def _render_diff_panel(summary: dict):
    """差分分析（2日間 / 期間推移）"""
    st.markdown("#### 🔄 差分分析")

    dates_desc = sorted(summary["dates"], reverse=True)
    if len(dates_desc) < 2:
        st.info(
            "差分分析には2日分以上のデータが必要です。毎営業日にPCFを取得して蓄積してください。"
            f"（現在: {len(dates_desc)}日分）"
        )
        return

    diff_tabs = st.tabs(["📅 2日間差分", "📈 期間推移（1週間/1ヶ月/3ヶ月）"])
    with diff_tabs[0]:
        _render_two_day_diff(dates_desc)
    with diff_tabs[1]:
        _render_period_trend(summary)


def _render_two_day_diff(dates_desc: list[str]):
    """2日間差分（従来ビュー）"""

    col1, col2 = st.columns(2)
    with col1:
        date_from = st.selectbox("📅 比較元（古い日）", dates_desc, index=1, key="etf2083_diff_from")
    with col2:
        date_to = st.selectbox("📅 比較先（新しい日）", dates_desc, index=0, key="etf2083_diff_to")

    if date_from >= date_to:
        st.warning("比較元は比較先より古い日付を選んでください。")
        return

    diff = get_diff(date_from, date_to)
    if diff["status"] != "ok":
        st.error(diff.get("message", "エラー"))
        return

    # サマリ
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🆕 新規組入", len(diff["new"]))
    c2.metric("❌ 除外", len(diff["removed"]))
    c3.metric("⬆️ 買い増し", len(diff["increases"]))
    c4.metric("⬇️ 売却", len(diff["decreases"]))
    c5.metric("➖ 変化なし", diff["unchanged_count"])

    st.divider()

    # 新規・除外
    if diff["new"] or diff["removed"]:
        c_new, c_rm = st.columns(2)
        with c_new:
            st.markdown(f"##### 🆕 新規組入（{len(diff['new'])}銘柄）")
            if diff["new"]:
                df_n = pd.DataFrame(diff["new"])
                df_n["評価額(億)"] = df_n["market_value"].apply(lambda v: f"{v / 1e8:.2f}")
                df_n = df_n[["code", "name", "shares", "stock_price", "評価額(億)", "weight"]]
                df_n.columns = ["コード", "銘柄名", "株数", "株価", "評価額(億)", "構成比(%)"]
                st.dataframe(df_n, use_container_width=True, hide_index=True)
            else:
                st.caption("なし")
        with c_rm:
            st.markdown(f"##### ❌ 除外（{len(diff['removed'])}銘柄）")
            if diff["removed"]:
                df_r = pd.DataFrame(diff["removed"])
                df_r["評価額(億)"] = df_r["market_value"].apply(lambda v: f"{v / 1e8:.2f}")
                df_r = df_r[["code", "name", "shares", "stock_price", "評価額(億)", "weight"]]
                df_r.columns = ["コード", "銘柄名", "株数", "株価", "評価額(億)", "構成比(%)"]
                st.dataframe(df_r, use_container_width=True, hide_index=True)
            else:
                st.caption("なし")

    # 買い増し・売却
    if diff["increases"] or diff["decreases"]:
        st.divider()
        c_up, c_dn = st.columns(2)
        with c_up:
            st.markdown(f"##### ⬆️ 買い増し Top20")
            if diff["increases"]:
                df_u = pd.DataFrame(diff["increases"][:20])
                df_u = df_u[["code", "name", "shares_from", "shares_to", "shares_diff", "change_pct"]]
                df_u.columns = ["コード", "銘柄名", "株数(前)", "株数(後)", "増減", "変化率(%)"]
                st.dataframe(
                    df_u, use_container_width=True, hide_index=True,
                    column_config={
                        "変化率(%)": st.column_config.NumberColumn(format="+%.2f%%"),
                        "増減": st.column_config.NumberColumn(format="+%d"),
                    },
                )
            else:
                st.caption("なし")
        with c_dn:
            st.markdown(f"##### ⬇️ 売却 Top20")
            if diff["decreases"]:
                df_d = pd.DataFrame(diff["decreases"][:20])
                df_d = df_d[["code", "name", "shares_from", "shares_to", "shares_diff", "change_pct"]]
                df_d.columns = ["コード", "銘柄名", "株数(前)", "株数(後)", "増減", "変化率(%)"]
                st.dataframe(
                    df_d, use_container_width=True, hide_index=True,
                    column_config={
                        "変化率(%)": st.column_config.NumberColumn(format="%.2f%%"),
                        "増減": st.column_config.NumberColumn(format="%d"),
                    },
                )
            else:
                st.caption("なし")


def _render_period_trend(summary: dict):
    """期間推移ビュー: 1週間/1ヶ月/3ヶ月/全期間"""
    PERIOD_OPTIONS = [
        ("1週間", 7),
        ("1ヶ月", 30),
        ("3ヶ月", 90),
        ("半年", 180),
        ("全期間", 0),
    ]

    col_p1, col_p2 = st.columns([2, 3])
    with col_p1:
        label = st.radio(
            "期間",
            options=[l for l, _ in PERIOD_OPTIONS],
            index=1,  # デフォルト1ヶ月
            horizontal=True,
            key="etf2083_period_radio",
        )
    days = dict(PERIOD_OPTIONS)[label]

    trend = get_period_trend(days=days)
    movers = get_period_movers(days=days, top_n=15)

    if trend.get("status") == "insufficient":
        st.warning(f"⚠️ {label}分のデータがまだ不足しています。毎営業日にPCFを取得して蓄積してください。")
        return

    with col_p2:
        st.caption(
            f"📅 期間: **{trend['date_from']}** 〜 **{trend['date_to']}**"
            f"（{len(trend['dates'])}日分）"
        )

    # ===== サマリメトリクス =====
    if movers.get("status") == "ok":
        c1, c2, c3, c4, c5 = st.columns(5)
        delta_holdings = movers["total_to"] - movers["total_from"]
        c1.metric("🎯 銘柄数変化", f"{movers['total_to']}", f"{delta_holdings:+d}")
        c2.metric("🆕 新規組入", len(movers["new"]))
        c3.metric("❌ 除外", len(movers["removed"]))
        c4.metric("⬆️ 構成比UP Top", len(movers["gainers"]))
        c5.metric("⬇️ 構成比DOWN Top", len(movers["losers"]))
    elif movers.get("status") == "insufficient":
        st.info("📊 まだ1日分しかデータがないため、期間推移の比較はできません。")
        return

    st.divider()

    # ===== 総評価額・銘柄数の推移 =====
    trend_df = pd.DataFrame(trend["trend_daily"])
    if len(trend_df) >= 2:
        trend_df["date"] = pd.to_datetime(trend_df["date"])
        trend_df["評価額(億)"] = trend_df["total_market_value"] / 1e8

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=trend_df["date"], y=trend_df["評価額(億)"],
            mode="lines+markers", name="総評価額（億円）",
            line=dict(color=COLORS[0], width=2.5),
            marker=dict(size=6),
            fill="tozeroy",
            fillcolor="rgba(0,229,255,0.10)",
            yaxis="y1",
        ))
        fig.add_trace(go.Scatter(
            x=trend_df["date"], y=trend_df["total_holdings"],
            mode="lines+markers", name="組入銘柄数",
            line=dict(color=COLORS[1], width=2.5, dash="dash"),
            marker=dict(size=6),
            yaxis="y2",
        ))
        fig.update_layout(
            title="📊 総評価額 & 組入銘柄数 の推移",
            height=340,
            xaxis=dict(title=""),
            yaxis=dict(title="総評価額（億円）", side="left"),
            yaxis2=dict(title="銘柄数", overlaying="y", side="right", showgrid=False),
            hovermode="x unified",
            legend=dict(orientation="h", y=-0.18),
            margin=dict(l=10, r=10, t=40, b=30),
        )
        _apply_dark(fig)
        st.plotly_chart(fig, use_container_width=True)

    # ===== Top10の構成比推移（積み上げエリア） =====
    weight_ts = trend.get("weight_timeseries", {})
    top_codes = trend.get("top_codes", [])
    top_names = trend.get("top_names", {})

    if weight_ts and len(trend["dates"]) >= 2:
        fig2 = go.Figure()
        for i, code in enumerate(top_codes):
            series = weight_ts.get(code, [])
            if not series:
                continue
            dates = [s["date"] for s in series]
            weights = [s["weight"] for s in series]
            color = COLORS[i % len(COLORS)]
            fig2.add_trace(go.Scatter(
                x=pd.to_datetime(dates),
                y=weights,
                mode="lines",
                name=f"{code} {top_names.get(code, '')}",
                line=dict(color=color, width=2),
                stackgroup="one",
                hovertemplate=f"<b>{code} {top_names.get(code, '')}</b><br>"
                              "%{x|%Y-%m-%d}: %{y:.3f}%<extra></extra>",
            ))
        fig2.update_layout(
            title="🏆 上位10銘柄の構成比推移（積み上げ）",
            height=400,
            xaxis=dict(title=""),
            yaxis=dict(title="構成比 (%)", ticksuffix="%"),
            hovermode="x unified",
            legend=dict(orientation="h", y=-0.22, font=dict(size=10)),
            margin=dict(l=10, r=10, t=40, b=30),
        )
        _apply_dark(fig2)
        st.plotly_chart(fig2, use_container_width=True)

    # ===== 期間中の最大変動銘柄（構成比ベース） =====
    if movers.get("status") == "ok":
        st.markdown(f"##### 📊 {label}中の構成比変動ランキング（継続保有銘柄のみ）")
        col_g, col_l = st.columns(2)

        with col_g:
            st.markdown("**⬆️ 構成比UP（Top15）**")
            if movers["gainers"]:
                df_g = pd.DataFrame(movers["gainers"])
                df_g = df_g[["code", "name", "weight_from", "weight_to", "weight_diff", "shares_change_pct"]].copy()
                df_g.columns = ["コード", "銘柄名", "期初構成比(%)", "期末構成比(%)", "構成比差(pp)", "株数変化(%)"]
                st.dataframe(
                    df_g, use_container_width=True, hide_index=True,
                    column_config={
                        "期初構成比(%)": st.column_config.NumberColumn(format="%.3f"),
                        "期末構成比(%)": st.column_config.NumberColumn(format="%.3f"),
                        "構成比差(pp)": st.column_config.NumberColumn(format="+%.3f"),
                        "株数変化(%)": st.column_config.NumberColumn(format="+%.2f%%"),
                    },
                )
            else:
                st.caption("なし")

        with col_l:
            st.markdown("**⬇️ 構成比DOWN（Top15）**")
            if movers["losers"]:
                df_l = pd.DataFrame(movers["losers"])
                df_l = df_l[["code", "name", "weight_from", "weight_to", "weight_diff", "shares_change_pct"]].copy()
                df_l.columns = ["コード", "銘柄名", "期初構成比(%)", "期末構成比(%)", "構成比差(pp)", "株数変化(%)"]
                st.dataframe(
                    df_l, use_container_width=True, hide_index=True,
                    column_config={
                        "期初構成比(%)": st.column_config.NumberColumn(format="%.3f"),
                        "期末構成比(%)": st.column_config.NumberColumn(format="%.3f"),
                        "構成比差(pp)": st.column_config.NumberColumn(format="%.3f"),
                        "株数変化(%)": st.column_config.NumberColumn(format="%.2f%%"),
                    },
                )
            else:
                st.caption("なし")

    # ===== 新規・除外（期間内） =====
    if movers.get("status") == "ok" and (movers["new"] or movers["removed"]):
        st.divider()
        st.markdown(f"##### 🆕 {label}中の新規組入・除外")
        col_n, col_r = st.columns(2)
        with col_n:
            st.markdown(f"**🆕 新規組入（{len(movers['new'])}銘柄）**")
            if movers["new"]:
                df_n = pd.DataFrame(movers["new"])
                df_n["評価額(億)"] = df_n["market_value"].apply(lambda v: f"{v / 1e8:.2f}")
                df_n = df_n[["code", "name", "shares", "評価額(億)", "weight"]]
                df_n.columns = ["コード", "銘柄名", "株数", "評価額(億)", "構成比(%)"]
                st.dataframe(df_n, use_container_width=True, hide_index=True)
            else:
                st.caption("なし")
        with col_r:
            st.markdown(f"**❌ 除外（{len(movers['removed'])}銘柄）**")
            if movers["removed"]:
                df_r = pd.DataFrame(movers["removed"])
                df_r["評価額(億)"] = df_r["market_value"].apply(lambda v: f"{v / 1e8:.2f}")
                df_r = df_r[["code", "name", "shares", "評価額(億)", "weight"]]
                df_r.columns = ["コード", "銘柄名", "株数", "評価額(億)", "構成比(%)"]
                st.dataframe(df_r, use_container_width=True, hide_index=True)
            else:
                st.caption("なし")


def _render_timeline(summary: dict):
    """銘柄別タイムライン"""
    st.markdown("#### 📈 銘柄別タイムライン")

    if summary["total_snapshots"] < 2:
        st.info("タイムライン表示には2日分以上のデータが必要です。")
        return

    # 最新日のTop20から選択
    top20 = summary["top20"]
    if not top20:
        st.info("データがありません")
        return

    options = [f"{h['code']} {h['name']}" for h in top20]
    code_map = {f"{h['code']} {h['name']}": h["code"] for h in top20}

    selected = st.selectbox(
        "銘柄を選択（最新日のTop20）",
        options,
        key="etf2083_timeline_select",
    )
    if not selected:
        return
    code = code_map[selected]

    tl = get_timeline(code)
    if not tl:
        st.warning(f"{code} のタイムラインデータなし")
        return

    df = pd.DataFrame(tl)
    df["fetch_date"] = pd.to_datetime(df["fetch_date"])

    # 3段チャート: 株数 / 評価額 / 構成比
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["fetch_date"], y=df["shares"],
        mode="lines+markers", name="保有株数",
        line=dict(color=COLORS[0], width=2.5),
        marker=dict(size=6),
        yaxis="y1",
    ))
    fig.add_trace(go.Scatter(
        x=df["fetch_date"], y=df["market_value"] / 1e8,
        mode="lines+markers", name="評価額(億円)",
        line=dict(color=COLORS[2], width=2.5, dash="dash"),
        marker=dict(size=6),
        yaxis="y2",
    ))
    fig.update_layout(
        height=420,
        xaxis=dict(title="日付"),
        yaxis=dict(title="保有株数", side="left"),
        yaxis2=dict(title="評価額(億円)", overlaying="y", side="right"),
        hovermode="x unified",
        margin=dict(l=10, r=10, t=30, b=30),
    )
    _apply_dark(fig)
    st.plotly_chart(fig, use_container_width=True)

    # 構成比チャート
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=df["fetch_date"], y=df["weight"],
        mode="lines+markers", fill="tozeroy",
        line=dict(color=COLORS[1], width=2.5),
        marker=dict(size=6),
        fillcolor="rgba(124,58,237,0.18)",
        name="構成比(%)",
    ))
    fig2.update_layout(
        height=260,
        xaxis=dict(title="日付"),
        yaxis=dict(title="構成比 (%)"),
        margin=dict(l=10, r=10, t=30, b=30),
        showlegend=False,
    )
    _apply_dark(fig2)
    st.plotly_chart(fig2, use_container_width=True)


def _render_new_and_removed(summary: dict):
    """全期間の新規組入・除外銘柄"""
    st.markdown(f"#### 🆕 全期間の変化（{summary['date_first']} → {summary['date_last']}）")

    if summary["total_snapshots"] < 2:
        st.info("2日分以上のデータが必要です。")
        return

    col_new, col_rm = st.columns(2)
    with col_new:
        st.markdown(f"##### 🆕 新規組入 ({len(summary['new_since_start'])}銘柄)")
        if summary["new_since_start"]:
            latest = get_holdings(summary["date_last"])
            code_set = set(summary["new_since_start"])
            filtered = [h for h in latest if h["code"] in code_set]
            df = pd.DataFrame(filtered)
            if not df.empty:
                df["評価額(億)"] = df["market_value"].apply(lambda v: f"{v / 1e8:.2f}")
                df = df[["code", "name", "shares", "stock_price", "評価額(億)", "weight"]]
                df.columns = ["コード", "銘柄名", "株数", "株価", "評価額(億)", "構成比(%)"]
                st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("なし")

    with col_rm:
        st.markdown(f"##### ❌ 除外 ({len(summary['removed_since_start'])}銘柄)")
        if summary["removed_since_start"]:
            first = get_holdings(summary["date_first"])
            code_set = set(summary["removed_since_start"])
            filtered = [h for h in first if h["code"] in code_set]
            df = pd.DataFrame(filtered)
            if not df.empty:
                df["評価額(億)"] = df["market_value"].apply(lambda v: f"{v / 1e8:.2f}")
                df = df[["code", "name", "shares", "stock_price", "評価額(億)", "weight"]]
                df.columns = ["コード", "銘柄名", "株数", "株価", "評価額(億)", "構成比(%)"]
                st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("なし")
