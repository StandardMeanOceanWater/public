"""
test_finmind.py — 測試 FinMind API 連線 + 台指期 + 原油
"""
import urllib.request
import json
import ssl
import os

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

BASE = "/mnt/f/MD/scripts"
TOKEN_FILE = os.path.join(BASE, "config.json")

with open(TOKEN_FILE, "r") as f:
    config = json.load(f)

TOKEN = config["finmind_token"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

print(f"Token (first 20 chars): {TOKEN[:20]}...")
print(f"Token length: {len(TOKEN)}")
print()

# 1. 測試 API 用量
print("=== API 用量 ===")
try:
    url = "https://api.web.finmindtrade.com/v2/user_info"
    req = urllib.request.Request(url, headers=HEADERS)
    resp = urllib.request.urlopen(req, timeout=15, context=ctx)
    info = json.loads(resp.read().decode())
    print(f"  Status: {info.get('status')}")
    print(f"  User: {info.get('user_id')}")
    print(f"  Level: {info.get('level_title')}")
    print(f"  Used: {info.get('user_count')} / {info.get('api_request_limit')}")
except Exception as e:
    print(f"  ERROR: {e}")

print()

# 2. 台指期 TX
print("=== 台指期 TX ===")
try:
    url = "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanFuturesDaily&data_id=TX&start_date=20260605&end_date=20260608"
    req = urllib.request.Request(url, headers=HEADERS)
    resp = urllib.request.urlopen(req, timeout=30, context=ctx)
    data = json.loads(resp.read().decode())
    records = data.get("data", [])

    near = [r for r in records
            if "/" not in str(r.get("contract_date", ""))
            and r.get("settlement_price", 0) > 0]

    print(f"  Total records: {len(records)}")
    print(f"  Near-month with settlement: {len(near)}")

    for r in sorted(near, key=lambda x: x["date"]):
        print(f"  {r['date']}  contract={r['contract_date']}  settlement={r['settlement_price']}  close={r['close']}")

    if near:
        latest = max(near, key=lambda x: x["date"])
        print(f"\n  Latest settlement: {latest['settlement_price']} (date: {latest['date']})")
except Exception as e:
    print(f"  ERROR: {e}")

print()

# 3. 原油
print("=== 原油 ===")
for oil in ["WTI", "Brent"]:
    try:
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=CrudeOilPrices&data_id={oil}&start_date=20260601&end_date=20260608"
        req = urllib.request.Request(url, headers=HEADERS)
        resp = urllib.request.urlopen(req, timeout=30, context=ctx)
        data = json.loads(resp.read().decode())
        records = data.get("data", [])
        print(f"  {oil}: {len(records)} records")
        for r in records:
            print(f"    {r['date']}  {r['price']} USD")
    except Exception as e:
        print(f"  {oil}: ERROR {e}")

print()

# 4. 台積電（證交所）
print("=== 台積電（證交所 OpenAPI）===")
try:
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode())
    for r in data:
        if r["Code"] == "2330":
            print(f"  Date: {r['Date']}  Close: {r['ClosingPrice']}  Change: {r['Change']}")
            break
except Exception as e:
    print(f"  ERROR: {e}")

print()

# 5. 加權指數
print("=== 加權指數（證交所 FMTQIK）===")
try:
    url = "https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read().decode())
    for r in data[-3:]:
        print(f"  {r['Date']}  TAIEX={r['TAIEX']}  Change={r['Change']}")
except Exception as e:
    print(f"  ERROR: {e}")

print()

# 6. GoldAPI
print("=== GoldAPI.io ===")
GOLD_KEY = config["goldapi_key"]
for metal in ["XAU", "XAG", "XPT"]:
    try:
        url = f"https://www.goldapi.io/api/{metal}/USD"
        req = urllib.request.Request(url, headers={"x-access-token": GOLD_KEY, "Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode())
        print(f"  {metal}: ${data.get('price')} USD/oz  (chp: {data.get('chp')}%)")
    except Exception as e:
        print(f"  {metal}: ERROR {e}")

print()

# 7. 台銀匯率
print("=== 台灣銀行匯率 ===")
try:
    url = "https://rate.bot.com.tw/xrt/flcsv/0/day"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=15)
    text = resp.read().decode()
    import csv
    import io
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        cur = row.get("幣別", "")
        if cur in ("USD", "CNY", "JPY"):
            print(f"  {cur}: spot_sell={row.get('即期', row.get('即期匯率', '?'))}")
except Exception as e:
    print(f"  ERROR: {e}")

print()

# 8. BTC
print("=== blockchain.com BTC ===")
try:
    url = "https://blockchain.com/ticker"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read().decode())
    print(f"  USD: {data.get('USD', {}).get('last')}")
    print(f"  TWD: {data.get('TWD', {}).get('last')}")
except Exception as e:
    print(f"  ERROR: {e}")
