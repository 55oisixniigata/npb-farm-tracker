# NPBファーム 集客トラッカー 2026

NPBファーム公式戦の観客動員数を自動収集・可視化するダッシュボード。

## 🔄 自動更新

GitHub Actionsで **毎日JST 23:00** に自動実行：

1. dメニュースポーツからPlaywrightでスクレイピング
2. `data.json` に追記
3. `index.html` を再生成
4. GitHub Pagesに自動デプロイ

## 📁 ファイル構成

```
├── index.html              # ダッシュボード（GitHub Pagesで公開）
├── data.json               # 試合データ（自動更新）
├── scripts/
│   ├── scraper.py          # Playwrightスクレイパー
│   └── build_html.py       # index.html更新スクリプト
└── .github/workflows/
    └── update.yml          # GitHub Actions定義
```

## 🚀 GitHub Pagesの設定

1. リポジトリの **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: **main** / **/ (root)**
4. Save

## ⚙️ 手動実行

```bash
pip install playwright
playwright install chromium
python scripts/scraper.py
python scripts/build_html.py
```

## 📊 データについて

- データソース: [dメニュースポーツ](https://service.smt.docomo.ne.jp/portal/sports/baseball_f/)
- 収録期間: 2026年3月14日（開幕）〜
- 前年比較: 2025年の同試合数時点での平均と比較
