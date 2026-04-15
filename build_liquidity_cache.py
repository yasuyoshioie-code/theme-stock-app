"""全銘柄の直近30日平均売買代金を計算して liquidity_cache.parquet に保存

取得は一度だけでよい。週次ぐらいで再実行すれば十分。
結果: ticker → avg_value_yen（平均売買代金・円）
"""
from __future__ import annotations

import concurrent.futures as cf
import os
import time
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

import pandas as pd
import yfinance as yf

APP_DIR = os.path.dirname(__file__)
PARQUET_SRC = os.path.join(APP_DIR, "default_sectors.parquet")
CACHE_DST = os.path.join(APP_DIR, "liquidity_cache.parquet")

BATCH_SIZE = 100
MAX_WORKERS = 4


def _download_batch(batch: list[str], start: str, end: str) -> pd.DataFrame | None:
    try:
        data = yf.download(
            batch,
            start=start,
            end=end,
            group_by="ticker",
            progress=False,
            threads=True,
            auto_adjust=False,
        )
        return data if data is not None and not data.empty else None
    except Exception:
        return None


def main() -> None:
    df = pd.read_parquet(PARQUET_SRC)
    tickers = sorted(df["ticker"].unique().tolist())
    print(f"[tickers] {len(tickers)} unique")

    end = datetime.now()
    start = end - timedelta(days=45)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    batches = [tickers[i : i + BATCH_SIZE] for i in range(0, len(tickers), BATCH_SIZE)]
    print(f"[batches] {len(batches)} × {BATCH_SIZE}")

    t0 = time.time()
    results: list[pd.DataFrame] = []
    with cf.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(_download_batch, b, start_str, end_str) for b in batches]
        for i, fut in enumerate(cf.as_completed(futures), 1):
            data = fut.result()
            if data is not None:
                results.append(data)
            print(f"  [{i}/{len(batches)}] done in {time.time()-t0:.1f}s")
    print(f"[fetched] {len(results)} batches in {time.time()-t0:.1f}s")

    liq: dict[str, float] = {}
    for data in results:
        if not isinstance(data.columns, pd.MultiIndex):
            continue
        for ticker in data.columns.get_level_values(0).unique():
            try:
                sub = data[ticker]
                if "Close" not in sub.columns or "Volume" not in sub.columns:
                    continue
                close = sub["Close"].astype(float)
                volume = sub["Volume"].astype(float)
                avg_val = (close * volume).mean()
                if pd.notna(avg_val) and avg_val > 0:
                    liq[ticker] = float(avg_val)
            except Exception:
                continue

    out = pd.DataFrame([{"ticker": t, "avg_value_yen": v} for t, v in liq.items()])
    out = out.sort_values("avg_value_yen", ascending=False).reset_index(drop=True)
    out.to_parquet(CACHE_DST, engine="pyarrow", compression="zstd", index=False)
    size_mb = os.path.getsize(CACHE_DST) / 1024 / 1024
    print(f"[written] {CACHE_DST} ({len(out)} tickers, {size_mb:.2f} MB)")

    print("\n[top 10]")
    for _, r in out.head(10).iterrows():
        print(f"  {r['ticker']}: {r['avg_value_yen']/1e8:.1f}億円")

    print("\n[distribution]")
    thresholds = [1e9, 5e8, 1e8, 5e7, 1e7]
    for th in thresholds:
        n = (out["avg_value_yen"] >= th).sum()
        print(f"  >= {th/1e8:.1f}億円: {n}銘柄")


if __name__ == "__main__":
    main()
