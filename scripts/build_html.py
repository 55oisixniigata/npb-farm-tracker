#!/usr/bin/env python3
"""
data.json の内容を index.html の INITIAL_DATA と DATA_VERSION に書き込む
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DATA_FILE = REPO_ROOT / "data.json"
HTML_FILE = REPO_ROOT / "index.html"


def main():
    with open(DATA_FILE, encoding='utf-8') as f:
        sidecar = json.load(f)

    version = sidecar.get('version', '2026-v0')
    games = sidecar.get('games', [])

    json_compact = json.dumps(games, ensure_ascii=False, separators=(',', ':'))

    with open(HTML_FILE, encoding='utf-8') as f:
        content = f.read()

    # INITIAL_DATA を差し替え
    content = re.sub(
        r'const INITIAL_DATA = \[.*?\];',
        f'const INITIAL_DATA = {json_compact};',
        content,
        flags=re.DOTALL
    )

    # DATA_VERSION を差し替え（存在しない場合はスキップ）
    if "const DATA_VERSION = '" in content:
        content = re.sub(
            r"const DATA_VERSION = '[^']*';",
            f"const DATA_VERSION = '{version}';",
            content
        )

    # last-updated の静的テキストも更新
    if games:
        latest = max(g['date'] for g in games)
        content = re.sub(
            r'最終更新: [^<"]*',
            f'最終更新: {latest}',
            content
        )

    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ index.html 更新完了: {len(games)}試合 / {version} / 最終{latest if games else '—'}")


if __name__ == '__main__':
    main()
