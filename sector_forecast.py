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


# ==========================================================
# 日本テーマ名 → 米国セクターETF キーワードマップ
# ==========================================================
#
# テーマ名にキーワードが含まれていたら、対応する ETF の前日変化率を補正に反映する。
# 朝7時に取得した ETF パフォーマンス（NY終値）から日本市場の翌日寄り付きを予測する仕組み。
#
# 各ルール: (キーワード, ETFティッカー, 係数, 理由ラベル)
#   係数はスケーリング用（最終的に ±30 にクリップ）

THEME_ETF_KEYWORDS: list[tuple[str, str, float, str]] = [
    # ===== 半導体系 =====
    ("半導体", "SMH", 1.4, "米半導体ETF"),
    ("半導体", "SOXX", 0.8, "SOX"),  # 重複強調
    ("SiC", "SMH", 1.2, "米半導体ETF"),
    ("露光", "SMH", 1.2, "米半導体ETF"),

    # ===== AI / ソフトウェア =====
    ("AI", "AIQ", 1.3, "米AI ETF"),
    ("人工知能", "AIQ", 1.3, "米AI ETF"),
    ("エッジAI", "AIQ", 1.2, "米AI ETF"),
    ("SaaS", "IGV", 1.3, "米ソフトウェアETF"),
    ("クラウド", "IGV", 1.1, "米ソフトウェアETF"),
    ("データセンター", "IGV", 0.8, "米ソフトウェアETF"),
    ("データセンター", "XLK", 0.6, "米テック"),
    ("量子", "ARKK", 1.0, "ARKイノベーション"),
    ("DX", "IGV", 0.7, "米ソフトウェアETF"),

    # ===== サイバーセキュリティ =====
    ("サイバー", "HACK", 1.5, "米サイバーETF"),
    ("セキュリティ", "HACK", 1.3, "米サイバーETF"),

    # ===== ロボット / ドローン =====
    ("ロボット", "BOTZ", 1.4, "米ロボット/AI ETF"),
    ("ロボティクス", "BOTZ", 1.3, "米ロボット/AI ETF"),
    ("ドローン", "ITA", 0.8, "米防衛ETF"),
    ("ドローン", "BOTZ", 0.6, "米ロボットETF"),
    ("宇宙", "ITA", 1.0, "米防衛ETF"),

    # ===== 防衛 =====
    ("防衛", "ITA", 1.5, "米防衛ETF"),
    ("兵器", "ITA", 1.3, "米防衛ETF"),

    # ===== バイオ/医療 =====
    ("バイオ", "XBI", 1.4, "米バイオETF"),
    ("ゲノム", "ARKG", 1.3, "米ゲノムETF"),
    ("再生医療", "XBI", 1.2, "米バイオETF"),
    ("医薬", "XBI", 1.0, "米バイオETF"),
    ("医療", "IHI", 0.6, "米医療機器ETF"),
    ("ヘルスケア", "XLV", 0.8, "米ヘルスケア"),
    ("創薬", "XBI", 1.2, "米バイオETF"),

    # ===== 金融 =====
    ("銀行", "KRE", 1.2, "米地方銀行ETF"),
    ("地銀", "KRE", 1.3, "米地方銀行ETF"),
    ("金融", "XLF", 0.8, "米金融"),
    ("フィンテック", "FINX", 1.3, "米フィンテックETF"),
    ("決済", "FINX", 1.1, "米フィンテックETF"),

    # ===== エネルギー =====
    ("原油", "XLE", 1.3, "米エネルギー"),
    ("石油", "XLE", 1.3, "米エネルギー"),
    ("天然ガス", "XLE", 1.2, "米エネルギー"),
    ("エネルギー", "XLE", 0.7, "米エネルギー"),
    ("総合商社", "XLE", 0.5, "米エネルギー"),

    # ===== 金/貴金属 =====
    ("金地金", "GDX", 1.4, "米金鉱株ETF"),
    ("貴金属", "GDX", 1.2, "米金鉱株ETF"),
    ("金鉱", "GDX", 1.5, "米金鉱株ETF"),
    ("レアアース", "REMX", 1.3, "米希土類ETF"),
    ("希土類", "REMX", 1.3, "米希土類ETF"),
    ("レアメタル", "REMX", 1.1, "米希土類ETF"),

    # ===== 原子力/ウラン =====
    ("原子力", "URA", 1.4, "米ウランETF"),
    ("ウラン", "URA", 1.5, "米ウランETF"),
    ("核融合", "URA", 1.0, "米ウランETF"),  # やや弱い相関

    # ===== クリーンエネルギー =====
    ("太陽光", "TAN", 1.5, "米ソーラーETF"),
    ("太陽電池", "TAN", 1.4, "米ソーラーETF"),
    ("ソーラー", "TAN", 1.5, "米ソーラーETF"),
    ("風力", "FAN", 1.5, "米風力ETF"),
    ("洋上風力", "FAN", 1.4, "米風力ETF"),
    ("クリーン", "ICLN", 1.2, "米クリーンエネETF"),
    ("再エネ", "ICLN", 1.3, "米クリーンエネETF"),
    ("再生可能", "ICLN", 1.2, "米クリーンエネETF"),
    ("脱炭素", "ICLN", 1.0, "米クリーンエネETF"),
    ("水素", "ICLN", 0.7, "米クリーンエネETF"),

    # ===== 電池/EV =====
    ("電池", "LIT", 1.3, "米リチウム/電池ETF"),
    ("リチウム", "LIT", 1.5, "米リチウム/電池ETF"),
    ("EV", "LIT", 0.8, "米リチウム/電池ETF"),
    ("電気自動車", "LIT", 0.9, "米リチウム/電池ETF"),

    # ===== 不動産/REIT =====
    ("REIT", "XLRE", 1.4, "米REIT"),
    ("不動産", "XLRE", 0.8, "米REIT"),

    # ===== ゲーム/エンタメ =====
    ("ゲーム", "ESPO", 1.3, "米ゲーム/eスポーツETF"),
    ("eスポーツ", "ESPO", 1.5, "米ゲーム/eスポーツETF"),
    ("メタバース", "ESPO", 0.9, "米ゲーム/eスポーツETF"),
    ("メタバース", "ARKK", 0.6, "ARKイノベーション"),

    # ===== ブロックチェーン/仮想通貨 =====
    ("ブロックチェーン", "BLOK", 1.5, "米ブロックチェーンETF"),
    ("仮想通貨", "BLOK", 1.4, "米ブロックチェーンETF"),
    ("暗号資産", "BLOK", 1.4, "米ブロックチェーンETF"),

    # ===== 運輸 =====
    ("航空", "JETS", 1.3, "米航空ETF"),
    ("海運", "XLI", 0.5, "米資本財"),  # SEA ETF 廃止のため代替
    ("運輸", "XLI", 0.5, "米資本財"),

    # ===== 消費関連 =====
    ("インバウンド", "XLY", 0.6, "米一般消費"),
    ("小売", "XLP", 0.6, "米生活必需品"),
    ("食品", "XLP", 0.6, "米生活必需品"),

    # ===== 通信 =====
    ("5G", "XLC", 1.0, "米通信"),
    ("通信", "XLC", 0.7, "米通信"),

    # ===== IPO =====
    ("IPO", "ARKK", 0.8, "ARKイノベーション"),
]


def compute_us_etf_bonus(theme_name: str, etf_perfs: dict) -> tuple[float, list[str]]:
    """テーマ名から米国セクターETFの補正スコアを算出

    Args:
        theme_name: 日本語テーマ名
        etf_perfs: us_sector_perf.fetch_us_sector_performance() の戻り値
                   dict[ticker, ETFPerformance]

    Returns:
        (bonus_score, reason_list)  bonus は ±30 にクリップ
    """
    if not etf_perfs:
        return 0.0, []

    total = 0.0
    reasons: list[str] = []
    seen_labels: set[str] = set()

    for kw, tic, coef, label in THEME_ETF_KEYWORDS:
        if kw not in theme_name:
            continue
        perf = etf_perfs.get(tic)
        if perf is None or perf.change_pct is None:
            continue
        pct = perf.change_pct
        if abs(pct) < 0.05:
            continue
        contrib = pct * coef * 4  # スケーリング
        total += contrib

        # 同じラベル重複は抑制
        if abs(contrib) >= 1.0 and label not in seen_labels:
            sign = "↑" if pct > 0 else "↓"
            reasons.append(f"{label}{sign}{abs(pct):.2f}%")
            seen_labels.add(label)

    total = max(-30.0, min(30.0, total))
    return total, reasons


def compute_sector_forecast(
    pred_df: pd.DataFrame,
    snapshot: USSnapshot,
    etf_perfs: dict | None = None,
) -> pd.DataFrame:
    """銘柄別NDXスコアをセクター集計し、米国補正を加えた「明日温度」を計算

    Args:
        pred_df: rank_next_day の戻り値（NDXスコア列を持つ銘柄別DF）
        snapshot: 米国市場スナップショット
        etf_perfs: 米国セクターETFのパフォーマンス（optional、なければ指数補正のみ）

    Returns:
        columns: セクター, NDX平均, 強気銘柄数, 銘柄数, 指数補正, ETF補正, 明日温度, 補正理由
        明日温度 = NDX平均 * 0.6 + (50 + 指数補正 + ETF補正) * 0.4
    """
    if pred_df.empty or "セクター" not in pred_df.columns or "NDXスコア" not in pred_df.columns:
        return pd.DataFrame()

    rows = []
    for sector, grp in pred_df.groupby("セクター"):
        ndx_mean = float(grp["NDXスコア"].mean())
        strong_cnt = int((grp["NDXスコア"] >= 60).sum())
        stock_cnt = len(grp)

        idx_bonus, idx_reasons = compute_us_bonus(sector, snapshot)
        etf_bonus, etf_reasons = (0.0, []) if etf_perfs is None else compute_us_etf_bonus(sector, etf_perfs)

        # 合算補正（クリップ±40 - ETF と指数の二重加算を許容）
        combined = max(-40.0, min(40.0, idx_bonus + etf_bonus))

        # 明日温度: NDX 0.6 + US(指数+ETF) 0.4
        tomorrow = ndx_mean * 0.6 + (50.0 + combined) * 0.4

        all_reasons = idx_reasons + etf_reasons
        rows.append({
            "セクター": sector,
            "NDX平均": round(ndx_mean, 1),
            "強気銘柄数": strong_cnt,
            "銘柄数": stock_cnt,
            "指数補正": round(idx_bonus, 1),
            "ETF補正": round(etf_bonus, 1),
            "明日温度": round(tomorrow, 1),
            "補正理由": " / ".join(all_reasons) if all_reasons else "",
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
