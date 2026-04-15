"""ETF 2083（NF・日本成長株アクティブ上場投信）組入銘柄トラッカー

機能:
  - 東証PCF（日次）から組入銘柄CSVを取得
  - SQLite に日次スナップショットを蓄積
  - 日付間の差分分析（新規・除外・買い増し・売却）
  - 銘柄別タイムライン（株数・評価額・構成比推移）

データソース:
  - https://inav.ice.com/pcf-download/2083.csv （平日 7:50-23:55 のみ）

元ネタ: etf2083-tracker (FastAPI + React) → Streamlit統合版。
"""
from __future__ import annotations

import csv
import sqlite3
import urllib.request
import urllib.error
from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path

PCF_URL = "https://inav.ice.com/pcf-download/2083.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
DB_PATH = Path(__file__).parent / "data" / "etf2083.db"
JST = timezone(timedelta(hours=9))


# ==========================================================
# 日本語名マッピング（PCFは英語名のため）
# ==========================================================
CODE_TO_JP: dict[str, str] = {
    "7203": "トヨタ自動車", "6758": "ソニーグループ", "8306": "三菱UFJフィナンシャル・グループ",
    "6861": "キーエンス", "8035": "東京エレクトロン", "6501": "日立製作所",
    "9984": "ソフトバンクグループ", "9432": "日本電信電話（NTT）", "6098": "リクルートホールディングス",
    "7741": "ホーヤ（HOYA）", "4063": "信越化学工業", "4568": "第一三共",
    "9433": "KDDI", "6902": "デンソー", "7974": "任天堂",
    "8058": "三菱商事", "6367": "ダイキン工業", "3382": "セブン&アイ・ホールディングス",
    "4519": "中外製薬", "6594": "ニデック", "6920": "レーザーテック",
    "8316": "三井住友フィナンシャルグループ", "8411": "みずほフィナンシャルグループ",
    "8766": "東京海上ホールディングス", "8801": "三井不動産", "8802": "三菱地所",
    "8591": "オリックス", "8750": "第一生命ホールディングス", "8309": "三井住友トラストHD",
    "8001": "伊藤忠商事", "8031": "三井物産", "8053": "住友商事", "8015": "豊田通商",
    "7267": "ホンダ", "7269": "スズキ", "7270": "SUBARU", "7201": "日産自動車",
    "7211": "三菱自動車工業", "7261": "マツダ", "6326": "クボタ",
    "7011": "三菱重工業", "7012": "川崎重工業", "7013": "IHI",
    "6702": "富士通", "6503": "三菱電機", "6504": "富士電機", "6506": "安川電機",
    "6645": "オムロン", "6674": "ジーエス・ユアサ", "6701": "NEC",
    "6723": "ルネサスエレクトロニクス", "6724": "セイコーエプソン",
    "6752": "パナソニックHD", "6762": "TDK", "6770": "アルプスアルパイン",
    "6841": "横河電機", "6857": "アドバンテスト", "6869": "シスメックス",
    "6954": "ファナック", "6971": "京セラ", "6976": "太陽誘電",
    "6981": "村田製作所", "7735": "SCREENホールディングス",
    "7751": "キヤノン", "7752": "リコー",
    "6146": "ディスコ", "6526": "ソシオネクスト", "6963": "ローム", "8036": "日立ハイテク",
    "4684": "オービック", "4689": "Zホールディングス", "4812": "電通総研",
    "4755": "楽天グループ", "9434": "ソフトバンク", "9613": "NTTデータグループ",
    "3659": "ネクソン", "4478": "フリー", "3697": "SHIFT", "4385": "メルカリ",
    "2413": "エムスリー", "3923": "ラクス", "9766": "コナミグループ",
    "9697": "カプコン", "9684": "スクウェア・エニックスHD", "7532": "パン・パシフィックINTL HD",
    "4502": "武田薬品工業", "4503": "アステラス製薬", "4507": "塩野義製薬",
    "4523": "エーザイ", "4528": "小野薬品工業", "4578": "大塚ホールディングス",
    "4543": "テルモ", "4151": "協和キリン",
    "3401": "帝人", "3402": "東レ", "3407": "旭化成",
    "4005": "住友化学", "4021": "日産化学", "4042": "東ソー", "4043": "トクヤマ",
    "4061": "デンカ", "4183": "三井化学", "4188": "三菱ケミカルグループ", "4208": "UBE",
    "4452": "花王", "4901": "富士フイルムHD", "4911": "資生堂",
    "5401": "日本製鉄", "5411": "JFEホールディングス", "5706": "三井金属鉱業",
    "5713": "住友金属鉱山", "5714": "DOWAホールディングス",
    "5802": "住友電気工業", "5803": "フジクラ",
    "6103": "オークマ", "6113": "アマダ", "6273": "SMC",
    "6301": "小松製作所", "6302": "住友重機械工業", "6305": "日立建機",
    "6361": "荏原製作所", "6370": "栗田工業", "6471": "日本精工", "6473": "ジェイテクト",
    "1801": "大成建設", "1802": "大林組", "1803": "清水建設", "1812": "鹿島建設",
    "1925": "大和ハウス工業", "1928": "積水ハウス", "1878": "大東建託",
    "2502": "アサヒグループHD", "2503": "キリンホールディングス",
    "2801": "キッコーマン", "2802": "味の素", "2914": "日本たばこ産業（JT）",
    "7453": "良品計画", "9983": "ファーストリテイリング", "3099": "三越伊勢丹HD",
    "9020": "JR東日本", "9021": "JR西日本", "9022": "JR東海",
    "9062": "日本通運", "9064": "ヤマトホールディングス",
    "9101": "日本郵船", "9104": "商船三井", "9107": "川崎汽船",
    "1605": "INPEX", "5019": "出光興産", "5020": "ENEOSホールディングス",
    "9501": "東京電力HD", "9502": "中部電力", "9503": "関西電力",
    "2127": "日本M&AセンターHD", "4307": "野村総合研究所", "6988": "日東電工",
    "7733": "オリンパス", "9602": "東宝", "2587": "サントリー食品INTL",
    "4612": "日本ペイントHD", "6479": "ミネベアミツミ", "4661": "オリエンタルランド",
    "6532": "ベイカレント・コンサルティング", "2317": "システナ", "9143": "SGホールディングス",
    "7936": "アシックス", "8830": "住友不動産", "5631": "日本製鋼所",
    "3064": "モノタロウ", "7846": "パイロットコーポレーション", "3891": "ニッポン高度紙工業",
    "4536": "参天製薬", "8111": "ゴールドウイン", "5801": "古河電気工業",
    "4516": "日本新薬", "7832": "バンダイナムコHD", "6951": "日本電子",
    "6845": "アズビル", "4666": "パーク24", "285A": "キオクシアホールディングス",
    "4046": "大阪ソーダ", "7730": "マニー", "2001": "ニップン",
    "7202": "いすゞ自動車", "7182": "ゆうちょ銀行", "7366": "リタリコ",
    "4088": "エア・ウォーター", "9830": "トラスコ中山", "5991": "日本発條",
    "7747": "朝日インテック", "5334": "日本特殊陶業", "4461": "第一工業製薬",
    "6750": "エレコム", "4686": "ジャストシステム", "4022": "ラサ工業",
    "6754": "アンリツ", "4613": "関西ペイント", "6134": "フジ",
    "6383": "ダイフク", "7911": "TOPPANホールディングス", "6331": "三菱化工機",
    "4617": "中国塗料", "4403": "日油", "6871": "日本マイクロニクス",
    "4071": "プラスアルファ・コンサルティング",
}


def to_jp_name(code: str, en_name: str = "") -> str:
    """証券コード→日本語名。未登録なら英語名をそのまま返す。"""
    return CODE_TO_JP.get(code, en_name)


# ==========================================================
# PCF CSV パーサー（ICE Data Services 形式）
# ==========================================================
def parse_pcf_csv(raw_csv: str) -> dict:
    """PCF CSVをパースして構造化データを返す。"""
    lines = raw_csv.strip().split("\n")
    if len(lines) < 4:
        raise ValueError(f"PCF行数不足: {len(lines)}行")

    header_cols = [c.strip().strip('"') for c in lines[0].split(",")]
    value_cols = [c.strip().strip('"') for c in lines[1].split(",")]
    meta = dict(zip(header_cols, value_cols))

    shares_outstanding = _to_float(meta.get("Shares Outstanding", "0"))
    fund_cash = _to_float(meta.get("Fund Cash Component", "0"))

    data_start = 2
    while data_start < len(lines) and lines[data_start].strip() == "":
        data_start += 1
    if data_start >= len(lines):
        raise ValueError("銘柄ヘッダー行が見つかりません")

    reader = csv.DictReader(lines[data_start:])
    holdings = []
    total_market_value = 0.0

    for row in reader:
        code = _get_field(row, ["Code", "code", "Ticker", "Securities Code"])
        if not code or code.lower().startswith("discl") or code.lower().startswith("note"):
            continue

        name = _get_field(row, ["Name", "name", "Security Name", "Constituent Name"])
        isin = _get_field(row, ["ISIN", "isin"])
        exchange = _get_field(row, ["Exchange", "exchange"])
        currency = _get_field(row, ["Currency", "currency"]) or "JPY"
        shares = _to_float(_get_field(row, ["Shares", "Shares Amount", "shares"]))
        stock_price = _to_float(_get_field(row, ["Stock Price", "Price", "stock_price"]))
        market_value = _to_float(_get_field(row, ["Market Value", "market_value"]))

        if not market_value and shares and stock_price:
            market_value = shares * stock_price
        total_market_value += market_value

        holdings.append({
            "code": code,
            "name": to_jp_name(code, name),
            "isin": isin,
            "exchange": exchange,
            "currency": currency,
            "shares": shares,
            "stock_price": stock_price,
            "market_value": market_value,
            "weight": 0.0,
        })

    if total_market_value > 0:
        for h in holdings:
            h["weight"] = round(h["market_value"] / total_market_value * 100, 4)

    return {
        "shares_outstanding": shares_outstanding,
        "fund_cash_component": fund_cash,
        "holdings": holdings,
    }


def is_pcf_available(raw: str) -> bool:
    """HTMLや時間外メッセージでないか判定"""
    lower = raw[:500].lower()
    if "<html" in lower:
        return False
    if "pcf file download service" in lower:
        return False
    if raw.strip() == "":
        return False
    return True


def _get_field(row: dict, keys: list) -> str:
    stripped = {rk.strip(): rv for rk, rv in row.items()}
    for k in keys:
        if k in stripped and stripped[k]:
            return stripped[k].strip().strip('"')
    return ""


def _to_float(s: str) -> float:
    if not s:
        return 0.0
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return 0.0


# ==========================================================
# SQLite ストレージ
# ==========================================================
def _get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """テーブル作成"""
    with closing(_get_conn()) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS pcf_snapshots (
            fetch_date TEXT PRIMARY KEY,
            shares_outstanding REAL DEFAULT 0,
            fund_cash_component REAL DEFAULT 0,
            total_holdings INTEGER DEFAULT 0,
            source TEXT DEFAULT 'pcf',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS holdings (
            fetch_date TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT DEFAULT '',
            shares REAL DEFAULT 0,
            stock_price REAL DEFAULT 0,
            market_value REAL DEFAULT 0,
            weight REAL DEFAULT 0,
            PRIMARY KEY (fetch_date, code)
        );
        CREATE INDEX IF NOT EXISTS idx_holdings_date ON holdings(fetch_date);
        CREATE INDEX IF NOT EXISTS idx_holdings_code ON holdings(code);
        """)
        conn.commit()


def save_snapshot(fetch_date: str, parsed: dict, source: str = "pcf"):
    """パース済みデータをDBに保存（同日データは上書き）"""
    init_db()
    with closing(_get_conn()) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO pcf_snapshots
            (fetch_date, shares_outstanding, fund_cash_component, total_holdings, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            fetch_date,
            parsed["shares_outstanding"],
            parsed["fund_cash_component"],
            len(parsed["holdings"]),
            source,
            datetime.now().isoformat(),
        ))
        conn.execute("DELETE FROM holdings WHERE fetch_date = ?", (fetch_date,))
        conn.executemany("""
            INSERT INTO holdings
            (fetch_date, code, name, shares, stock_price, market_value, weight)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            (fetch_date, h["code"], h["name"], h["shares"],
             h["stock_price"], h["market_value"], h["weight"])
            for h in parsed["holdings"]
        ])
        conn.commit()


def fetch_latest_pcf() -> dict:
    """東証PCFを取得→DB保存→結果を返す"""
    init_db()
    date = datetime.now(JST).strftime("%Y-%m-%d")

    with closing(_get_conn()) as conn:
        existing = conn.execute(
            "SELECT fetch_date FROM pcf_snapshots WHERE fetch_date = ?", (date,)
        ).fetchone()
    if existing:
        return {"status": "skip", "date": date, "message": f"{date}は取得済み"}

    try:
        req = urllib.request.Request(PCF_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        return {"status": "error", "message": f"ネットワークエラー: {e}"}

    if not is_pcf_available(raw):
        return {"status": "unavailable", "message": "PCFダウンロード時間外（平日 7:50-23:55）"}

    try:
        parsed = parse_pcf_csv(raw)
    except Exception as e:
        return {"status": "error", "message": f"パース失敗: {e}"}

    save_snapshot(date, parsed, source="pcf")
    return {"status": "ok", "date": date, "count": len(parsed["holdings"])}


def import_csv_manual(raw_csv: str, date: str) -> dict:
    """手動アップロードCSVを保存"""
    if not is_pcf_available(raw_csv):
        return {"status": "error", "message": "有効なPCFデータではありません"}
    try:
        parsed = parse_pcf_csv(raw_csv)
    except Exception as e:
        return {"status": "error", "message": f"パース失敗: {e}"}
    save_snapshot(date, parsed, source="pcf_import")
    return {"status": "ok", "date": date, "count": len(parsed["holdings"])}


# ==========================================================
# 参照API
# ==========================================================
def list_dates() -> list[dict]:
    """取得済み日付一覧（新しい順）"""
    init_db()
    with closing(_get_conn()) as conn:
        rows = conn.execute("""
            SELECT fetch_date, total_holdings, shares_outstanding, source
            FROM pcf_snapshots ORDER BY fetch_date DESC
        """).fetchall()
    return [dict(r) for r in rows]


def get_holdings(date: str) -> list[dict]:
    """特定日の全銘柄（評価額降順）"""
    init_db()
    with closing(_get_conn()) as conn:
        rows = conn.execute("""
            SELECT code, name, shares, stock_price, market_value, weight
            FROM holdings WHERE fetch_date = ?
            ORDER BY market_value DESC
        """, (date,)).fetchall()
    return [dict(r) for r in rows]


def get_diff(date_from: str, date_to: str) -> dict:
    """2日間の差分分析"""
    from_rows = {r["code"]: r for r in get_holdings(date_from)}
    to_rows = {r["code"]: r for r in get_holdings(date_to)}
    if not from_rows:
        return {"status": "error", "message": f"{date_from}のデータなし"}
    if not to_rows:
        return {"status": "error", "message": f"{date_to}のデータなし"}

    from_codes = set(from_rows.keys())
    to_codes = set(to_rows.keys())

    new = [to_rows[c] for c in sorted(to_codes - from_codes)]
    removed = [from_rows[c] for c in sorted(from_codes - to_codes)]

    changes = []
    unchanged = 0
    for c in from_codes & to_codes:
        sf = from_rows[c]["shares"]
        st = to_rows[c]["shares"]
        if sf and st != sf:
            pct = (st - sf) / sf * 100
            changes.append({
                "code": c,
                "name": to_rows[c]["name"],
                "shares_from": sf,
                "shares_to": st,
                "shares_diff": st - sf,
                "change_pct": round(pct, 2),
                "value_from": from_rows[c]["market_value"],
                "value_to": to_rows[c]["market_value"],
                "weight_to": to_rows[c]["weight"],
            })
        else:
            unchanged += 1

    increases = sorted([c for c in changes if c["shares_diff"] > 0],
                       key=lambda x: -x["change_pct"])
    decreases = sorted([c for c in changes if c["shares_diff"] < 0],
                       key=lambda x: x["change_pct"])

    return {
        "status": "ok",
        "date_from": date_from, "date_to": date_to,
        "total_from": len(from_codes), "total_to": len(to_codes),
        "new": new, "removed": removed,
        "increases": increases, "decreases": decreases,
        "unchanged_count": unchanged,
    }


def get_timeline(code: str) -> list[dict]:
    """銘柄別の株数・評価額推移（古い順）"""
    init_db()
    with closing(_get_conn()) as conn:
        rows = conn.execute("""
            SELECT fetch_date, shares, stock_price, market_value, weight
            FROM holdings WHERE code = ? ORDER BY fetch_date
        """, (code,)).fetchall()
    return [dict(r) for r in rows]


def get_period_trend(days: int = 30) -> dict:
    """指定日数の期間推移データを返す。

    Returns
    -------
    {
      "status": "ok" | "insufficient",
      "date_from": str,
      "date_to": str,
      "dates": list[str],
      "trend_daily": [
        {"date": str, "total_holdings": int, "total_market_value": float,
         "shares_outstanding": float}
      ],
      "top_codes": list[str],     # 最新日のtop10銘柄コード
      "top_names": dict[code, name],
      "weight_timeseries": {code: [{"date": str, "weight": float, "market_value": float}]},
    }
    """
    init_db()
    dates_info = list_dates()
    if not dates_info:
        return {"status": "empty"}

    all_dates_asc = sorted([d["fetch_date"] for d in dates_info])
    date_to = all_dates_asc[-1]

    # 指定日数前以降の日付だけ残す（足りなければ最古まで）
    if days > 0:
        from datetime import datetime as _dt, timedelta as _td
        cutoff = (_dt.strptime(date_to, "%Y-%m-%d") - _td(days=days)).strftime("%Y-%m-%d")
        period_dates = [d for d in all_dates_asc if d >= cutoff]
    else:
        period_dates = all_dates_asc  # 全期間

    if len(period_dates) < 1:
        return {"status": "insufficient", "message": "期間内にデータなし"}

    date_from = period_dates[0]

    # 日毎のサマリ
    with closing(_get_conn()) as conn:
        placeholder = ",".join(["?"] * len(period_dates))
        snap_rows = conn.execute(f"""
            SELECT fetch_date, total_holdings, shares_outstanding
            FROM pcf_snapshots
            WHERE fetch_date IN ({placeholder})
            ORDER BY fetch_date
        """, period_dates).fetchall()
        holdings_rows = conn.execute(f"""
            SELECT fetch_date, code, name, shares, market_value, weight
            FROM holdings
            WHERE fetch_date IN ({placeholder})
            ORDER BY fetch_date
        """, period_dates).fetchall()

    # 日毎総評価額
    daily_mv = {}
    for r in holdings_rows:
        daily_mv[r["fetch_date"]] = daily_mv.get(r["fetch_date"], 0.0) + (r["market_value"] or 0)

    trend_daily = []
    for r in snap_rows:
        trend_daily.append({
            "date": r["fetch_date"],
            "total_holdings": r["total_holdings"],
            "total_market_value": daily_mv.get(r["fetch_date"], 0.0),
            "shares_outstanding": r["shares_outstanding"],
        })

    # 最新日のTop10
    latest = [r for r in holdings_rows if r["fetch_date"] == date_to]
    latest_sorted = sorted(latest, key=lambda r: -(r["market_value"] or 0))[:10]
    top_codes = [r["code"] for r in latest_sorted]
    top_names = {r["code"]: r["name"] for r in latest_sorted}

    # 各topコードの期間中推移
    weight_ts = {c: [] for c in top_codes}
    for r in holdings_rows:
        c = r["code"]
        if c in weight_ts:
            weight_ts[c].append({
                "date": r["fetch_date"],
                "weight": r["weight"] or 0,
                "market_value": r["market_value"] or 0,
                "shares": r["shares"] or 0,
            })
    for c in weight_ts:
        weight_ts[c].sort(key=lambda x: x["date"])

    return {
        "status": "ok",
        "date_from": date_from,
        "date_to": date_to,
        "dates": period_dates,
        "trend_daily": trend_daily,
        "top_codes": top_codes,
        "top_names": top_names,
        "weight_timeseries": weight_ts,
    }


def get_period_movers(days: int = 30, top_n: int = 10) -> dict:
    """指定期間の最大変動銘柄（構成比ベース）

    Returns
    -------
    {
      "status": "ok" | "insufficient",
      "date_from": str, "date_to": str,
      "gainers": [...],   # 構成比の増加が大きい順
      "losers": [...],    # 減少が大きい順
      "new": [...],       # 期間中に新規組入
      "removed": [...],   # 期間中に除外
    }
    """
    trend = get_period_trend(days)
    if trend.get("status") != "ok":
        return {"status": trend.get("status", "empty")}

    date_from = trend["date_from"]
    date_to = trend["date_to"]

    if date_from == date_to:
        return {"status": "insufficient", "message": "期間内に1日分しかデータがありません"}

    diff = get_diff(date_from, date_to)
    if diff["status"] != "ok":
        return diff

    # 構成比変化で並び替え（株数変化でなく金額ベース）
    from_map = {r["code"]: r for r in get_holdings(date_from)}
    to_map = {r["code"]: r for r in get_holdings(date_to)}

    movers = []
    for code in set(from_map.keys()) & set(to_map.keys()):
        wf = from_map[code]["weight"] or 0
        wt = to_map[code]["weight"] or 0
        mf = from_map[code]["market_value"] or 0
        mt = to_map[code]["market_value"] or 0
        sf = from_map[code]["shares"] or 0
        stt = to_map[code]["shares"] or 0
        movers.append({
            "code": code,
            "name": to_map[code]["name"],
            "weight_from": wf,
            "weight_to": wt,
            "weight_diff": round(wt - wf, 4),
            "market_value_from": mf,
            "market_value_to": mt,
            "shares_from": sf,
            "shares_to": stt,
            "shares_diff": stt - sf,
            "shares_change_pct": round((stt - sf) / sf * 100, 2) if sf else 0,
        })

    gainers = sorted(movers, key=lambda x: -x["weight_diff"])[:top_n]
    losers = sorted(movers, key=lambda x: x["weight_diff"])[:top_n]

    return {
        "status": "ok",
        "date_from": date_from,
        "date_to": date_to,
        "gainers": gainers,
        "losers": losers,
        "new": diff["new"],
        "removed": diff["removed"],
        "total_from": diff["total_from"],
        "total_to": diff["total_to"],
    }


def get_summary() -> dict:
    """全期間サマリ"""
    dates = list_dates()
    if not dates:
        return {"status": "empty", "total_snapshots": 0}

    dates_asc = sorted([d["fetch_date"] for d in dates])
    first_date = dates_asc[0]
    last_date = dates_asc[-1]

    first_codes = {r["code"] for r in get_holdings(first_date)}
    last_holdings = get_holdings(last_date)
    last_codes = {r["code"] for r in last_holdings}
    top20 = last_holdings[:20]

    return {
        "status": "ok",
        "dates": dates_asc,
        "date_first": first_date,
        "date_last": last_date,
        "total_snapshots": len(dates_asc),
        "holdings_first": len(first_codes),
        "holdings_last": len(last_codes),
        "new_since_start": sorted(last_codes - first_codes),
        "removed_since_start": sorted(first_codes - last_codes),
        "top20": top20,
    }
