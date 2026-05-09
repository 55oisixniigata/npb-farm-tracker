#!/usr/bin/env python3
"""
NPBファーム集客トラッカー 自動更新スクレイパー
Cloudflare Worker経由でNPB公式から観客数を取得する
"""

import json
import os
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).parent.parent
DATA_FILE = REPO_ROOT / "data.json"

# Cloudflare WorkerのURL
WORKER_URL = "https://npb-farm-scraper.wsss716.workers.dev"

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
    '横浜DeNA': 'DeNA', '読売': '巨人', '東京ヤクルト': 'ヤクルト',
    'オイシックス新潟': 'オイシックス', 'ハヤテ静岡': 'ハヤテ',
    '広島東洋': '広島', 'オリックス': 'オリックス', '中日': '中日',
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

def fetch_games_for_date(date_str):
    """Cloudflare Worker経由でNPBから試合データを取得"""
    try:
        res = requests.get(f"{WORKER_URL}/?date={date_str}", timeout=30)
        if res.status_code != 200:
            print(f"  {date_str}: Worker エラー {res.status_code}")
            return []
        data = res.json()
        games = data.get('games', [])
        print(f"  {date_str}: {len(games)}試合取得")
        return games
    except Exception as e:
        print(f"  {date_str}: エラー {e}")
        return []

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
        sidecar['updated_at'] = date.today().isoformat()
        save_data(sidecar)
        print("✅ すでに最新です（追加データなし）")
        sys.exit(0)

    print(f"取得対象: {target_dates[0]} 〜 {target_dates[-1]} ({len(target_dates)}日分)")

    new_games = []
    for d in target_dates:
        fetched = fetch_games_for_date(d)
        for g in fetched:
            if g['id'] in existing_ids:
                continue
            # チーム名を正規化
            g['home'] = norm(g['home'])
            g['away'] = norm(g['away'])
            new_games.append(g)
            existing_ids.add(g['id'])
            print(f"  ✅ {g['date']} {g['home']} vs {g['away']} {g['audience']:,}人")
        time.sleep(0.5)

    if not new_games:
        sidecar['updated_at'] = date.today().isoformat()
        save_data(sidecar)
        print("⚠️  新規データなし（試合なし、または雨天中止）")
        sys.exit(0)
    
    all_games = games + new_games
    all_games.sort(key=lambda x: (x['date'], x['id']))

    new_version = next_version(sidecar.get('version', '2026-v0'))
    sidecar['version'] = new_version
    sidecar['updated_at'] = date.today().isoformat()  # ← これを追加
    sidecar['games'] = all_games
    save_data(sidecar)
    send_slack(new_games, all_games, os.environ.get('SLACK_WEBHOOK_URL', ''))

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

def send_slack(new_games, all_games, webhook_url):
    if not webhook_url:
        return
    
    from collections import defaultdict
    stats = defaultdict(lambda: {'total': 0, 'count': 0})
    for g in all_games:
        stats[g['home']]['total'] += g['audience']
        stats[g['home']]['count'] += 1
    
    sorted_stats = sorted(stats.items(), key=lambda x: -x[1]['total'])
    
    start_date = min(g['date'] for g in all_games)
    end_date = max(g['date'] for g in all_games)
    
    medals = ['🥇', '🥈', '🥉']
    ranking_lines = []
    for i, (team, s) in enumerate(sorted_stats):
        avg = round(s['total'] / s['count'])
        medal = medals[i] if i < 3 else f'{i+1}.'
        ranking_lines.append(f'{medal}　{team}：{s["total"]:,}人　（avg {avg:,}人）')
    
    text = (
        f'📣 *NPBファーム集客トラッカー更新*\n'
        f'📅 {start_date}〜{end_date}　／　📊 +{len(new_games)}試合（累計 {len(all_games)}試合）\n\n'
        f'━━━━━━━━━━━━━━━━━━━━━━\n'
        f'🏆 ホーム観客動員数ランキング\n'
        f'━━━━━━━━━━━━━━━━━━━━━━\n'
        + '\n'.join(ranking_lines) + '\n\n'
        f'🔗 https://55oisixniigata.github.io/npb-farm-tracker/'
    )
    
    import urllib.request
    import json as _json
    payload = _json.dumps({'text': text}).encode('utf-8')
    req = urllib.request.Request(webhook_url, data=payload, headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=10)
    print('✅ Slack通知送信完了')

if __name__ == '__main__':
    main()
