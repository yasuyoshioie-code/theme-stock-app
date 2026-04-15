"""default_sectors.xlsx を Parquet に変換（ロード時間 数十秒 → 数百ms）

Parquet は単一ファイル列指向なので、1,578テーマ×数銘柄 ≒ 数千行 なら 1MB 未満で
読み込みは pyarrow で 100-300ms 程度に短縮される。

出力フォーマット: columns = [theme, 証券コード, 銘柄名, ticker]
"""
from __future__ import annotations

import os
import time

import pandas as pd

SRC = os.path.join(os.path.dirname(__file__), "default_sectors.xlsx")
DST = os.path.join(os.path.dirname(__file__), "default_sectors.parquet")


def main() -> None:
    t0 = time.time()
    xl = pd.ExcelFile(SRC, engine="openpyxl")
    print(f"[open] {len(xl.sheet_names)} sheets in {time.time()-t0:.1f}s")

    rows: list[dict] = []
    for i, sheet in enumerate(xl.sheet_names):
        df = xl.parse(sheet)
        if df.empty or len(df.columns) < 2:
            continue
        code_col = df.columns[0]
        name_col = df.columns[1]
        for _, r in df.iterrows():
            code = str(r[code_col]).strip()
            name = str(r[name_col]).strip()
            if code in ("nan", "None", "") or len(code) < 3:
                continue
            if code.isdigit():
                code = code.zfill(4)
            rows.append({
                "theme": sheet,
                "証券コード": code,
                "銘柄名": name,
                "ticker": code + ".T",
            })
        if (i + 1) % 200 == 0:
            print(f"  [{i+1}/{len(xl.sheet_names)}] sheets parsed")

    out = pd.DataFrame(rows)
    print(f"[parsed] {len(out)} rows in {time.time()-t0:.1f}s")

    out.to_parquet(DST, engine="pyarrow", compression="zstd", index=False)
    size_mb = os.path.getsize(DST) / 1024 / 1024
    print(f"[written] {DST} = {size_mb:.2f} MB")

    # 読み戻しで検証
    t1 = time.time()
    back = pd.read_parquet(DST, engine="pyarrow")
    print(f"[read-back] {len(back)} rows, {back['theme'].nunique()} themes in {time.time()-t1:.2f}s")


if __name__ == "__main__":
    main()
