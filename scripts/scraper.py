#!/usr/bin/env python3
"""
NPBファーム集客トラッカー 自動更新スクレイパー
npb.jp/bis/2026/games/ から静的HTMLで観客数を取得する
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
    '千葉ロッテマリーンズ': 'ロッテ', '北海道日本ハムファイターズ': '日本ハム',
    '東北楽天ゴールデンイーグルス': '楽天', '福岡ソフトバンクホークス': 'ソフトバンク',
    '埼玉西武ライオンズ': '西武', 'オリックス・バファローズ': 'オリックス',
    '読売ジャイアンツ': '巨人', '東京ヤクルトスワローズ': 'ヤクルト',
    '横浜DeNAベイスターズ': 'DeNA', '阪神タイガース': '阪神',
    '広島東洋カープ': '広島', '中日ドラゴンズ': '中日',
    'オイシックス新潟アルビレックスBC': 'オイシックス', 'ハヤテベンチャーズ静岡': 'ハヤテ',
    '東北楽天': '楽天', '埼玉西武': '西武', '千葉ロッテ': 'ロッテ',
    '北海道日本ハム': '日本ハム', '福岡ソフトバンク': 'ソフトバンク',
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html',
    'Accept-Language': 'ja',
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

def get_farm_game_ids():
    """日程一覧ページからファーム試合IDを全取得"""
    url = 'https://npb.jp/bis/2026/games/index_farm.html'
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            print(f"  日程ページ取得失敗: {res.status_code}")
            return []
        ids = list(dict.fromkeys(
            re.findall(r'fs\d+', res.text)
        ))
        print(f"  ゲームID取得: {len(ids)}件")
        return ids
    except Exception as e:
        print(f"  日程ページエラー: {e}")
        return []

def scrape_game(game_id, target_dates):
    """個別試合ページから観客数・チーム・日付を取得"""
    url = f'https://npb.jp/bis/2026/games/{game_id}.html'
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            return None
        html = res.text

        # 日付を取得（fs2026MMDD形式から）
        date_match = re.search(r'fs(\d{4})(\d{2})(\d{2})', game_id)
        if not date_match:
            return None
        game_date = f'{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}'

        # 対象日でなければスキップ
        if game_date not in target_dates:
            return None

        # 観客数
        aud_match = re.search(r'入場者\s*[-－]\s*([\d,]+)', html)
        if not aud_match:
            return None
        audience = int(aud_match.group(1).replace(',', ''))

        # チーム名（タイトルから）
        title_match = re.search(r'（(.+?)vs(.+?)）', html)
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
        print(f"  エラー {game_id}: {e}")
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

    # 全ゲームIDを取得
    all_ids = get_farm_game_ids()
    target_set = set(target_dates)

    new_games = []
    for game_id in all_ids:
        if game_id in existing_ids:
            continue

        result = scrape_game(game_id, target_set)
        if result:
            new_games.append(result)
            existing_ids.add(game_id)
            print(f"  ✅ {result['date']} {result['home']} vs {result['away']} {result['audience']:,}人")
        time.sleep(0.3)

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
