#!/usr/bin/env python3
"""
每日半日限免報 - App/Game free deals aggregator
================================================
Cron job: ef03aaf8a53 (12:10 + 17:30 daily)
Bot: @Newsboy_Hermes_bot

ACTIVE SOURCES (verified working from WSL):
  1. newmobilelife.com  — Mac/PC/iOS/Android 限免, URL 含日期 /YYYY/MM/DD/
  2. yipee.cc (Dr.愛瘋) — iOS/Android 限免週報, 文章 block 含 YYYY-MM-DD meta
  3. 4gamers.com.tw    — 遊戲限免, URL 含日期 YYYYMMDD

INACTIVE / BLOCKED SOURCES (WSL network limitations):
  - AppAdvice / RSS feeds     → DNS resolve failure (WSL can't reach)
  - Reddit r/AppHookup        → HTTP 403 (Reddit blocks non-US IPs)
  - TouchArcade               → HTTP 403
  - APKPure / 酷安 / 應用匯   → HTTP 403-404 (Chinese sites blocked from TW IP)
  - iMore RSS                 → Works but content is tech news, not free deals

NOTE: WSL network routes through 10.255.255.254 (Windows host DNS).
Most international sites fail DNS resolution or return 403.
To add more sources, consider:
  a) Running the script on a Windows host (not WSL)
  b) Using a proxy/VPN from WSL
  c) Adding sources manually when you find working URLs from your phone

RULES:
  - Mobile/iOS/Android: always included
  - PC/Mac/Steam: only if original price > 500 TWD
  - Article must be published today
  - Article body checked for expiry text (e.g. "放送到 6/4 截止")
  - Dedup: seen_links.json tracks reported URLs across runs
  - If no new deals found: sends "目前無新限時免費新增應用程式"
"""

import urllib.request, re, os, json, datetime, time

# ===== Settings =====
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
TMP_DIR = "/tmp/daily_free_report"
os.makedirs(TMP_DIR, exist_ok=True)
SEEN_FILE = os.path.join(TMP_DIR, "seen_links.json")
TODAY = datetime.date.today()

MOBILE_KEYWORDS = ["iphone", "ipad", "ios", "android", "手機", "app", "mobile"]
PC_KEYWORDS = ["pc", "mac", "steam", "windows"]

# Expiry patterns: look for deadline text in article body
EXPIRY_PATTERNS = [
    r'(?:期限|截止|到期|結束|至|到)\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})',
    r'(?:期限|截止|到期|結束|至|到)\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
    r'(?:期限|截止|到期|結束|至|到)\s*(\d{1,2})月(\d{1,2})[日號]?',
    r'(?:only available|deadline|expires?)\s*(?:until|before|on)?\s*(\w+)\s+(\d{1,2})',
]

def is_mobile(title):
    t = title.lower()
    return any(k in t for k in MOBILE_KEYWORDS)

def is_pc_and_price_ok(title):
    t = title.lower()
    is_pc_only = any(k in t for k in PC_KEYWORDS) and not is_mobile(title)
    if not is_pc_only:
        return True  # Not PC-only, include
    # PC-only: check price
    price = re.search(r'(?:NT\$|\$)\s*(\d[\d,]*)', title)
    if price:
        p = int(price.group(1).replace(",", ""))
        return p > 500
    return False  # Price unknown, skip PC-only

def check_expiry(url):
    """
    Fetch article body and check if the deal is still active.
    Returns True if still valid, False if expired, None if can't determine.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode("utf-8", errors="replace")

        # Remove scripts/styles
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)

        # Extract body text
        body_match = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
        if not body_match:
            body_match = re.search(r'class="entry-content[^"]*?"[^>]*>(.*?)</div>\s*</div>\s*</div>', html, re.DOTALL)
        body = body_match.group(1) if body_match else html
        text = re.sub(r'<[^>]+>', ' ', body)
        text = re.sub(r'\s+', ' ', text)

        for pattern in EXPIRY_PATTERNS:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                groups = m.groups()
                try:
                    if len(groups) == 3:
                        y, mo, d = int(groups[0]), int(groups[1]), int(groups[2])
                        if y < 100:  # day-month-year format
                            d, mo, y = y, mo, d
                        deadline = datetime.date(y, mo, d)
                        # Deal valid if deadline is today or future
                        if deadline <= today.date():
                            # Check for hour info near the match
                            context = text[max(0, m.start()-30):m.end()+50]
                            hour_match = re.search(r'(\d{1,2}):(\d{2})', context)
                            if hour_match:
                                h, mi = int(hour_match.group(1)), int(hour_match.group(2))
                                deadline_dt = datetime.datetime(y, mo, d, h, mi)
                                return deadline_dt > now
                            # No hour info: if deadline is today, check if after current report slot
                            if deadline == today.date():
                                return True  # Include it, let user decide
                            return False
                        return True  # Future deadline
                except (ValueError, OSError):
                    continue

        # Special handling for "放送到..." or "限時到..." text within the article
        # Yipee style: "放送到 6/4 上午 12:00 截止"
        match = re.search(r'(?:放送到|限時到|到)\s*(\d{1,2})[/-](\d{1,2})\s*(上午|下午|凌晨|晚上)?\s*(\d{1,2}):?(\d{2})?', text)
        if match:
            mo, d = int(match.group(1)), int(match.group(2))
            tod = match.group(3) or ""
            h = int(match.group(4)) if match.group(4) else 0
            mi = int(match.group(5)) if match.group(5) else 0
            year = now.year
            if mo < now.month:  # next year? unlikely for free deals but handle
                year += 1
            try:
                deadline_dt = datetime.datetime(year, mo, d, h, mi)
                if "下午" in tod or "晚上" in tod:
                    if deadline_dt.hour < 12:
                        deadline_dt = deadline_dt.replace(hour=deadline_dt.hour + 12)
                return deadline_dt > now
            except (ValueError, OSError):
                pass

        # NewMobileLife style: "限時免費到 5/30" or similar
        match = re.search(r'限時(?:免費|到)\s*(\d{1,2})[/-](\d{1,2})', text)
        if match:
            mo, d = int(match.group(1)), int(match.group(2))
            deadline = datetime.date(now.year, mo, d)
            return deadline >= today.date()

        # No expiry found in body — assume still valid (title already said 限時免費)
        return True
    except Exception as e:
        print(f"  Expiry check failed for {url[:60]}: {e}")
        return True  # Include on error — better to over-report than miss

def tg_send(text):
    if len(text) > 4000:
        chunks = []
        while len(text) > 4000:
            cut = text[:4000].rfind('\n')
            if cut < 2000: cut = 4000
            chunks.append(text[:cut])
            text = text[cut:]
        chunks.append(text)
        for chunk in chunks:
            data = json.dumps({"chat_id": CHAT_ID, "text": chunk, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}).encode("utf-8")
            req = urllib.request.Request(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                data=data, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=15)
        return {"ok": True}
    data = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=data, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read().decode())

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=15)
    return resp.read().decode("utf-8", errors="replace")

def parse_newmobilelife():
    url = "https://www.newmobilelife.com/category/apps-%E6%83%85%E5%A0%B1/%E9%99%90%E6%99%82%E5%85%8D%E8%B2%BB%E6%83%85%E5%A0%B1/"
    try:
        html = fetch_html(url)
        articles = re.findall(
            r'<article[^>]*>.*?<h2[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?</h2>.*?</article>',
            html, re.DOTALL
        )
        results = []
        for link, title in articles:
            title = re.sub(r'<[^>]+>', '', title).strip()
            if not title or not link:
                continue
            if "免費" not in title and "free" not in title.lower():
                continue
            # Check article date from URL
            date_in_url = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', link)
            if date_in_url:
                ad = datetime.date(int(date_in_url.group(1)), int(date_in_url.group(2)), int(date_in_url.group(3)))
                if ad < TODAY:
                    continue
            if not is_pc_and_price_ok(title):
                continue
            results.append({"title": title, "url": link, "source": "NewMobileLife"})
        return results
    except Exception as e:
        print(f"NewMobileLife error: {e}")
        return []

def parse_yipee():
    url = "https://app.yipee.cc/category/limited-time-free/"
    try:
        html = fetch_html(url)
        article_blocks = re.findall(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
        results = []
        for block in article_blocks:
            # Date check from block meta
            date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', block)
            if date_match:
                ad = datetime.date(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
                if ad < TODAY:
                    continue
            # Find actual article link (skip nav links)
            links = re.findall(r'<a[^>]*href="(https://app\.yipee\.cc/\d+/[^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            for link, title in links:
                title = re.sub(r'<[^>]+>', '', title).strip()
                if not title or "頁" in title or "@" in title:
                    continue
                if title in ("新消息", "近期關鍵焦點", "限時免費", "Dr.愛瘋"):
                    continue
                if "限時免費" not in title and "免費" not in title:
                    continue
                if not is_pc_and_price_ok(title):
                    continue
                results.append({"title": title, "url": link, "source": "Dr.愛瘋(Yipee)"})
                break  # Only one real article per block
        return results
    except Exception as e:
        print(f"Yipee error: {e}")
        return []

def parse_4gamers():
    url = "https://www.4gamers.com.tw/news/tag/%E9%99%90%E6%99%82%E5%85%8D%E8%B2%BB"
    try:
        html = fetch_html(url)
        articles = re.findall(
            r'<a[^>]*href="(https://www\.4gamers\.com\.tw/news[^"]*)"[^>]*>.*?<h3[^>]*>(.*?)</h3>',
            html, re.DOTALL
        )
        results = []
        for link, title in articles:
            title = re.sub(r'<[^>]+>', '', title).strip()
            if not title or not link or "免費" not in title:
                continue
            # 4gamers URL has date: /news/20260529120001
            date_match = re.search(r'/news/(\d{4})(\d{2})(\d{2})', link)
            if date_match:
                ad = datetime.date(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
                if ad < TODAY:
                    continue
            if not is_pc_and_price_ok(title):
                continue
            results.append({"title": title, "url": link, "source": "4Gamers"})
        return results
    except Exception as e:
        print(f"4Gamers error: {e}")
        return []

def main():
    now = datetime.datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M")
    slot = "午間" if now.hour < 15 else "傍晚"
    seen = load_seen()

    print(f"[{now_str}] Fetching articles from 3 sources...")
    articles = []
    articles.extend(parse_newmobilelife())
    print(f"  NewMobileLife: {len(articles)} candidates")
    articles.extend(parse_yipee())
    print(f"  Yipee: {len(articles)} total candidates")
    articles.extend(parse_4gamers())
    print(f"  4Gamers: {len(articles)} total candidates")

    # Check expiry for each article (fetch body)
    valid_articles = []
    for a in articles:
        if a["url"] in seen:
            continue
        print(f"  Checking expiry: {a['title'][:50]}...")
        try:
            is_valid = check_expiry(a["url"])
        except Exception as e:
            print(f"    Error: {e}")
            is_valid = True  # Include on error
        if is_valid:
            a["url"]  # just access to ensure key exists
            valid_articles.append(a)
            seen.add(a["url"])
        else:
            print(f"    EXPIRED - skipped")
            seen.add(a["url"])  # Still mark as seen
        time.sleep(0.3)  # Rate limit

    save_seen(seen)

    if not valid_articles:
        msg = f"🎮<b>限免報-{slot}</b>({now_str})\n\n📱 目前無新限時免費新增應用程式"
        print(msg)
        tg_send(msg)
        return

    # Build message
    lines = [f"🎮<b>限免報-{slot}</b>({now_str})\n"]
    lines.append(f"📱{len(valid_articles)}筆\n")

    by_source = {}
    for a in valid_articles:
        by_source.setdefault(a["source"], []).append(a)

    icons = {"NewMobileLife": "📰", "Dr.愛瘋(Yipee)": "🍎", "4Gamers": "🎮"}
    for src in ["NewMobileLife", "Dr.愛瘋(Yipee)", "4Gamers"]:
        if src in by_source:
            lines.append(f"{icons.get(src,'📌')}<b>{src}</b>")
            for a in by_source[src]:
                lines.append(f'  •<a href=\"{a["url"]}\">{a["title"]}</a>')
            lines.append("")

    msg = "\n".join(lines)
    print(f"\n--- Message ---\n{msg}\n--- Sending ---")
    result = tg_send(msg)
    print("Sent!" if result.get("ok") else f"Failed: {result}")

if __name__ == "__main__":
    main()
