"""翌営業日の上昇期待銘柄ランキング

世界最高レベルのトレーダー／アナリスト視点で、10種のテクニカル指標を加重平均し
「NDXスコア」（Next-Day eXpected, 0〜100）を算出する。

設計思想
--------
- 終値の強さ・出来高・モメンタム・RSI・MACD・移動平均整列・ブレイクアウト を総合判断
- 過熱感（RSI>80, 急騰ギャップ）は減点
- 流動性フィルタ（薄商い銘柄除外）
- 明快なスコア + トレーダーコメントで判断根拠を可視化
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ==========================================================
# テクニカル指標計算
# ==========================================================

def _rsi(close: pd.Series, period: int = 14) -> float:
    """RSI (Relative Strength Index) 14期間"""
    if len(close) < period + 1:
        return 50.0
    delta = close.diff().dropna()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]
    if avg_loss == 0 or pd.isna(avg_loss):
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return float(100 - 100 / (1 + rs))


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _macd(close: pd.Series) -> tuple[float, float, float]:
    """MACD, Signal, Histogram の最終値を返す"""
    if len(close) < 35:
        return 0.0, 0.0, 0.0
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    macd = ema12 - ema26
    signal = _ema(macd, 9)
    hist = macd - signal
    return float(macd.iloc[-1]), float(signal.iloc[-1]), float(hist.iloc[-1])


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    """ATR (Average True Range) - ボラティリティ指標"""
    if len(close) < period + 1:
        return 0.0
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


# ==========================================================
# 個別指標スコアリング（各 0〜100）
# ==========================================================

def _score_close_strength(high: float, low: float, close: float) -> float:
    """終値強さ: 高値引け = 100, 安値引け = 0"""
    if high == low:
        return 50.0
    return max(0.0, min(100.0, (close - low) / (high - low) * 100))


def _score_volume_surge(today_vol: float, avg_vol_20: float) -> float:
    """出来高急増: 平均比。1倍=30、2倍=75、3倍以上=100"""
    if avg_vol_20 == 0 or pd.isna(avg_vol_20):
        return 30.0
    ratio = today_vol / avg_vol_20
    if ratio >= 3.0:
        return 100.0
    if ratio >= 2.0:
        return 75.0 + (ratio - 2.0) * 25.0
    if ratio >= 1.5:
        return 55.0 + (ratio - 1.5) * 40.0
    if ratio >= 1.0:
        return 30.0 + (ratio - 1.0) * 50.0
    return max(0.0, ratio * 30.0)


def _score_momentum(change_pct: float, cap: float = 10.0) -> float:
    """モメンタム: ±cap%でクリップ。-cap%=0, 0%=50, +cap%=100"""
    clipped = max(-cap, min(cap, change_pct))
    return (clipped + cap) / (2 * cap) * 100.0


def _score_rsi(rsi: float) -> float:
    """RSI健全性:
    50-70: 最適ゾーン (100点)
    40-50 / 70-80: 注意 (70点)
    30-40 / 80-85: 警戒 (40点)
    <30 or >85: 減点（反発 / 反落警戒）
    """
    if 50 <= rsi <= 70:
        return 100.0
    if 40 <= rsi < 50:
        return 70.0 + (rsi - 40) * 3.0  # 40=70, 49=97
    if 70 < rsi <= 80:
        return 100.0 - (rsi - 70) * 3.0  # 70=100, 80=70
    if 30 <= rsi < 40:
        return 40.0 + (rsi - 30) * 3.0
    if 80 < rsi <= 85:
        return 40.0 - (rsi - 80) * 8.0  # 過熱減点
    if rsi > 85:
        return max(0.0, 40.0 - (rsi - 80) * 8.0)
    # rsi < 30 = 売られすぎ反発期待
    return 30.0


def _score_macd(hist: float, prev_hist: float, close: float) -> float:
    """MACDヒストグラム: 正値&拡大=100, 正値&縮小=65, 負値&拡大=30, 負値&縮小=10"""
    if close == 0:
        return 50.0
    hist_norm = hist / close * 100  # 価格比で正規化
    prev_norm = prev_hist / close * 100

    if hist_norm > 0 and hist_norm > prev_norm:
        return 100.0
    if hist_norm > 0:
        return 65.0
    if hist_norm > prev_norm:
        return 45.0  # ゼロライン接近中
    return 15.0


def _score_ma_alignment(close: float, ma5: float, ma25: float, ma75: float) -> float:
    """移動平均整列:
    パーフェクトオーダー (Close>MA5>MA25>MA75) = 100
    上昇型 (Close>MA5>MA25) = 75
    中立 (Close>MA5) = 50
    弱気 (Close<MA5) = 20
    """
    if any(pd.isna(x) or x == 0 for x in (ma5, ma25, ma75)):
        if pd.notna(ma5) and ma5 > 0:
            return 50.0 if close > ma5 else 25.0
        return 50.0
    if close > ma5 > ma25 > ma75:
        return 100.0
    if close > ma5 > ma25:
        return 75.0
    if close > ma5:
        return 50.0
    return 20.0


def _score_breakout(close: float, high_20d_max: float) -> float:
    """20日高値ブレイクアウト: 終値が20日高値を更新 = 100, 近辺(95%)=70, それ以下=30"""
    if high_20d_max == 0 or pd.isna(high_20d_max):
        return 30.0
    ratio = close / high_20d_max
    if ratio >= 1.0:
        return 100.0
    if ratio >= 0.97:
        return 80.0
    if ratio >= 0.93:
        return 55.0
    return 30.0


def _score_volatility_penalty(day_change_pct: float, atr_pct: float) -> float:
    """ボラティリティ調整:
    1日で+15%以上急騰 = 過熱ペナルティ
    ATRが極端に高い = 減点
    """
    penalty = 0.0
    if day_change_pct > 15:
        penalty += (day_change_pct - 15) * 3
    if atr_pct > 8:
        penalty += (atr_pct - 8) * 2
    return min(penalty, 40.0)


def _classify_ma(close: float, ma5: float, ma25: float, ma75: float) -> str:
    if any(pd.isna(x) for x in (ma5, ma25, ma75)):
        return "計算不可"
    if close > ma5 > ma25 > ma75:
        return "🔥 パーフェクト"
    if close > ma5 > ma25:
        return "🟢 強気"
    if close > ma5:
        return "🟡 中立"
    return "🔴 弱気"


def _classify_macd(hist: float, prev_hist: float) -> str:
    if hist > 0 and hist > prev_hist:
        return "🟢 上昇加速"
    if hist > 0:
        return "🟢 上昇"
    if hist > prev_hist:
        return "🟡 底入れ"
    return "🔴 下落"


def _classify_rsi(rsi: float) -> str:
    if rsi > 80:
        return f"🔴 {rsi:.0f} 過熱"
    if rsi >= 70:
        return f"🟠 {rsi:.0f} 高値警戒"
    if rsi >= 50:
        return f"🟢 {rsi:.0f} 健全"
    if rsi >= 30:
        return f"🟡 {rsi:.0f} 調整"
    return f"🔵 {rsi:.0f} 売られすぎ"


def _trader_note(
    score: float,
    close_strength: float,
    vol_ratio: float,
    rsi: float,
    ma_class: str,
    breakout: bool,
    day_change: float,
) -> str:
    """トレーダーの判断コメント（最大2つ組み合わせ）"""
    notes = []
    if breakout and close_strength > 70:
        notes.append("20日高値更新・高値引け")
    elif close_strength > 80:
        notes.append("高値引けで強い買い残存")
    elif close_strength < 30:
        notes.append("安値引けで弱含み")

    if vol_ratio >= 2.5:
        notes.append(f"出来高{vol_ratio:.1f}倍の急増")
    elif vol_ratio >= 1.5:
        notes.append(f"出来高{vol_ratio:.1f}倍")

    if rsi > 80:
        notes.append("RSI過熱、反落警戒")
    elif rsi < 30:
        notes.append("売られすぎ反発期待")

    if "パーフェクト" in ma_class:
        notes.append("MAパーフェクトオーダー")
    elif "強気" in ma_class:
        notes.append("MA上昇トレンド")

    if day_change > 15:
        notes.append("急騰注意（過熱）")

    if not notes:
        if score >= 70:
            return "総合モメンタム良好"
        if score >= 50:
            return "中立"
        return "弱含み"
    return " / ".join(notes[:3])


# ==========================================================
# メインランキング関数
# ==========================================================

def get_next_day_ranking(
    data: pd.DataFrame,
    sector_tickers: dict[str, list[str]],
    sectors_info: dict[str, pd.DataFrame],
    min_turnover_oku: float = 1.0,
) -> pd.DataFrame:
    """翌営業日の上昇期待度ランキングを返す

    Parameters
    ----------
    data : MultiIndex DataFrame [(ticker, [Open, High, Low, Close, Volume])]
    sector_tickers : {セクター名: [ticker list]}
    sectors_info : {セクター名: DataFrame with 銘柄名}
    min_turnover_oku : 直近売買代金の最低ライン（億円）— 流動性フィルタ

    Returns
    -------
    pd.DataFrame  ランキング済み（NDXスコア降順、1始まりindex）
    """
    if data.empty:
        return pd.DataFrame()

    # ticker -> (sector, name) の逆引き
    ticker_meta = {}
    for sector, tickers in sector_tickers.items():
        info_df = sectors_info.get(sector, pd.DataFrame())
        for tk in tickers:
            name = tk.replace(".T", "")
            if not info_df.empty and "銘柄名" in info_df.columns and "ticker" in info_df.columns:
                m = info_df[info_df["ticker"] == tk]
                if not m.empty:
                    name = m.iloc[0]["銘柄名"]
            ticker_meta[tk] = (sector, name)

    # 指標計算用の重み（合計=1.0）
    weights = {
        "close_strength": 0.18,
        "volume_surge": 0.15,
        "momentum_5d": 0.12,
        "rsi": 0.10,
        "macd": 0.10,
        "ma_alignment": 0.12,
        "breakout": 0.08,
        "turnover_surge": 0.08,
        "momentum_1d": 0.07,
    }

    rows = []

    available_tickers = sorted(set(data.columns.get_level_values(0)))

    for ticker in available_tickers:
        if ticker not in ticker_meta:
            continue
        sector, name = ticker_meta[ticker]

        try:
            close = data[(ticker, "Close")].dropna()
            high = data[(ticker, "High")].dropna()
            low = data[(ticker, "Low")].dropna()
            volume = data[(ticker, "Volume")].dropna()
        except KeyError:
            continue

        if len(close) < 10:
            continue

        # 直近売買代金で流動性フィルタ
        turnover = close * volume
        recent_turnover_oku = float(turnover.iloc[-1] / 1e8) if not turnover.empty else 0.0
        if recent_turnover_oku < min_turnover_oku:
            continue

        # --- 最新値 ---
        last_close = float(close.iloc[-1])
        last_high = float(high.iloc[-1])
        last_low = float(low.iloc[-1])
        last_volume = float(volume.iloc[-1])

        # 前日変化率
        prev_close = float(close.iloc[-2]) if len(close) >= 2 else last_close
        day_change = ((last_close / prev_close - 1) * 100) if prev_close > 0 else 0.0

        # 5日前比
        mom5_base = float(close.iloc[-6]) if len(close) >= 6 else float(close.iloc[0])
        momentum_5d = ((last_close / mom5_base - 1) * 100) if mom5_base > 0 else 0.0

        # 出来高・売買代金 平均（20日）
        avg_vol_20 = float(volume.iloc[-21:-1].mean()) if len(volume) >= 21 else float(volume.mean())
        vol_ratio = (last_volume / avg_vol_20) if avg_vol_20 > 0 else 1.0
        avg_turn_20 = float(turnover.iloc[-21:-1].mean()) if len(turnover) >= 21 else float(turnover.mean())
        turn_ratio = (float(turnover.iloc[-1]) / avg_turn_20) if avg_turn_20 > 0 else 1.0

        # 移動平均
        ma5 = float(close.iloc[-5:].mean()) if len(close) >= 5 else last_close
        ma25 = float(close.iloc[-25:].mean()) if len(close) >= 25 else last_close
        ma75 = float(close.iloc[-75:].mean()) if len(close) >= 75 else last_close

        # 20日高値
        high_20d_max = float(high.iloc[-20:-1].max()) if len(high) >= 21 else float(high.max())
        is_breakout = last_close >= high_20d_max

        # RSI / MACD / ATR
        rsi = _rsi(close)
        macd_val, signal_val, hist = _macd(close)
        prev_hist = _macd(close.iloc[:-1])[2] if len(close) >= 36 else hist
        atr = _atr(high, low, close)
        atr_pct = (atr / last_close * 100) if last_close > 0 else 0.0

        # --- 個別スコア ---
        s_close = _score_close_strength(last_high, last_low, last_close)
        s_vol = _score_volume_surge(last_volume, avg_vol_20)
        s_turn = _score_volume_surge(float(turnover.iloc[-1]), avg_turn_20)
        s_mom5 = _score_momentum(momentum_5d, cap=15.0)
        s_mom1 = _score_momentum(day_change, cap=5.0)
        s_rsi = _score_rsi(rsi)
        s_macd = _score_macd(hist, prev_hist, last_close)
        s_ma = _score_ma_alignment(last_close, ma5, ma25, ma75)
        s_brk = _score_breakout(last_close, high_20d_max)

        # --- 加重平均 ---
        raw_score = (
            s_close * weights["close_strength"]
            + s_vol * weights["volume_surge"]
            + s_mom5 * weights["momentum_5d"]
            + s_rsi * weights["rsi"]
            + s_macd * weights["macd"]
            + s_ma * weights["ma_alignment"]
            + s_brk * weights["breakout"]
            + s_turn * weights["turnover_surge"]
            + s_mom1 * weights["momentum_1d"]
        )

        # ボラティリティペナルティ
        penalty = _score_volatility_penalty(day_change, atr_pct)
        ndx_score = max(0.0, min(100.0, raw_score - penalty))

        ma_class = _classify_ma(last_close, ma5, ma25, ma75)
        macd_class = _classify_macd(hist, prev_hist)
        rsi_class = _classify_rsi(rsi)

        note = _trader_note(
            ndx_score, s_close, vol_ratio, rsi, ma_class, is_breakout, day_change
        )

        rows.append(
            {
                "セクター": sector,
                "銘柄コード": ticker.replace(".T", ""),
                "銘柄名": name,
                "NDXスコア": round(ndx_score, 1),
                "終値": round(last_close, 1),
                "前日比(%)": round(day_change, 2),
                "終値強さ(%)": round(s_close, 0),
                "出来高倍率": round(vol_ratio, 2),
                "売買代金(億円)": round(recent_turnover_oku, 1),
                "5日変化(%)": round(momentum_5d, 2),
                "RSI": rsi_class,
                "MACD": macd_class,
                "MA整列": ma_class,
                "ブレイク": "✅" if is_breakout else "—",
                "トレーダー判断": note,
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values("NDXスコア", ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = "順位"
    return df


# ==========================================================
# セクター別ランキング（任意のセクター絞込用）
# ==========================================================

def filter_ranking_by_sector(df: pd.DataFrame, sectors: list[str]) -> pd.DataFrame:
    """ランキングをセクターで絞り込み"""
    if df.empty or not sectors or "すべて" in sectors:
        return df
    return df[df["セクター"].isin(sectors)].copy()
