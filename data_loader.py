import pandas as pd
import streamlit as st


@st.cache_data(show_spinner="内蔵データを読み込み中...")
def load_sector_data(uploaded_file) -> dict[str, pd.DataFrame]:
    """xlsxファイルを読み込み、セクター名→銘柄DataFrameの辞書を返す

    対応フォーマット:
    1. .parquet: 列 [theme, 証券コード, 銘柄名, ticker] の高速フォーマット（推奨）
    2. xlsx 各シート = 1セクター（シート名がセクター名）
    3. xlsx「テーマ別個別銘柄」シートに全テーマが縦に連結（■ テーマ名 で区切り）

    uploaded_file: UploadedFile オブジェクト または ファイルパス文字列
    """
    # --- Parquet 高速パス ---
    if isinstance(uploaded_file, str) and uploaded_file.endswith(".parquet"):
        return _load_parquet(uploaded_file)

    excel_file = pd.ExcelFile(uploaded_file, engine="openpyxl")
    sectors = {}

    for sheet_name in excel_file.sheet_names:
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name, engine="openpyxl")

        if df.empty or len(df.columns) < 2:
            continue

        # --- フォーマット2: 「■ テーマ名」で区切られた縦連結シートを検出 ---
        first_col_values = df.iloc[:, 0].astype(str)
        has_theme_markers = first_col_values.str.startswith("■").any()

        if has_theme_markers or sheet_name in ("テーマ別個別銘柄",):
            parsed = _parse_concatenated_sheet(df)
            sectors.update(parsed)
            continue

        # --- シートがテーマ一覧（メタ情報）の場合はスキップ ---
        col_names_str = " ".join(str(c) for c in df.columns)
        if "テーマ名" in col_names_str and "関連銘柄数" in col_names_str:
            continue

        # --- フォーマット1: 通常のシート（シート名 = セクター名） ---
        parsed_df = _parse_single_sheet(df)
        if parsed_df is not None and len(parsed_df) > 0:
            sectors[sheet_name] = parsed_df

    return sectors


def _load_parquet(path: str) -> dict[str, pd.DataFrame]:
    """Parquetから theme→DataFrame 辞書を構築（数百ms）"""
    df = pd.read_parquet(path, engine="pyarrow")
    sectors: dict[str, pd.DataFrame] = {}
    for theme, group in df.groupby("theme", sort=False):
        sectors[theme] = group.drop(columns=["theme"]).reset_index(drop=True)
    return sectors


def _parse_concatenated_sheet(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """■ テーマ名 で区切られた縦連結シートをパースする"""
    sectors = {}
    current_theme = None
    rows = []

    for _, row in df.iterrows():
        val0 = str(row.iloc[0]).strip()

        # ■ で始まる行 → テーマ名のセパレータ
        if val0.startswith("■"):
            # 前のテーマのデータを保存
            if current_theme and rows:
                sector_df = _build_sector_df(rows)
                if sector_df is not None and len(sector_df) > 0:
                    sectors[current_theme] = sector_df
            current_theme = val0.replace("■", "").strip()
            rows = []
            continue

        # ヘッダー行（証券コード, 銘柄名, 市場）→ スキップ
        if val0 in ("証券コード", "コード", "code"):
            continue

        # 空行・NaN → スキップ
        if val0 in ("nan", "", "None"):
            continue

        # データ行
        rows.append(row)

    # 最後のテーマを保存
    if current_theme and rows:
        sector_df = _build_sector_df(rows)
        if sector_df is not None and len(sector_df) > 0:
            sectors[current_theme] = sector_df

    # 最初のテーマ名がない場合（シート名のカラムヘッダーがテーマ名）
    if not sectors and len(df) > 0:
        first_col = str(df.columns[0]).strip()
        if first_col.startswith("■"):
            theme_name = first_col.replace("■", "").strip()
            all_rows = []
            for _, row in df.iterrows():
                val0 = str(row.iloc[0]).strip()
                if val0 not in ("証券コード", "コード", "nan", "", "None"):
                    all_rows.append(row)
            if all_rows:
                sector_df = _build_sector_df(all_rows)
                if sector_df is not None:
                    sectors[theme_name] = sector_df

    return sectors


def _build_sector_df(rows: list) -> pd.DataFrame | None:
    """行リストからセクターDataFrameを構築する"""
    if not rows:
        return None

    df = pd.DataFrame(rows)
    df.columns = range(len(df.columns))  # リセット
    df = df.reset_index(drop=True)

    # 証券コードの正規化
    df[0] = df[0].astype(str).str.strip()
    # 数字以外（アルファベット混在コード対応: 285A等）
    # 純粋な数字の場合は4桁ゼロパディング
    df[0] = df[0].apply(lambda x: x.zfill(4) if x.isdigit() else x)

    result = pd.DataFrame()
    result["証券コード"] = df[0]
    result["銘柄名"] = df[1].astype(str).str.strip() if len(df.columns) > 1 else ""
    if len(df.columns) > 2:
        result["市場"] = df[2].astype(str).str.strip()
    result["ticker"] = result["証券コード"] + ".T"

    # 無効な行を除外
    result = result[result["証券コード"].str.len() >= 3]
    result = result[~result["証券コード"].isin(["nan", "None", ""])]
    result = result.reset_index(drop=True)

    return result if len(result) > 0 else None


def _parse_single_sheet(df: pd.DataFrame) -> pd.DataFrame | None:
    """通常の1シート = 1セクター形式をパースする"""
    code_col = None
    name_col = None
    for col in df.columns:
        col_str = str(col)
        if "コード" in col_str or "code" in col_str.lower():
            code_col = col
        if "銘柄" in col_str or "name" in col_str.lower():
            name_col = col

    if code_col is None:
        code_col = df.columns[0]
    if name_col is None and len(df.columns) > 1:
        name_col = df.columns[1]

    df[code_col] = df[code_col].astype(str).str.strip()
    df[code_col] = df[code_col].apply(lambda x: x.zfill(4) if x.isdigit() else x)

    result = pd.DataFrame()
    result["証券コード"] = df[code_col]
    result["銘柄名"] = df[name_col].astype(str).str.strip() if name_col else ""
    result["ticker"] = result["証券コード"] + ".T"

    # 無効な行を除外
    result = result[result["証券コード"].str.len() >= 3]
    result = result[~result["証券コード"].isin(["nan", "None", ""])]
    result = result.reset_index(drop=True)

    return result if len(result) > 0 else None


def get_all_tickers(sectors: dict[str, pd.DataFrame]) -> list[str]:
    """全セクターから重複排除した全ティッカーリストを返す"""
    all_tickers = set()
    for df in sectors.values():
        all_tickers.update(df["ticker"].tolist())
    return sorted(all_tickers)


def get_sector_tickers(sectors: dict[str, pd.DataFrame]) -> dict[str, list[str]]:
    """セクター名→ティッカーリストの辞書を返す"""
    return {name: df["ticker"].tolist() for name, df in sectors.items()}
