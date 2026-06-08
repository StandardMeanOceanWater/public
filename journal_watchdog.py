#!/usr/bin/env python3
"""
Journal Watchdog — checks if Pages build is ready, then sends Telegram.
Runs every 30 min from 14:00-22:00 on Fridays.
"""
import json, os, sys, urllib.request
from datetime import datetime
from pathlib import Path

STATUS_FILE = Path("/mnt/f/MD/notes/.journal_pending.json")
ENV_FILE = Path.home() / ".hermes" / ".env"

def load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

load_env()
BOT_TOKEN = os.environ.get("NEWSBOY_BOT_TOKEN", "")
CHAT_ID = os.environ.get("NEWSBOY_CHAT_ID", "686734095")
CHAT_ID2 = os.environ.get("NEWSBOY_CHAT_ID2", "")

def send_telegram(text):
    if not BOT_TOKEN:
        return False
    targets = [CHAT_ID]
    if CHAT_ID2:
        targets.append(CHAT_ID2)
    chunks = []
    while len(text) > 4000:
        cut = text[:4000].rfind("\n")
        if cut < 2000:
            cut = 4000
        chunks.append(text[:cut])
        text = text[cut:]
    chunks.append(text)
    for target in targets:
        for chunk in chunks:
            data = json.dumps({
                "chat_id": target,
                "text": chunk,
                "parse_mode": "HTML",
                "link_preview_options": {"is_disabled": True}
            }).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                data=data, headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(req, timeout=15)
            except Exception as e:
                print(f"  Telegram error (target {target}): {e}")
                return False
    return True

def main():
    if not STATUS_FILE.exists():
        print("  No status file — nothing pending")
        return

    status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    if status.get("sent"):
        print("  Already sent — cleaning up")
        STATUS_FILE.unlink()
        return

    now = datetime.now()
    html_url = status["html_url"]
    raw_url = status["raw_url"]
    date_str = status["date"]
    # Cutoff: 22:00
    cutoff_hour = 22

    # Check if Pages is ready
    pages_ready = False
    try:
        req = urllib.request.Request(html_url, method="HEAD")
        resp = urllib.request.urlopen(req, timeout=10)
        if resp.status == 200:
            pages_ready = True
    except Exception:
        pass

    if pages_ready:
        link_url = html_url
        link_label = "渲染版"
    elif now.hour >= cutoff_hour:
        link_url = raw_url
        link_label = "原始 MD（渲染逾時）"
    else:
        print(f"  Pages not ready yet ({now.hour}:{now.minute:02d} < {cutoff_hour}:00) — waiting")
        return

    # Build and send notification
    lines = [f'<a href=\"{link_url}\">📰 本週科學期刊 — {date_str}</a>', ""]
    if status["science_count"]:
        lines.append(f"Science {status['science_header']}：{status['science_count']} 篇")
    if status["nature_count"]:
        lines.append(f"Nature Vol {status['nature_vol']} Iss {status['nature_iss']}：{status['nature_count']} 篇")
    if status["nature_online_count"]:
        lines.append(f"  線上先行：{status['nature_online_count']} 篇")
    lines.append("")
    lines.append(f"（{link_label}）")

    notify_text = "\n".join(lines)
    if send_telegram(notify_text):
        print("  Telegram sent")
        status["sent"] = True
        STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        print("  Status updated")
    else:
        print("  Telegram failed — will retry next tick")

if __name__ == "__main__":
    main()
