"""米国セクターETF のパフォーマンス取得

朝7時(JST) ≒ NY市場クローズ直後に最新値を取得し、
日本市場の翌日寄り付きに影響しそうなセクターの強弱を可視化する。

データ元: yfinance（無料・リアルタイム）
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

import pandas as pd
import streamlit as st
import yfinance as yf

JST = timezone(timedelta(hours=9))


# ==========================================================
# 米国セクターETF 定義
# ==========================================================
#
# ticker → (日本語名, カテゴリ, 説明)
#
# 主要セクター (XL系 = State Street Select Sector SPDR):
#   XLK=テクノロジー, XLF=金融, XLE=エネルギー, XLV=ヘルスケア
#   XLI=資本財, XLB=素材, XLU=公共, XLP=生活必需品
#   XLY=一般消費, XLRE=不動産, XLC=コミュニケーション
#
# サブセクター (VanEck / iShares / ARK系):
#   SMH=半導体, SOXX=半導体, IGV=ソフトウェア, HACK=サイバー, CIBR=サイバー
#   XBI=バイオテック, IHI=医療機器, ARKG=ゲノム, ARKK=イノベーション
#   ITA=防衛, PPA=防衛, KBE=地方銀行, KRE=地方銀行
#   GDX=金鉱株, GDXJ=小型金鉱, SLV=銀, URA=ウラン, LIT=リチウム, BATT=バッテリー
#   ICLN=クリーンエネ, TAN=ソーラー, FAN=風力, HDRO=水素
#   BOTZ=ロボット, ROBO=ロボット, AIQ=AI, MOON=ARK宇宙
#   BLOK=ブロックチェーン, IBIT=BTC, FINX=フィンテック
#   IYT=運輸, XTN=運輸, SEA=海運, JETS=航空
#   IPO=IPO, MOAT=ワイドモート, ESPO=ゲーム
#   MJ=大麻, REMX=希土類

US_SECTOR_ETFS: dict[str, tuple[str, str]] = {
    # ===== 主要11セクター =====
    "XLK": ("🇺🇸 テクノロジー", "major"),
    "XLF": ("🇺🇸 金融", "major"),
    "XLE": ("🇺🇸 エネルギー", "major"),
    "XLV": ("🇺🇸 ヘルスケア", "major"),
    "XLI": ("🇺🇸 資本財/産業", "major"),
    "XLB": ("🇺🇸 素材", "major"),
    "XLU": ("🇺🇸 公共", "major"),
    "XLP": ("🇺🇸 生活必需品", "major"),
    "XLY": ("🇺🇸 一般消費", "major"),
    "XLRE": ("🇺🇸 不動産(REIT)", "major"),
    "XLC": ("🇺🇸 コミュニケーション", "major"),

    # ===== テーマETF =====
    "SMH": ("半導体ETF", "theme"),
    "IGV": ("ソフトウェアETF", "theme"),
    "HACK": ("サイバーセキュリティETF", "theme"),
    "XBI": ("バイオテックETF", "theme"),
    "IHI": ("医療機器ETF", "theme"),
    "ARKG": ("ゲノム/バイオイノベーション", "theme"),
    "ARKK": ("ARKイノベーション", "theme"),
    "ITA": ("航空宇宙・防衛ETF", "theme"),
    "KRE": ("地方銀行ETF", "theme"),
    "GDX": ("金鉱株ETF", "theme"),
    "URA": ("ウラン/原子力ETF", "theme"),
    "LIT": ("リチウム/電池ETF", "theme"),
    "ICLN": ("クリーンエネルギーETF", "theme"),
    "TAN": ("ソーラー/太陽光ETF", "theme"),
    "FAN": ("風力発電ETF", "theme"),
    "BOTZ": ("ロボット/AI ETF", "theme"),
    "AIQ": ("AI ETF", "theme"),
    "BLOK": ("ブロックチェーンETF", "theme"),
    "FINX": ("フィンテックETF", "theme"),
    "JETS": ("航空業界ETF", "theme"),
    "ESPO": ("eスポーツ/ゲームETF", "theme"),
    "REMX": ("希土類/戦略金属ETF", "theme"),
}


@dataclass
class ETFPerformance:
    ticker: str
    name: str
    category: str
    close: float | None
    prev_close: float | None
    change_pct: float | None
    fetched_at: datetime

    @property
    def change_str(self) -> str:
        if self.change_pct is None:
            return "—"
        return f"{self.change_pct:+.2f}%"


def _compute_change(hist: pd.DataFrame) -> tuple[float | None, float | None, float | None]:
    """履歴DFから (close, prev_close, change_pct) を返す"""
    if hist is None or len(hist) < 2:
        return None, None, None
    close = float(hist["Close"].iloc[-1])
    prev = float(hist["Close"].iloc[-2])
    if prev == 0:
        return close, prev, None
    return close, prev, (close - prev) / prev * 100


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_us_sector_performance() -> dict[str, ETFPerformance]:
    """米国セクターETF 全ティッカーの直近1日変化率を取得

    TTL 1h キャッシュ。朝7時以降に呼ぶと、その日の NY 終値が入る想定。
    NY 市場夜間帯は前日の値。

    Returns:
        ticker → ETFPerformance
    """
    tickers = list(US_SECTOR_ETFS.keys())
    # まとめてダウンロード（yfinance のバッチ機能）
    try:
        data = yf.download(
            tickers,
            period="5d",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as e:
        st.warning(f"米国セクターETF 取得エラー: {e}")
        data = None

    now = datetime.now(JST)
    result: dict[str, ETFPerformance] = {}

    for tic in tickers:
        name, cat = US_SECTOR_ETFS[tic]
        close, prev, pct = None, None, None
        if data is not None and not data.empty:
            try:
                # MultiIndex カラム (ticker, field)
                if isinstance(data.columns, pd.MultiIndex):
                    sub = data[tic]
                    close, prev, pct = _compute_change(sub)
                else:
                    # 単一ティッカーの場合はトップレベルに直接 Close が来る
                    close, prev, pct = _compute_change(data)
            except Exception:
                pass
        result[tic] = ETFPerformance(
            ticker=tic,
            name=name,
            category=cat,
            close=close,
            prev_close=prev,
            change_pct=pct,
            fetched_at=now,
        )

    return result


def get_sector_etf_rankings(
    perfs: dict[str, ETFPerformance],
    category: str | None = None,
    top_n: int = 10,
) -> list[ETFPerformance]:
    """パフォーマンス高順のランキングを返す

    Args:
        perfs: fetch_us_sector_performance の戻り値
        category: "major" or "theme" で絞り込み、None なら全て
        top_n: 上位件数
    """
    items = [p for p in perfs.values() if p.change_pct is not None]
    if category:
        items = [p for p in items if p.category == category]
    items.sort(key=lambda x: x.change_pct or 0, reverse=True)
    return items[:top_n]
