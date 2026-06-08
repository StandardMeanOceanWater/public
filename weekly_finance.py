#!/usr/bin/env python3
"""
每週財經快訊 — 週一刊 + 週日報

週一刊（06:21）：國際行情 + 上週收盤價週變化總結
週日報（06:21）：國際行情 + 一週變化折線圖

格式規則（2026-06-08 定稿）：
  ▲ = 漲（紅色），▼ = 跌（綠色），— = 無變化（灰色）
  數值不加正負號、不加逗號
  國際行情中的貴金屬和比特幣顯示 TWD 換算值
  匯率小數 2 位，其餘整數
"""

import urllib.request
import json
import csv
import datetime
import os
import sys
import io

# ===== 載入設定 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env():
    env_path = os.path.join(os.path.expanduser("~"), ".hermes", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

_load_env()
GOLDAPI_API_KEY = os.environ.get("GOLDAPI_API_KEY", "")
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")

# Telegram 設定
BOT_TOKEN = os.environ.get("NEWSBOY_BOT_TOKEN", "")
CHAT_ID = os.environ.get("NEWSBOY_CHAT_ID", "686734095")
HISTORY_PATH = os.path.join(BASE_DIR, "finance_history.csv")

# ===== 工具函式 =====
def fmt_change(pct):
    """格式化漲跌：(符號, 百分比文字)"""
    if pct is None:
        return "—", "—"
    if pct > 0:
        return "▲", f"{abs(pct):.1f}%"
    elif pct < 0:
        return "▼", f"{abs(pct):.1f}%"
    return "—", "—"


def fmt_num(val, decimals=0):
    """格式化數值，不加逗號"""
    if decimals == 0:
        return f"{int(round(val))}"
    return f"{val:.{decimals}f}"


def calc_pct_change(current, previous):
    if not previous or previous == 0:
        return None
    return (current - previous) / previous * 100


def tg_send(text, photo_path=None):
    """發送 Telegram 訊息（先文字，等 5 秒後再送圖）"""
    if not BOT_TOKEN:
        print("⚠️ BOT_TOKEN 未設定，跳過發送")
        return

    # 先送文字
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
            "link_preview_options": {"is_disabled": True},
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=15)
        except Exception as e:
            print(f"⚠️ Telegram 發送失敗: {e}")

    # 等 5 秒再送圖
    if photo_path and os.path.exists(photo_path):
        import time
        time.sleep(5)
        boundary = "----WebKitFormBoundary"
        with open(photo_path, "rb") as f:
            img_data = f.read()

        body = (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"chat_id\"\r\n\r\n"
            f"{CHAT_ID}\r\n"
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"photo\"; filename=\"chart.png\"\r\n"
            f"Content-Type: image/png\r\n\r\n"
        ).encode() + img_data + (
            f"\r\n--{boundary}--\r\n"
        ).encode()

        req = urllib.request.Request(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            urllib.request.urlopen(req, timeout=30)
            print("✅ 圖片發送成功")
        except Exception as e:
            print(f"⚠️ 圖片發送失敗: {e}")


# ===== 歷史數據 =====
def load_history():
    if not os.path.exists(HISTORY_PATH):
        return []
    with open(HISTORY_PATH, "r") as f:
        return list(csv.DictReader(f))


def get_history_for_date(date_str):
    """取得指定日期的歷史數據"""
    history = load_history()
    for row in history:
        if row.get("date") == date_str:
            return row
    return None


def get_last_n_trading_days(n):
    """取得最近 n 個交易日的歷史數據"""
    history = load_history()
    return history[-n:] if len(history) >= n else history


# ===== 抓取當日數據（與 daily_finance.py 相同）=====
def api_get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {})
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read().decode())


def api_get_text(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {})
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.read().decode()


def get_twb_fx():
    """台灣銀行即期匯率（用 raw csv.reader 正確解析兩組買賣價）"""
    url = "https://rate.bot.com.tw/xrt/flcsv/0/day"
    text = api_get_text(url)
    reader = csv.reader(io.StringIO(text))
    next(reader)  # skip header

    result = {}
    for row in reader:
        if not row:
            continue
        cur = row[0]
        if cur in ("USD", "CNY", "JPY"):
            spot_buy = float(row[3]) if len(row) > 3 else 0
            spot_sell = 0
            for i in range(10, len(row)):
                if row[i] == "本行賣出":
                    spot_sell = float(row[i + 2]) if i + 2 < len(row) else 0
                    break
            result[cur] = {"spot_buy": spot_buy, "spot_sell": spot_sell}
    return result


def get_goldapi(metal):
    url = f"https://www.goldapi.io/api/{metal}/USD"
    headers = {"x-access-token": GOLDAPI_API_KEY, "Content-Type": "application/json"}
    data = api_get(url, headers=headers)
    return {"price": data.get("price", 0), "chp": data.get("chp", 0)}


def get_twse_taiex():
    url = "https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK"
    data = api_get(url)
    if not data:
        return None
    latest = data[-1]
    return {"taifex": float(latest.get("TAIEX", 0)), "change": float(latest.get("Change", 0))}


def get_twse_stock(code):
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    data = api_get(url)
    for r in data:
        if r.get("Code") == code:
            return {"close": float(r.get("ClosingPrice", 0)), "change": float(r.get("Change", 0))}
    return None


def get_btc():
    url = "https://blockchain.com/ticker"
    data = api_get(url)
    return {
        "usd": float(data.get("USD", {}).get("last", 0)),
        "twd": float(data.get("TWD", {}).get("last", 0)),
    }


def get_yahoo_metal(yahoo_symbol):
    """Yahoo Finance 金屬價格（備案）"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
    headers = {"User-Agent": "Mozilla/5.0"}
    data = api_get(url, headers=headers)
    result = data.get("chart", {}).get("result", [{}])[0]
    meta = result.get("meta", {})
    price = meta.get("regularMarketPrice", 0)
    prev_close = meta.get("chartPreviousClose", 0)
    chp = ((price - prev_close) / prev_close * 100) if prev_close else 0
    return {"price": price, "prev_close": prev_close, "chp": chp}


def get_yahoo_metal_historical(yahoo_symbol, target_date):
    """Yahoo Finance 歷史價格（某日收盤價）"""
    # 取近一週的資料
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range=1mo&interval=1d"
    headers = {"User-Agent": "Mozilla/5.0"}
    data = api_get(url, headers=headers)
    result = data.get("chart", {}).get("result", [{}])[0]
    ts = result.get("timestamp", [])
    quotes = result.get("indicators", {}).get("quote", [{}])[0]
    closes = quotes.get("close", [])
    import datetime
    for t, c in zip(ts, closes):
        d = datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d")
        if d == target_date and c:
            return {"price": c, "date": d}
    return None


METAL_SOURCES = [
    ("XAU", "GC=F", "gold_usd"),
    ("XAG", "SI=F", "silver_usd"),
    ("XPT", "PL=F", "platinum_usd"),
]


def get_metal_price(goldapi_symbol, yahoo_symbol):
    """GoldAPI → Yahoo 備案"""
    try:
        return get_goldapi(goldapi_symbol)
    except:
        pass
    try:
        return get_yahoo_metal(yahoo_symbol)
    except:
        return None


def get_goldapi_historical(metal, date_yyyymmdd):
    """GoldAPI 歷史價格"""
    url = f"https://www.goldapi.io/api/{metal}/USD/{date_yyyymmdd}"
    headers = {"x-access-token": GOLDAPI_API_KEY, "Content-Type": "application/json"}
    data = api_get(url, headers=headers)
    return {"price": data.get("price", 0)}


def find_closest_date(records, target_date):
    """從 FinMind records 找最接近目標日期的 price"""
    target = target_date.strftime("%Y-%m-%d") if hasattr(target_date, 'strftime') else target_date
    for r in reversed(records):
        d = r.get("date", "")
        if d <= target:
            return {"price": float(r.get("price", 0) or 0), "date": d}
    if records:
        r = records[-1]
        return {"price": float(r.get("price", 0) or 0), "date": r.get("date", "")}
    return None


# ===== FinMind API (台指期 + 原油) =====
def get_finmind(dataset, data_id=None, start_date=None, end_date=None):
    """FinMind API 通用呼叫"""
    params = {"dataset": dataset}
    if data_id:
        params["data_id"] = data_id
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    p = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"https://api.finmindtrade.com/api/v4/data?{p}"
    headers = {"Authorization": f"Bearer {FINMIND_TOKEN}"}
    data = api_get(url, headers=headers)
    return data.get("data", [])


def get_finmind_oil(oil_type):
    """FinMind 原油(WTI 或 Brent)"""
    start = (datetime.date.today() - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
    records = get_finmind("CrudeOilPrices", data_id=oil_type, start_date=start)
    if records:
        r = records[-1]
        return {"price": float(r.get("price", 0)), "date": r.get("date", "")}
    return None


def get_finmind_tx():
    """FinMind 台指期 TX 近月結算價"""
    today = datetime.date.today().strftime("%Y-%m-%d")
    start = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    records = get_finmind("TaiwanFuturesDaily", data_id="TX",
                          start_date=start, end_date=today)
    near = [r for r in records
            if "/" not in str(r.get("contract_date", ""))
            and r.get("settlement_price", 0) > 0]
    if not near:
        return None
    latest = max(near, key=lambda x: x["date"])
    return {
        "date": latest["date"],
        "settlement": float(latest["settlement_price"]),
        "close": float(latest.get("close", 0)),
    }


# ===== 週一刊 =====
def generate_monday_report():
    """週一特刊：國際行情 + 上週收盤價週變化"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    today = datetime.date.today()

    lines = [f"📊 <b>財經快訊週報 — 週一刊</b> ({now})\n"]

    # --- 抓取今日數據 ---
    fx = get_twb_fx()
    usd_rate = fx.get("USD", {}).get("spot_sell", 0)

    # 貴金屬（GoldAPI → Yahoo 備案）
    metals = {}
    for gs, ys, _ in METAL_SOURCES:
        metals[gs] = get_metal_price(gs, ys)

    # 台股
    try:
        taiex = get_twse_taiex()
    except:
        taiex = None
    try:
        tsmc = get_twse_stock("2330")
    except:
        tsmc = None
    btc = get_btc()

    # --- 上週收盤資料（CSV 優先 → API 補位）---
    last_friday = today - datetime.timedelta(days=(today.weekday() - 4) % 7)
    if last_friday >= today:
        last_friday -= datetime.timedelta(days=7)
    last_monday = last_friday - datetime.timedelta(days=4)
    prev_friday = last_friday - datetime.timedelta(days=7)
    date_range = f"{last_monday.strftime('%m%d')}->{last_friday.strftime('%m%d')}"

    lf_str = last_friday.strftime("%Y-%m-%d")
    pf_str = prev_friday.strftime("%Y-%m-%d")
    lf_yymmdd = last_friday.strftime("%Y%m%d")
    pf_yymmdd = prev_friday.strftime("%Y%m%d")

    # CSV 資料（如果有）
    fri_data = get_history_for_date(lf_str)
    prev_fri_data = get_history_for_date(pf_str)

    # --- API 歷史補位（CSV 沒有的話直接從 API 撈）---
    hist = {}  # 存 API 歷史資料

    # 貴金屬歷史（GoldAPI → Yahoo 備案）
    for (gs, ys, key) in METAL_SOURCES:
        pk = f"prev_{key}"
        # GoldAPI 歷史
        goldapi_ok = False
        try:
            d = get_goldapi_historical(gs, lf_yymmdd)
            if d["price"]:
                hist[key] = d["price"]
                d2 = get_goldapi_historical(gs, pf_yymmdd)
                if d2["price"]:
                    hist[pk] = d2["price"]
                    goldapi_ok = True
        except:
            pass
        # GoldAPI 失敗 → Yahoo 歷史
        if not goldapi_ok:
            try:
                d = get_yahoo_metal_historical(ys, lf_str)
                if d and d["price"]:
                    hist[key] = d["price"]
                d2 = get_yahoo_metal_historical(ys, pf_str)
                if d2 and d2["price"]:
                    hist[pk] = d2["price"]
            except:
                pass

    # 原油歷史（FinMind 已有 date range）
    for oil_type, key in [("WTI", "wti_usd"), ("Brent", "brent_usd")]:
        pk = f"prev_{key}"
        try:
            start = pf_str
            end = lf_str
            recs = get_finmind("CrudeOilPrices", data_id=oil_type, start_date=start, end_date=end)
            if recs:
                lf_rec = find_closest_date(recs, lf_str)
                if lf_rec and lf_rec["price"] > 0:
                    hist[key] = lf_rec["price"]
                pf_rec = find_closest_date(recs, pf_str)
                if pf_rec and pf_rec["price"] > 0:
                    hist[pk] = pf_rec["price"]
        except:
            pass

    # 台指期歷史（FinMind）
    try:
        tx_recs = get_finmind("TaiwanFuturesDaily", data_id="TX", start_date=pf_str, end_date=lf_str)
        if tx_recs:
            near = [r for r in tx_recs
                    if "/" not in str(r.get("contract_date", ""))
                    and r.get("settlement_price", 0) > 0]
            if near:
                lf_tx = find_closest_date(near, lf_str)
                if lf_tx:
                    hist["tx_settlement"] = lf_tx["price"]
                pf_tx = find_closest_date(near, pf_str)
                if pf_tx:
                    hist["prev_tx_settlement"] = pf_tx["price"]
    except:
        pass

    # 加權指數歷史（FMTQIK 回傳全部資料，過濾日期）
    try:
        all_taiex = api_get("https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK")
        if all_taiex:
            for r in all_taiex:
                d = r.get("Date", "")
                # 民國的日期格式：1150605
                if len(d) == 7:
                    cy = int(d[:3]) + 1911
                    cm = int(d[3:5])
                    cd = int(d[5:7])
                    greg = f"{cy:04d}-{cm:02d}-{cd:02d}"
                    if greg == lf_str:
                        hist["twii"] = float(r.get("TAIEX", 0))
                    elif greg == pf_str:
                        hist["prev_twii"] = float(r.get("TAIEX", 0))
    except:
        pass

    # Helper: 從歷史拿數值（CSV → API → None）
    def val_from_hist(csv_row, csv_key, hist_key):
        if csv_row:
            v = csv_row.get(csv_key, "")
            if v:
                return float(v)
        if hist_key in hist:
            return hist[hist_key]
        return None

    # --- 國際行情（上週變化）---
    lines.append(f"💱 <b>臺幣匯率變化</b>")

    # 今日匯率 + 週漲跌
    for cur, label, key in [("USD", "USD", "usd_spot_sell"), ("CNY", "CNY", "cny_spot_sell")]:
        if cur in fx:
            val = fx[cur]["spot_sell"]
            fri_rate = val_from_hist(fri_data, key, f"{cur.lower()}_rate")
            pct = calc_pct_change(val, fri_rate) if fri_rate else None
            sym, pct_str = fmt_change(pct)
            lines.append(f"    {label} {fmt_num(val, 2)} {sym}{pct_str}")
    if "JPY" in fx:
        jpy = fx["JPY"]["spot_sell"]
        if jpy > 0:
            display = 1 / jpy
            fri_jpy = val_from_hist(fri_data, "jpy_spot_buy", "jpy_rate")
            if fri_jpy:
                pct = calc_pct_change(display, 1 / fri_jpy)
            else:
                pct = None
            sym, pct_str = fmt_change(pct)
            lines.append(f"    1/JPY {fmt_num(display, 2)} {sym}{pct_str}")
    lines.append("")

    lines.append(f"🌍 <b>國際行情（{date_range}）</b>")
    # 貴金屬
    for metal, label, key in [("XAU", "黃金 XAU", "gold_usd"), ("XAG", "白銀 XAG", "silver_usd"), ("XPT", "鉑金 XPT", "platinum_usd")]:
        if metals.get(metal):
            usd_price = metals[metal]["price"]
            twd_price = usd_price * usd_rate
            fri_v = val_from_hist(fri_data, key, key)
            prev_v = val_from_hist(prev_fri_data, f"prev_{key}", f"prev_{key}")
            if fri_v and prev_v:
                fri_twd = fri_v * float(fri_data.get("usd_spot_sell", usd_rate) if fri_data else usd_rate)
                prev_twd = prev_v * float(prev_fri_data.get("usd_spot_sell", usd_rate) if prev_fri_data else usd_rate)
                pct = calc_pct_change(fri_twd, prev_twd)
            else:
                pct = None
            sym, pct_str = fmt_change(pct)
            lines.append(f"    {label} {fmt_num(twd_price)} TWD {sym}{pct_str}")
        else:
            lines.append(f"    {label}  取得失敗")

    # 原油
    for oil_type, label, key in [("WTI", "原油WTI", "wti_usd"), ("Brent", "原油Brent", "brent_usd")]:
        fri_v = val_from_hist(fri_data, key, key)
        prev_v = val_from_hist(prev_fri_data, f"prev_{key}", f"prev_{key}")
        if fri_v and prev_v and fri_v > 0 and prev_v > 0:
            pct = calc_pct_change(fri_v, prev_v)
            sym, pct_str = fmt_change(pct)
            lines.append(f"    {label} {fmt_num(fri_v, 2)} USD {sym}{pct_str}")
        elif fri_v and fri_v > 0:
            # 有上週五收盤但無前週比較
            lines.append(f"    {label} {fmt_num(fri_v, 2)} USD ——")
        else:
            lines.append(f"    {label}  無上週資料")

    # 比特幣（僅 CSV，API 無歷史端點）
    if btc:
        twd_price = btc["twd"]
        fri_v = val_from_hist(fri_data, "btc_twd", "btc_twd")
        prev_v = val_from_hist(prev_fri_data, "btc_twd", "prev_btc_twd")
        pct = calc_pct_change(fri_v, prev_v) if fri_v and prev_v else None
        sym, pct_str = fmt_change(pct)
        lines.append(f"    比特幣 {fmt_num(twd_price, 2)} TWD {sym}{pct_str}")
    else:
        lines.append("    比特幣  取得失敗")
    lines.append("")

    # --- 台股週變化 ---
    lines.append("📈 <b>台股週變化：</b>")

    if taiex:
        val = taiex["taifex"]
        fri_v = val_from_hist(fri_data, "twii", "twii")
        prev_v = val_from_hist(prev_fri_data, "twii", "prev_twii")
        if fri_v and prev_v:
            pct = calc_pct_change(fri_v, prev_v)
        else:
            pct = None
        sym, pct_str = fmt_change(pct)
        lines.append(f"    加權指數 {fmt_num(val)} {sym}{pct_str}")
    else:
        lines.append("    加權指數 取得失敗")

    if tsmc:
        val = tsmc["close"]
        # 台積電無 API 歷史，僅 CSV
        fri_v = val_from_hist(fri_data, "tsmc", "tsmc")
        prev_v = val_from_hist(prev_fri_data, "tsmc", "prev_tsmc")
        pct = calc_pct_change(fri_v, prev_v) if fri_v and prev_v else None
        sym, pct_str = fmt_change(pct)
        lines.append(f"    台積電(2330) {fmt_num(val)} {sym}{pct_str}")
    else:
        lines.append("    台積電(2330) 取得失敗")

    # 台指期（週一凌晨 5:00 收盤 = 週日夜盤）
    fri_tx_v = val_from_hist(fri_data, "tx_settlement", "tx_settlement")
    prev_tx_v = val_from_hist(prev_fri_data, "tx_settlement", "prev_tx_settlement")
    if fri_tx_v and prev_tx_v:
        pct = calc_pct_change(fri_tx_v, prev_tx_v)
        sym, pct_str = fmt_change(pct)
        lines.append(f"    台指期 {fmt_num(fri_tx_v)} {sym}{pct_str}")
    elif fri_tx_v:
        lines.append(f"    台指期 {fmt_num(fri_tx_v)} ——")
    else:
        lines.append("    台指期 無上週資料")

    return "\n".join(lines)


# ===== 週日報 =====
def generate_sunday_report():
    """週日報：國際行情 + 折線圖 + 本週總結"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    today = datetime.date.today()

    lines = [f"📊 <b>財經快訊 — 週日報</b> ({now})\n"]

    # --- 抓取今日數據（同平日格式）---
    fx = get_twb_fx()
    usd_rate = fx.get("USD", {}).get("spot_sell", 0)

    # 貴金屬（GoldAPI → Yahoo 備案）
    metals = {}
    for gs, ys, _ in METAL_SOURCES:
        metals[gs] = get_metal_price(gs, ys)

    taiex = get_twse_taiex()
    tsmc = get_twse_stock("2330")
    btc = get_btc()

    # 原油 + 台指期
    try:
        wti_data = get_finmind_oil("WTI")
    except:
        wti_data = None
    try:
        brent_data = get_finmind_oil("Brent")
    except:
        brent_data = None
    try:
        tx_data = get_finmind_tx()
    except:
        tx_data = None

    # 💱 匯率
    lines.append("💱 <b>台灣銀行匯率（即期）</b>")
    history = load_history()
    prev_row = history[-2] if len(history) >= 2 else None
    for cur, label in [("USD", "USD"), ("CNY", "CNY"), ("JPY", "1/JPY")]:
        if cur in fx:
            val = fx[cur]["spot_sell"]
            if cur == "JPY" and val > 0:
                val = 1 / val
                prev_val = float(prev_row.get("jpy_spot_buy", 0)) if prev_row else 0
                if prev_val > 0:
                    pct = calc_pct_change(val, 1 / prev_val)
                else:
                    pct = None
            else:
                prev_val = float(prev_row.get(f"fx_{cur}", prev_row.get({"USD":"usd_spot_sell","CNY":"cny_spot_sell"}.get(cur,""), 0))) if prev_row else 0
                pct = calc_pct_change(val, prev_val) if prev_val else None
            sym, pct_str = fmt_change(pct)
            lines.append(f"  {label} {fmt_num(val, 2)} {sym}{pct_str}")
    lines.append("")

    # 🌍 國際行情
    lines.append("🌍 <b>國際行情</b>")
    for metal, label, icon in [("XAU", "黃金", "🥇"), ("XAG", "白銀", "🥈"), ("XPT", "鉑金", "⚪")]:
        if metals.get(metal):
            twd = metals[metal]["price"] * usd_rate
            chp = metals[metal].get("chp")
            sym, pct_str = fmt_change(chp)
            lines.append(f"  {icon} {label} {fmt_num(twd)} {sym}{pct_str}")
        else:
            lines.append(f"  {icon} {label} 取得失敗")

    # 原油 + 比特幣（含日變化）
    for item, label, icon, price, key in [
        (wti_data, "原油WTI", "🛢️", wti_data["price"] if wti_data else None, "wti_usd"),
        (brent_data, "原油Brent", "🛢️", brent_data["price"] if brent_data else None, "brent_usd"),
        (btc, "比特幣", "₿", btc["twd"] if btc else None, "btc_twd"),
    ]:
        if item:
            prev_v = float(prev_row.get(key, 0)) if prev_row else 0
            pct = calc_pct_change(price, prev_v) if prev_v else None
            sym, pct_str = fmt_change(pct)
            if label == "比特幣":
                lines.append(f"  {icon} {label} {fmt_num(price, 2)} {sym}{pct_str}")
            else:
                lines.append(f"  {icon} {label} {fmt_num(price, 2)} {sym}{pct_str}")

    # 📈 重要數值週變化
    lines.append("📈 <b>重要數值週變化</b>")
    lines.append("  （見下方折線圖）")
    lines.append("")

    # 📋 本週總結
    lines.append("📋 <b>本週總結</b>")

    # 從歷史數據計算本週漲跌
    last_week = get_last_n_trading_days(5)
    if len(last_week) >= 2:
        first = last_week[0]
        last = last_week[-1]

        summary_items = []
        for key, label in [
            ("gold_usd", "黃金"),
            ("silver_usd", "白銀"),
            ("wti_usd", "WTI"),
            ("twii", "加權指數"),
            ("tsmc", "台積電"),
            ("tx_settlement", "台指期"),
        ]:
            try:
                first_val = float(first.get(key, 0))
                last_val = float(last.get(key, 0))
                pct = calc_pct_change(last_val, first_val) if first_val else None
                if pct is not None:
                    summary_items.append((label, pct))
            except:
                pass

        # 排序：漲最多 / 跌最多
        summary_items.sort(key=lambda x: x[1], reverse=True)

        if summary_items:
            top = summary_items[0]  # 漲最多
            bottom = summary_items[-1]  # 跌最多
            sym_up, pct_up = fmt_change(top[1])
            sym_down, pct_down = fmt_change(bottom[1])
            lines.append(f"   漲最多：{top[0]}  {sym_up}{pct_up}")
            lines.append(f"   跌最多：{bottom[0]}  {sym_down}{pct_down}")
    else:
        lines.append("  數據不足，無法計算")

    # --- 畫折線圖 ---
    chart_path = draw_weekly_chart()

    msg = "\n".join(lines)
    return msg, chart_path


def draw_weekly_chart():
    """畫一週變化折線圖，回傳圖片路徑"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        # 設定中文字型
        matplotlib.rcParams["font.sans-serif"] = [
            "Noto Sans CJK TC", "Noto Sans CJK SC",
            "AR PL UMing TW", "DejaVu Sans",
        ]
        matplotlib.rcParams["axes.unicode_minus"] = False

        # 取得最近 5 個交易日
        days = get_last_n_trading_days(5)
        if len(days) < 2:
            return None

        dates = []
        gold_chg = []
        tsmc_chg = []
        usd_chg = []

        for i, row in enumerate(days):
            d = row.get("date", "")
            if d:
                dt = datetime.datetime.strptime(d, "%Y-%m-%d")
                dates.append(dt.strftime("%m/%d"))

            # 計算每日漲跌（與前一天比較）
            if i > 0:
                prev = days[i - 1]
                try:
                    g = calc_pct_change(float(row.get("gold_usd", 0)), float(prev.get("gold_usd", 0)))
                    t = calc_pct_change(float(row.get("tsmc", 0)), float(prev.get("tsmc", 0)))
                    u = calc_pct_change(float(row.get("usd_spot_sell", 0)), float(prev.get("usd_spot_sell", 0)))
                    gold_chg.append(g if g else 0)
                    tsmc_chg.append(t if t else 0)
                    usd_chg.append(u if u else 0)
                except:
                    gold_chg.append(0)
                    tsmc_chg.append(0)
                    usd_chg.append(0)
            else:
                # 第一天無前日可比較
                gold_chg.append(0)
                tsmc_chg.append(0)
                usd_chg.append(0)

        # 第一天的漲跌用 0
        if dates and not gold_chg:
            gold_chg = [0]
            tsmc_chg = [0]
            usd_chg = [0]

        if not dates:
            return None

        fig, ax = plt.subplots(figsize=(8, 4))
        x = range(len(dates))

        ax.plot(x, gold_chg, "o-", color="#FFD700", label="黃金", linewidth=2, markersize=6)
        ax.plot(x, tsmc_chg, "s-", color="#0066CC", label="台積電", linewidth=2, markersize=6)
        ax.plot(x, usd_chg, "^-", color="#CC3300", label="美元", linewidth=2, markersize=6)
        ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(dates)
        ax.set_title("一週變化趨勢", fontsize=14)
        ax.set_ylabel("漲跌幅 %")
        ax.legend(loc="best")
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        chart_path = "/tmp/weekly_chart.png"
        plt.savefig(chart_path, dpi=100, bbox_inches="tight")
        plt.close()
        return chart_path

    except ImportError:
        print("⚠️ matplotlib 未安裝，跳過折線圖")
        return None
    except Exception as e:
        print(f"⚠️ 折線圖繪製失敗: {e}")
        return None


# ===== 主邏輯 =====
def main():
    today = datetime.date.today()
    weekday = today.weekday()  # 0=Mon, 6=Sun

    if weekday == 0:  # 週一
        msg = generate_monday_report()
        tg_send(msg)

    elif weekday == 6:  # 週日
        msg, chart_path = generate_sunday_report()
        tg_send(msg, photo_path=chart_path)

    else:
        print(f"今天不是週一或週日（weekday={weekday}），跳過")


if __name__ == "__main__":
    main()
