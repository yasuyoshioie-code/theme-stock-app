import io
import os
import re
import time as _time
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# デフォルトのセクターデータファイル（アプリ内蔵）
DEFAULT_XLSX = os.path.join(os.path.dirname(__file__), "default_sectors.xlsx")

from data_loader import load_sector_data, get_all_tickers, get_sector_tickers
from market_data import fetch_market_data_with_progress
from analysis import (
    aggregate_by_sector,
    get_sector_summary,
    get_stock_detail,
    get_momentum_ranking,
    get_period_comparison,
    get_hot_sectors,
    get_stock_momentum,
)
from charts import (
    sector_bar_chart,
    timeseries_chart,
    momentum_bar_chart,
    week_change_bar_chart,
    period_change_bar_chart,
    comparison_bar_chart,
    normalized_chart,
    stock_detail_bar,
    stock_momentum_bar_chart,
    stock_change_heatmap,
    market_ranking_bar,
)
from market_ranking import (
    RANKING_TYPES,
    MARKET_OPTIONS,
    TERM_OPTIONS,
    CATEGORY_ORDER,
    get_ranking_categories,
    fetch_ranking_via_read_html,
    fetch_multiple_rankings,
)
from news_feed import (
    NEWS_SOURCES,
    fetch_all_news,
    get_source_names,
    get_default_sources,
    get_source_icon,
    get_source_color,
)
from disclosure import (
    fetch_disclosure,
    get_category_color,
    check_new_disclosures,
)
from shikiho_csv import (
    CsvType,
    detect_csv_type,
    load_stock_price_csv,
    load_watchlist_csv,
    load_generic_csv,
    stock_price_candlestick,
    stock_price_summary,
    watchlist_profit_chart,
)
from world_indices import (
    fetch_world_indices,
    get_region_color,
    REGION_ORDER,
)

st.set_page_config(
    page_title="テーマ株セクター 売買代金ダッシュボード",
    page_icon="📊",
    layout="wide",
)

# ブラウザ翻訳プロンプトを抑制（lang="ja" をHTMLに注入）
st.markdown(
    '<meta name="google" content="notranslate">',
    unsafe_allow_html=True,
)
import streamlit.components.v1 as components
components.html(
    '<script>document.documentElement.lang="ja";</script>',
    height=0,
)

st.title("テーマ株セクター 売買代金ダッシュボード")

# --- サイドバー ---
with st.sidebar:
    st.header("設定")

    # デフォルトデータの有無を表示
    has_default = os.path.exists(DEFAULT_XLSX)
    if has_default:
        st.success("✅ 内蔵データ: テーマ株40セクター")
    uploaded_file = st.file_uploader(
        "別のデータで上書き（任意）",
        type=["xlsx"],
        help="アップロードしなければ内蔵の40セクターデータを使用します",
    )

    st.divider()

    # 期間選択
    period_preset = st.selectbox(
        "期間プリセット",
        ["1週間", "1ヶ月", "3ヶ月", "6ヶ月", "1年", "カスタム"],
        index=1,
    )

    period_map = {
        "1週間": 7,
        "1ヶ月": 30,
        "3ヶ月": 90,
        "6ヶ月": 180,
        "1年": 365,
    }

    if period_preset == "カスタム":
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("開始日", datetime.now() - timedelta(days=30))
        with col2:
            end_date = st.date_input("終了日", datetime.now())
    else:
        days = period_map[period_preset]
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

    st.divider()

    # 集計単位
    freq = st.radio("集計単位", ["日次", "週次", "月次"], horizontal=True)
    freq_map = {"日次": "D", "週次": "W", "月次": "M"}

# --- テンプレート生成 ---
@st.cache_data
def generate_template() -> bytes:
    """サンプル入りテンプレートxlsxをメモリ上で生成"""
    themes = {
        "半導体": [
            ("6857", "アドバンテスト"),
            ("6920", "レーザーテック"),
            ("8035", "東京エレクトロン"),
            ("6146", "ディスコ"),
            ("6723", "ルネサスエレクトロニクス"),
        ],
        "AI関連": [
            ("9984", "ソフトバンクグループ"),
            ("6758", "ソニーグループ"),
            ("6501", "日立製作所"),
            ("6702", "富士通"),
            ("6861", "キーエンス"),
        ],
        "防衛": [
            ("7011", "三菱重工業"),
            ("7012", "川崎重工業"),
            ("7721", "東京計器"),
            ("6208", "石川製作所"),
            ("4274", "細谷火工"),
        ],
    }
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, stocks in themes.items():
            df = pd.DataFrame(stocks, columns=["証券コード", "銘柄名"])
            df.to_excel(writer, sheet_name=name, index=False)
    return buf.getvalue()


# --- メインコンテンツ ---
# データソース決定: アップロード優先、なければ内蔵データ
if uploaded_file is not None:
    data_source = uploaded_file
    data_label = "アップロードデータ"
elif os.path.exists(DEFAULT_XLSX):
    data_source = DEFAULT_XLSX
    data_label = "内蔵データ（テーマ株40セクター）"
else:
    st.info("サイドバーからテーマ株スプレッドシート (.xlsx) をアップロードしてください。")
    st.markdown(
        """
        ### スプレッドシートの形式
        - **1シート = 1テーマセクター**（シート名がセクター名になります）
        - 各シートには「証券コード」「銘柄名」列を入れてください

        | 証券コード | 銘柄名 |
        |---|---|
        | 6857 | アドバンテスト |
        | 6920 | レーザーテック |
        | 8035 | 東京エレクトロン |
        """
    )
    st.download_button(
        label="📥 テンプレートをダウンロード",
        data=generate_template(),
        file_name="テーマ株テンプレート.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.stop()

st.caption(f"📂 データソース: {data_label}")

# データ読込
sectors = load_sector_data(data_source)
sector_tickers = get_sector_tickers(sectors)
all_tickers = get_all_tickers(sectors)

# サイドバー: セクター選択（データ読込後）
with st.sidebar:
    st.divider()
    selected_sectors = st.multiselect(
        "表示セクター",
        options=list(sectors.keys()),
        default=list(sectors.keys()),
    )

# 読込結果の表示
with st.expander("読み込んだセクター情報", expanded=False):
    for name, df in sectors.items():
        st.markdown(f"**{name}**: {len(df)}銘柄")
        st.dataframe(df[["証券コード", "銘柄名"]].reset_index(drop=True), hide_index=True, height=150)

# データ取得ボタン
if st.button("📈 売買代金データを取得", type="primary", use_container_width=True):
    st.session_state["fetch_triggered"] = True
    st.session_state["start_date"] = pd.Timestamp(start_date).strftime("%Y-%m-%d")
    st.session_state["end_date"] = pd.Timestamp(end_date).strftime("%Y-%m-%d")
    st.session_state["freq"] = freq_map[freq]
    st.session_state["selected_sectors"] = selected_sectors

# 売買代金データの取得（トリガー済みの場合のみ）
has_market_data = False
if st.session_state.get("fetch_triggered"):
    start_str = st.session_state["start_date"]
    end_str = st.session_state["end_date"]
    current_freq = st.session_state["freq"]
    current_sectors = st.session_state["selected_sectors"]

    selected_tickers = set()
    for s in current_sectors:
        if s in sector_tickers:
            selected_tickers.update(sector_tickers[s])
    selected_tickers = sorted(selected_tickers)

    if selected_tickers:
        st.info(f"取得対象: {len(selected_tickers)}銘柄 | 期間: {start_str} 〜 {end_str}")

        data = fetch_market_data_with_progress(
            tickers_tuple=tuple(selected_tickers),
            start_date=start_str,
            end_date=end_str,
        )

        if not data.empty:
            available = sorted(set(data.columns.get_level_values(0))) if isinstance(data.columns, pd.MultiIndex) else []
            st.success(f"取得完了: {len(available)}銘柄 | データ形状: {data.shape}")

            # 集計
            filtered_sector_tickers = {k: v for k, v in sector_tickers.items() if k in current_sectors}
            sector_df = aggregate_by_sector(data, filtered_sector_tickers, freq=current_freq)
            summary = get_sector_summary(sector_df)
            detail = get_stock_detail(data, filtered_sector_tickers, sectors)

            # 変化率・ランキング計算
            momentum = get_momentum_ranking(sector_df)
            comparison = get_period_comparison(sector_df)
            hot_sectors = get_hot_sectors(sector_df, top_n=5)
            stock_momentum = get_stock_momentum(data, filtered_sector_tickers, sectors)
            has_market_data = True
        else:
            st.error("データの取得に失敗しました。期間やセクターを確認してください。")
    else:
        st.warning("セクターが選択されていません。")

# --- タブ表示 ---
# ニュース・市場ランキングは常に表示、売買代金系はデータ取得後に表示
tab8, tab9, tab11, tab10, tab7, tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["📰 ニュース", "📋 適時開示", "🌏 世界の株価", "📙 四季報CSV", "🏆 市場ランキング", "📊 セクター概況", "🔥 盛り上がりランキング", "📈 時系列推移", "🔄 セクター比較", "🗂️ 銘柄別詳細", "🚀 銘柄別変化率"]
)

_NEED_DATA_MSG = "⬆️ 上の「📈 売買代金データを取得」ボタンを押してデータを取得してください。"

# ===== タブ1: セクター概況 =====
with tab1:
    if has_market_data:
        st.plotly_chart(sector_bar_chart(summary), use_container_width=True)
        st.subheader("セクター別サマリー")
        st.dataframe(summary, use_container_width=True)
    else:
        st.info(_NEED_DATA_MSG)

# ===== タブ2: 盛り上がりランキング（新機能） =====
with tab2:
    if has_market_data:
        st.subheader("🔥 セクター盛り上がりランキング")
        st.caption("直近5日変化率・期間後半変化率・vs期間平均 の加重平均でスコア化")

        if not momentum.empty:
            col1, col2 = st.columns([3, 2])
            with col1:
                st.plotly_chart(momentum_bar_chart(momentum), use_container_width=True)
            with col2:
                st.dataframe(momentum, use_container_width=True, height=400)

        st.divider()
        st.subheader("週間・期間 変化率")

        if not comparison.empty:
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(week_change_bar_chart(comparison), use_container_width=True)
            with col2:
                st.plotly_chart(period_change_bar_chart(comparison), use_container_width=True)

            st.subheader("比較データ詳細")
            st.dataframe(comparison, use_container_width=True, hide_index=True)
    else:
        st.info(_NEED_DATA_MSG)

# ===== タブ3: 時系列推移（改良版） =====
with tab3:
    if has_market_data:
        st.subheader("📈 売買代金 時系列推移")

        chart_mode = st.radio(
            "表示モード",
            ["すべて表示", "盛り上がりTop5を強調", "カスタム選択"],
            horizontal=True,
            key="chart_mode",
        )

        if chart_mode == "すべて表示":
            highlight = None
            chart_sectors = current_sectors
        elif chart_mode == "盛り上がりTop5を強調":
            highlight = hot_sectors
            chart_sectors = current_sectors
            st.caption(f"強調セクター: {', '.join(hot_sectors)}")
        else:
            highlight = st.multiselect(
                "強調表示するセクターを選択",
                options=current_sectors,
                default=hot_sectors[:3] if hot_sectors else current_sectors[:3],
                key="highlight_sectors",
            )
            chart_sectors = current_sectors

        st.plotly_chart(
            timeseries_chart(sector_df, chart_sectors, highlight_sectors=highlight),
            use_container_width=True,
        )
    else:
        st.info(_NEED_DATA_MSG)

# ===== タブ4: セクター比較 =====
with tab4:
    if has_market_data:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(
                comparison_bar_chart(sector_df, current_sectors), use_container_width=True
            )
        with col2:
            st.plotly_chart(
                normalized_chart(sector_df, current_sectors), use_container_width=True
            )
    else:
        st.info(_NEED_DATA_MSG)

# ===== タブ5: 銘柄別詳細 =====
with tab5:
    if has_market_data:
        st.plotly_chart(stock_detail_bar(detail), use_container_width=True)
        st.subheader("銘柄別売買代金一覧")
        st.dataframe(detail.reset_index(drop=True), use_container_width=True, hide_index=True)
    else:
        st.info(_NEED_DATA_MSG)

# ===== タブ6: 銘柄別変化率（新機能） =====
with tab6:
    if has_market_data:
        st.subheader("🚀 銘柄別 売買代金変化率ランキング")
        st.caption("前日比・週間変化・月間変化・vs期間平均 の加重平均で急騰スコアを算出")

        if not stock_momentum.empty:
            col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
            with col_f1:
                sector_filter = st.multiselect(
                    "セクターで絞り込み",
                    options=["すべて"] + sorted(stock_momentum["セクター"].unique().tolist()),
                    default=["すべて"],
                    key="stock_momentum_sector_filter",
                )
            with col_f2:
                top_n_select = st.selectbox(
                    "表示件数",
                    [10, 20, 30, 50, 100],
                    index=1,
                    key="stock_momentum_top_n",
                )
            with col_f3:
                sort_col = st.selectbox(
                    "ソート基準",
                    ["急騰スコア", "前日比(%)", "週間変化(%)", "月間変化(%)", "vs平均(%)"],
                    index=0,
                    key="stock_momentum_sort",
                )

            filtered_momentum = stock_momentum.copy()
            if "すべて" not in sector_filter:
                filtered_momentum = filtered_momentum[
                    filtered_momentum["セクター"].isin(sector_filter)
                ]

            filtered_momentum = filtered_momentum.sort_values(
                sort_col, ascending=False
            ).reset_index(drop=True)
            filtered_momentum.index = filtered_momentum.index + 1
            filtered_momentum.index.name = "順位"

            st.markdown(f"**対象銘柄数: {len(filtered_momentum)}**")

            col1, col2 = st.columns([3, 2])
            with col1:
                st.plotly_chart(
                    stock_momentum_bar_chart(filtered_momentum, top_n=top_n_select),
                    use_container_width=True,
                )
            with col2:
                st.dataframe(
                    filtered_momentum.head(top_n_select),
                    use_container_width=True,
                    height=600,
                )

            st.divider()
            st.subheader("変化率ヒートマップ")
            st.plotly_chart(
                stock_change_heatmap(filtered_momentum, top_n=min(top_n_select, 30)),
                use_container_width=True,
            )
        else:
            st.warning("銘柄別の変化率データを計算できませんでした。")
    else:
        st.info(_NEED_DATA_MSG)

# ===== タブ7: 市場ランキング =====
with tab7:
    st.subheader("🏆 市場ランキング（Yahoo Finance Japan）")
    st.caption("Yahoo Finance Japan からリアルタイムのランキングデータを取得します")

    # ランキング設定
    col_r1, col_r2, col_r3 = st.columns([2, 1, 1])

    categories = get_ranking_categories()

    with col_r1:
        # カテゴリ選択
        selected_category = st.selectbox(
            "カテゴリ",
            CATEGORY_ORDER,
            index=0,
            key="ranking_category",
        )
        # ランキング種類
        available_rankings = categories.get(selected_category, [])
        selected_ranking = st.selectbox(
            "ランキング種類",
            available_rankings,
            index=0,
            key="ranking_type",
        )

    with col_r2:
        selected_market = st.selectbox(
            "市場",
            list(MARKET_OPTIONS.keys()),
            index=0,
            key="ranking_market",
        )
        market_code = MARKET_OPTIONS[selected_market]

    with col_r3:
        selected_term = st.selectbox(
            "期間",
            list(TERM_OPTIONS.keys()),
            index=0,
            key="ranking_term",
        )
        term_code = TERM_OPTIONS[selected_term]

        ranking_pages = st.selectbox(
            "取得ページ数",
            [1, 2, 3],
            index=0,
            key="ranking_pages",
            help="1ページ = 約50銘柄",
        )

    # 取得ボタン
    if st.button("📡 ランキングを取得", key="fetch_ranking", use_container_width=True):
        with st.spinner(f"{selected_ranking} を取得中..."):
            ranking_df = fetch_ranking_via_read_html(
                ranking_name=selected_ranking,
                market=market_code,
                term=term_code,
                pages=ranking_pages,
            )
            st.session_state["ranking_data"] = ranking_df
            st.session_state["ranking_name"] = selected_ranking

    # 一括取得ボタン
    st.divider()
    col_batch1, col_batch2 = st.columns([1, 3])
    with col_batch1:
        if st.button("📡 主要ランキング一括取得", key="fetch_all_rankings"):
            quick_rankings = ["値上がり率", "値下がり率", "出来高", "売買代金上位", "ストップ高", "ストップ安"]
            progress_bar = st.progress(0, text="ランキングを取得中...")

            def update_progress(pct, text):
                progress_bar.progress(pct, text=text)

            results = fetch_multiple_rankings(
                ranking_names=quick_rankings,
                market=market_code,
                term=term_code,
                pages=1,
                progress_callback=update_progress,
            )
            st.session_state["batch_rankings"] = results
            progress_bar.empty()

    with col_batch2:
        st.caption("値上がり率・値下がり率・出来高・売買代金上位・ストップ高・ストップ安 を一括取得")

    # --- 個別ランキング表示 ---
    if "ranking_data" in st.session_state and st.session_state["ranking_data"] is not None:
        rdf = st.session_state["ranking_data"]
        rname = st.session_state.get("ranking_name", "ランキング")

        if not rdf.empty:
            st.subheader(f"{rname} ({selected_market} / {selected_term})")
            st.markdown(f"**取得件数: {len(rdf)}銘柄**")

            col1, col2 = st.columns([3, 2])
            with col1:
                st.plotly_chart(
                    market_ranking_bar(rdf, rname, top_n=50),
                    use_container_width=True,
                    key="single_ranking_chart",
                )
            with col2:
                st.dataframe(rdf, use_container_width=True, height=800, hide_index=True, key="single_ranking_df")
        else:
            st.warning(f"{rname} のデータを取得できませんでした。")

    # --- 一括ランキング表示 ---
    if "batch_rankings" in st.session_state:
        st.divider()
        st.subheader("📊 主要ランキング一覧")

        batch_data = st.session_state["batch_rankings"]

        # ランキングごとにフル表示
        ranking_names = [k for k, v in batch_data.items() if not v.empty]
        for idx, rname in enumerate(ranking_names):
            rdf = batch_data[rname]
            st.markdown(f"### {rname} ({len(rdf)}銘柄)")
            col1, col2 = st.columns([3, 2])
            with col1:
                st.plotly_chart(
                    market_ranking_bar(rdf, rname, top_n=50),
                    use_container_width=True,
                    key=f"batch_chart_{idx}_{rname}",
                )
            with col2:
                st.dataframe(rdf, use_container_width=True, height=600, hide_index=True, key=f"batch_df_{idx}_{rname}")
            if idx < len(ranking_names) - 1:
                st.divider()

# ===== タブ8: ニュース =====
with tab8:
    st.subheader("📰 株式ニュースフィード")
    st.caption("主要メディアの最新株式・経済ニュースをリアルタイムで取得")

    # ソース選択・設定
    col_n1, col_n2, col_n3 = st.columns([3, 1, 1])
    with col_n1:
        selected_sources = st.multiselect(
            "ニュースソース",
            options=get_source_names(),
            default=get_default_sources(),
            key="news_sources",
        )
    with col_n2:
        per_page = st.selectbox(
            "1ページ表示件数",
            [50, 100, 200],
            index=1,
            key="news_per_page",
        )
    with col_n3:
        auto_refresh_interval = st.selectbox(
            "自動更新間隔",
            [("OFF", 0), ("1分", 60), ("3分", 180), ("5分", 300), ("10分", 600)],
            index=3,  # デフォルト: 5分
            format_func=lambda x: x[0],
            key="news_auto_interval",
        )
        auto_interval_sec = auto_refresh_interval[1]

    # 自動更新ON/OFFトグル
    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        manual_fetch = st.button("📡 ニュースを取得", key="fetch_news", type="primary", use_container_width=True)
    with col_btn2:
        if auto_interval_sec > 0:
            auto_on = st.toggle("🔄 自動更新ON", value=st.session_state.get("news_auto_on", False), key="news_auto_toggle")
            st.session_state["news_auto_on"] = auto_on
        else:
            auto_on = False
            st.session_state["news_auto_on"] = False
            st.caption("自動更新: OFF")

    # --- ニュース取得関数 ---
    def _do_fetch_news(show_progress=True):
        if not selected_sources:
            st.warning("ソースを1つ以上選択してください。")
            return
        if show_progress:
            progress_bar = st.progress(0, text="ニュースを取得中...")
            def update_news_progress(pct, text):
                progress_bar.progress(pct, text=text)
        else:
            update_news_progress = None

        news_items = fetch_all_news(
            sources=selected_sources,
            progress_callback=update_news_progress,
        )
        if show_progress:
            progress_bar.empty()

        st.session_state["news_items"] = news_items
        st.session_state["news_fetched_at"] = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        st.session_state["news_last_fetch_ts"] = _time.time()
        st.session_state["news_page"] = 1  # 新規取得時はページ1に戻す

    # 手動取得
    if manual_fetch:
        _do_fetch_news(show_progress=True)

    # 自動更新チェック: 前回取得から間隔が過ぎていたら自動取得
    if auto_on and auto_interval_sec > 0:
        last_ts = st.session_state.get("news_last_fetch_ts", 0)
        elapsed = _time.time() - last_ts
        if elapsed >= auto_interval_sec:
            _do_fetch_news(show_progress=True)

    # 自動更新タイマー表示
    if auto_on and auto_interval_sec > 0 and "news_last_fetch_ts" in st.session_state:
        last_ts = st.session_state["news_last_fetch_ts"]
        next_refresh = last_ts + auto_interval_sec
        remaining = int(next_refresh - _time.time())
        if remaining > 0:
            mins, secs = divmod(remaining, 60)
            st.info(f"🔄 自動更新ON（{auto_refresh_interval[0]}間隔） — 次回更新まで {mins}分{secs}秒")
        else:
            st.info(f"🔄 自動更新ON（{auto_refresh_interval[0]}間隔） — 更新中...")

    # ニュース表示
    if "news_items" in st.session_state:
        items = st.session_state["news_items"]
        fetched_at = st.session_state.get("news_fetched_at", "")

        if items:
            st.success(f"取得記事数: {len(items)}件 | 取得時刻: {fetched_at}")

            # ソースフィルタ
            all_sources_in_data = sorted(set(item.source for item in items))
            filter_source = st.multiselect(
                "ソースで絞り込み",
                options=["すべて"] + all_sources_in_data,
                default=["すべて"],
                key="news_filter_source",
            )

            filtered_items = items
            if "すべて" not in filter_source:
                filtered_items = [item for item in items if item.source in filter_source]

            # ページネーション
            total_items = len(filtered_items)
            total_pages = max(1, (total_items + per_page - 1) // per_page)

            # ページ番号の管理
            if "news_page" not in st.session_state:
                st.session_state["news_page"] = 1
            current_page = st.session_state["news_page"]
            current_page = min(current_page, total_pages)

            start_idx = (current_page - 1) * per_page
            end_idx = min(start_idx + per_page, total_items)
            display_items = filtered_items[start_idx:end_idx]

            # ページナビ（上部）
            col_pg1, col_pg2, col_pg3, col_pg4, col_pg5 = st.columns([1, 1, 2, 1, 1])
            with col_pg1:
                if st.button("⏮ 最初", key="news_pg_first", disabled=(current_page <= 1), use_container_width=True):
                    st.session_state["news_page"] = 1
                    st.rerun()
            with col_pg2:
                if st.button("◀ 前へ", key="news_pg_prev", disabled=(current_page <= 1), use_container_width=True):
                    st.session_state["news_page"] = current_page - 1
                    st.rerun()
            with col_pg3:
                st.markdown(
                    f"<div style='text-align:center;padding:8px 0;font-weight:600;'>"
                    f"📄 {current_page} / {total_pages} ページ "
                    f"（{start_idx+1}〜{end_idx}件 / 全{total_items}件）</div>",
                    unsafe_allow_html=True,
                )
            with col_pg4:
                if st.button("次へ ▶", key="news_pg_next", disabled=(current_page >= total_pages), use_container_width=True):
                    st.session_state["news_page"] = current_page + 1
                    st.rerun()
            with col_pg5:
                if st.button("最後 ⏭", key="news_pg_last", disabled=(current_page >= total_pages), use_container_width=True):
                    st.session_state["news_page"] = total_pages
                    st.rerun()

            # --- カードCSS ---
            import html as _html

            _news_css = """
            <style>
            .news-card {
                border: 1px solid #e0e0e0;
                border-radius: 10px;
                padding: 14px 18px;
                margin-bottom: 10px;
                background: #fafafa;
                transition: box-shadow 0.2s, border-color 0.2s;
            }
            .news-card:hover {
                box-shadow: 0 2px 12px rgba(0,0,0,0.10);
                border-color: #b0b0b0;
            }
            .news-card-header {
                display: flex;
                align-items: center;
                gap: 10px;
                margin-bottom: 6px;
                flex-wrap: wrap;
            }
            .news-badge {
                display: inline-block;
                padding: 2px 10px;
                border-radius: 12px;
                font-size: 0.75em;
                font-weight: 600;
                letter-spacing: 0.02em;
                white-space: nowrap;
            }
            .news-age {
                color: #888;
                font-size: 0.80em;
                white-space: nowrap;
            }
            .news-category {
                display: inline-block;
                padding: 1px 8px;
                border-radius: 8px;
                font-size: 0.70em;
                background: #ECEFF1;
                color: #546E7A;
                font-weight: 500;
            }
            .news-title {
                font-size: 1.0em;
                font-weight: 600;
                line-height: 1.45;
                margin-bottom: 4px;
            }
            .news-title a {
                color: #1a1a1a;
                text-decoration: none;
            }
            .news-title a:hover {
                color: #1976D2;
                text-decoration: underline;
            }
            .news-summary {
                color: #666;
                font-size: 0.85em;
                line-height: 1.5;
                margin-top: 2px;
            }
            .news-time {
                color: #aaa;
                font-size: 0.75em;
                margin-top: 4px;
            }
            .news-left-bar {
                border-left: 4px solid;
                padding-left: 14px;
            }
            </style>
            """
            st.markdown(_news_css, unsafe_allow_html=True)

            # --- カード一括レンダリング ---
            cards_html_parts = []
            for idx, item in enumerate(display_items):
                icon = get_source_icon(item.source)
                age = item.age_str()
                time_str = item.published_str()
                bg_color, fg_color = get_source_color(item.source)

                safe_title = _html.escape(item.title)
                safe_source = _html.escape(item.source)
                safe_url = _html.escape(item.url)
                safe_summary = ""
                if item.summary:
                    s = item.summary[:150] + ("..." if len(item.summary) > 150 else "")
                    safe_summary = _html.escape(s)
                safe_category = _html.escape(item.category) if item.category else ""

                card = f"""
                <div class="news-card news-left-bar" style="border-left-color: {bg_color};">
                  <div class="news-card-header">
                    <span class="news-badge" style="background:{bg_color};color:{fg_color};">{icon} {safe_source}</span>
                    {"<span class='news-category'>" + safe_category + "</span>" if safe_category else ""}
                    <span class="news-age">{_html.escape(age)}</span>
                  </div>
                  <div class="news-title">
                    <a href="{safe_url}" target="_blank" rel="noopener noreferrer">{safe_title}</a>
                  </div>
                  {"<div class='news-summary'>" + safe_summary + "</div>" if safe_summary else ""}
                  {"<div class='news-time'>" + _html.escape(time_str) + "</div>" if time_str else ""}
                </div>
                """
                cards_html_parts.append(card)

            # 一括で注入（分割するとStreamlitが重くなるので）
            BATCH = 25
            for i in range(0, len(cards_html_parts), BATCH):
                chunk = "\n".join(cards_html_parts[i:i + BATCH])
                st.markdown(chunk, unsafe_allow_html=True)

            # ページナビ（下部）
            if total_pages > 1:
                col_bpg1, col_bpg2, col_bpg3, col_bpg4, col_bpg5 = st.columns([1, 1, 2, 1, 1])
                with col_bpg1:
                    if st.button("⏮ 最初", key="news_bpg_first", disabled=(current_page <= 1), use_container_width=True):
                        st.session_state["news_page"] = 1
                        st.rerun()
                with col_bpg2:
                    if st.button("◀ 前へ", key="news_bpg_prev", disabled=(current_page <= 1), use_container_width=True):
                        st.session_state["news_page"] = current_page - 1
                        st.rerun()
                with col_bpg3:
                    st.markdown(
                        f"<div style='text-align:center;padding:8px 0;font-weight:600;'>"
                        f"📄 {current_page} / {total_pages} ページ</div>",
                        unsafe_allow_html=True,
                    )
                with col_bpg4:
                    if st.button("次へ ▶", key="news_bpg_next", disabled=(current_page >= total_pages), use_container_width=True):
                        st.session_state["news_page"] = current_page + 1
                        st.rerun()
                with col_bpg5:
                    if st.button("最後 ⏭", key="news_bpg_last", disabled=(current_page >= total_pages), use_container_width=True):
                        st.session_state["news_page"] = total_pages
                        st.rerun()
        else:
            st.warning("ニュースが取得できませんでした。ソースを変更してみてください。")

    # 自動更新: st_autorefresh で定期的にページをリロード
    if auto_on and auto_interval_sec > 0:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(
            interval=auto_interval_sec * 1000,
            limit=None,
            key="news_autorefresh",
        )

# ===== タブ9: 適時開示 =====
with tab9:
    st.subheader("📋 適時開示速報（日経）")
    st.caption("日経電子版から最新の適時開示情報をリアルタイムで取得")

    # 設定行
    col_d1, col_d2, col_d3 = st.columns([1, 1, 1])
    with col_d1:
        disclosure_pages = st.selectbox(
            "取得ページ数",
            [1, 2, 3, 5],
            index=0,
            key="disclosure_pages",
            help="1ページ = 約50件",
        )
    with col_d2:
        disc_auto_interval = st.selectbox(
            "自動更新間隔",
            [("OFF", 0), ("1分", 60), ("3分", 180), ("5分", 300), ("10分", 600)],
            index=3,  # デフォルト: 5分
            format_func=lambda x: x[0],
            key="disc_auto_interval",
        )
        disc_auto_sec = disc_auto_interval[1]
    with col_d3:
        disc_notify = st.toggle(
            "🔔 新着通知ON",
            value=st.session_state.get("disc_notify", True),
            key="disc_notify_toggle",
        )
        st.session_state["disc_notify"] = disc_notify

    # ボタン行
    col_db1, col_db2 = st.columns([1, 1])
    with col_db1:
        disc_manual = st.button("📡 適時開示を取得", key="fetch_disc", type="primary", use_container_width=True)
    with col_db2:
        if disc_auto_sec > 0:
            disc_auto_on = st.toggle("🔄 自動更新ON", value=st.session_state.get("disc_auto_on", False), key="disc_auto_toggle")
            st.session_state["disc_auto_on"] = disc_auto_on
        else:
            disc_auto_on = False
            st.session_state["disc_auto_on"] = False
            st.caption("自動更新: OFF")

    # --- 取得関数 ---
    def _do_fetch_disclosure():
        with st.spinner("適時開示を取得中..."):
            items = fetch_disclosure(pages=disclosure_pages)

        # 新着チェック
        prev_keys = st.session_state.get("disc_prev_keys", set())
        if prev_keys and disc_notify:
            new_items = check_new_disclosures(items, prev_keys)
            if new_items:
                st.toast(f"🔔 新着開示 {len(new_items)}件!", icon="🔔")
                for ni in new_items[:5]:
                    st.toast(f"📄 {ni.company}: {ni.title[:40]}")
                st.session_state["disc_new_keys"] = {ni.unique_key for ni in new_items}
            else:
                st.session_state["disc_new_keys"] = set()
        else:
            st.session_state["disc_new_keys"] = set()

        # キーを保存
        st.session_state["disc_prev_keys"] = {item.unique_key for item in items}
        st.session_state["disc_items"] = items
        st.session_state["disc_fetched_at"] = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        st.session_state["disc_last_fetch_ts"] = _time.time()
        st.session_state["disc_page"] = 1  # ページリセット

    # 手動取得
    if disc_manual:
        _do_fetch_disclosure()

    # 自動更新
    if disc_auto_on and disc_auto_sec > 0:
        last_ts = st.session_state.get("disc_last_fetch_ts", 0)
        elapsed = _time.time() - last_ts
        if elapsed >= disc_auto_sec:
            _do_fetch_disclosure()

    # タイマー表示
    if disc_auto_on and disc_auto_sec > 0 and "disc_last_fetch_ts" in st.session_state:
        last_ts = st.session_state["disc_last_fetch_ts"]
        next_refresh = last_ts + disc_auto_sec
        remaining = int(next_refresh - _time.time())
        if remaining > 0:
            mins, secs = divmod(remaining, 60)
            st.info(f"🔄 自動更新ON（{disc_auto_interval[0]}間隔） — 次回更新まで {mins}分{secs}秒")
        else:
            st.info(f"🔄 自動更新ON（{disc_auto_interval[0]}間隔） — 更新中...")

    # --- 開示カード表示 ---
    if "disc_items" in st.session_state:
        items = st.session_state["disc_items"]
        fetched_at = st.session_state.get("disc_fetched_at", "")
        new_keys = st.session_state.get("disc_new_keys", set())

        if items:
            st.success(f"取得件数: {len(items)}件 | 取得時刻: {fetched_at}")

            # カテゴリフィルタ
            all_cats = sorted(set(item.category for item in items))
            filter_cat = st.multiselect(
                "資料区分で絞り込み",
                options=["すべて"] + all_cats,
                default=["すべて"],
                key="disc_filter_cat",
            )

            # 企業名検索
            search_company = st.text_input(
                "🔍 企業名で検索",
                value="",
                key="disc_search_company",
                placeholder="企業名を入力...",
            )

            filtered = items
            if "すべて" not in filter_cat:
                filtered = [it for it in filtered if it.category in filter_cat]
            if search_company.strip():
                q = search_company.strip()
                filtered = [it for it in filtered if q in it.company or q in it.title]

            # --- ページネーション設定 ---
            disc_per_page = st.selectbox(
                "1ページ表示件数", [50, 100, 200], index=1, key="disc_per_page",
            )
            total_disc_items = len(filtered)
            total_disc_pages = max(1, -(-total_disc_items // disc_per_page))  # ceil

            # フィルタ変更時にページリセット
            disc_filter_key = f"{filter_cat}_{search_company}"
            if st.session_state.get("_disc_filter_key") != disc_filter_key:
                st.session_state["disc_page"] = 1
                st.session_state["_disc_filter_key"] = disc_filter_key

            disc_current_page = st.session_state.get("disc_page", 1)
            disc_current_page = max(1, min(disc_current_page, total_disc_pages))
            st.session_state["disc_page"] = disc_current_page

            disc_start = (disc_current_page - 1) * disc_per_page
            disc_end = min(disc_start + disc_per_page, total_disc_items)
            display_disc = filtered[disc_start:disc_end]

            st.markdown(f"**表示中: {disc_start+1}〜{disc_end}件 / 全{total_disc_items}件（{len(items)}件中）**")

            # ページナビ（上部）
            if total_disc_pages > 1:
                col_dp1, col_dp2, col_dp3, col_dp4, col_dp5 = st.columns([1, 1, 2, 1, 1])
                with col_dp1:
                    if st.button("⏮ 最初", key="disc_pg_first", disabled=(disc_current_page <= 1), use_container_width=True):
                        st.session_state["disc_page"] = 1
                        st.rerun()
                with col_dp2:
                    if st.button("◀ 前へ", key="disc_pg_prev", disabled=(disc_current_page <= 1), use_container_width=True):
                        st.session_state["disc_page"] = disc_current_page - 1
                        st.rerun()
                with col_dp3:
                    st.markdown(
                        f"<div style='text-align:center;padding:8px 0;font-weight:600;'>"
                        f"📄 {disc_current_page} / {total_disc_pages} ページ</div>",
                        unsafe_allow_html=True,
                    )
                with col_dp4:
                    if st.button("次へ ▶", key="disc_pg_next", disabled=(disc_current_page >= total_disc_pages), use_container_width=True):
                        st.session_state["disc_page"] = disc_current_page + 1
                        st.rerun()
                with col_dp5:
                    if st.button("最後 ⏭", key="disc_pg_last", disabled=(disc_current_page >= total_disc_pages), use_container_width=True):
                        st.session_state["disc_page"] = total_disc_pages
                        st.rerun()

            import html as _html

            # 開示カードCSS
            _disc_css = """
            <style>
            .disc-card {
                border: 1px solid #e0e0e0;
                border-radius: 10px;
                padding: 12px 16px;
                margin-bottom: 8px;
                background: #fafafa;
                transition: box-shadow 0.2s, border-color 0.2s;
            }
            .disc-card:hover {
                box-shadow: 0 2px 12px rgba(0,0,0,0.10);
                border-color: #b0b0b0;
            }
            .disc-card.disc-new {
                background: #FFF8E1;
                border-color: #FFB300;
                border-width: 2px;
            }
            .disc-header {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 6px;
                flex-wrap: wrap;
            }
            .disc-badge {
                display: inline-block;
                padding: 2px 10px;
                border-radius: 12px;
                font-size: 0.75em;
                font-weight: 600;
                white-space: nowrap;
            }
            .disc-new-tag {
                display: inline-block;
                padding: 2px 8px;
                border-radius: 8px;
                font-size: 0.70em;
                font-weight: 700;
                background: #FF6F00;
                color: #FFF;
                animation: disc-pulse 1.5s ease-in-out infinite;
            }
            @keyframes disc-pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.6; }
            }
            .disc-time {
                color: #888;
                font-size: 0.80em;
                white-space: nowrap;
            }
            .disc-company {
                font-weight: 700;
                font-size: 0.90em;
                color: #333;
            }
            .disc-title {
                font-size: 0.95em;
                font-weight: 500;
                line-height: 1.45;
                margin-top: 4px;
            }
            .disc-title a {
                color: #1a1a1a;
                text-decoration: none;
            }
            .disc-title a:hover {
                color: #1565C0;
                text-decoration: underline;
            }
            .disc-left-bar {
                border-left: 4px solid;
                padding-left: 14px;
            }
            </style>
            """
            st.markdown(_disc_css, unsafe_allow_html=True)

            cards = []
            for item in display_disc:
                bg, fg = get_category_color(item.category)
                is_new = item.unique_key in new_keys

                safe_title = _html.escape(item.title)
                safe_company = _html.escape(item.company)
                safe_cat = _html.escape(item.category)
                safe_url = _html.escape(item.url) if item.url else ""
                safe_age = _html.escape(item.age_str())
                time_label = _html.escape(f"{item.date_str} {item.time_str}")

                new_tag = '<span class="disc-new-tag">🔔 NEW</span>' if is_new else ""
                card_class = "disc-card disc-left-bar disc-new" if is_new else "disc-card disc-left-bar"

                title_html = f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">{safe_title}</a>' if safe_url else safe_title

                card = f"""
                <div class="{card_class}" style="border-left-color: {bg};">
                  <div class="disc-header">
                    <span class="disc-badge" style="background:{bg};color:{fg};">{safe_cat}</span>
                    <span class="disc-company">{safe_company}</span>
                    {new_tag}
                    <span class="disc-time">{time_label} ({safe_age})</span>
                  </div>
                  <div class="disc-title">
                    {title_html}
                  </div>
                </div>
                """
                cards.append(card)

            # バッチレンダリング
            BATCH = 25
            for i in range(0, len(cards), BATCH):
                chunk = "\n".join(cards[i:i + BATCH])
                st.markdown(chunk, unsafe_allow_html=True)

            # ページナビ（下部）
            if total_disc_pages > 1:
                col_dbp1, col_dbp2, col_dbp3, col_dbp4, col_dbp5 = st.columns([1, 1, 2, 1, 1])
                with col_dbp1:
                    if st.button("⏮ 最初", key="disc_bpg_first", disabled=(disc_current_page <= 1), use_container_width=True):
                        st.session_state["disc_page"] = 1
                        st.rerun()
                with col_dbp2:
                    if st.button("◀ 前へ", key="disc_bpg_prev", disabled=(disc_current_page <= 1), use_container_width=True):
                        st.session_state["disc_page"] = disc_current_page - 1
                        st.rerun()
                with col_dbp3:
                    st.markdown(
                        f"<div style='text-align:center;padding:8px 0;font-weight:600;'>"
                        f"📄 {disc_current_page} / {total_disc_pages} ページ</div>",
                        unsafe_allow_html=True,
                    )
                with col_dbp4:
                    if st.button("次へ ▶", key="disc_bpg_next", disabled=(disc_current_page >= total_disc_pages), use_container_width=True):
                        st.session_state["disc_page"] = disc_current_page + 1
                        st.rerun()
                with col_dbp5:
                    if st.button("最後 ⏭", key="disc_bpg_last", disabled=(disc_current_page >= total_disc_pages), use_container_width=True):
                        st.session_state["disc_page"] = total_disc_pages
                        st.rerun()
        else:
            st.warning("適時開示データを取得できませんでした。")

    # 自動更新: st_autorefresh
    if disc_auto_on and disc_auto_sec > 0:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(
            interval=disc_auto_sec * 1000,
            limit=None,
            key="disc_autorefresh",
        )

# ===== タブ11: 世界の株価 =====
with tab11:
    st.subheader("🌏 世界の株価・為替・商品")
    st.caption("日経平均・NYダウ・為替・商品・仮想通貨のリアルタイムデータ")

    # 設定行
    col_w1, col_w2 = st.columns([1, 1])
    with col_w1:
        world_manual = st.button("📡 世界の株価を取得", key="fetch_world", type="primary", use_container_width=True)
    with col_w2:
        world_auto_interval = st.selectbox(
            "自動更新間隔",
            [("OFF", 0), ("30秒", 30), ("1分", 60), ("3分", 180), ("5分", 300)],
            index=2,  # デフォルト: 1分
            format_func=lambda x: x[0],
            key="world_auto_interval",
        )
        world_auto_sec = world_auto_interval[1]

    # 地域フィルタ
    selected_regions = st.multiselect(
        "表示する地域",
        options=REGION_ORDER,
        default=REGION_ORDER,
        key="world_regions",
    )

    # 取得処理
    def _do_fetch_world():
        with st.spinner("世界の株価を取得中..."):
            items = fetch_world_indices()
        st.session_state["world_items"] = items
        st.session_state["world_fetched_at"] = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        st.session_state["world_last_fetch_ts"] = _time.time()

    if world_manual:
        _do_fetch_world()

    # 自動更新（初回取得後のみ発動）
    if world_auto_sec > 0 and "world_last_fetch_ts" in st.session_state:
        last_ts = st.session_state["world_last_fetch_ts"]
        if _time.time() - last_ts >= world_auto_sec:
            _do_fetch_world()

    # タイマー
    if world_auto_sec > 0 and "world_last_fetch_ts" in st.session_state:
        remaining = int(st.session_state["world_last_fetch_ts"] + world_auto_sec - _time.time())
        if remaining > 0:
            mins, secs = divmod(remaining, 60)
            st.info(f"🔄 自動更新ON（{world_auto_interval[0]}間隔） — 次回更新まで {mins}分{secs}秒")

    # 表示
    if "world_items" in st.session_state:
        items = st.session_state["world_items"]
        fetched_at = st.session_state.get("world_fetched_at", "")

        if items:
            filtered = [it for it in items if it.region in selected_regions]
            st.success(f"取得指標数: {len(filtered)}件 | 取得時刻: {fetched_at}")

            import html as _html

            # CSS
            _world_css = """
            <style>
            .world-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: 10px;
                margin-bottom: 16px;
            }
            .world-card {
                border: 1px solid #e0e0e0;
                border-radius: 10px;
                padding: 12px 16px;
                background: #fafafa;
                transition: box-shadow 0.2s;
            }
            .world-card:hover {
                box-shadow: 0 2px 12px rgba(0,0,0,0.10);
            }
            .world-card.world-up {
                border-left: 4px solid #EF5350;
            }
            .world-card.world-down {
                border-left: 4px solid #26A69A;
            }
            .world-card.world-flat {
                border-left: 4px solid #9E9E9E;
            }
            .world-name {
                font-size: 0.85em;
                font-weight: 600;
                color: #333;
                margin-bottom: 4px;
                display: flex;
                align-items: center;
                gap: 6px;
            }
            .world-region-badge {
                display: inline-block;
                padding: 1px 6px;
                border-radius: 8px;
                font-size: 0.65em;
                font-weight: 600;
            }
            .world-value {
                font-size: 1.35em;
                font-weight: 700;
                color: #1a1a1a;
                margin: 4px 0;
            }
            .world-change {
                font-size: 0.90em;
                font-weight: 600;
            }
            .world-change.up { color: #EF5350; }
            .world-change.down { color: #26A69A; }
            .world-change.flat { color: #9E9E9E; }
            .world-time {
                font-size: 0.70em;
                color: #aaa;
                margin-top: 4px;
            }
            .world-section-title {
                font-size: 1.1em;
                font-weight: 700;
                margin: 16px 0 8px 0;
                padding: 4px 12px;
                border-radius: 6px;
                display: inline-block;
            }
            </style>
            """
            st.markdown(_world_css, unsafe_allow_html=True)

            # 地域ごとにグループ化
            from itertools import groupby
            for region, group_items in groupby(filtered, key=lambda x: x.region):
                bg, fg = get_region_color(region)
                st.markdown(
                    f'<div class="world-section-title" style="background:{bg};color:{fg};">'
                    f'{_html.escape(region)}</div>',
                    unsafe_allow_html=True,
                )

                cards = []
                for item in group_items:
                    if item.is_up:
                        card_class = "world-card world-up"
                        change_class = "up"
                        arrow = "▲"
                    elif item.is_down:
                        card_class = "world-card world-down"
                        change_class = "down"
                        arrow = "▼"
                    else:
                        card_class = "world-card world-flat"
                        change_class = "flat"
                        arrow = "─"

                    safe_name = _html.escape(item.name)
                    safe_flag = _html.escape(item.flag)

                    cards.append(f"""<div class="{card_class}">
  <div class="world-name"><span>{safe_flag}</span> <span>{safe_name}</span></div>
  <div class="world-value">{_html.escape(item.value_str)}</div>
  <div class="world-change {change_class}">{arrow} {_html.escape(item.change_str)} ({_html.escape(item.change_pct_str)})</div>
  <div class="world-time">{_html.escape(item.time_str)}</div>
</div>""")

                grid_html = '<div class="world-grid">' + "\n".join(cards) + '</div>'
                st.markdown(grid_html, unsafe_allow_html=True)
        else:
            st.warning("データを取得できませんでした。")
    else:
        st.info("👆「📡 世界の株価を取得」ボタンを押してください。")

    # 自動更新: st_autorefresh
    if world_auto_sec > 0 and "world_last_fetch_ts" in st.session_state:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(
            interval=world_auto_sec * 1000,
            limit=None,
            key="world_autorefresh",
        )

# ===== タブ10: 四季報CSV分析 =====
with tab10:
    st.subheader("📙 四季報オンライン CSV分析")
    st.caption("四季報オンライン プレミアムからダウンロードしたCSVを読み込んで分析")

    # CSVアップローダー
    st.markdown("""
    **対応CSV:**
    - 📈 **株価CSV** — ローソク足チャート・移動平均線・出来高
    - 📋 **ウォッチリスト一覧CSV** — 損益分析・ポートフォリオ一覧
    - 📊 **指標CSV / 業績CSV** — Chrome拡張からの指標・業績データ
    """)

    shikiho_files = st.file_uploader(
        "四季報CSVをアップロード",
        type=["csv"],
        accept_multiple_files=True,
        key="shikiho_csv_upload",
        help="複数ファイルを同時にアップロード可能",
    )

    if shikiho_files:
        for file_idx, uploaded_csv in enumerate(shikiho_files):
            st.divider()
            file_name = uploaded_csv.name

            try:
                # まず汎用読み込みで種類判定
                raw_df = pd.read_csv(uploaded_csv, encoding="utf-8-sig", nrows=5)
                uploaded_csv.seek(0)
                csv_type = detect_csv_type(raw_df)

                st.markdown(f"### 📄 {file_name}")
                st.caption(f"自動判定: **{csv_type.value}** | サイズ: {uploaded_csv.size:,} bytes")

                if csv_type == CsvType.STOCK_PRICE:
                    # --- 株価CSV ---
                    df = load_stock_price_csv(uploaded_csv)

                    if not df.empty:
                        # サマリーカード
                        stats = stock_price_summary(df)
                        cols = st.columns(len(stats))
                        for i, (label, value) in enumerate(stats.items()):
                            with cols[i % len(cols)]:
                                st.metric(label, value)

                        # ローソク足チャート
                        ticker_name = re.sub(r"_daily.*\.csv$", "", file_name, flags=re.IGNORECASE)
                        fig = stock_price_candlestick(df, title=f"{ticker_name} 株価チャート")
                        st.plotly_chart(fig, use_container_width=True, key=f"shikiho_candle_{file_idx}")

                        # データテーブル
                        with st.expander("📊 生データを表示", expanded=False):
                            st.dataframe(
                                df.reset_index(),
                                use_container_width=True,
                                height=400,
                                key=f"shikiho_price_df_{file_idx}",
                            )
                    else:
                        st.warning("株価データの読み込みに失敗しました。")

                elif csv_type == CsvType.WATCHLIST:
                    # --- ウォッチリスト ---
                    df = load_watchlist_csv(uploaded_csv)

                    if not df.empty:
                        st.success(f"ウォッチリスト: {len(df)}銘柄")

                        # 損益チャート
                        chart = watchlist_profit_chart(df)
                        if chart:
                            st.plotly_chart(chart, use_container_width=True, key=f"shikiho_wl_chart_{file_idx}")

                        # テーブル表示
                        st.dataframe(
                            df,
                            use_container_width=True,
                            height=min(600, len(df) * 35 + 50),
                            hide_index=True,
                            key=f"shikiho_wl_df_{file_idx}",
                        )

                        # 基本統計
                        pnl_col = next((c for c in df.columns if "損益(%)" in c or "損益(%" in c), None)
                        if pnl_col and df[pnl_col].notna().any():
                            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                            with col_s1:
                                st.metric("銘柄数", f"{len(df)}")
                            with col_s2:
                                winners = (df[pnl_col] > 0).sum()
                                st.metric("含み益銘柄", f"{winners}銘柄", delta=f"{winners/len(df)*100:.0f}%")
                            with col_s3:
                                st.metric("最大利益", f"{df[pnl_col].max():+.1f}%")
                            with col_s4:
                                st.metric("最大損失", f"{df[pnl_col].min():+.1f}%")
                    else:
                        st.warning("ウォッチリストの読み込みに失敗しました。")

                elif csv_type in (CsvType.INDICATORS, CsvType.FINANCIAL):
                    # --- 指標/業績CSV ---
                    df = load_generic_csv(uploaded_csv)

                    if not df.empty:
                        label = "指標データ" if csv_type == CsvType.INDICATORS else "業績データ"
                        st.success(f"{label}: {len(df)}銘柄 × {len(df.columns)}項目")

                        # テーブル表示
                        st.dataframe(
                            df,
                            use_container_width=True,
                            height=min(600, len(df) * 35 + 50),
                            hide_index=True,
                            key=f"shikiho_gen_df_{file_idx}",
                        )

                        # 数値列のサマリー
                        numeric_cols = df.select_dtypes(include="number").columns.tolist()
                        if numeric_cols:
                            with st.expander("📊 統計サマリー", expanded=False):
                                st.dataframe(
                                    df[numeric_cols].describe().T.round(2),
                                    use_container_width=True,
                                    key=f"shikiho_gen_stats_{file_idx}",
                                )

                            # ソート機能
                            sort_col = st.selectbox(
                                "並び替え列",
                                options=numeric_cols,
                                index=0,
                                key=f"shikiho_sort_{file_idx}",
                            )
                            sort_order = st.radio(
                                "順序",
                                ["降順", "昇順"],
                                horizontal=True,
                                key=f"shikiho_order_{file_idx}",
                            )
                            sorted_df = df.sort_values(
                                sort_col, ascending=(sort_order == "昇順")
                            ).reset_index(drop=True)
                            sorted_df.index = sorted_df.index + 1
                            sorted_df.index.name = "順位"
                            st.dataframe(
                                sorted_df,
                                use_container_width=True,
                                height=600,
                                key=f"shikiho_sorted_df_{file_idx}",
                            )
                    else:
                        st.warning("データの読み込みに失敗しました。")

                else:
                    # --- 不明なCSV → 汎用表示 ---
                    df = load_generic_csv(uploaded_csv)
                    if not df.empty:
                        st.info(f"CSV種類を自動判定できませんでした。汎用表示します（{len(df)}行 × {len(df.columns)}列）")
                        st.dataframe(
                            df,
                            use_container_width=True,
                            height=min(600, len(df) * 35 + 50),
                            hide_index=True,
                            key=f"shikiho_unk_df_{file_idx}",
                        )
                    else:
                        st.error("CSVの読み込みに失敗しました。")

            except Exception as e:
                st.error(f"❌ {file_name} の読み込みエラー: {e}")

    else:
        # ガイダンス表示
        st.info("👆 四季報オンラインからダウンロードしたCSVファイルをアップロードしてください。")

        st.markdown("""
        #### 📥 CSVの取得方法

        **株価CSV（プレミアム限定）:**
        1. 四季報オンラインで銘柄ページを開く
        2. 「時系列株価」セクションの「株価CSVダウンロード」ボタンをクリック
        3. ダウンロードされたCSVをここにアップロード

        **ウォッチリストCSV:**
        1. ウォッチリストページの「一覧」タブを開く
        2. 「CSVダウンロード」ボタンをクリック

        **指標・業績CSV（Chrome拡張）:**
        1. Chrome拡張「四季報オンライン BrowserExtension」をインストール
        2. ウォッチリストの「指標」or「業績」タブを開く
        3. 拡張機能のCSVボタンでダウンロード

        > 💡 **複数ファイルを同時にアップロード可能です！**
        """)

# フッター
st.divider()
if has_market_data:
    st.caption(f"データ期間: {start_str} 〜 {end_str} | 集計単位: {freq} | データソース: Yahoo Finance (yfinance)")
else:
    st.caption("データソース: Yahoo Finance (yfinance) | ニュース・市場ランキングは売買代金データ取得不要で利用できます")
