#!/usr/bin/env python3
"""Git post-commit hook — 自動記錄 commit 到 hermes-daily"""
import subprocess, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

tz = timezone(timedelta(hours=8))
now = datetime.now(tz)

repo_path = Path.cwd()
daily_dir = Path("/mnt/f/MD/hermes-daily")
daily_file = daily_dir / f"{now.strftime('%Y-%m-%d')}.md"

# 從 git 取得 commit 資訊
try:
    branch = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, timeout=5
    ).stdout.strip()
    msg = subprocess.run(
        ["git", "-C", str(repo_path), "log", "-1", "--format=%s"],
        capture_output=True, text=True, timeout=5
    ).stdout.strip()
    repo_name = repo_path.name
except:
    sys.exit(0)

# 寫入 daily log（若檔案存在則 append，不存在則略過）
if not daily_file.exists():
    sys.exit(0)

lines = daily_file.read_text(encoding="utf-8").splitlines()

# 找 ### 區段結尾或檔案結尾插入
# 在最後一個 ### 區段之前插入一則 commit 紀錄
entry = f"- `{now.strftime('%H:%M')}` [{repo_name}] `{branch}` {msg}"

# 檢查是否已存在相同紀錄（避免重複觸發）
if any(entry in l for l in lines):
    sys.exit(0)

# 插到所有 ### 區段之後、檔案最末
# 找最後一個非空白行
insert_pos = len(lines)
for i in range(len(lines)-1, -1, -1):
    if lines[i].strip():
        insert_pos = i + 1
        break

lines.insert(insert_pos, entry)
daily_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
