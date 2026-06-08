#!/usr/bin/env python3
"""
Weekly API usage report for Jin Lin.
Checks: Exa (log count), DeepL (API), OpenRouter (API + model breakdown)
Sends report via Telegram.
"""

import json
import os
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────
LOG_DIR = Path.home() / ".hermes" / "logs"
ENV_FILE = Path.home() / ".hermes" / ".env"

EXA_COST_PER_SEARCH = 0.007
EXA_TOTAL_CREDIT = 20.00
USAGE_THRESHOLD = 0.85

# ── Helpers ─────────────────────────────────────────────────
def read_env_key(name):
    if not ENV_FILE.exists():
        return ""
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{name}=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip()
    return ""

def curl_get(url, headers=None, timeout=15):
    cmd = ["curl", "-s", "--max-time", str(timeout), url]
    if headers:
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+5)
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return None

def count_exa_from_log():
    count = 0
    for log_file in LOG_DIR.glob("*.log"):
        try:
            result = subprocess.run(
                ["grep", "-c", "Exa search", str(log_file)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip().isdigit():
                count += int(result.stdout.strip())
        except Exception:
            pass
    return count

# ── Check each service ──────────────────────────────────────
def check_exa():
    searches = count_exa_from_log()
    cost = searches * EXA_COST_PER_SEARCH
    pct = (cost / EXA_TOTAL_CREDIT * 100) if EXA_TOTAL_CREDIT else 0
    return {
        "service": "Exa",
        "usage": f"{searches:,} searches",
        "cost": f"${cost:.2f}",
        "budget": f"${EXA_TOTAL_CREDIT:.2f}",
        "pct": pct,
        "raw_pct": pct,
        "details": f"${EXA_COST_PER_SEARCH}/search",
        "status": "ok" if pct < USAGE_THRESHOLD * 100 else "warning",
    }

def check_deepl():
    key = read_env_key("DEEPL_API_KEY")
    if not key:
        return {"service": "DeepL", "status": "no_key", "details": "API key not set"}
    data = curl_get(
        "https://api-free.deepl.com/v2/usage",
        {"Authorization": f"DeepL-Auth-Key {key}"}
    )
    if not data:
        return {"service": "DeepL", "status": "error", "details": "API request failed"}
    count = data.get("character_count", 0)
    limit = data.get("character_limit", 1_000_000)
    pct = (count / limit * 100) if limit else 0
    return {
        "service": "DeepL",
        "usage": f"{count:,} chars",
        "cost": "Free",
        "budget": f"{limit:,} chars/mo",
        "pct": pct,
        "raw_pct": pct,
        "details": f"Free tier, resets monthly",
        "status": "ok" if pct < USAGE_THRESHOLD * 100 else "warning",
    }

def check_openrouter():
    key = read_env_key("OPENROUTER_API_KEY")
    if not key:
        return {"service": "OpenRouter", "status": "no_key"}
    # Credits
    credits = curl_get(
        "https://openrouter.ai/api/v1/credits",
        {"Authorization": f"Bearer {key}"}
    )
    if not credits:
        return {"service": "OpenRouter", "status": "error"}

    total_credits = credits.get("data", {}).get("total_credits", 0)
    total_usage = credits.get("data", {}).get("total_usage", 0)
    remaining = max(0, total_credits - total_usage)
    pct = (total_usage / total_credits * 100) if total_credits else 0

    result = {
        "service": "OpenRouter",
        "usage": f"${total_usage:.2f} used",
        "cost": f"${total_usage:.2f}",
        "budget": f"${total_credits:.2f}",
        "pct": pct,
        "raw_pct": pct,
        "remaining": f"${remaining:.2f}",
        "details": None,
        "status": "ok",
    }

    # Key-level rate limit info
    key_info = curl_get(
        "https://openrouter.ai/api/v1/key",
        {"Authorization": f"Bearer {key}"}
    )
    if key_info and key_info.get("data"):
        kd = key_info["data"]
        limit = kd.get("limit")
        limit_remaining = kd.get("limit_remaining")
        is_free = kd.get("is_free_tier", False)
        usage_daily = kd.get("usage_daily", 0)
        usage_weekly = kd.get("usage_weekly", 0)
        usage_monthly = kd.get("usage_monthly", 0)

        if is_free:
            result["details"] = f"Free tier | Daily: ${usage_daily:.2f} | Weekly: ${usage_weekly:.2f} | Monthly: ${usage_monthly:.2f}"
            # Free tier 沒有明確 limit，但通常有 rate limit
            result["budget"] = "Free tier (rate limited)"
        elif limit and limit_remaining is not None:
            key_pct = ((limit - limit_remaining) / limit * 100) if limit else 0
            result["details"] = f"Key quota: {limit_remaining:.0f}/{limit:.0f} ({key_pct:.0f}% used)"

    return result

# ── Format report ───────────────────────────────────────────
def format_report(results):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"📊 <b>API 用量週報</b> ({now})",
        f"",
    ]

    warnings = []
    for r in results:
        if r.get("status") in ("error", "no_key"):
            status_icon = "⚠️"
        elif r.get("status") == "warning":
            status_icon = "🔴"
            warnings.append(r["service"])
        else:
            status_icon = "🟢"

        line = f"{status_icon} <b>{r['service']}</b>"
        if "usage" in r:
            line += f"\n   用量：{r['usage']}"
        if "cost" in r and r["cost"] != "Free":
            line += f" | 費用：{r['cost']}"
        if "budget" in r:
            line += f"\n   額度：{r['budget']}"
        if "pct" in r:
            line += f" | 使用率：{r['raw_pct']:.1f}%"
        if "remaining" in r:
            line += f"\n   剩餘：{r['remaining']}"
        if "details" in r and r["details"]:
            line += f"\n   {r['details']}"
        lines.append(line)

    if warnings:
        lines.append("")
        lines.append(f"⚠️ <b>警告：{', '.join(warnings)} 已達 {USAGE_THRESHOLD*100:.0f}% 門檻！</b>")

    return "\n".join(lines)

def send_telegram(message):
    bot_token = read_env_key("NEWSBOY_BOT_TOKEN")
    chat_id = read_env_key("NEWSBOY_CHAT_ID")
    if not bot_token or not chat_id:
        print("Telegram not configured")
        return False

    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True}
    }).encode()

    cmd = [
        "curl", "-s", "--max-time", "15",
        "-X", "POST",
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        "-H", "Content-Type: application/json",
        "-d", payload.decode()
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        data = json.loads(result.stdout)
        return data.get("ok", False)
    except Exception as e:
        print(f"Telegram send error: {e}")
        return False

# ── Main ────────────────────────────────────────────────────
def main():
    print("Checking API usage...")

    results = [
        check_exa(),
        check_deepl(),
        check_openrouter(),
    ]

    report = format_report(results)
    plain = report.replace("<b>", "").replace("</b>", "")
    print(plain)

    if "--send" in sys.argv:
        if send_telegram(report):
            print("\n✅ Telegram sent")
        else:
            print("\n❌ Telegram failed")

if __name__ == "__main__":
    main()
