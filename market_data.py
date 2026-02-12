import pandas as pd
import yfinance as yf
import streamlit as st

BATCH_SIZE = 50  # yfinanceのレート制限対策


def fetch_market_data_with_progress(
    tickers_tuple: tuple[str, ...],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """プログレスバー付きでデータ取得"""
    tickers = list(tickers_tuple)
    all_data = []
    failed = []

    total_batches = (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE
    progress_bar = st.progress(0, text="株価データを取得中...")

    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        progress_bar.progress(
            batch_num / total_batches,
            text=f"株価データを取得中... ({batch_num}/{total_batches}バッチ, {len(batch)}銘柄)",
        )

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
                    data.columns = pd.MultiIndex.from_product(
                        [[batch[0]], data.columns]
                    )
            else:
                data = yf.download(
                    batch,
                    start=start_date,
                    end=end_date,
                    group_by="ticker",
                    progress=False,
                    threads=True,
                )

            if not data.empty:
                all_data.append(data)
            else:
                failed.extend(batch)
        except Exception as e:
            st.warning(f"バッチ {batch_num} の取得エラー: {e}")
            failed.extend(batch)

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
