#!/usr/bin/env python3
"""
NPBファーム集客トラッカー 自動更新スクレイパー
dメニュースポーツからPlaywrightでデータを取得し、data.jsonを更新する
"""

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

# ── パス設定 ──
REPO_ROOT = Path(__file__).parent.parent
DATA_FILE = REPO_ROOT / "data.json"

# ── チーム名正規化（全角ASCII→半角） ──
def to_half(s):
    return ''.join(
        chr(ord(c) - 0xFEE0) if '\uFF01' <= c <= '\uFF5E' else c
        for c in s
    )

def norm(name):
    return to_half(name)

# ── data.json 読み込み ──
def load_data():
    if DATA_FILE.exists():
        with open(DATA_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {"version": "2026-v0", "games": []}

# ── data.json 保存 ──
def save_data(sidecar):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(sidecar, f, ensure_ascii=False, separators=(',', ':'))

# ── 取得対象日を計算 ──
def get_target_dates(games):
    if not games:
        # データがない場合は開幕日から昨日まで
        start = date(2026, 3, 14)
    else:
        latest = max(g['date'] for g in games)
        start = date.fromisoformat(latest) + timedelta(days=1)
    yesterday = date.today() - timedelta(days=1)
    if start > yesterday:
        return []
    dates = []
    cur = start
    while cur <= yesterday:
        dates.append(cur.isoformat())
        cur += timedelta(days=1)
    return dates

# ── Playwrightでdメニュースポーツをスクレイピング ──
def scrape_with_playwright(target_dates, existing_ids):
    results = []

    scrape_js = """
async (targetDates, existingIds) => {
    const toHalf = s => s.replace(/[\\uFF01-\\uFF5E]/g, c => String.fromCharCode(c.charCodeAt(0) - 0xFEE0));
    const norm = n => toHalf(n);
    const existingSet = new Set(existingIds);
    const allResults = [];

    async function sleep(ms) {
        return new Promise(r => setTimeout(r, ms));
    }

    async function fetchGameIds(dateStr) {
        const md = dateStr.slice(5).replace('-', '');
        const url = `https://service.smt.docomo.ne.jp/portal/sports/baseball_f/schedule.html?md=${md}`;
        try {
            const res = await fetch(url, {credentials: 'omit'});
            const html = await res.text();
            const matches = [...html.matchAll(/game_id=(\\d+)/g)];
            return [...new Set(matches.map(m => m[1]))];
        } catch(e) {
            console.error('fetchGameIds error:', e);
            return [];
        }
    }

    async function scrapeGame(id) {
        const url = `https://service.smt.docomo.ne.jp/portal/sports/baseball_f/schedule_live.html?game_id=${id}`;
        try {
            const res = await fetch(url, {credentials: 'omit'});
            const html = await res.text();

            // 観客数
            const audMatch = html.match(/観客数[^<]*<\\/th>[^<]*<td[^>]*>([\\d,]+)人/);
            const audience = audMatch ? parseInt(audMatch[1].replace(/,/g, '')) : null;

            // タイトルから日付・チーム名
            const titleMatch = html.match(/<title>([^<]+)<\\/title>/);
            const title = titleMatch ? titleMatch[1] : '';
            const tm = title.match(/^(\\S+)\\s+vs\\s+(\\S+)\\((\\d{4})年(\\d{1,2})月(\\d{1,2})日\\)/);
            const home = tm ? norm(tm[1]) : '';
            const away = tm ? norm(tm[2]) : '';
            const actualDate = tm
                ? `${tm[3]}-${String(tm[4]).padStart(2,'0')}-${String(tm[5]).padStart(2,'0')}`
                : null;

            return { id, home, away, audience, actualDate };
        } catch(e) {
            console.error('scrapeGame error:', id, e);
            return null;
        }
    }

    for (const dateStr of targetDates) {
        const ids = await fetchGameIds(dateStr);
        console.log(`${dateStr}: ${ids.length}件のIDを検出`);

        for (const id of ids) {
            if (existingSet.has(id)) continue;

            const info = await scrapeGame(id);
            if (!info || info.audience === null || !info.home) continue;

            if (info.actualDate && info.actualDate !== dateStr) {
                console.warn(`${id}: 日付不一致(期待:${dateStr} 実際:${info.actualDate}) スキップ`);
                continue;
            }

            allResults.push({
                id,
                date: dateStr,
                home: info.home,
                away: info.away,
                audience: info.audience
            });
            existingSet.add(id);
            console.log(`✅ ${id}: ${info.home}vs${info.away} ${info.audience}人`);
            await sleep(500);
        }
        await sleep(300);
    }

    return allResults;
}
"""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        # dメニュースポーツのトップページを開いてからfetch（CORS回避）
        print("dメニュースポーツにアクセス中...")
        try:
            page.goto(
                'https://service.smt.docomo.ne.jp/portal/sports/baseball_f/',
                timeout=30000,
                wait_until='domcontentloaded'
            )
        except Exception as e:
            print(f"初期アクセスエラー（続行）: {e}")

        print(f"対象日: {target_dates}")
        print(f"既存ID数: {len(existing_ids)}件")

        new_games = page.evaluate(scrape_js, [target_dates, list(existing_ids)])

        browser.close()

    return new_games

# ── バージョン番号インクリメント ──
def next_version(current):
    m = re.search(r'v(\d+)$', current)
    n = int(m.group(1)) if m else 0
    return f'2026-v{n + 1}'

# ── メイン ──
def main():
    print("=== NPBファーム集客トラッカー 自動更新 ===")

    sidecar = load_data()
    games = sidecar.get('games', [])
    existing_ids = {g['id'] for g in games}

    target_dates = get_target_dates(games)
    if not target_dates:
        print("✅ すでに最新です（追加データなし）")
        sys.exit(0)

    print(f"取得対象: {target_dates[0]} 〜 {target_dates[-1]} ({len(target_dates)}日分)")

    new_games = scrape_with_playwright(target_dates, existing_ids)

    if not new_games:
        print("⚠️  新規データなし（試合なし、または取得失敗）")
        sys.exit(0)

    # データ統合
    all_games = games + new_games
    all_games.sort(key=lambda x: (x['date'], x['id']))

    new_version = next_version(sidecar.get('version', '2026-v0'))
    sidecar['version'] = new_version
    sidecar['games'] = all_games

    save_data(sidecar)

    print(f"\n✅ 更新完了: +{len(new_games)}試合 / 累計{len(all_games)}試合 / {new_version}")

    # サマリー表示
    from collections import defaultdict
    stats = defaultdict(lambda: {'total': 0, 'count': 0})
    for g in all_games:
        stats[g['home']]['total'] += g['audience']
        stats[g['home']]['count'] += 1

    print("\n=== ホーム観客動員数ランキング ===")
    for i, (team, s) in enumerate(
        sorted(stats.items(), key=lambda x: -x[1]['total']), 1
    ):
        avg = round(s['total'] / s['count'])
        medal = ['🥇', '🥈', '🥉'][i - 1] if i <= 3 else f'{i}.'
        print(f"{medal} {team}: {s['total']:,}人 ({s['count']}試合 / avg {avg:,}人)")

if __name__ == '__main__':
    main()
