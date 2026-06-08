#!/usr/bin/env python3
"""
Weekly Journal Report — Science + Nature Research Articles
- Science: RSS RDF feed, filter by dc:type = "Research Article"
- Nature: RSS RDF feed, filter by URL prefix /articles/s41586-
- Translate titles via Gemini 2.5 Flash
- Output: MD file + Telegram notification
"""

import json, re, sys, os, urllib.request, subprocess
from datetime import datetime, timedelta
from pathlib import Path

# ── Config ──────────────────────────────────────────────────
HOME = Path.home()
ENV_FILE = HOME / ".hermes" / ".env"
MD_DIR = Path("/mnt/f/MD/notes")
GITHUB_REPO = "StandardMeanOceanWater/public"

def load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

load_env()
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY", "")
BOT_TOKEN = os.environ.get("NEWSBOY_BOT_TOKEN", "")
CHAT_ID = os.environ.get("NEWSBOY_CHAT_ID", "686734095")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ── HTTP helpers ────────────────────────────────────────────
def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  fetch error: {e}")
        return ""

def gemini_translate(titles, prompt_prefix="Translate to Chinese"):
    if not GOOGLE_KEY or not titles:
        return titles
    
    all_translations = []
    batch_size = 30  # 每批 30 個，避免 output 截斷
    
    for i in range(0, len(titles), batch_size):
        batch = titles[i:i+batch_size]
        prompt = f"{prompt_prefix}. One per line, format: \"number. Chinese translation\". Only return translations.\n\n"
        prompt += "\n".join(f"{j+1}. {t}" for j, t in enumerate(batch))
        body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 8192, "temperature": 0}
        }).encode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GOOGLE_KEY}"
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=60)
            result = json.loads(resp.read().decode())
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
            for line in lines:
                if ". " in line:
                    all_translations.append(line.split(". ", 1)[1])
                else:
                    all_translations.append(line)
        except Exception as e:
            print(f"  Gemini error: {e}")
            all_translations.extend(batch)  # 失敗時用原文
    
    return all_translations

# ── Science RSS ─────────────────────────────────────────────
def parse_science_rss():
    url = "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science"
    content = fetch(url)
    if not content:
        return [], [], [], "", ""

    items = re.findall(r'<item\s+rdf:about="([^"]+)">(.*?)</item>', content, re.DOTALL)

    # 從 channel 抓期數資訊
    vol_match = re.search(r'<prism:volume>(\d+)</prism:volume>', content)
    issue_match = re.search(r'<prism:number>(\d+)</prism:number>', content)
    date_match = re.search(r'<prism:coverDisplayDate>([^<]+)</prism:coverDisplayDate>', content)

    vol = vol_match.group(1) if vol_match else "?"
    issue = issue_match.group(1) if issue_match else "?"
    date_str = date_match.group(1)[:10] if date_match else datetime.now().strftime("%Y-%m-%d")

    research_articles = []
    in_depth_articles = []
    in_other_journals = None

    for item_url, item in items:
        t = re.search(r'<dc:type>(.*?)</dc:type>', item)
        title = re.search(r'<title>(.*?)</title>', item)
        doi = re.search(r'<prism:doi>(.*?)</prism:doi>', item)
        prism_url = re.search(r'<prism:url>(.*?)</prism:url>', item)

        if not title or not doi:
            continue

        title_str = title.group(1).strip()
        doi_str = doi.group(1).strip().replace("doi:", "").strip()
        link = f"https://doi.org/{doi_str}"

        # In Other Journals：標題就是 "In Other Journals"
        if title_str == "In Other Journals":
            in_other_journals = {"title_en": title_str, "doi": doi_str, "link": link}
            continue

        item_type = t.group(1).strip() if t else ""

        if item_type == "Research Article":
            research_articles.append({"title_en": title_str, "doi": doi_str, "link": link})
        elif item_type == "In Depth":
            # In Depth 連結去掉 ?af=R 後綴
            raw_url = prism_url.group(1).strip() if prism_url else ""
            clean_link = raw_url.split("?")[0] if "?" in raw_url else raw_url
            in_depth_articles.append({"title_en": title_str, "doi": doi_str, "link": clean_link})

    header = f"Volume {vol}, Issue {issue}"
    return research_articles, in_depth_articles, in_other_journals, header, date_str

# ── Nature 當期（HTML）────────────────────────────────────────
def parse_nature_html_current():
    """抓 Nature 官網當期頁面，從 Research 區塊取出研究文章。

    比 Crossref 30 天 500 筆精準且輕量：
    - 只抓一頁 HTML（~300KB），無需過濾 95% 垃圾
    - 精準命中當期，不靠猜測最新期號
    - 自動取得 volume / issue"""
    url = "https://www.nature.com/nature/current-issue"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Referer": "https://www.nature.com/",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  Nature HTML fetch error: {e}")
        return [], ""

    # 從 redirect 後的 URL 取出 volume / issue
    final_url = resp.url
    vol_iss = re.search(r'/volumes/(\d+)/issues/(\d+)', final_url)
    if not vol_iss:
        print("  Could not extract volume/issue from URL")
        return [], ""
    vol = vol_iss.group(1)
    iss = vol_iss.group(2)

    # 只抓 <h2>Research</h2> 到下一個 <h2> 之間的區塊
    research_section = re.search(
        r'<h2[^>]*>Research</h2>(.*?)<h2[^>]*>',
        html, re.DOTALL
    )
    if not research_section:
        print("  Could not find Research section on page")
        return [], ""

    section = research_section.group(1)
    articles = re.findall(
        r'href="/articles/(s41586-[^"/]+)"[^>]*>([^<]+)</a>',
        section
    )

    result = []
    for doi_suffix, title in articles:
        title = title.strip()
        if any(k in title for k in ['Correction', 'Reply', 'Retraction']):
            continue
        doi_full = f"10.1038/{doi_suffix}"
        link = f"https://doi.org/{doi_full}"
        result.append({
            "title_en": title,
            "doi": doi_suffix,
            "link": link,
            "volume": vol,
            "issue": iss,
        })

    header = f"Vol. {vol}, Issue {iss}"
    print(f"  Nature HTML: {len(result)} research articles ({header})")
    return result, header

def parse_nature_crossref_weekly(from_date_8d, to_date_8d):
    """抓本週 8 天，只拿無期號的研究文章（線上先行）"""
    url = f"https://api.crossref.org/works?filter=issn:0028-0836,from-pub-date:{from_date_8d},until-pub-date:{to_date_8d}&rows=100&sort=published-online&order=desc"
    content = fetch(url)
    if not content:
        return [], ""

    try:
        d = json.loads(content)
        items = d.get("message", {}).get("items", [])
    except Exception as e:
        print(f"  Crossref parse error: {e}")
        return [], ""

    articles = []
    for item in items:
        doi = item.get("DOI", "")
        # 只收研究文章（s41586 開頭）且無期號
        if not doi.startswith("10.1038/s41586-"):
            continue
        if item.get("volume") and item.get("issue"):
            continue  # 有期號的不收（當期已收過）

        title = item.get("title", ["?"])[0]
        if any(k in title for k in ['Correction', 'Reply', 'Retraction']):
            continue
        doi_str = doi.replace("10.1038/", "")
        link = f"https://doi.org/{doi}"

        articles.append({
            "title_en": title,
            "doi": doi_str,
            "link": link,
            "volume": "",
            "issue": "",
        })

    return articles, ""

# ── Format MD ───────────────────────────────────────────────
def clean_title(title):
    """Remove CDATA tags and clean up title."""
    # Remove <![CDATA[...]]>
    title = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', title)
    # Remove HTML tags
    title = re.sub(r'<[^>]+>', '', title)
    # Clean whitespace
    title = title.strip()
    return title

def format_md(date_str, science_research, science_in_depth, science_in_other, science_header, nature_articles, nature_header, from_date, to_date):
    lines = []

    # 日期放大 + 標題
    lines.append(f"# 本週科學期刊 — {date_str}")
    lines.append("")

    # Science
    if science_research:
        lines.append(f"### SCIENCE | {science_header}")
        lines.append("")
        for i, a in enumerate(science_research, 1):
            title_zh = clean_title(a.get("title_zh", a["title_en"]))
            if len(title_zh) < 5:
                title_zh = a["title_en"]
            lines.append(f"{i}. [{title_zh}]({a['link']})")
        lines.append("")

    # Science In Depth（新聞特報）
    if science_in_depth:
        in_depth_parts = []
        for a in science_in_depth:
            title_zh = clean_title(a.get("title_zh", a["title_en"]))
            if len(title_zh) < 5:
                title_zh = a["title_en"]
            in_depth_parts.append(f"[{title_zh}]({a['link']})")
        lines.append(f"新聞特報：{' / '.join(in_depth_parts)}")
        lines.append("")

    # Science In Other Journals（編輯選文）
    if science_in_other:
        title_zh = clean_title(science_in_other.get("title_zh", science_in_other["title_en"]))
        if len(title_zh) < 5:
            title_zh = science_in_other["title_en"]
        lines.append(f"編輯選文：[{title_zh}]({science_in_other['link']})")
        lines.append("")

    # Nature：只拿有期號的（當期）
    if nature_articles:
        # 有期號的
        with_vol = [a for a in nature_articles if a.get("volume") and a.get("issue")]
        # 無期號的（本週線上先行）
        no_vol = [a for a in nature_articles if not (a.get("volume") and a.get("issue"))]

        if with_vol:
            v = with_vol[0].get("volume", "?")
            iss = with_vol[0].get("issue", "?")
            lines.append(f"### NATURE | Vol. {v}, Issue {iss}")
            lines.append("")
            for i, a in enumerate(with_vol, 1):
                title_zh = clean_title(a.get("title_zh", a["title_en"]))
                if len(title_zh) < 5:
                    title_zh = a["title_en"]
                lines.append(f"{i}. [{title_zh}]({a['link']})")
            lines.append("")

        if no_vol:
            lines.append(f"### NATURE | CrossRef this week (PDF Maybe)")
            lines.append("")
            lines.append(f"*{from_date} to {to_date}*")
            lines.append("")
            for i, a in enumerate(no_vol, 1):
                title_zh = clean_title(a.get("title_zh", a["title_en"]))
                if len(title_zh) < 5:
                    title_zh = a["title_en"]
                lines.append(f"{i}. [{title_zh}]({a['link']})")
            lines.append("")

    return "\n".join(lines)

# ── GitHub push ─────────────────────────────────────────────
def push_to_github(filename, content):
    if not GITHUB_TOKEN:
        return None
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/notes/{filename}"
    content_b64 = __import__("base64").b64encode(content.encode()).decode()

    # 檢查檔案是否存在
    try:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        })
        resp = urllib.request.urlopen(req, timeout=10)
        existing = json.loads(resp.read().decode())
        sha = existing.get("sha")
    except Exception:
        sha = None

    data = json.dumps({
        "message": f"Add {filename}",
        "content": content_b64,
        **({"sha": sha} if sha else {})
    }).encode()

    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json"
    }, method="PUT")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read().decode())
        return result.get("content", {}).get("html_url")
    except Exception as e:
        print(f"  GitHub push error: {e}")
        return None

# ── Telegram ────────────────────────────────────────────────
def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        return False
    # 分段發送（Telegram 限制 4096 chars）
    chunks = []
    while len(text) > 4000:
        cut = text[:4000].rfind("\n")
        if cut < 2000:
            cut = 4000
        chunks.append(text[:cut])
        text = text[cut:]
    chunks.append(text)

    for chunk in chunks:
        data = json.dumps({
            "chat_id": CHAT_ID,
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
            print(f"  Telegram error: {e}")
            return False
    return True

# ── Main ────────────────────────────────────────────────────
def main():
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    print(f"=== Weekly Journal Report — {date_str} ===\n")

    # 計算日期區間
    # Nature 當期：直接抓官網 current-issue，不需日期範圍
    # Nature 線上先行：上週四（上個 calendar week）→ 這週五
    weekday = today.weekday()  # Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
    monday_this_week = today - timedelta(days=weekday)      # 這週一
    last_thursday = monday_this_week - timedelta(days=4)     # 上週四
    this_friday = monday_this_week + timedelta(days=4)       # 這週五
    from_date_weekly = last_thursday.strftime("%Y-%m-%d")
    to_date_weekly = this_friday.strftime("%Y-%m-%d")

    print(f"Online-first range: {from_date_weekly} to {to_date_weekly}（上週四→這週五）")
    print()

    # ── Science RSS ──
    print("Fetching Science RSS...")
    science_research, science_in_depth, science_in_other, science_header, science_date = parse_science_rss()
    print(f"  Research: {len(science_research)}, In Depth: {len(science_in_depth)}, In Other: {'Yes' if science_in_other else 'No'}\n")

    # ── Nature 當期（官網 HTML）──
    print("Fetching Nature current issue (HTML)...")
    nature_current, nature_header = parse_nature_html_current()
    print(f"  Current issue: {len(nature_current)} articles\n")

    # ── Nature 線上先行（Crossref，上週四→這週五，無期號）──
    print("Fetching Nature online-first (Crossref, no volume)...")
    nature_weekly, _ = parse_nature_crossref_weekly(from_date_weekly, to_date_weekly)
    print(f"  Online first: {len(nature_weekly)} articles\n")

    # ── 翻譯：先當期，再本週 ──
    print()

    # 當期翻譯（Science + Nature current）
    current_titles = [a["title_en"] for a in science_research]
    current_titles += [a["title_en"] for a in science_in_depth]
    if science_in_other:
        current_titles.append(science_in_other["title_en"])
    current_titles += [a["title_en"] for a in nature_current]

    print(f"Translating current batch ({len(current_titles)} titles)...")
    current_translations = gemini_translate(current_titles, "Translate to Traditional Chinese (繁體中文). One per line, format: 'number. Traditional Chinese translation'. Only return translations.")

    # 本週翻譯（Nature weekly）
    weekly_titles = [a["title_en"] for a in nature_weekly]
    print(f"Translating weekly batch ({len(weekly_titles)} titles)...")
    weekly_translations = gemini_translate(weekly_titles, "Translate to Traditional Chinese (繁體中文). One per line, format: 'number. Traditional Chinese translation'. Only return translations.")

    # ── 配對翻譯 ──
    idx = 0
    for a in science_research:
        if idx < len(current_translations):
            a["title_zh"] = current_translations[idx]
        idx += 1
    for a in science_in_depth:
        if idx < len(current_translations):
            a["title_zh"] = current_translations[idx]
        idx += 1
    if science_in_other:
        if idx < len(current_translations):
            science_in_other["title_zh"] = current_translations[idx]
        idx += 1
    for a in nature_current:
        if idx < len(current_translations):
            a["title_zh"] = current_translations[idx]
        idx += 1

    for i, a in enumerate(nature_weekly):
        if i < len(weekly_translations):
            a["title_zh"] = weekly_translations[i]

    # ── 產生 MD ──
    # nature_articles = current + weekly 合併，format_m  自行分離有期號/無期號
    all_nature = nature_current + nature_weekly
    md_content = format_md(date_str, science_research, science_in_depth, science_in_other, science_header, all_nature, nature_header, from_date_weekly, to_date_weekly)

    # 存檔
    filename = f"weekly_journal_{date_str}.md"
    filepath = MD_DIR / filename
    filepath.write_text(md_content, encoding="utf-8")
    print(f"\nSaved: {filepath}")
    print(f"Size: {len(md_content)} chars")

    # GitHub push
    if GITHUB_TOKEN:
        print("\nPushing to GitHub...")
        url = push_to_github(filename, md_content)
        if url:
            print(f"  GitHub URL: {url}")
        else:
            print("  GitHub push failed")

    # ── Write status file for watchdog ──
    status = {
        "date": date_str,
        "html_url": f"https://standardmeanoceanwater.github.io/public/notes/weekly_journal_{date_str}.html",
        "raw_url": f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/notes/{filename}",
        "filename": filename,
        "science_header": science_header,
        "science_count": len(science_research),
        "nature_count": len(nature_current),
        "nature_vol": nature_current[0].get("volume", "?") if nature_current else "?",
        "nature_iss": nature_current[0].get("issue", "?") if nature_current else "?",
        "nature_online_count": len(nature_weekly),
        "sent": False
    }
    status_path = Path("/mnt/f/MD/notes/.journal_pending.json")
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Status file written — watchdog will deliver via Telegram when Pages is ready")

    print("\n=== Done ===")
    print(md_content)

if __name__ == "__main__":
    main()
