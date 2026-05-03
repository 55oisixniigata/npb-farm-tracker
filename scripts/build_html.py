#!/usr/bin/env python3
"""
data.json の内容を確認するだけ（index.htmlは触らない）
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DATA_FILE = REPO_ROOT / "data.json"


def main():
    with open(DATA_FILE, encoding='utf-8') as f:
        sidecar = json.load(f)

    version = sidecar.get('version', '2026-v0')
    games = sidecar.get('games', [])
    latest = max(g['date'] for g in games) if games else '—'

    print(f"✅ data.json 確認: {len(games)}試合 / {version} / 最終{latest}")


if __name__ == '__main__':
    main()
