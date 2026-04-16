"""明日上がりそうな銘柄 スコアリングエンジン

全データソースを統合分析し、プライム/スタンダード/グロース別に
明日上昇期待の銘柄をスコア付きで返す。

データソース（5層分析）:
1. 売買代金ランキング — 機関投資家の注目度
2. 値上がり率・出来高増加率 — モメンタム
3. 米国セクターETF — テーマ別追い風/逆風
4. 米国主要指数 — マクロ環境（SOX/NASDAQ/VIX等）
5. テーマ人気度 — 1,578テーマへの資金集中度
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from market_ranking import fetch_ranking_via_read_html
from us_sector_perf import fetch_us_sector_performance, ETFPerformance
from sector_forecast import THEME_ETF_KEYWORDS, compute_us_etf_bonus


# ------------------------------------------------------------------
# スコアリング定数
# ------------------------------------------------------------------

WEIGHTS = {
    "trading_value": 25,   # 売買代金ランク
    "momentum": 25,        # 値動き + 出来高
    "us_theme": 25,        # 米国テーマ連動
    "theme_heat": 15,      # テーマ集中度
    "macro": 10,           # マクロ環境
}


@dataclass
class StockSignal:
    """1銘柄の分析シグナル"""
    code: str
    name: str
    market: str
    price: float = 0.0
    change_pct: float = 0.0
    trading_value: float = 0.0       # 売買代金(円)

    # スコア内訳
    score_trading_value: float = 0.0  # 売買代金スコア (0-100)
    score_momentum: float = 0.0       # モメンタムスコア (0-100)
    score_us_theme: float = 0.0       # 米国テーマ連動スコア (0-100)
    score_theme_heat: float = 0.0     # テーマ集中度スコア (0-100)
    score_macro: float = 0.0          # マクロスコア (0-100)

    total_score: float = 0.0
    signals: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)


# ------------------------------------------------------------------
# 1. データ取得（まとめて取得）
# ------------------------------------------------------------------

def _fetch_rankings() -> dict[str, pd.DataFrame]:
    """売買代金 + 値上がり + 出来高増加率を3市場から取得"""
    results = {}
    for rtype in ("売買代金上位", "値上がり率", "出来高増加率"):
        frames = []
        for mkey in ("all", "tokyo2", "tokyog"):
            pages = 4 if mkey == "all" else 2
            df = fetch_ranking_via_read_html(rtype, market=mkey, pages=pages)
            if not df.empty:
                frames.append(df)
        if frames:
            combined = pd.concat(frames, ignore_index=True)
            combined = combined.drop_duplicates(subset=["コード"], keep="first")
            results[rtype] = combined
    return results


# ------------------------------------------------------------------
# 2. 個別スコア計算
# ------------------------------------------------------------------

def _score_trading_value(code: str, tv_df: pd.DataFrame) -> tuple[float, str | None]:
    """売買代金ランクからスコア（上位ほど高い）"""
    if tv_df.empty:
        return 0.0, None
    row = tv_df[tv_df["コード"] == code]
    if row.empty:
        return 0.0, None
    rank = int(row.iloc[0].get("順位", 999))
    if rank <= 10:
        score = 100
    elif rank <= 30:
        score = 85
    elif rank <= 50:
        score = 70
    elif rank <= 100:
        score = 55
    else:
        score = 35
    return score, f"売買代金{rank}位"


def _score_momentum(
    code: str,
    change_pct: float,
    rise_df: pd.DataFrame,
    vol_df: pd.DataFrame,
) -> tuple[float, list[str]]:
    """値動き + 出来高からモメンタムスコア"""
    score = 50.0  # ベース
    signals = []

    # 値上がり率ランキングに入っている = モメンタムあり
    if not rise_df.empty:
        row = rise_df[rise_df["コード"] == code]
        if not row.empty:
            rank = int(row.iloc[0].get("順位", 999))
            if rank <= 20:
                score += 30
                signals.append(f"値上がり率{rank}位")
            elif rank <= 50:
                score += 20
                signals.append(f"値上がり率{rank}位")
            else:
                score += 10

    # 出来高急増 = 注目集中
    if not vol_df.empty:
        row = vol_df[vol_df["コード"] == code]
        if not row.empty:
            rank = int(row.iloc[0].get("順位", 999))
            vol_rate = row.iloc[0].get("出来高増加率(%)", 0)
            if rank <= 30:
                score += 25
                signals.append(f"出来高急増{rank}位({vol_rate:.0f}%増)")
            elif rank <= 100:
                score += 15

    # 前日比が適度にプラス (+1%〜+8%) は良いシグナル
    if 1.0 <= change_pct <= 8.0:
        score += 15
    elif 0 < change_pct < 1.0:
        score += 5
    elif change_pct > 15.0:
        score -= 20  # 過熱ペナルティ
        signals.append("⚠️過熱注意")
    elif change_pct < -3.0:
        score -= 15

    return max(0, min(100, score)), signals


def _score_us_theme(
    themes: list[str],
    etf_perfs: dict[str, ETFPerformance] | None,
) -> tuple[float, list[str]]:
    """米国セクターETF連動スコア"""
    if not etf_perfs or not themes:
        return 50.0, []

    total_bonus = 0.0
    signals = []
    for theme in themes:
        bonus, reasons = compute_us_etf_bonus(theme, etf_perfs)
        if bonus != 0:
            total_bonus += bonus
            signals.extend(reasons)

    # clamp & normalize: -30〜+30 → 20〜80
    clamped = max(-30, min(30, total_bonus))
    score = 50 + clamped * (50 / 30)

    # 重複排除
    signals = list(dict.fromkeys(signals))[:3]
    return max(0, min(100, score)), signals


def _score_theme_heat(
    themes: list[str],
    tv_df: pd.DataFrame,
    ticker_to_themes: dict[str, list[str]],
) -> tuple[float, str | None]:
    """テーマ集中度: 銘柄が属するテーマに資金が集中しているか"""
    if not themes or tv_df.empty:
        return 50.0, None

    # 売買代金ランキング内の銘柄コード集合
    hot_codes = set(tv_df["コード"].astype(str).tolist())

    # 各テーマの「ヒット率」（ランキング入り銘柄の割合）
    heat_scores = []
    hottest_theme = ""
    best_heat = 0
    for theme in themes:
        # テーマ内の銘柄コードを取得
        theme_codes = set()
        for code, t_list in ticker_to_themes.items():
            if theme in t_list:
                theme_codes.add(code)
        if not theme_codes:
            continue
        hit_count = len(theme_codes & hot_codes)
        heat = hit_count / len(theme_codes) * 100
        heat_scores.append(heat)
        if heat > best_heat:
            best_heat = heat
            hottest_theme = theme

    if not heat_scores:
        return 50.0, None

    avg_heat = sum(heat_scores) / len(heat_scores)
    # normalize: 0-30% → 30-100 score
    score = 30 + min(avg_heat, 30) * (70 / 30)

    signal = f"注目テーマ:{hottest_theme}" if hottest_theme and best_heat > 5 else None
    return min(100, score), signal


def _score_macro(us_snapshot: dict | None) -> tuple[float, list[str]]:
    """マクロ環境スコア（米国主要指数）"""
    if not us_snapshot:
        return 50.0, []

    score = 50.0
    signals = []

    for key, label, weight in [
        ("sox", "SOX", 8),
        ("nasdaq", "NASDAQ", 6),
        ("sp500", "S&P500", 5),
        ("dow", "NYダウ", 4),
        ("vix", "VIX", -7),  # VIX上昇は悪材料
        ("usdjpy", "ドル円", 3),
    ]:
        val = us_snapshot.get(key)
        if val is None:
            continue
        chg = val.get("change_pct", 0)
        if chg is None:
            continue
        contrib = chg * weight
        score += contrib
        if abs(chg) > 0.5:
            direction = "↑" if chg > 0 else "↓"
            signals.append(f"{label}{direction}{abs(chg):.1f}%")

    return max(0, min(100, score)), signals[:3]


# ------------------------------------------------------------------
# 3. メインエントリポイント
# ------------------------------------------------------------------

def compute_tomorrow_picks(
    ticker_to_themes: dict[str, list[str]],
    etf_perfs: dict[str, ETFPerformance] | None = None,
    us_snapshot: dict | None = None,
) -> dict[str, pd.DataFrame]:
    """全データソースを統合分析し、市場別の「明日上がりそう」銘柄を返す

    Returns:
        {"プライム": df, "スタンダード": df, "グロース": df}
        各df columns: [順位, コード, 銘柄名, 総合スコア, 取引値, 前日比(%),
                       売買代金(億円), シグナル, 注目テーマ,
                       S売買, Sモメ, S米国, Sテーマ, Sマクロ]
    """
    # --- データ取得 ---
    rankings = _fetch_rankings()
    tv_df = rankings.get("売買代金上位", pd.DataFrame())
    rise_df = rankings.get("値上がり率", pd.DataFrame())
    vol_df = rankings.get("出来高増加率", pd.DataFrame())

    if tv_df.empty:
        return {"プライム": pd.DataFrame(), "スタンダード": pd.DataFrame(), "グロース": pd.DataFrame()}

    # マクロスコア（全銘柄共通）
    macro_score, macro_signals = _score_macro(us_snapshot)

    # --- 全銘柄をスコアリング ---
    stocks: list[StockSignal] = []

    for _, row in tv_df.iterrows():
        code = str(row["コード"]).strip()
        name = str(row.get("名称", ""))
        market = str(row.get("市場", ""))
        price = float(row.get("取引値", 0) or 0)
        chg = float(row.get("前日比率(%)", 0) or 0)
        tv = float(row.get("売買代金", 0) or 0)
        themes = ticker_to_themes.get(code, [])

        sig = StockSignal(
            code=code, name=name, market=market,
            price=price, change_pct=chg, trading_value=tv,
            themes=themes[:5],  # 表示用に上位5テーマ
        )

        # 各層スコア
        sig.score_trading_value, s1 = _score_trading_value(code, tv_df)
        sig.score_momentum, s2_list = _score_momentum(code, chg, rise_df, vol_df)
        sig.score_us_theme, s3_list = _score_us_theme(themes, etf_perfs)
        sig.score_theme_heat, s4 = _score_theme_heat(themes, tv_df, ticker_to_themes)
        sig.score_macro = macro_score

        # シグナル集約
        all_signals = []
        if s1:
            all_signals.append(s1)
        all_signals.extend(s2_list)
        all_signals.extend(s3_list)
        if s4:
            all_signals.append(s4)
        all_signals.extend(macro_signals)
        sig.signals = all_signals[:5]

        # 総合スコア
        sig.total_score = (
            sig.score_trading_value * WEIGHTS["trading_value"]
            + sig.score_momentum * WEIGHTS["momentum"]
            + sig.score_us_theme * WEIGHTS["us_theme"]
            + sig.score_theme_heat * WEIGHTS["theme_heat"]
            + sig.score_macro * WEIGHTS["macro"]
        ) / 100

        stocks.append(sig)

    # --- 市場別に分類 ---
    MARKET_MAP = {
        "東証PRM": "プライム",
        "東証STD": "スタンダード",
        "東証GRT": "グロース",
    }

    result = {}
    for market_code, market_name in MARKET_MAP.items():
        market_stocks = [s for s in stocks if s.market == market_code]
        market_stocks.sort(key=lambda x: x.total_score, reverse=True)

        rows = []
        for i, s in enumerate(market_stocks[:50], 1):
            rows.append({
                "順位": i,
                "コード": s.code,
                "銘柄名": s.name,
                "総合スコア": round(s.total_score, 1),
                "取引値": s.price,
                "前日比(%)": round(s.change_pct, 2),
                "売買代金(億円)": int(s.trading_value / 1e8),
                "シグナル": " / ".join(s.signals) if s.signals else "—",
                "注目テーマ": ", ".join(s.themes[:3]) if s.themes else "—",
                "S売買": round(s.score_trading_value, 0),
                "Sモメ": round(s.score_momentum, 0),
                "S米国": round(s.score_us_theme, 0),
                "Sテーマ": round(s.score_theme_heat, 0),
                "Sマクロ": round(s.score_macro, 0),
            })
        result[market_name] = pd.DataFrame(rows)

    return result
