#!/usr/bin/env python3
"""
Bridge inbox processor（no_agent 模式）— 單一檔案版
讀取 bridge.jsonl 中 from: tyto 的訊息，簡單指令直接處理，回覆寫入同一檔案
"""
import json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

tz = timezone(timedelta(hours=8))
BRIDGE_DIR = Path.home() / ".hermes" / "bridge"
BRIDGE = BRIDGE_DIR / "bridge.jsonl"
POS = BRIDGE_DIR / "bubo_pos.txt"

def get_pos():
    """回傳上次處理到的 message ID"""
    return POS.read_text().strip() if POS.exists() else None

def set_pos(msg_id):
    POS.write_text(msg_id)

def read_new():
    """掃 bridge.jsonl 中所有 from=tyto 且 id 比上次新的訊息"""
    if not BRIDGE.exists():
        return []
    last_id = get_pos()
    msgs, found = [], last_id is None
    for line in BRIDGE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
        except:
            continue
        if m.get("from") != "tyto":
            continue
        if found:
            msgs.append(m)
        elif m.get("id") == last_id:
            found = True
    return msgs

def reply(text):
    """回覆寫入同一 bridge.jsonl"""
    msg = {
        "id": f"bubo-{datetime.now(tz).strftime('%H%M%S')}",
        "from": "bubo",
        "to": "tyto",
        "text": text,
        "timestamp": datetime.now(tz).isoformat(),
    }
    with open(BRIDGE, "a", encoding="utf-8") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")

def extract_item(text, prefix):
    item = text.split(prefix, 1)[-1].strip()
    for e in ["🔴", "🟡", "🟢", "⬜", "✅"]:
        item = item.replace(e, "").strip()
    return item

def handle(msg):
    text = msg.get("text", "").strip()
    if not text:
        return "skip"

    # STATUS
    if text == "STATUS":
        todo = Path("/home/jin/.hermes/todo.md")
        n = (
            sum(
                1
                for l in todo.read_text().splitlines()
                if l.strip() and l.strip()[0].isdigit() and "**" in l
            )
            if todo.exists()
            else 0
        )
        reply(f"STATUS: 待辦 {n} 項，系統正常")
        return "done"

    # TODO 完成 / TODO DONE
    prefix = ""
    if text.upper().startswith("TODO DONE"):
        prefix = "TODO DONE"
    elif text.startswith("TODO 完成"):
        prefix = "TODO 完成"
    if prefix:
        item = extract_item(text, prefix)
        todo = Path("/home/jin/.hermes/todo.md")
        if todo.exists() and item:
            lines = todo.read_text().splitlines()
            found = False
            for i, line in enumerate(lines):
                clean = line.lstrip("0123456789. ").replace("**", "").strip()
                if item in clean and "##" not in line and line.strip():
                    lines.pop(i)
                    for j, l in enumerate(lines):
                        if "## 📝" in l:
                            lines.insert(j, f"- [x] {clean}")
                            break
                    todo.write_text("\n".join(lines))
                    reply(f"✅ 已完成：{item}")
                    found = True
                    break
            if not found:
                reply(f"⚠️ 找不到：{item}")
        else:
            reply(f"✅ 標記完成：{item}")
        return "done"

    # TODO 新增 / TODO ADD
    prefix = ""
    if text.upper().startswith("TODO ADD"):
        prefix = "TODO ADD"
    elif text.startswith("TODO 新增"):
        prefix = "TODO 新增"
    if prefix:
        item = extract_item(text, prefix)
        todo = Path("/home/jin/.hermes/todo.md")
        if todo.exists() and item:
            content = todo.read_text()
            lines = content.splitlines(True)
            for i, l in enumerate(lines):
                if "## 🟢" in l:
                    lines.insert(i, f"15. **{item}** — 新增自 Telegram\n")
                    break
            todo.write_text("".join(lines))
        reply(f"➕ 新增：{item}")
        return "done"

    # NOTIFY
    if text.startswith("NOTIFY"):
        reply(f"BUBO 通知：{text[6:].strip()}")
        return "done"

    # 其餘 → 回覆"需要 agent 處理"
    reply(
        f"收到：{text[:80]}{'…' if len(text) > 80 else ''}\n（此訊息需 agent 模式處理，請稍後查看結果）"
    )
    return "needs_agent"

def main():
    msgs = read_new()
    if not msgs:
        print("No new messages")
        return

    last_id = None
    needs_agent = False
    for msg in msgs:
        result = handle(msg)
        if result == "needs_agent":
            needs_agent = True
        last_id = msg.get("id")

    if last_id:
        set_pos(last_id)

    if needs_agent:
        print("NEEDS_AGENT:有訊息需要 agent 處理")
    print(f"Processed {len(msgs)} message(s)")

if __name__ == "__main__":
    main()
