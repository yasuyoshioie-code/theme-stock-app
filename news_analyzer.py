"""ニュース分析モジュール

機能:
  1. ニュース本文から **個別銘柄の材料** を抽出（証券コード + 銘柄名 + セクター）
  2. センチメント判定（ポジティブ/ネガティブ/中立）
  3. **ブログ記事タイトル** の自動生成（SEO最適化済みテンプレート）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ==========================================================
# センチメント判定
# ==========================================================

_POSITIVE_KEYWORDS = [
    # 業績・株価系ポジティブ
    "上方修正", "増益", "増収", "最高益", "最高値", "過去最高", "記録的",
    "急騰", "暴騰", "上昇", "続伸", "高騰", "反発", "反騰",
    "上場", "新規上場", "IPO", "立ち会い外買付",
    # 事業ポジティブ
    "買収", "統合", "M&A", "提携", "業務提携", "資本業務提携",
    "新製品", "新サービス", "新技術", "ブレイクスルー",
    "採用", "受注", "大型受注", "契約", "成約",
    "認可", "承認", "認定", "ライセンス",
    "配当", "増配", "特別配当", "自社株買い", "株主優待",
    # マクロポジティブ
    "好調", "堅調", "強含み", "景気回復", "追い風", "追い風",
    "金利引き下げ", "利下げ", "緩和",
    "過去最多", "好決算", "好業績", "躍進",
    # 政策・外部環境
    "国策", "支援", "補助金", "優遇",
    # 賛意系
    "期待", "追い風", "関心", "注目",
]

_NEGATIVE_KEYWORDS = [
    # 業績ネガティブ
    "下方修正", "減益", "減収", "赤字", "大幅赤字", "過去最悪",
    "急落", "暴落", "下落", "続落", "崩落", "反落", "下振れ",
    # 事業ネガティブ
    "損失", "減損", "不適切会計", "粉飾", "不正", "リコール",
    "業績悪化", "悪化", "苦戦", "不振", "低迷",
    "倒産", "破綻", "清算", "民事再生", "会社更生法", "上場廃止",
    "訴訟", "提訴", "敗訴", "違反", "制裁", "課徴金",
    # マクロネガティブ
    "景気後退", "リセッション", "不況", "減速", "冷え込み",
    "金利引き上げ", "利上げ", "引き締め",
    "地政学リスク", "紛争", "制裁",
    "向かい風", "懸念", "リスク", "警戒",
]

_BREAKING_KEYWORDS = [
    "速報", "緊急", "速報", "臨時",
]


def detect_sentiment(text: str) -> str:
    """ポジティブ/ネガティブ/中立 を判定"""
    if not text:
        return "neutral"
    pos = sum(1 for kw in _POSITIVE_KEYWORDS if kw in text)
    neg = sum(1 for kw in _NEGATIVE_KEYWORDS if kw in text)
    if pos > neg and pos >= 1:
        return "positive"
    if neg > pos and neg >= 1:
        return "negative"
    return "neutral"


def is_breaking(text: str) -> bool:
    """速報ニュースかどうか"""
    return any(kw in text for kw in _BREAKING_KEYWORDS)


# ==========================================================
# 銘柄抽出
# ==========================================================

@dataclass
class StockMention:
    code: str   # "7203"
    name: str   # "トヨタ自動車"
    sector: str = ""


def build_stock_index(sectors_info: dict) -> list[tuple[str, str, str]]:
    """known stocksリストを作る: [(code, name, sector), ...]

    sectors_info: {sector_name: DataFrame(証券コード, 銘柄名)}
    """
    stocks = []
    seen = set()
    for sector, df in sectors_info.items():
        if df.empty or "証券コード" not in df.columns or "銘柄名" not in df.columns:
            continue
        for _, row in df.iterrows():
            code = str(row["証券コード"]).strip()
            name = str(row["銘柄名"]).strip()
            key = (code, name)
            if key in seen or not code or not name:
                continue
            seen.add(key)
            stocks.append((code, name, sector))
    # 銘柄名長いもの順にソート（部分マッチで誤検知を防ぐため）
    stocks.sort(key=lambda x: len(x[1]), reverse=True)
    return stocks


# 一般的な企業名の別表記マップ（代表的なもの）
_NAME_ALIASES = {
    "トヨタ自動車": ["トヨタ"],
    "本田技研工業": ["ホンダ", "本田"],
    "日産自動車": ["日産"],
    "ソニーグループ": ["ソニー", "SONY"],
    "ソフトバンクグループ": ["ソフトバンクG", "SBG"],
    "三菱UFJフィナンシャル・グループ": ["三菱UFJ", "MUFG"],
    "三井住友フィナンシャルグループ": ["三井住友FG", "SMFG"],
    "みずほフィナンシャルグループ": ["みずほFG", "みずほ"],
    "セブン&アイ・ホールディングス": ["セブン&アイ", "セブン＆アイ"],
    "ファーストリテイリング": ["ファーストリテイリング", "FR", "ユニクロ"],
    "任天堂": ["任天堂", "ニンテンドー"],
    "東京エレクトロン": ["東エレク", "TEL"],
    "信越化学工業": ["信越化", "信越化学"],
    "日立製作所": ["日立"],
    "三菱重工業": ["三菱重工", "MHI"],
    "川崎重工業": ["川崎重工", "KHI"],
    "キオクシアHD": ["キオクシア"],
    "アドバンテスト": ["アドバンテスト"],
    "レーザーテック": ["レーザーテック"],
    "ルネサスエレクトロニクス": ["ルネサス"],
    "富士通": ["富士通"],
    "キーエンス": ["キーエンス"],
    "ディスコ": ["DISCO", "ディスコ"],
    "SUMCO": ["SUMCO", "サムコ"],
    "NTTデータグループ": ["NTTデータ"],
    "日本電信電話": ["NTT"],
    "KDDI": ["KDDI", "au"],
    "ソフトバンク": ["ソフトバンク"],
}


def extract_stock_mentions(
    text: str,
    known_stocks: list[tuple[str, str, str]],
    max_mentions: int = 5,
) -> list[StockMention]:
    """ニュース本文から言及されている既知銘柄を抽出

    抽出ロジック:
      1. 4桁コード直接マッチ ("<7203>" や " 7203 ")
      2. 銘柄名の完全/部分マッチ
      3. 別表記（トヨタ、SBG、MUFG など）
    """
    if not text or not known_stocks:
        return []

    found = {}  # code -> StockMention

    # --- 1. コード直接マッチ ---
    # パターン: <7203>, (7203), 7203.T, 「7203」, 株価コード:7203 など
    code_patterns = [
        r"<(\d{4})>",
        r"【(\d{4})】",
        r"「(\d{4})」",
        r"\((\d{4})\)",
        r"\[(\d{4})\]",
        r"株価?(?:コード)?[\s::]+(\d{4})",
        r"銘柄?コード[\s::]+(\d{4})",
        r"(\d{4})\.T\b",
    ]
    all_codes_in_text = set()
    for pat in code_patterns:
        for m in re.finditer(pat, text):
            all_codes_in_text.add(m.group(1))

    # known_stocks index
    stock_by_code = {c: (c, n, s) for c, n, s in known_stocks}
    for code in all_codes_in_text:
        if code in stock_by_code and code not in found:
            c, n, s = stock_by_code[code]
            found[c] = StockMention(code=c, name=n, sector=s)

    # --- 2. 銘柄名マッチ（長いものから優先） ---
    for code, name, sector in known_stocks:
        if code in found or len(found) >= max_mentions:
            continue
        if len(name) < 2:  # 1文字は誤検知が多すぎる
            continue
        if name in text:
            found[code] = StockMention(code=code, name=name, sector=sector)

    # --- 3. 別表記マッチ ---
    if len(found) < max_mentions:
        for canonical, aliases in _NAME_ALIASES.items():
            for alias in aliases:
                if alias in text:
                    # canonicalでknown_stocks検索
                    for code, name, sector in known_stocks:
                        if code in found:
                            continue
                        if canonical in name or name in canonical:
                            found[code] = StockMention(code=code, name=name, sector=sector)
                            break
                    break
            if len(found) >= max_mentions:
                break

    return list(found.values())[:max_mentions]


# ==========================================================
# ブログタイトル生成
# ==========================================================

# ニュースタイプ判定用キーワード（判定優先順に評価される）
_NEWS_TYPES = {
    # 個別企業系
    "earnings_up": ["上方修正", "最高益", "増益", "過去最高", "好決算", "好業績"],
    "earnings_down": ["下方修正", "減益", "赤字", "業績悪化", "悪化"],
    "ma": ["買収", "M&A", "統合", "TOB", "公開買付", "子会社化", "経営統合"],
    "alliance": ["提携", "業務提携", "資本業務提携", "パートナーシップ"],
    "new_product": ["新製品", "新サービス", "新技術", "新型", "次世代"],
    "breakout": ["急騰", "暴騰", "高騰", "ストップ高", "上場来高値", "年初来高値"],
    "crash": ["急落", "暴落", "崩落", "ストップ安", "上場来安値", "年初来安値"],
    "ipo": ["新規上場", "IPO", "上場承認"],
    "dividend": ["増配", "配当", "株主還元", "自社株買い", "記念配当"],
    "scandal": ["不正", "粉飾", "リコール", "訴訟", "違反", "制裁", "課徴金"],
    "analyst": ["格付け", "目標株価", "レーティング", "アナリスト", "投資判断", "買い推奨", "売り推奨"],
    # マクロ・マーケット系（高PV狙い）
    "us_market": ["NYダウ", "ナスダック", "S&P500", "S&P", "米国株", "米株", "ウォール街", "FOMC", "FRB", "パウエル"],
    "forex": ["為替", "ドル円", "円安", "円高", "ユーロ円", "FX", "為替介入"],
    "commodity": ["原油", "金価格", "ゴールド", "WTI", "商品市況", "銅", "天然ガス", "プラチナ", "小麦"],
    "crypto": ["ビットコイン", "BTC", "イーサリアム", "仮想通貨", "暗号資産", "ブロックチェーン"],
    "bond": ["国債", "長期金利", "10年債", "利回り", "イールドカーブ"],
    "macro_jp": ["日銀", "植田", "金融政策決定会合", "マイナス金利", "YCC", "日本の物価", "CPI", "GDP"],
    "macro_global": ["ECB", "ラガルド", "世界経済", "IMF", "中国経済", "景気後退", "リセッション"],
    "geopolitics": ["地政学", "中東", "ウクライナ", "台湾有事", "米中", "制裁", "紛争"],
    # 個人投資家に響く系（高PV）
    "tax_nisa": ["NISA", "新NISA", "iDeCo", "節税", "税制", "所得税"],
    "policy": ["政策", "法改正", "規制", "補助金", "国策", "経済対策"],
    "market_overall": ["日経平均", "TOPIX", "東証", "株価指数", "マーケット", "相場全体", "全体相場", "主力株"],
    "theme_hot": ["AI", "半導体", "EV", "防衛", "宇宙", "量子", "バイオ", "再生エネルギー", "水素"],
}


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(kw in text for kw in keywords)


def detect_news_type(text: str) -> str:
    """ニュースタイプを判定"""
    for ntype, keywords in _NEWS_TYPES.items():
        if any(kw in text for kw in keywords):
            return ntype
    return "general"


def _pick_theme_from_stocks(stocks: list[StockMention]) -> str:
    """銘柄リストから共通テーマ（セクター）を抽出"""
    if not stocks:
        return ""
    sectors = [s.sector for s in stocks if s.sector]
    if not sectors:
        return ""
    # 最頻値
    from collections import Counter
    common = Counter(sectors).most_common(1)
    return common[0][0] if common else ""


def generate_blog_titles(
    news_title: str,
    summary: str,
    stocks: list[StockMention],
    sentiment: str,
) -> list[str]:
    """ブログ記事タイトル候補を複数生成（SEO最適化）

    方針:
      - 元ニュースのタイトルは一切切り詰めない（省略禁止）
      - 個別銘柄の材料だけでなく、マクロ/為替/米国株/NISA/アナリスト評価など
        高PV見込みのニュースも必ずブログ化できるよう全タイプに専用テンプレを用意
      - 最終的に3本以上のタイトル案を返す
    """
    full_text = f"{news_title} {summary}"
    ntype = detect_news_type(full_text)

    # 主要銘柄
    main_stock = stocks[0] if stocks else None
    theme = _pick_theme_from_stocks(stocks)

    titles: list[str] = []

    # ==================================================
    # 個別企業系テンプレ
    # ==================================================
    if ntype == "earnings_up":
        if main_stock:
            titles.append(f"【好決算】{main_stock.name}({main_stock.code})が最高益更新｜今後の株価見通しを徹底解説")
            titles.append(f"{main_stock.name}上方修正の中身を深掘り｜関連{theme or 'セクター'}への波及シナリオ")
            titles.append(f"なぜ{main_stock.name}は急伸したのか｜決算から読み解く買いサイン3選")
        else:
            titles.append(f"【決算速報】{news_title}｜勝ち組銘柄の共通点を徹底分析")
            titles.append(f"{theme or '注目セクター'}で好決算ラッシュ｜今から仕込める関連銘柄5選")
            titles.append(f"好決算銘柄はどう動く？｜『{news_title}』を投資家目線で解説")

    elif ntype == "earnings_down":
        if main_stock:
            titles.append(f"【衝撃】{main_stock.name}({main_stock.code})が下方修正｜関連銘柄への影響と今後の展開")
            titles.append(f"{main_stock.name}業績悪化の真相｜買い直しのタイミングを見極める")
            titles.append(f"{main_stock.name}株価急落の理由｜投資家が今知るべき3つのポイント")
        else:
            titles.append(f"【警戒】{news_title}｜関連セクターへの影響を予測")
            titles.append(f"業績悪化の波紋｜『{news_title}』から考える避難先銘柄")

    elif ntype == "ma":
        if main_stock:
            titles.append(f"【M&A】{main_stock.name}の買収劇を徹底分析｜{theme or '業界'}再編の号砲")
            titles.append(f"{main_stock.name}({main_stock.code})買収発表で急騰｜連れ高を狙える関連銘柄")
            titles.append(f"なぜ今{main_stock.name}が狙われたのか｜M&Aで読み解く{theme or '業界'}の未来")
        else:
            titles.append(f"【M&A速報】{news_title}｜業界再編で注目される関連銘柄")
            titles.append(f"買収ラッシュはどこまで続く？｜『{news_title}』と次のターゲット候補")

    elif ntype == "alliance":
        if main_stock:
            titles.append(f"【提携】{main_stock.name}が新パートナーと資本業務提携｜株価への影響は？")
            titles.append(f"{main_stock.name}({main_stock.code})の提携発表で急動意｜{theme or 'テーマ'}銘柄に資金流入")
            titles.append(f"『{news_title}』が示す{main_stock.name}の成長戦略｜投資家の評価を解説")
        else:
            titles.append(f"【提携速報】{news_title}｜動き出す{theme or '注目'}銘柄を先取り")
            titles.append(f"提携が意味する{theme or '業界'}の地殻変動｜『{news_title}』を読み解く")

    elif ntype == "new_product":
        if main_stock:
            titles.append(f"【新製品】{main_stock.name}が{theme or '業界'}に革命｜関連銘柄も急上昇へ")
            titles.append(f"{main_stock.name}({main_stock.code})新サービス発表｜買い場到来か徹底解説")
        titles.append(f"【徹底解説】{news_title}｜{theme or '関連'}銘柄の本命はどれか")
        titles.append(f"『{news_title}』のインパクト｜次に買われる関連テーマ銘柄")

    elif ntype == "breakout":
        if main_stock:
            titles.append(f"【急騰】{main_stock.name}が暴騰した3つの理由｜追随銘柄はこれだ")
            titles.append(f"{main_stock.name}({main_stock.code})ストップ高｜今から乗れる関連銘柄5選")
            titles.append(f"なぜ{main_stock.name}が急騰したのか｜{theme or 'テーマ'}再燃で連れ高期待")
        else:
            titles.append(f"【急騰速報】{news_title}｜次に狙うべき関連銘柄を分析")
            titles.append(f"『{news_title}』の勢いは本物か｜プロが見る続騰シナリオ")

    elif ntype == "crash":
        if main_stock:
            titles.append(f"【暴落】{main_stock.name}急落の真相｜反発のタイミングを見極める")
            titles.append(f"{main_stock.name}({main_stock.code})ストップ安｜売り材料を徹底検証")
            titles.append(f"『{news_title}』で動く関連銘柄｜押し目買いの判断基準")
        else:
            titles.append(f"【警戒】{news_title}｜関連セクターへの連鎖的影響は")
            titles.append(f"急落相場をどう読む？｜『{news_title}』で注目すべき避難先")

    elif ntype == "ipo":
        if main_stock:
            titles.append(f"【新規上場】{main_stock.name}IPO完全ガイド｜初値予想と注目ポイント")
        titles.append(f"【IPO注目】{news_title}｜投資家が絶対チェックすべきポイント")
        titles.append(f"今週のIPO本命銘柄｜『{news_title}』を徹底分析")
        titles.append(f"IPOで稼ぐ攻略法｜『{news_title}』から学ぶ注目ポイント")

    elif ntype == "dividend":
        if main_stock:
            titles.append(f"【増配】{main_stock.name}が株主還元強化｜高配当投資家が狙う銘柄に")
            titles.append(f"{main_stock.name}({main_stock.code})自社株買い発表｜株価への即効性を分析")
            titles.append(f"『{news_title}』をどう読む？｜配当利回りで選ぶ関連銘柄3選")
        else:
            titles.append(f"【株主還元】{news_title}｜高配当＆自社株買い銘柄を先取り")
            titles.append(f"配当狙いの長期投資家必見｜『{news_title}』と関連銘柄リスト")

    elif ntype == "scandal":
        if main_stock:
            titles.append(f"【注意】{main_stock.name}の不祥事｜株価への影響と関連銘柄へのリスク")
            titles.append(f"{main_stock.name}({main_stock.code})を巡る問題を解説｜保有者が取るべき行動")
        titles.append(f"【速報】{news_title}｜投資家が今チェックすべきリスク要因")

    elif ntype == "analyst":
        if main_stock:
            titles.append(f"【アナリスト評価】{main_stock.name}({main_stock.code})の目標株価引き上げ｜投資判断を読み解く")
            titles.append(f"{main_stock.name}のレーティング変更が示すシナリオ｜関連銘柄へのスピルオーバー")
        titles.append(f"【レーティング動向】{news_title}｜機関投資家の目線を解説")
        titles.append(f"アナリストが動いた銘柄を狙う｜『{news_title}』から読むトレード戦略")

    # ==================================================
    # マクロ・マーケット系テンプレ（高PV狙い）
    # ==================================================
    elif ntype == "us_market":
        titles.append(f"【米国株】{news_title}｜日本株への波及シナリオを徹底分析")
        titles.append(f"NYダウ・ナスダックの動きを読む｜『{news_title}』と連動する日本株")
        titles.append(f"『{news_title}』で動く米国ETFと日本株｜プロが見る3つのシナリオ")
        titles.append(f"米国発ニュース総まとめ｜{news_title}で押さえるべき関連銘柄")

    elif ntype == "forex":
        if "円安" in full_text:
            titles.append(f"【円安加速】{news_title}｜恩恵を受ける輸出関連銘柄ベスト10")
            titles.append(f"円安メリット株で逆境を勝ち抜く｜『{news_title}』で注目のセクター")
        elif "円高" in full_text:
            titles.append(f"【円高警戒】{news_title}｜内需・輸入関連で狙う反発銘柄")
        else:
            titles.append(f"【為替分析】{news_title}｜日本株への影響とセクター別シナリオ")
        titles.append(f"『{news_title}』を読み解く｜為替で動く関連銘柄と投資戦略")
        titles.append(f"FXと株の相関を考える｜{news_title}から学ぶポジション構築術")

    elif ntype == "commodity":
        titles.append(f"【商品市況】{news_title}｜関連資源株・商社株への影響を解説")
        titles.append(f"原油・金で動く銘柄｜『{news_title}』から読む商品相場と日本株")
        titles.append(f"『{news_title}』が示すインフレシナリオ｜資源関連銘柄の注目点")

    elif ntype == "crypto":
        titles.append(f"【仮想通貨】{news_title}｜ビットコイン急騰で動く関連日本株")
        titles.append(f"『{news_title}』で再燃する暗号資産ブーム｜関連銘柄ウォッチリスト")
        titles.append(f"仮想通貨と株の連動を分析｜{news_title}から見えるトレンド")

    elif ntype == "bond":
        titles.append(f"【金利動向】{news_title}｜銀行株・不動産株への影響を解説")
        titles.append(f"長期金利の上下で動くセクター｜『{news_title}』を投資家目線で分析")
        titles.append(f"『{news_title}』を踏まえたポートフォリオ戦略｜金利敏感株の選び方")

    elif ntype == "macro_jp":
        titles.append(f"【日銀動向】{news_title}｜金融政策の転換点と日本株の行方")
        titles.append(f"『{news_title}』から読む日銀シナリオ｜今押さえたい関連銘柄")
        titles.append(f"日銀ウォッチの視点｜{news_title}で動くセクターをプロが分析")

    elif ntype == "macro_global":
        titles.append(f"【世界経済】{news_title}｜日本株が受ける影響を徹底予測")
        titles.append(f"『{news_title}』が示す景気シナリオ｜今見直すべきポートフォリオ")
        titles.append(f"海外マクロを読む｜{news_title}で浮上する注目セクター")

    elif ntype == "geopolitics":
        titles.append(f"【地政学リスク】{news_title}｜防衛・資源・為替で動く銘柄")
        titles.append(f"『{news_title}』で日本株はどう動くか｜リスクオフ時の注目銘柄")
        titles.append(f"地政学で稼ぐ戦略｜『{news_title}』関連の防衛・インフラ銘柄")

    elif ntype == "tax_nisa":
        titles.append(f"【新NISA活用術】{news_title}｜2026年の最適ポートフォリオを作る")
        titles.append(f"『{news_title}』を受けての投資家対応｜NISA枠の使い方を再考")
        titles.append(f"NISA・iDeCoで賢く運用｜{news_title}をきっかけに見直すべき銘柄")
        titles.append(f"税制変更で動く投資家心理｜『{news_title}』と節税戦略")

    elif ntype == "policy":
        titles.append(f"【国策テーマ】{news_title}｜関連銘柄に追い風・本命はこれだ")
        titles.append(f"{theme or '政策'}テーマで急騰期待｜今仕込むべき関連銘柄を厳選")
        titles.append(f"『{news_title}』を読み解く｜補助金・規制緩和で動く3セクター")
        if main_stock:
            titles.append(f"{main_stock.name}({main_stock.code})が政策恩恵｜なぜ今注目されるのか")

    elif ntype == "market_overall":
        titles.append(f"【相場解説】{news_title}｜日経平均の次の動きを読み解く")
        titles.append(f"『{news_title}』はチャンスかリスクか｜今の相場でやるべき3つのこと")
        titles.append(f"相場の主導役はどこへ？｜{news_title}でローテーションを占う")
        titles.append(f"日経・TOPIXで勝つ戦略｜『{news_title}』を投資家目線で分析")

    elif ntype == "theme_hot":
        titles.append(f"【注目テーマ】{news_title}｜本命・出遅れ銘柄を完全リスト化")
        titles.append(f"『{news_title}』で再燃するテーマ株｜プロが見る本命の条件")
        titles.append(f"旬のテーマで勝つ｜{news_title}から読む中長期シナリオ")

    else:
        # ==================================================
        # general フォールバック
        #   - 個別銘柄あり → 銘柄ベースの3案
        #   - セクターあり → セクターテーマ案
        #   - それ以外   → 投資家向け高PVテンプレ
        # ==================================================
        if main_stock and sentiment == "positive":
            titles.append(f"【注目】{main_stock.name}が動意｜{theme or 'テーマ'}関連で連れ高期待の3銘柄")
            titles.append(f"{main_stock.name}({main_stock.code})急動意の背景｜『{news_title}』を投資家目線で解説")
            titles.append(f"今買うべきか待つべきか｜{main_stock.name}と{news_title}を徹底検証")
        elif main_stock and sentiment == "negative":
            titles.append(f"{main_stock.name}({main_stock.code})に逆風｜『{news_title}』のインパクトを分析")
            titles.append(f"【注意】{main_stock.name}で今起きていること｜関連{theme or '銘柄'}にも波及懸念")
            titles.append(f"{main_stock.name}の値動きをどう読むか｜『{news_title}』から考える対応策")
        elif main_stock:
            titles.append(f"{main_stock.name}({main_stock.code})最新動向｜『{news_title}』の影響を徹底分析")
            titles.append(f"【解説】{main_stock.name}に何が起きたのか｜関連{theme or '銘柄'}への波及")
            titles.append(f"{main_stock.name}ウォッチ｜『{news_title}』から読むトレードアイデア")
        elif theme:
            titles.append(f"【{theme}】{news_title}｜本命銘柄を徹底解説")
            titles.append(f"{theme}テーマ再燃の予感｜『{news_title}』で狙うべき関連銘柄")
            titles.append(f"『{news_title}』を読み解く｜{theme}で先回りすべき投資戦略")
        else:
            # 個別銘柄もテーマも判定できない場合でも必ずブログ化できるように
            titles.append(f"【速報解説】{news_title}｜投資家への影響をプロ目線で分析")
            titles.append(f"『{news_title}』を3分で理解｜今日押さえるべき関連銘柄と展開")
            titles.append(f"株トレーダー必見｜『{news_title}』で動く主要テーマと注目銘柄")
            titles.append(f"{news_title}から考える投資戦略｜個人投資家が取るべき3つの対応")

    # ==================================================
    # ユニバーサル追加（全タイプ共通の保険タイトル）
    # 個別銘柄材料がない場合でも、PV狙いの汎用タイトルを2本追加
    # ==================================================
    if not main_stock:
        titles.append(f"『{news_title}』の本質を解説｜投資家が絶対に知るべきポイント")

    # 重複除去・フィルタ
    seen = set()
    uniq = []
    for t in titles:
        t = t.strip()
        if not t or t in seen:
            continue
        seen.add(t)
        uniq.append(t)

    # 最低3本は出したい（足りなければ汎用テンプレで補完）
    while len(uniq) < 3:
        candidate = f"『{news_title}』を深掘り｜投資家目線で読み解く次の一手"
        if candidate in seen:
            break
        seen.add(candidate)
        uniq.append(candidate)

    return uniq[:5]


# ==========================================================
# 統合: NewsItemを分析してメタ情報を返す
# ==========================================================

@dataclass
class NewsAnalysis:
    mentioned_stocks: list[StockMention] = field(default_factory=list)
    sentiment: str = "neutral"
    is_breaking: bool = False
    news_type: str = "general"
    blog_titles: list[str] = field(default_factory=list)

    @property
    def has_stock_material(self) -> bool:
        """個別銘柄の材料があるかどうか"""
        return len(self.mentioned_stocks) > 0

    @property
    def sentiment_emoji(self) -> str:
        if self.sentiment == "positive":
            return "📈"
        if self.sentiment == "negative":
            return "📉"
        return "➖"

    @property
    def sentiment_label(self) -> str:
        if self.sentiment == "positive":
            return "ポジティブ"
        if self.sentiment == "negative":
            return "ネガティブ"
        return "中立"


def analyze_news_item(
    title: str,
    summary: str,
    known_stocks: list[tuple[str, str, str]],
) -> NewsAnalysis:
    """ニュース1件を総合分析"""
    full_text = f"{title} {summary}"
    stocks = extract_stock_mentions(full_text, known_stocks)
    sentiment = detect_sentiment(full_text)
    breaking = is_breaking(full_text)
    ntype = detect_news_type(full_text)
    blog = generate_blog_titles(title, summary, stocks, sentiment)
    return NewsAnalysis(
        mentioned_stocks=stocks,
        sentiment=sentiment,
        is_breaking=breaking,
        news_type=ntype,
        blog_titles=blog,
    )
