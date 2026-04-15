"""明日盛り上がりそうセクター予測

NDXスコア（銘柄別）をセクター単位で集計し、米国市場の動向を加味して
「明日温度」スコアを算出する。

設計思想
--------
- 銘柄別NDXスコア平均 × 0.7 + 米国補正 × 0.3
- 米国市場の主要指標（NYダウ/NASDAQ/S&P500/SOX/VIX/ドル円/米10年債/WTI）から
  セクターごとの相関ボーナス/ペナルティを適用
- 例: SOX↑ → 半導体系セクターに + / VIX↑ → ディフェンシブに + / ドル円↑ → 輸出関連に +
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


# ==========================================================
# 米国市場 → セクター相関ルール
# ==========================================================
#
# 各ルール: (米国指標コード, 相関係数, 理由の短文)
#   相関係数 > 0  : 米国指標が上昇するとセクターに追い風
#   相関係数 < 0  : 米国指標が上昇するとセクターに逆風（または逆相関）
#
# 指標コードは world_indices.py の INDEX_MAP に準拠
#   211=NYダウ / 212=NASDAQ / 213=S&P500 / 216=FANG+ / 611=SOX / 621=VIX
#   811=米10年債 / 511=ドル円 / 921=WTI原油 / 931=NY金 / 1001=BTC

SECTOR_US_BONUS_RULES: dict[str, list[tuple[str, float, str]]] = {
    # ===== 半導体系（SOX直結）=====
    "半導体": [("611", 1.5, "SOX半導体"), ("212", 0.6, "NASDAQ")],
    "半導体製造装置": [("611", 1.5, "SOX半導体"), ("212", 0.5, "NASDAQ")],
    "半導体部材・部品": [("611", 1.3, "SOX半導体"), ("212", 0.4, "NASDAQ")],
    "パワー半導体": [("611", 1.2, "SOX半導体"), ("212", 0.4, "NASDAQ")],

    # ===== AI/ハイテク（NASDAQ・FANG+）=====
    "人工知能": [("216", 1.3, "FANG+"), ("212", 1.0, "NASDAQ"), ("611", 0.6, "SOX")],
    "フィジカルAI": [("216", 1.2, "FANG+"), ("212", 0.9, "NASDAQ")],
    "SaaS": [("212", 1.2, "NASDAQ"), ("216", 0.6, "FANG+")],
    "データセンター": [("212", 1.0, "NASDAQ"), ("611", 0.8, "SOX")],
    "サイバーセキュリティ": [("212", 1.0, "NASDAQ"), ("216", 0.5, "FANG+")],
    "量子コンピューター": [("212", 1.0, "NASDAQ"), ("611", 0.7, "SOX")],
    "ドローン": [("212", 0.8, "NASDAQ")],
    "ロボット": [("212", 0.8, "NASDAQ"), ("611", 0.5, "SOX")],
    "ゲーム関連": [("212", 0.9, "NASDAQ"), ("216", 0.5, "FANG+")],

    # ===== 金融（米10年債利回り）=====
    "銀行": [("811", 1.4, "米10年債"), ("211", 0.3, "NYダウ")],
    "地方銀行": [("811", 1.4, "米10年債")],

    # ===== 為替感応株 =====
    "円安メリット": [("511", 1.8, "ドル円")],
    "円高メリット": [("511", -1.8, "ドル円")],
    "総合商社": [("921", 1.0, "WTI原油"), ("511", 0.7, "ドル円"), ("211", 0.3, "NYダウ")],

    # ===== エネルギー・商品 =====
    "海底資源": [("921", 1.2, "WTI原油")],
    "レアアース": [("211", 0.4, "NYダウ"), ("921", 0.3, "WTI原油")],
    "レアメタル": [("211", 0.4, "NYダウ"), ("921", 0.3, "WTI原油")],
    "ダイヤモンド": [("211", 0.4, "NYダウ")],
    "水素": [("921", 0.5, "WTI原油"), ("212", 0.4, "NASDAQ")],
    "核融合発電": [("212", 0.7, "NASDAQ")],
    "ペロブスカイト太陽電池": [("212", 0.6, "NASDAQ")],
    "原子力発電": [("921", 0.5, "WTI原油")],
    "電力会社": [("621", 0.5, "VIX恐怖指数")],

    # ===== 金（NY金と正相関）=====
    "金": [("931", 1.5, "NY金"), ("621", 0.4, "VIX恐怖指数")],

    # ===== ディフェンシブ（VIX上昇で買われる）=====
    "食品": [("621", 0.8, "VIX恐怖指数")],
    "食品スーパー": [("621", 0.7, "VIX恐怖指数")],

    # ===== 防衛（地政学リスク=VIX連動）=====
    "防衛": [("621", 1.0, "VIX恐怖指数"), ("211", 0.3, "NYダウ")],

    # ===== インフラ =====
    "国土強靱化": [("211", 0.3, "NYダウ")],
    "建設": [("211", 0.3, "NYダウ")],
    "ゼネコン": [("211", 0.3, "NYダウ")],
    "下水道": [("211", 0.2, "NYダウ")],
    "港湾運送": [("211", 0.4, "NYダウ"), ("921", 0.3, "WTI原油")],

    # ===== 仮想通貨 =====
    "仮想通貨": [("1001", 1.8, "ビットコイン")],

    # ===== 大型指数連動 =====
    "TOPIXコア30": [("211", 0.8, "NYダウ"), ("213", 0.8, "S&P500")],
    "JPX日経400": [("211", 0.6, "NYダウ"), ("213", 0.6, "S&P500")],
    "2025年のIPO": [("212", 0.8, "NASDAQ"), ("216", 0.5, "FANG+")],
}


# ==========================================================
# 米国市場データ処理
# ==========================================================

US_INDICATOR_CODES = {
    "211": "NYダウ",
    "212": "NASDAQ",
    "213": "S&P500",
    "216": "FANG+",
    "611": "SOX半導体",
    "621": "VIX恐怖指数",
    "811": "米10年債",
    "511": "ドル円",
    "921": "WTI原油",
    "931": "NY金",
    "1001": "ビットコイン",
}


@dataclass
class USSnapshot:
    """米国市場スナップショット"""
    items: list  # list[IndexData]
    by_code: dict[str, object]  # code → IndexData

    def get_pct(self, code: str) -> float:
        """指定コードの変化率(%)を返す。データなしは 0.0。"""
        item = self.by_code.get(code)
        if item is None or item.change_pct is None:
            return 0.0
        return float(item.change_pct)

    def mood_score(self) -> tuple[float, str]:
        """総合ムード (-100〜+100) と評価コメントを返す"""
        # ダウ・NASDAQ・S&P500 の平均を主軸にし、VIX と逆相関
        dow = self.get_pct("211")
        nas = self.get_pct("212")
        sp = self.get_pct("213")
        vix = self.get_pct("621")
        sox = self.get_pct("611")

        # 基本: 主要3指数の平均（+2%→+50, -2%→-50 スケール）
        base = (dow + nas + sp) / 3 * 25
        # SOX は半導体セクターへの影響が大きいので加点
        base += sox * 5
        # VIX は逆相関（+10%→-20）
        base -= vix * 2

        score = max(-100.0, min(100.0, base))

        if score >= 40:
            label = "🔥 強気"
        elif score >= 15:
            label = "🟢 やや強気"
        elif score >= -15:
            label = "⚪ 中立"
        elif score >= -40:
            label = "🟠 やや弱気"
        else:
            label = "🔴 弱気"

        return score, label


def make_us_snapshot(world_items: Iterable) -> USSnapshot:
    """fetch_world_indices() の戻り値から USSnapshot を構築"""
    items = [x for x in world_items if x.region == "米国" or x.code in ("511", "921", "931", "1001")]
    by_code = {x.code: x for x in items if x.code in US_INDICATOR_CODES}
    return USSnapshot(items=items, by_code=by_code)


# ==========================================================
# セクター温度計算
# ==========================================================

def compute_us_bonus(sector: str, snapshot: USSnapshot) -> tuple[float, list[str]]:
    """セクターごとの米国補正スコアと理由リストを返す

    Returns:
        (bonus_score, reason_list)
        bonus_score: -30〜+30 程度に収まるように設計
    """
    rules = SECTOR_US_BONUS_RULES.get(sector)
    if not rules:
        return 0.0, []

    total = 0.0
    reasons: list[str] = []

    for code, coef, label in rules:
        pct = snapshot.get_pct(code)
        if abs(pct) < 0.05:
            continue
        contrib = pct * coef * 5  # スケーリング係数
        total += contrib

        # 理由には影響の大きかった指標のみ残す
        if abs(contrib) >= 1.0:
            sign = "↑" if pct > 0 else "↓"
            reasons.append(f"{label}{sign}{abs(pct):.2f}%")

    # ±30 にクリップ
    total = max(-30.0, min(30.0, total))
    return total, reasons


def compute_sector_forecast(pred_df: pd.DataFrame, snapshot: USSnapshot) -> pd.DataFrame:
    """銘柄別NDXスコアをセクター集計し、米国補正を加えた「明日温度」を計算

    Args:
        pred_df: rank_next_day の戻り値（NDXスコア列を持つ銘柄別DF）
        snapshot: 米国市場スナップショット

    Returns:
        columns: セクター, NDX平均, 強気銘柄数, 銘柄数, US補正, 明日温度, US理由
        明日温度 = NDX平均 * 0.7 + (50 + US補正) * 0.3
    """
    if pred_df.empty or "セクター" not in pred_df.columns or "NDXスコア" not in pred_df.columns:
        return pd.DataFrame()

    rows = []
    for sector, grp in pred_df.groupby("セクター"):
        ndx_mean = float(grp["NDXスコア"].mean())
        strong_cnt = int((grp["NDXスコア"] >= 60).sum())
        stock_cnt = len(grp)
        us_bonus, reasons = compute_us_bonus(sector, snapshot)
        # 明日温度: NDX平均の重み0.7 + US要素(0中心に+bonus)の重み0.3
        tomorrow = ndx_mean * 0.7 + (50.0 + us_bonus) * 0.3
        rows.append({
            "セクター": sector,
            "NDX平均": round(ndx_mean, 1),
            "強気銘柄数": strong_cnt,
            "銘柄数": stock_cnt,
            "US補正": round(us_bonus, 1),
            "明日温度": round(tomorrow, 1),
            "US理由": " / ".join(reasons) if reasons else "",
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("明日温度", ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = "順位"
    return df


def heat_emoji(score: float) -> str:
    """温度スコアから絵文字を返す"""
    if score >= 70:
        return "🔥🔥"
    if score >= 60:
        return "🔥"
    if score >= 50:
        return "🟢"
    if score >= 40:
        return "🟡"
    return "🔵"
