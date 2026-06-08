#!/usr/bin/env python3
"""
每週期刊報 - Science + Nature 當期目錄推送
每週五 13:30 發送
"""

import urllib.request, urllib.parse, re, os, json, datetime

# ===== 設定 =====
def load_env():
    env_path = os.path.join(os.path.expanduser("~"), ".hermes", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

load_env()
BOT_TOKEN = os.environ.get("NEWSBOY_BOT_TOKEN", "")
CHAT_ID = os.environ.get("NEWSBOY_CHAT_ID", "686734095")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
TMP_DIR = "/tmp/weekly_journal"

os.makedirs(TMP_DIR, exist_ok=True)

def tg_send(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read().decode())

def translate_titles(titles):
    """用 DeepL 翻譯標題成繁體中文"""
    if not titles:
        return titles

    DEEPL_KEY = os.environ.get("DEEPL_API_KEY", "")
    if not DEEPL_KEY:
        return titles

    url = "https://api-free.deepl.com/v2/translate"
    translated = []
    try:
        for title in titles:
            data = urllib.parse.urlencode({
                "text": title,
                "target_lang": "ZH"
            }).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"DeepL-Auth-Key {DEEPL_KEY}"
            })
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read().decode())
            t = result.get("translations", [{}])
            translated.append(t[0]["text"] if t else title)
        return translated
    except Exception as e:
        print(f"翻譯失敗: {e}")
        return titles

def fetch_html(url):
    cache_file = os.path.join(TMP_DIR, re.sub(r'[^\w]', '_', url) + ".html")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=30)
    html = resp.read().decode("utf-8")
    with open(cache_file, "w", encoding="utf-8") as f:
        f.write(html)
    return html

def parse_nature(html):
    vol_match = re.search(r'Volume\s+(\d+)\s+Issue\s+(\d+).*?,\s*(\d+\s+\w+\s+\d{4})', html)
    if vol_match:
        vol, issue, date = vol_match.groups()
        issue_title = f"NATURE Volume {vol} Issue {issue}, {date}"
    else:
        issue_title = "NATURE"

    articles = []
    for m in re.finditer(r'href="(/articles/s41586-[^"]+)".*?<h3[^>]*>(.*?)</h3>', html, re.DOTALL):
        link, title = m.groups()
        title = re.sub(r'<[^>]+>', '', title).strip()
        # 過濾更正文
        if title and len(title) > 10 and not re.match(r'^(Author|Publisher)\s+Correction', title):
            articles.append({"title": title, "url": f"https://www.nature.com{link}"})

    return issue_title, articles

def parse_science_html(html):
    vol_match = re.search(r'Volume\s+(\d+)\s*\|\s*Issue\s+(\d+).*?(\d+\s+\w+\s+\d{4})', html)
    if vol_match:
        vol, issue, date = vol_match.groups()
        issue_title = f"Science Volume {vol}|Issue {issue}|{date}"
    else:
        issue_title = "Science"

    all_articles = []
    for m in re.finditer(r'href="(/doi/10\.1126/science\.[^"]+)".*?<h3[^>]*>(.*?)</h3>', html, re.DOTALL):
        link, title = m.groups()
        title = re.sub(r'<[^>]+>', '', title).strip()
        if title and len(title) > 10:
            all_articles.append({"title": title, "url": f"https://www.science.org{link}"})

    highlights = [a for a in all_articles if len(a["title"]) < 80][:10]
    research = [a for a in all_articles if len(a["title"]) >= 80][:20]
    return issue_title, highlights, research

def main():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"📚 <b>每週期刊報</b> ({now})\n"]

    # ===== Science =====
    science_html = os.path.join(TMP_DIR, "science_current.html")
    if os.path.exists(science_html):
        try:
            with open(science_html, "r", encoding="utf-8") as f:
                html = f.read()
            issue_title, highlights, research = parse_science_html(html)
            lines.append(f"## {issue_title}")
            lines.append("🔗 https://www.science.org/toc/science/current\n")

            if highlights:
                titles = [a["title"] for a in highlights]
                translated = translate_titles(titles)
                lines.append("### 選究選粹 (Research Highlights)")
                for i, (a, t) in enumerate(zip(highlights, translated), 1):
                    lines.append(f'{i}. <a href="{a["url"]}">{t}</a>')
                lines.append("")

            if research:
                titles = [a["title"] for a in research]
                translated = translate_titles(titles)
                lines.append("### 研究論文 (Research Articles)")
                for i, (a, t) in enumerate(zip(research, translated), 1):
                    lines.append(f'{i}. <a href="{a["url"]}">{t}</a>')
                lines.append("")

            os.remove(science_html)
        except Exception as e:
            lines.append(f"❌ Science 解析失敗: {e}\n")
    else:
        lines.append("## Science")
        lines.append('🔗 <a href="https://www.science.org/toc/science/current">點此查看當期目錄</a>')
        lines.append("")

    # ===== Nature =====
    try:
        html = fetch_html("https://www.nature.com/nature/current-issue")
        issue_title, articles = parse_nature(html)
        lines.append(f"## {issue_title}")
        lines.append("🔗 https://www.nature.com/nature/current-issue\n")

        if articles:
            titles = [a["title"] for a in articles]
            translated = translate_titles(titles)
            lines.append("### 研究論文 (Research Articles)")
            for i, (a, t) in enumerate(zip(articles, translated), 1):
                lines.append(f'{i}. <a href="{a["url"]}">{t}</a>')
            lines.append("")
    except Exception as e:
        lines.append(f"❌ Nature 取得失敗: {e}\n")

    msg = "\n".join(lines)
    print(msg)
    print("\n--- 發送 Telegram ---")
    result = tg_send(msg)
    print("發送成功" if result.get("ok") else f"發送失敗: {result}")

if __name__ == "__main__":
    main()
