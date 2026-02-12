import pandas as pd


def calculate_trading_value(data: pd.DataFrame, ticker: str) -> pd.Series:
    """個別銘柄の売買代金を計算（Close x Volume）"""
    try:
        close = data[(ticker, "Close")]
        volume = data[(ticker, "Volume")]
        return (close * volume).fillna(0)
    except KeyError:
        return pd.Series(dtype=float)


def aggregate_by_sector(
    data: pd.DataFrame,
    sector_tickers: dict[str, list[str]],
    freq: str = "D",
) -> pd.DataFrame:
    """セクター別の売買代金を集計する"""
    result = {}
    for sector, tickers in sector_tickers.items():
        sector_values = pd.DataFrame(index=data.index)
        for ticker in tickers:
            tv = calculate_trading_value(data, ticker)
            if not tv.empty:
                sector_values[ticker] = tv
        if not sector_values.empty:
            result[sector] = sector_values.sum(axis=1)
        else:
            result[sector] = pd.Series(0, index=data.index)

    df = pd.DataFrame(result)

    # リサンプリング
    if freq == "W":
        df = df.resample("W").sum()
    elif freq == "M":
        df = df.resample("ME").sum()

    return df


def get_sector_summary(sector_df: pd.DataFrame) -> pd.DataFrame:
    """セクター別サマリー（合計・平均・最大）を返す"""
    summary = pd.DataFrame(
        {
            "売買代金合計(億円)": sector_df.sum() / 1e8,
            "日次平均(億円)": sector_df.mean() / 1e8,
            "日次最大(億円)": sector_df.max() / 1e8,
        }
    )
    summary = summary.round(1)
    summary = summary.sort_values("売買代金合計(億円)", ascending=False)
    return summary


# ----------------------------------------------------------------
# 変化率・モメンタム分析
# ----------------------------------------------------------------

def get_momentum_ranking(sector_df: pd.DataFrame) -> pd.DataFrame:
    """セクター別の変化率ランキングを計算する

    直近5日 vs 前5日、直近1週間 vs 前1週間、直近期間の後半 vs 前半
    のような比較で「盛り上がり度」を数値化する。
    """
    if sector_df.empty or len(sector_df) < 2:
        return pd.DataFrame()

    n = len(sector_df)
    rows = []

    for sector in sector_df.columns:
        series = sector_df[sector]
        latest_val = series.iloc[-1] / 1e8  # 直近値（億円）

        # --- 直近5日平均 vs その前5日平均 ---
        if n >= 10:
            recent_5 = series.iloc[-5:].mean()
            prev_5 = series.iloc[-10:-5].mean()
        elif n >= 4:
            half = n // 2
            recent_5 = series.iloc[-half:].mean()
            prev_5 = series.iloc[:half].mean()
        else:
            recent_5 = series.iloc[-1]
            prev_5 = series.iloc[0]

        wow_change = _safe_pct(recent_5, prev_5)

        # --- 期間の後半 vs 前半 ---
        mid = n // 2
        first_half = series.iloc[:mid].mean()
        second_half = series.iloc[mid:].mean()
        period_change = _safe_pct(second_half, first_half)

        # --- 直近値 vs 期間平均 ---
        period_avg = series.mean()
        vs_avg = _safe_pct(series.iloc[-1], period_avg)

        # --- 盛り上がりスコア（3つの変化率の加重平均） ---
        score = wow_change * 0.4 + period_change * 0.3 + vs_avg * 0.3

        rows.append(
            {
                "セクター": sector,
                "直近値(億円)": round(latest_val, 1),
                "直近5日変化率": round(wow_change, 1),
                "期間後半変化率": round(period_change, 1),
                "vs期間平均": round(vs_avg, 1),
                "盛り上がりスコア": round(score, 1),
            }
        )

    df = pd.DataFrame(rows)
    df = df.sort_values("盛り上がりスコア", ascending=False).reset_index(drop=True)
    df.index = df.index + 1  # 1始まり
    df.index.name = "順位"
    return df


def get_period_comparison(sector_df: pd.DataFrame) -> pd.DataFrame:
    """直近週 vs 前週、直近月 vs 前月 の比較テーブル"""
    if sector_df.empty or len(sector_df) < 2:
        return pd.DataFrame()

    n = len(sector_df)
    rows = []

    for sector in sector_df.columns:
        series = sector_df[sector]

        # 直近5営業日 vs 前5営業日
        if n >= 10:
            this_week = series.iloc[-5:].sum() / 1e8
            last_week = series.iloc[-10:-5].sum() / 1e8
        else:
            half = max(n // 2, 1)
            this_week = series.iloc[-half:].sum() / 1e8
            last_week = series.iloc[:half].sum() / 1e8

        week_change = _safe_pct(this_week, last_week)

        # 直近半期間 vs 前半期間
        mid = n // 2
        this_period = series.iloc[mid:].sum() / 1e8
        last_period = series.iloc[:mid].sum() / 1e8
        period_change = _safe_pct(this_period, last_period)

        rows.append(
            {
                "セクター": sector,
                "直近週(億円)": round(this_week, 1),
                "前週(億円)": round(last_week, 1),
                "週間変化率(%)": round(week_change, 1),
                "直近半期間(億円)": round(this_period, 1),
                "前半期間(億円)": round(last_period, 1),
                "期間変化率(%)": round(period_change, 1),
            }
        )

    df = pd.DataFrame(rows)
    df = df.sort_values("週間変化率(%)", ascending=False).reset_index(drop=True)
    return df


def get_hot_sectors(sector_df: pd.DataFrame, top_n: int = 5) -> list[str]:
    """盛り上がりスコア上位のセクター名リストを返す"""
    ranking = get_momentum_ranking(sector_df)
    if ranking.empty:
        return list(sector_df.columns)[:top_n]
    return ranking["セクター"].head(top_n).tolist()


def _safe_pct(current: float, previous: float) -> float:
    """安全にパーセンテージ変化を計算"""
    if previous == 0 or pd.isna(previous) or pd.isna(current):
        return 0.0
    return (current - previous) / abs(previous) * 100


def get_stock_detail(
    data: pd.DataFrame,
    sector_tickers: dict[str, list[str]],
    sectors_info: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """銘柄別の売買代金詳細を返す"""
    rows = []
    for sector, tickers in sector_tickers.items():
        info_df = sectors_info.get(sector, pd.DataFrame())
        for ticker in tickers:
            tv = calculate_trading_value(data, ticker)
            total = tv.sum() if not tv.empty else 0
            avg = tv.mean() if not tv.empty else 0

            # 銘柄名を取得
            name = ticker
            if not info_df.empty and "銘柄名" in info_df.columns:
                match = info_df[info_df["ticker"] == ticker]
                if not match.empty:
                    name = match.iloc[0]["銘柄名"]

            rows.append(
                {
                    "セクター": sector,
                    "銘柄コード": ticker.replace(".T", ""),
                    "銘柄名": name,
                    "売買代金合計(億円)": round(total / 1e8, 1),
                    "日次平均(億円)": round(avg / 1e8, 1),
                }
            )

    return pd.DataFrame(rows).sort_values("売買代金合計(億円)", ascending=False)


# ----------------------------------------------------------------
# 銘柄別 売買代金変化率
# ----------------------------------------------------------------

def get_stock_momentum(
    data: pd.DataFrame,
    sector_tickers: dict[str, list[str]],
    sectors_info: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """銘柄別の売買代金変化率を計算する

    - 昨日 vs 5日前平均
    - 直近5日平均 vs 前5日平均（≒週間変化率）
    - 直近5日平均 vs 20日前平均（≒月間変化率）
    """
    if data.empty:
        return pd.DataFrame()

    n = len(data)
    rows = []

    for sector, tickers in sector_tickers.items():
        info_df = sectors_info.get(sector, pd.DataFrame())
        for ticker in tickers:
            tv = calculate_trading_value(data, ticker)
            if tv.empty or tv.sum() == 0:
                continue

            # 銘柄名
            name = ticker.replace(".T", "")
            if not info_df.empty and "銘柄名" in info_df.columns:
                match = info_df[info_df["ticker"] == ticker]
                if not match.empty:
                    name = match.iloc[0]["銘柄名"]

            latest = tv.iloc[-1] / 1e8  # 直近（億円）
            avg_all = tv.mean() / 1e8

            # 直近5日平均
            recent_5 = tv.iloc[-5:].mean() if n >= 5 else tv.mean()
            # 前5日平均（6〜10日前）
            prev_5 = tv.iloc[-10:-5].mean() if n >= 10 else tv.iloc[:max(n // 2, 1)].mean()
            # 20日前付近の5日平均
            prev_20 = tv.iloc[:5].mean() if n >= 20 else tv.iloc[:max(n // 3, 1)].mean()

            # 変化率
            day_change = _safe_pct(tv.iloc[-1], tv.iloc[-2]) if n >= 2 else 0.0
            week_change = _safe_pct(recent_5, prev_5)
            month_change = _safe_pct(recent_5, prev_20)
            vs_avg = _safe_pct(tv.iloc[-1], tv.mean())

            # 総合スコア
            score = day_change * 0.2 + week_change * 0.35 + month_change * 0.25 + vs_avg * 0.2

            rows.append(
                {
                    "セクター": sector,
                    "銘柄コード": ticker.replace(".T", ""),
                    "銘柄名": name,
                    "直近(億円)": round(latest, 2),
                    "日次平均(億円)": round(avg_all, 2),
                    "前日比(%)": round(day_change, 1),
                    "週間変化(%)": round(week_change, 1),
                    "月間変化(%)": round(month_change, 1),
                    "vs平均(%)": round(vs_avg, 1),
                    "急騰スコア": round(score, 1),
                }
            )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values("急騰スコア", ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = "順位"
    return df
