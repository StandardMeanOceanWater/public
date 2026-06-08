#!/usr/bin/env python3
"""
每日財經快訊 FLAT 平日版(週二～六 06:21)
從各官方源頭抓取數據,計算漲跌,發送 Telegram

資料源:
  匯率      → 台灣銀行 CSV(免 key)
  黃金/白銀/鉑金 → GoldAPI.io LBMA 現貨(免費 100 req/月)
  原油 WTI/Brent → FinMind(免費 600 req/hr)
  比特幣    → blockchain.com(免 key)
  加權指數  → 證交所 OpenAPI FMTQIK(免 key)
  台積電    → 證交所 OpenAPI STOCK_DAY_ALL(免 key)
  台指期    → FinMind TaiwanFuturesDaily(免費)

格式規則(2026-06-08 定稿):
  UP = 漲(紅色),DOWN = 跌(綠色),FLAT = 無變化(灰色)
  數值不加正負號,不加逗號
  匯率小數 2 位,其餘整數
"""


import urllib.request
import json
import csv
import datetime
import os
import sys
import io

# ===== 載入設定 =====
# API keys 統一從 ~/.hermes/.env 讀取,絕不硬編碼
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _load_env():
    "載入 ~/.hermes/.env 中的環境變數"
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
BOT_TOKEN = os.environ.get("NEWSBOY_BOT_TOKEN", "")
CHAT_ID = os.environ.get("NEWSBOY_CHAT_ID", "686734095")

# 歷史數據路徑
HISTORY_PATH = os.path.join(BASE_DIR, "finance_history.csv")

# ===== API 呼叫工具 =====
def api_get(url, headers=None, timeout=30):
    """通用 HTTP GET"""
    req = urllib.request.Request(url, headers=headers or {})
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read().decode())


def api_get_text(url, headers=None, timeout=30):
    """通用 HTTP GET 回傳文字"""
    req = urllib.request.Request(url, headers=headers or {})
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.read().decode()


# ===== 1. 台灣銀行匯率 =====
def get_twb_fx():
    """台灣銀行即期匯率
    台銀 CSV 欄位順序(兩組:買入/賣出):
      幣別, 匯率(本行買入), 現金(買入), 即期(買入), 遠期...,
           匯率(本行賣出), 現金(賣出), 即期(賣出), 遠期...
    我們需要: USD/CNY 即期賣出, JPY 即期買入 (倒數顯示)
    """
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
            # 即期買入 = row[3](在第一組)
            spot_buy = float(row[3]) if len(row) > 3 else 0
            # 即期賣出 = row[12](在第二組,「本行賣出」後面)
            spot_sell = 0
            for i in range(10, len(row)):
                if row[i] == "本行賣出":
                    spot_sell = float(row[i + 2]) if i + 2 < len(row) else 0
                    break
            result[cur] = {
                "spot_buy": spot_buy,   # 即期買入
                "spot_sell": spot_sell,  # 即期賣出
            }
    return result


# ===== 2. GoldAPI.io LBMA 現貨 =====
def get_goldapi(metal):
    """取得 LBMA 現貨價格(USD/oz)"""
    url = f"https://www.goldapi.io/api/{metal}/USD"
    headers = {
        "x-access-token": GOLDAPI_API_KEY,
        "Content-Type": "application/json",
    }
    data = api_get(url, headers=headers)
    return {
        "price": data.get("price", 0),
        "prev_close": data.get("prev_close_price", 0),
        "chp": data.get("chp", 0),  # change percent
    }


def get_yahoo_metal(yahoo_symbol):
    """Yahoo Finance 金屬價格（備案，免 key 無限次）
    yahoo_symbol: GC=F (黃金), SI=F (白銀), PL=F (鉑金)
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
    headers = {"User-Agent": "Mozilla/5.0"}
    data = api_get(url, headers=headers)
    result = data.get("chart", {}).get("result", [{}])[0]
    meta = result.get("meta", {})
    price = meta.get("regularMarketPrice", 0)
    prev_close = meta.get("chartPreviousClose", 0)
    chp = ((price - prev_close) / prev_close * 100) if prev_close else 0
    return {"price": price, "prev_close": prev_close, "chp": chp}


METAL_SOURCES = [
    ("XAU", "GC=F", "黃金"),
    ("XAG", "SI=F", "白銀"),
    ("XPT", "PL=F", "鉑金"),
]


def get_metal_price(goldapi_symbol, yahoo_symbol):
    """嘗試 GoldAPI → 失敗自動降級 Yahoo"""
    try:
        return get_goldapi(goldapi_symbol)
    except Exception:
        pass
    try:
        return get_yahoo_metal(yahoo_symbol)
    except Exception:
        return None


# ===== 3. 證交所 OpenAPI =====
def get_twse_taiex():
    """證交所每日市場成交資訊(含加權指數 TAIEX)"""
    url = "https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK"
    data = api_get(url)
    if not data:
        return None
    latest = data[-1]  # 最新一筆
    return {
        "date": latest.get("Date", ""),
        "taifex": float(latest.get("TAIEX", 0)),
        "change": float(latest.get("Change", 0)),
    }


def get_twse_stock(code):
    """證交所個股日成交(從 STOCK_DAY_ALL 過濾)"""
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    data = api_get(url)
    for r in data:
        if r.get("Code") == code:
            return {
                "date": r.get("Date", ""),
                "close": float(r.get("ClosingPrice", 0)),
                "change": float(r.get("Change", 0)),
            }
    return None


# ===== 4. FinMind =====
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
    """FinMind 原油(WTI 或 Brent)
    注意: 需要 start_date 參數才能成功呼叫
    """
    start = (datetime.date.today() - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
    records = get_finmind("CrudeOilPrices", data_id=oil_type, start_date=start)
    if records:
        r = records[-1]
        return {"price": float(r.get("price", 0)), "date": r.get("date", "")}
    return None


def get_finmind_tx():
    """FinMind 台指期 TX 近月結算價"""
    today = datetime.date.today().strftime("%Y-%m-%d")
    # 查最近 5 天
    start = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    records = get_finmind("TaiwanFuturesDaily", data_id="TX",
                          start_date=start, end_date=today)

    # 過濾:只要近月(無 "/" 的合約日期)且有 settlement_price
    near = [r for r in records
            if "/" not in str(r.get("contract_date", ""))
            and r.get("settlement_price", 0) > 0]

    if not near:
        return None

    # 取最新一筆
    latest = max(near, key=lambda x: x["date"])
    return {
        "date": latest["date"],
        "settlement": float(latest["settlement_price"]),
        "close": float(latest.get("close", 0)),
    }


# ===== 5. blockchain.com 比特幣 =====
def get_btc():
    """blockchain.com BTC 價格"""
    url = "https://blockchain.com/ticker"
    data = api_get(url)
    usd = data.get("USD", {})
    twd = data.get("TWD", {})
    return {
        "usd": float(usd.get("last", 0)),
        "twd": float(twd.get("last", 0)),
    }


# ===== 歷史數據管理 =====
def load_history():
    """載入 finance_history.csv"""
    if not os.path.exists(HISTORY_PATH):
        return []
    with open(HISTORY_PATH, "r") as f:
        reader = csv.DictReader(f)
        return list(reader)


def save_history_row(row):
    """寫入一筆到 finance_history.csv"""
    file_exists = os.path.exists(HISTORY_PATH)
    with open(HISTORY_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def get_prev_data():
    """取得前一日的歷史數據(用於計算漲跌)"""
    history = load_history()
    if not history:
        return {}
    return history[-1]


# ===== 漲跌計算與格式化 =====
def fmt_change(pct):
    """
    格式化漲跌顯示
    回傳 (符號, 百分比文字)
    - ▲ 漲（無正負號）
    - ▼ 跌（無正負號）
    - — 無變化
    """
    if pct is None:
        return "—", "—"
    if pct > 0:
        return "▲", f"{abs(pct):.1f}%"
    elif pct < 0:
        return "▼", f"{abs(pct):.1f}%"
    else:
        return "—", "—"


def fmt_num(val, decimals=0):
    """格式化數值，不加逗號"""
    if decimals == 0:
        return f"{int(round(val))}"
    return f"{val:.{decimals}f}"


def calc_pct_change(current, previous):
    """計算漲跌百分比"""
    if not previous or previous == 0:
        return None
    return (current - previous) / previous * 100


# ===== 主邏輯 =====
def main():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    today = datetime.date.today()
    weekday = today.weekday()  # 0=Mon, 6=Sun

    lines = [f"📊 <b>每日財經快訊</b> ({now})\n"]

    # --- 抓取所有數據 ---
    errors = []

    # 1. 匯率
    try:
        fx = get_twb_fx()
    except Exception as e:
        errors.append(f"匯率: {e}")
        fx = {}

    # 2. 貴金屬（GoldAPI → Yahoo 備案）
    metals = {}
    for gs, ys, name in METAL_SOURCES:
        try:
            metals[gs] = get_metal_price(gs, ys)
        except:
            metals[gs] = None

    # 3. 加權指數 + 台積電
    try:
        taiex_data = get_twse_taiex()
    except Exception as e:
        errors.append(f"加權指數: {e}")
        taiex_data = None

    try:
        tsmc_data = get_twse_stock("2330")
    except Exception as e:
        errors.append(f"台積電: {e}")
        tsmc_data = None

    # 4. 台指期
    try:
        tx_data = get_finmind_tx()
    except Exception as e:
        errors.append(f"台指期: {e}")
        tx_data = None

    # 5. 原油
    try:
        wti_data = get_finmind_oil("WTI")
    except Exception as e:
        errors.append(f"WTI: {e}")
        wti_data = None

    try:
        brent_data = get_finmind_oil("Brent")
    except Exception as e:
        errors.append(f"Brent: {e}")
        brent_data = None

    # 6. 比特幣
    try:
        btc_data = get_btc()
    except Exception as e:
        errors.append(f"比特幣: {e}")
        btc_data = None

    # --- 取得昨日數據(計算漲跌)---
    prev = get_prev_data()

    # --- 格式化輸出 ---

    # 💱 匯率
    lines.append("💱 <b>台灣銀行匯率(即期)</b>")
    usd_rate = 0
    for cur, label, fmt in [("USD", "USD", 2), ("CNY", "CNY", 2), ("JPY", "1/JPY", 2)]:
        if cur in fx:
            spot = fx[cur].get("spot_sell", 0)
            if cur == "JPY":
                # JPY 是倒數顯示
                if spot > 0:
                    display_val = 1 / spot
                else:
                    display_val = 0
                pass  # JPY 不需要設定 usd_rate
            else:
                display_val = spot
                if cur == "USD":
                    usd_rate = spot

            # 計算漲跌
            prev_str = prev.get(f"fx_{cur}", "") if prev else ""
            prev_val = float(prev_str) if prev_str else 0
            pct = calc_pct_change(spot, prev_val) if prev_val else None
            sym, pct_str = fmt_change(pct)

            lines.append(f"  {label} {fmt_num(display_val, 2)} {sym}{pct_str}")
        else:
            lines.append(f"  {label} 取得失敗")
    lines.append("")

    # 🌍 國際行情
    lines.append("🌍 <b>國際行情</b>")

    # 貴金屬(換算 TWD)
    for metal, name, icon in [("XAU", "黃金", "🥇"), ("XAG", "白銀", "🥈"), ("XPT", "鉑金", "⚪")]:
        if metals.get(metal):
            usd_price = metals[metal]["price"]
            twd_price = usd_price * usd_rate if usd_rate else 0
            prev_val = prev.get(f"{metal.lower()}_usd", "") if prev else ""
            prev_twd = float(prev_val) * float(prev.get("usd_spot_sell", 1)) if prev_val else 0
            pct = calc_pct_change(twd_price, prev_twd) if prev_twd else None
            sym, pct_str = fmt_change(pct)
            lines.append(f"  {icon} {name} {fmt_num(twd_price)} {sym}{pct_str}")
        else:
            lines.append(f"  {icon} {name} 取得失敗")

    # 原油
    for oil_type, label in [("WTI", "原油WTI"), ("Brent", "原油Brent")]:
        data = wti_data if oil_type == "WTI" else brent_data
        if data:
            price = data["price"]
            prev_str = prev.get(f"{oil_type.lower()}_usd", "") if prev else ""
            prev_price = float(prev_str) if prev_str else 0
            pct = calc_pct_change(price, prev_price) if prev_price else None
            sym, pct_str = fmt_change(pct)
            lines.append(f"  🛢️ {label} {fmt_num(price, 2)} {sym}{pct_str}")
        else:
            lines.append(f"  🛢️ {label} 取得失敗")

    # 比特幣
    if btc_data:
        twd_price = btc_data["twd"]
        prev_twd = float(prev.get("btc_twd", 0)) if prev else 0
        pct = calc_pct_change(twd_price, prev_twd) if prev_twd else None
        sym, pct_str = fmt_change(pct)
        lines.append(f"  ₿ 比特幣 {fmt_num(twd_price, 2)} {sym}{pct_str}")
    else:
        lines.append("  ₿ 比特幣 取得失敗")
    lines.append("")

    # 📈 台股
    lines.append("📈 <b>台股</b>")

    if taiex_data:
        val = taiex_data["taifex"]
        prev_val = float(prev.get("twii", 0)) if prev else 0
        pct = calc_pct_change(val, prev_val) if prev_val else None
        sym, pct_str = fmt_change(pct)
        lines.append(f"  加權指數 {fmt_num(val)} {sym}{pct_str}")
    else:
        lines.append("  加權指數 取得失敗")

    if tsmc_data:
        val = tsmc_data["close"]
        prev_val = float(prev.get("tsmc", 0)) if prev else 0
        pct = calc_pct_change(val, prev_val) if prev_val else None
        sym, pct_str = fmt_change(pct)
        lines.append(f"  台積電(2330) {fmt_num(val)} {sym}{pct_str}")
    else:
        lines.append("  台積電(2330) 取得失敗")

    if tx_data:
        val = tx_data["settlement"]
        prev_val = float(prev.get("tx_settlement", 0)) if prev else 0
        pct = calc_pct_change(val, prev_val) if prev_val else None
        sym, pct_str = fmt_change(pct)
        lines.append(f"  台指期 {fmt_num(val)} {sym}{pct_str}")
    else:
        lines.append("  台指期 取得失敗")

    # 錯誤報告
    if errors:
        lines.append("")
        lines.append(f"⚠️ 部分數據取得失敗: {', '.join(errors)}")

    msg = "\n".join(lines)

    # --- 儲存歷史 ---
    history_row = {
        "date": today.strftime("%Y-%m-%d"),
        "usd_spot_sell": str(fx.get("USD", {}).get("spot_sell", "")),
        "cny_spot_sell": str(fx.get("CNY", {}).get("spot_sell", "")),
        "jpy_spot_buy": str(fx.get("JPY", {}).get("spot_buy", "")),
        "gold_usd": str(metals.get("XAU", {}).get("price", "") if metals.get("XAU") else ""),
        "silver_usd": str(metals.get("XAG", {}).get("price", "") if metals.get("XAG") else ""),
        "platinum_usd": str(metals.get("XPT", {}).get("price", "") if metals.get("XPT") else ""),
        "wti_usd": str(wti_data.get("price", "") if wti_data else ""),
        "brent_usd": str(brent_data.get("price", "") if brent_data else ""),
        "btc_usd": str(btc_data.get("usd", "") if btc_data else ""),
        "twii": str(taiex_data.get("taifex", "") if taiex_data else ""),
        "tsmc": str(tsmc_data.get("close", "") if tsmc_data else ""),
        "tx_settlement": str(tx_data.get("settlement", "") if tx_data else ""),
    }
    save_history_row(history_row)

    # --- 發送 Telegram ---
    if BOT_TOKEN:
        tg_send(msg)


def tg_send(text):
    """發送 Telegram 訊息"""
    # Telegram 長度限制 4096
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
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=15)
        except Exception as e:
            print(f"Telegram 發送失敗: {e}")


if __name__ == "__main__":
    main()
