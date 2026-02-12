import sys
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd

# 元のスプレッドシートから全テーマ・銘柄をパース
ef = pd.ExcelFile(
    r"C:\Users\oievi\Downloads\テーマ別銘柄一覧_詳細.xlsx", engine="openpyxl"
)
df = pd.read_excel(ef, sheet_name="テーマ別個別銘柄", engine="openpyxl")

current_theme = str(df.columns[0]).replace("■", "").strip()
themes = {}
rows = []
for _, row in df.iterrows():
    val0 = str(row.iloc[0]).strip()
    if val0.startswith("■"):
        if current_theme and rows:
            themes[current_theme] = rows
        current_theme = val0.replace("■", "").strip()
        rows = []
        continue
    if val0 in ("証券コード", "コード", "nan", "", "None"):
        continue
    code = val0
    name = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
    rows.append((code, name))
if current_theme and rows:
    themes[current_theme] = rows

# =========================================================
# 追加銘柄（テーマごとに漏れている主要銘柄を補完）
# =========================================================
additions = {
    "レアアース": [
        ("4082", "第一稀元素化学工業"),
        ("5714", "DOWAホールディングス"),
    ],
    "防衛": [
        ("6503", "三菱電機"),
        ("4403", "日油"),
    ],
    "半導体": [
        ("6871", "日本マイクロニクス"),
        ("7741", "HOYA"),
        ("7751", "キヤノン"),
    ],
    "フィジカルAI": [
        ("6645", "オムロン"),
        ("6981", "村田製作所"),
    ],
    "ペロブスカイト太陽電池": [
        ("6255", "エヌ・ピー・シー"),
        ("4080", "田中化学研究所"),
    ],
    "人工知能": [
        ("4382", "HEROZ"),
        ("4443", "Sansan"),
    ],
    "データセンター": [
        ("9513", "J-POWER"),
    ],
    "地方銀行": [
        ("8336", "武蔵野銀行"),
        ("8342", "青森銀行"),
        ("8349", "東北銀行"),
    ],
    "サイバーセキュリティ": [
        ("4258", "FFRIセキュリティ"),
    ],
    "TOPIXコア30": [
        ("8058", "三菱商事"),
        ("8031", "三井物産"),
        ("6702", "富士通"),
        ("7267", "ホンダ"),
        ("4502", "武田薬品工業"),
        ("4503", "アステラス製薬"),
        ("6367", "ダイキン工業"),
        ("6971", "京セラ"),
        ("9020", "JR東日本"),
        ("9022", "JR東海"),
        ("4568", "第一三共"),
        ("6594", "ニデック"),
        ("8766", "東京海上HD"),
        ("8801", "三井不動産"),
    ],
    "ドローン": [
        ("6378", "木村化工機"),
        ("9232", "パスコ"),
    ],
    "ダイヤモンド": [
        ("6136", "OSG"),
    ],
    "国土強靱化": [
        ("1719", "安藤ハザマ"),
        ("5233", "太平洋セメント"),
    ],
    "レアメタル": [
        ("4082", "第一稀元素化学工業"),
    ],
    "量子コンピューター": [
        ("6758", "ソニーG"),
    ],
    "パワー半導体": [
        ("6526", "ソシオネクスト"),
        ("6645", "オムロン"),
    ],
    "食品": [
        ("2264", "森永乳業"),
        ("2267", "ヤクルト本社"),
        ("2809", "キユーピー"),
    ],
    "核融合発電": [
        ("5802", "住友電気工業"),
        ("5406", "神戸製鋼所"),
    ],
    "銀行": [
        ("8750", "第一生命HD"),
    ],
    "海底資源": [
        ("5401", "日本製鉄"),
        ("9104", "商船三井"),
    ],
    "建設": [
        ("1719", "安藤ハザマ"),
        ("1945", "東京エネシス"),
    ],
    "円高メリット": [
        ("3141", "ウエルシアHD"),
    ],
    "半導体製造装置": [
        ("7741", "HOYA"),
        ("6871", "日本マイクロニクス"),
        ("6337", "テセック"),
    ],
    "ロボット": [
        ("6645", "オムロン"),
        ("6981", "村田製作所"),
    ],
    "金": [
        ("5801", "古河電気工業"),
    ],
    "食品スーパー": [
        ("7649", "スギHD"),
        ("3141", "ウエルシアHD"),
    ],
    "下水道": [
        ("6367", "ダイキン工業"),
    ],
    "ゼネコン": [
        ("1719", "安藤ハザマ"),
        ("1808", "長谷工コーポレーション"),
    ],
    "仮想通貨": [
        ("3825", "リミックスポイント"),
    ],
    "半導体部材・部品": [
        ("5802", "住友電気工業"),
        ("6526", "ソシオネクスト"),
    ],
    "水素": [
        ("5802", "住友電気工業"),
    ],
    "ゲーム関連": [
        ("7832", "バンダイナムコHD"),
        ("3851", "日本一ソフトウェア"),
    ],
    "円安メリット": [
        ("6367", "ダイキン工業"),
        ("7269", "スズキ"),
    ],
    "原子力発電": [
        ("5802", "住友電気工業"),
        ("5406", "神戸製鋼所"),
    ],
    "港湾運送": [
        ("9101", "日本郵船"),
        ("9104", "商船三井"),
        ("9107", "川崎汽船"),
    ],
    "JPX日経400": [
        ("4502", "武田薬品工業"),
        ("4568", "第一三共"),
        ("6367", "ダイキン工業"),
        ("8766", "東京海上HD"),
        ("8801", "三井不動産"),
        ("6594", "ニデック"),
        ("7267", "ホンダ"),
        ("9020", "JR東日本"),
        ("9022", "JR東海"),
    ],
}

# 統合処理
for theme, add_list in additions.items():
    if theme not in themes:
        continue
    existing_codes = set(code for code, _ in themes[theme])
    for code, name in add_list:
        if code not in existing_codes:
            themes[theme].append((code, name))
            existing_codes.add(code)

# xlsx出力
output_path = r"C:\Users\oievi\Documents\theme-stock-app\テーマ株セクター全40.xlsx"
with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
    for theme_name, stocks in themes.items():
        sheet_name = theme_name[:31]
        df_out = pd.DataFrame(stocks, columns=["証券コード", "銘柄名"])
        df_out.to_excel(writer, sheet_name=sheet_name, index=False)

print(f"完成: {output_path}")
print(f"テーマ数: {len(themes)}")
total = 0
for name, stocks in themes.items():
    print(f"  {name}: {len(stocks)}銘柄")
    total += len(stocks)
print(f"全銘柄数（重複込み）: {total}")

all_codes = set()
for stocks in themes.values():
    for code, _ in stocks:
        all_codes.add(code)
print(f"ユニーク銘柄数: {len(all_codes)}")
