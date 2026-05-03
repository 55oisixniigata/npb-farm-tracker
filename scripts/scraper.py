#!/usr/bin/env python3
"""
NPBファーム集客トラッカー 自動更新スクレイパー
npb.jp/bis/2026/games/fgmYYYYMMDD.html から試合IDを取得し
npb.jp/bis/2026/games/fsXXXX.html から観客数を取得する
"""

import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).parent.parent
DATA_FILE = REPO_ROOT / "data.json"

TEAM_MAP = {
    '千葉ロッテマリーンズ': 'ロッテ', '北海道日本ハムファイターズ': '日本ハム',
    '東北楽天ゴールデンイーグルス': '楽天', '福岡ソフトバンクホークス': 'ソフトバンク',
    '埼玉西武ライオンズ': '西武', 'オリックス・バファローズ': 'オリックス',
    '読売ジャイアンツ': '巨人', '東京ヤクルトスワローズ': 'ヤクルト',
    '横浜DeNAベイスターズ': 'DeNA', '阪神タイガース': '阪神',
    '広島東洋カープ': '広島', '中日ドラゴンズ': '中日',
    'オイシックス新潟アルビレックスBC': 'オイシックス', 'ハヤテベンチャーズ静岡': 'ハヤテ',
    '東北楽天': '楽天', '埼玉西武': '西武', '千葉ロッテ': 'ロッテ',
    '北海道日本ハム': '日本ハム', '福岡ソフトバンク': 'ソフトバンク',
    'ハヤテ静岡': 'ハヤテ', 'ハヤテ': 'ハヤテ',
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Referer': 'https://npb.jp/',
}

def norm(name):
    name = name.strip()
    return TEAM_MAP.get(name, name)

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

def get_game_ids_for_date(date_str):
    """日付ごとのページからファーム試合IDを取得"""
    ymd = date_str.replace('-', '')
    url = f'https://npb.jp/bis/2026/games/fgm{ymd}.html'
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  日程ページ {date_str}: status={res.status_code} len={len(res.text)}")
        if res.status_code != 200:
            return []
        ids = list(dict.fromkeys(re.findall(r'fs\d+', res.text)))
        print(f"  {date_str}: {len(ids)}件のゲームID: {ids}")
        return ids
    except Exception as e:
        print(f"  {date_str} エラー: {e}")
        return []

def scrape_game(game_id, game_date):
    """個別試合ページから観客数・チームを取得"""
    url = f'https://npb.jp/bis/2026/games/{game_id}.html'
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        html = res.text
        print(f"    {game_id}: status={res.status_code} len={len(html)}")

        if res.status_code != 200:
            return None

        # 観客数（複数パターン）
        aud_match = re.search(r'入場者[\s\u3000]*[-－\-][\s\u3000]*([\d,]+)', html)
        if not aud_match:
            idx = html.find('入場者')
            if idx >= 0:
                print(f"    入場者周辺: {repr(html[idx:idx+30])}")
            else:
                print(f"    入場者: 見つからず（中止の可能性）")
            return None
        audience = int(aud_match.group(1).replace(',', ''))

        # チーム名
        title_match = re.search(r'[（(](.+?)vs(.+?)[）)]', html)
        if not title_match:
            return None
        home = norm(title_match.group(1))
        away = norm(title_match.group(2))

        return {
            'id': game_id,
            'date': game_date,
            'home': home,
            'away': away,
            'audience': audience,
        }
    except Exception as e:
        print(f"    エラー {game_id}: {e}")
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

    new_games = []
    for d in target_dates:
        ids = get_game_ids_for_date(d)
        for game_id in ids:
            if game_id in existing_ids:
                continue
            result = scrape_game(game_id, d)
            if result:
                new_games.append(result)
                existing_ids.add(game_id)
                print(f"  ✅ {result['date']} {result['home']} vs {result['away']} {result['audience']:,}人")
            time.sleep(0.3)
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
