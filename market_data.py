import concurrent.futures as _cf
import threading

import pandas as pd
import streamlit as st
import yfinance as yf

# yfinance の同時接続上限を踏まえつつ、1バッチを大きめに、並列で走らせる
BATCH_SIZE = 100
MAX_WORKERS = 4

_PROGRESS_LOCK = threading.Lock()


def _download_batch(batch: list[str], start_date: str, end_date: str) -> tuple[list[str], pd.DataFrame | None]:
    """単一バッチをダウンロード。戻り値 = (batch, data or None)"""
    try:
        if len(batch) == 1:
            data = yf.download(
                batch,
                start=start_date,
                end=end_date,
                progress=False,
                threads=True,
            )
            if not data.empty and not isinstance(data.columns, pd.MultiIndex):
                data.columns = pd.MultiIndex.from_product([[batch[0]], data.columns])
        else:
            data = yf.download(
                batch,
                start=start_date,
                end=end_date,
                group_by="ticker",
                progress=False,
                threads=True,
            )
        if data is None or data.empty:
            return batch, None
        return batch, data
    except Exception:
        return batch, None


@st.cache_data(ttl=900, show_spinner=False)
def fetch_market_data_with_progress(
    tickers_tuple: tuple[str, ...],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """プログレスバー付きでデータ取得（バッチ並列 + 15分キャッシュ）

    同一ティッカーセット・同期間の再取得は 15 分キャッシュでスキップ。
    初回は MAX_WORKERS 並列でバッチダウンロード。
    """
    tickers = list(tickers_tuple)
    batches = [tickers[i : i + BATCH_SIZE] for i in range(0, len(tickers), BATCH_SIZE)]
    total_batches = len(batches)

    all_data: list[pd.DataFrame] = []
    failed: list[str] = []
    done = {"count": 0}

    progress_bar = st.progress(
        0,
        text=f"株価データを取得中... (0/{total_batches}バッチ, 並列{min(MAX_WORKERS, total_batches)})",
    )

    with _cf.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(_download_batch, b, start_date, end_date) for b in batches]
        for fut in _cf.as_completed(futures):
            batch, data = fut.result()
            if data is not None:
                all_data.append(data)
            else:
                failed.extend(batch)
            with _PROGRESS_LOCK:
                done["count"] += 1
                progress_bar.progress(
                    done["count"] / total_batches,
                    text=f"株価データを取得中... ({done['count']}/{total_batches}バッチ完了)",
                )

    progress_bar.empty()

    if failed:
        st.warning(f"{len(failed)}銘柄のデータ取得に失敗しました")

    if not all_data:
        return pd.DataFrame()

    if len(all_data) == 1:
        return all_data[0]

    result = pd.concat(all_data, axis=1)
    result = result.loc[:, ~result.columns.duplicated()]
    return result


def get_available_tickers(data: pd.DataFrame) -> list[str]:
    """取得できたティッカーの一覧を返す"""
    if isinstance(data.columns, pd.MultiIndex):
        return sorted(set(data.columns.get_level_values(0)))
    return []
