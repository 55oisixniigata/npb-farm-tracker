#!/usr/bin/env python3
"""
NPBファーム集客トラッカー 自動更新スクレイパー
NPB公式サイト(npb.jp)からファーム試合の観客数を取得する
"""

import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).parent.parent
DATA_FILE = REPO_ROOT / "data.json"

TEAM_MAP = {
    '千葉ロッテマリーンズ': 'ロッテ',
    '北海道日本ハムファイターズ': '日本ハム',
    '東北楽天ゴールデンイーグルス': '楽天',
    '福岡ソフトバンクホークス': 'ソフトバンク',
    '埼玉西武ライオンズ': '西武',
    'オリックス・バファローズ': 'オリックス',
    '読売ジャイアンツ': '巨人',
    '東京ヤクルトスワローズ': 'ヤクルト',
    '横浜DeNAベイスターズ': 'DeNA',
    '阪神タイガース': '阪神',
    '広島東洋カープ': '広島',
    '中日ドラゴンズ': '中日',
    'オイシックス新潟アルビレックスBC': 'オイシックス',
    'ハヤテベンチャーズ静岡': 'ハヤテ',
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'ja,en-US;q=0.7',
    'Referer': 'https://npb.jp/',
}

def norm(name):
    return TEAM_MAP.get(name.strip(), name.strip())

def load_data():
    if DATA_FILE.exists():
        with open(DATA_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {"version": "2026-v0", "games": []}

def save_data(sidecar):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(sidecar, f, ensure_ascii=False, separators=(',', ':'))

def get_target_dates(games):
    if not games:
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

def get_game_urls_for_month(year, month):
    url = f'https://npb.jp/farm/{year}/schedule_{month:02d}_detail.html'
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            print(f"  日程ページ取得失敗: {url} ({res.status_code})")
            return []
        soup = BeautifulSoup(res.text, 'html.parser')
        links = soup.find_all('a', href=re.compile(r'/scores/\d{4}/\d{4}/'))
        urls = list(dict.fromkeys(
            'https://npb.jp' + a['href'].rstrip('/')
            for a in links
        ))
        print(f"  {year}/{month:02d} 日程ページ: {len(urls)}試合のURLを取得")
        return urls
    except Exception as e:
        print(f"  日程ページエラー: {e}")
        return []

def scrape_game(url, game_date):
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            return None
        soup = BeautifulSoup(res.text, 'html.parser')
        text = soup.get_text()

        # 観客数
        aud_match = re.search(r'入場者\s*([\d,]+)人', text)
        if not aud_match:
            return None
        audience = int(aud_match.group(1).replace(',', ''))

        # ファーム試合かチェック（ファームは観客数が少ない＋タイトルで判断）
        # スコアボードのチーム名
        score_table = soup.find('table')
        teams = []
        if score_table:
            rows = score_table.find_all('tr')
            for row in rows[1:3]:  # ヘッダー除く最初の2行
                cells = row.find_all('td')
                if cells:
                    t = cells[0].get_text(strip=True)
                    # チーム名の長い部分を除去（略称部分を取得）
                    for full, short in TEAM_MAP.items():
                        if full in t or short in t:
                            teams.append(short)
                            break

        if len(teams) < 2:
            # h2タグから取得
            for h in soup.find_all(['h2', 'h3']):
                t = h.get_text()
                if 'VS' in t or 'vs' in t:
                    m = re.search(r'(.+?)\s+[Vv][Ss]\s+(.+)', t)
                    if m:
                        teams = [norm(m.group(1).strip()), norm(m.group(2).strip())]
                        break

        if len(teams) < 2:
            return None

        # URLからID生成
        gid_match = re.search(r'/scores/\d{4}/\d{4}/([\w-]+)$', url)
        gid = game_date.replace('-', '') + '_' + (gid_match.group(1) if gid_match else url.split('/')[-1])

        return {
            'id': gid,
            'date': game_date,
            'home': teams[0],
            'away': teams[1],
            'audience': audience,
        }
    except Exception as e:
        print(f"  スクレイピングエラー {url}: {e}")
        return None

def next_version(current):
    m = re.search(r'v(\d+)$', current)
    n = int(m.group(1)) if m else 0
    return f'2026-v{n + 1}'

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

    months = sorted(set((int(d[:4]), int(d[5:7])) for d in target_dates))

    all_url_map = []
    for year, month in months:
        urls = get_game_urls_for_month(year, month)
        for url in urls:
            dm = re.search(r'/scores/(\d{4})/(\d{2})(\d{2})/', url)
            if dm:
                d = f'{dm.group(1)}-{dm.group(2)}-{dm.group(3)}'
                all_url_map.append((d, url))
        time.sleep(1)

    target_set = set(target_dates)
    filtered = [(d, url) for d, url in all_url_map if d in target_set]
    print(f"対象日の試合URL: {len(filtered)}件")

    new_games = []
    seen_urls = set()
    for game_date, url in filtered:
        if url in seen_urls:
            continue
        seen_urls.add(url)

        result = scrape_game(url, game_date)
        if result:
            if result['id'] in existing_ids:
                continue
            new_games.append(result)
            existing_ids.add(result['id'])
            print(f"  ✅ {result['date']} {result['home']} vs {result['away']} {result['audience']:,}人")
        time.sleep(0.5)

    if not new_games:
        print("⚠️  新規データなし（試合なし、または取得失敗）")
        sys.exit(0)

    all_games = games + new_games
    all_games.sort(key=lambda x: (x['date'], x['id']))

    new_version = next_version(sidecar.get('version', '2026-v0'))
    sidecar['version'] = new_version
    sidecar['games'] = all_games
    save_data(sidecar)

    print(f"\n✅ 更新完了: +{len(new_games)}試合 / 累計{len(all_games)}試合 / {new_version}")

    from collections import defaultdict
    stats = defaultdict(lambda: {'total': 0, 'count': 0})
    for g in all_games:
        stats[g['home']]['total'] += g['audience']
        stats[g['home']]['count'] += 1

    print("\n=== ホーム観客動員数ランキング ===")
    for i, (team, s) in enumerate(sorted(stats.items(), key=lambda x: -x[1]['total']), 1):
        avg = round(s['total'] / s['count'])
        medal = ['🥇', '🥈', '🥉'][i - 1] if i <= 3 else f'{i}.'
        print(f"{medal} {team}: {s['total']:,}人 ({s['count']}試合 / avg {avg:,}人)")

if __name__ == '__main__':
    main()
