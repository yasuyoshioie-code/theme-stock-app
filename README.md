# Theme Stock Dashboard

日本株のテーマ別ダッシュボード。セクター一覧、ニュース分析、ETF 2083 組入銘柄トラッカー、翌日騰落予測をまとめた Streamlit アプリです。

## 🚀 ライブデモ

Streamlit Community Cloud にデプロイすると、以下の URL 形式で公開されます:

```
https://<username>-theme-stock-app-app-<hash>.streamlit.app
```

## ✨ 主な機能

- **セクター別株価ボード**: default_sectors.xlsx ベースで日本株を分類表示
- **ニュース統合**: moomoo / 日経 / 株探 / みんかぶ / ロイター / ブルームバーグ / Yahoo!ファイナンス / トウシル / マネクリ / フィスコ / TRADERS WEB 等、18 ソース
- **AI ブログタイトル生成**: ニュース本文から銘柄・センチメントを抽出し、SEO 向けブログタイトルを複数案提示
- **ETF 2083 (NEXT FUNDS 日経平均) 組入トラッカー**: ICE PCF を日次で取得し、2 日間差分・1 週間〜半年の推移・新規/除外を可視化
- **翌日騰落予測**: 複数指標でランキング

## 🏗 ローカル起動

```bash
pip install -r requirements.txt
streamlit run app.py
```

Python 3.11 推奨（`.python-version` 参照）。

## 🔐 シークレット

オプション機能は `.streamlit/secrets.toml` 経由で認証情報を渡します:

```toml
# 四季報オンライン プレミアム（要契約）
shikiho_premium_cookie = "<ブラウザで取得した Cookie ヘッダ全文>"
```

`.streamlit/secrets.toml` は `.gitignore` 済み。Streamlit Cloud では
ダッシュボードの「Secrets」タブに貼り付けます。

## 📂 主要ファイル

| ファイル | 役割 |
|---------|------|
| `app.py` | Streamlit エントリポイント（13 タブ構成） |
| `news_feed.py` | 18 ニュースソースから収集 |
| `news_analyzer.py` | 銘柄抽出 + センチメント + ブログタイトル生成（20 ニュースタイプ対応） |
| `etf2083.py` | ETF 2083 PCF 取得 & SQLite 永続化 |
| `etf2083_ui.py` | ETF 2083 タブ UI |
| `charts.py` | Plotly チャート生成 |
| `next_day_ranking.py` | 翌日騰落予測ロジック |
| `default_sectors.xlsx` | 初期セクター定義 |

## 📜 ライセンス

Private / Internal。
