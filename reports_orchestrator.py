#!/usr/bin/env python3
"""
Reports Orchestrator — 統一排程檢查 + 執行（no_agent 模式）
判斷此刻該跑哪個報紙任務，執行它，輸出 JSON 結果供 agent 處理
"""
import json, subprocess, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ========== 排程表 ==========
SCHEDULES = {
    "限免報": {
        "check": lambda now: (now.hour == 12 and 10 <= now.minute < 20)
                             or (now.hour == 17 and 10 <= now.minute < 20),
        "cmd": [sys.executable, str(Path("/mnt/f/MD/scripts/DinnerTimeFreeAPP.py"))],
        "run_any_day": True,
    },
    "API週報": {
        "check": lambda now: now.weekday() == 3 and now.hour == 7 and 0 <= now.minute < 10,
        "cmd": [sys.executable, str(Path("/mnt/f/MD/scripts/weekly_usage_report.py")), "--send"],
        "run_any_day": False,
    },
    "期刊報PhaseA": {
        "check": lambda now: now.weekday() == 3 and now.hour == 15 and 0 <= now.minute < 10,
        "cmd": [sys.executable, str(Path("/mnt/f/MD/scripts/weekly_journal.py"))],
        "run_any_day": False,
    },
    "TODO提醒": {
        "check": lambda now: now.hour == 19 and 0 <= now.minute < 10,
        "cmd": ["cat", str(Path.home() / ".hermes" / "todo.md")],
        "run_any_day": True,
    },
}

WATCHDOG_CMD = [sys.executable, str(Path("/mnt/f/MD/scripts/journal_watchdog.py"))]

def is_phase_b_time(now):
    """週五 13:00~22:00 每整點/半點跑 watchdog"""
    return now.weekday() == 4 and 13 <= now.hour < 22

def main():
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    result = {"task": None, "status": "skip", "output": ""}

    # 1. 先檢查排程任務
    for name, sched in SCHEDULES.items():
        if sched["check"](now):
            print(json.dumps({"task": name, "status": "running", "output": ""}))
            flush = True
            try:
                r = subprocess.run(sched["cmd"], capture_output=True, text=True, timeout=300)
                out = r.stdout.strip() + ("\n" + r.stderr.strip() if r.stderr.strip() else "")
                print(json.dumps({"task": name, "status": "ok" if r.returncode == 0 else "fail", "output": out[:2000]}, ensure_ascii=False))
                return
            except subprocess.TimeoutExpired:
                print(json.dumps({"task": name, "status": "timeout", "output": ""}))
                return

    # 2. Phase B watchdog — 自帶 Telegram 發送，只檢查是否該跑
    if is_phase_b_time(now):
        r = subprocess.run(WATCHDOG_CMD, capture_output=True, text=True, timeout=30)
        out = (r.stdout + r.stderr).strip()
        if out:
            print(json.dumps({"task": "期刊報PhaseB", "status": "watchdog", "output": out[:500]}, ensure_ascii=False))
            return

    # 3. 沒事
    print(json.dumps(result))

if __name__ == "__main__":
    main()
