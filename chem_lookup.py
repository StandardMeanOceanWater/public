#!/usr/bin/env python3
"""
chem_lookup.py — 輸入中文/英文化學名稱，取得 SMILES 與 LaTeX 代碼
用法：python chem_lookup.py
需要：pip install requests
選用：pip install mol2chemfig  （自動產生 chemfig 代碼）
"""

import requests
import sys
import json
import urllib.parse

PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

# 繁中 → 英文對照（常見化學名，避免翻譯 API 依賴）
ZH_MAP = {
    "苯": "benzene",
    "乙醇": "ethanol",
    "甲醇": "methanol",
    "丙酮": "acetone",
    "乙酸": "acetic acid",
    "乙醛": "acetaldehyde",
    "葡萄糖": "glucose",
    "果糖": "fructose",
    "蔗糖": "sucrose",
    "咖啡因": "caffeine",
    "阿斯匹靈": "aspirin",
    "阿司匹林": "aspirin",
    "乙醯水楊酸": "aspirin",
    "乙酰水杨酸": "aspirin",
    "多巴胺": "dopamine",
    "腎上腺素": "epinephrine",
    "膽固醇": "cholesterol",
    "青黴素": "penicillin G",
    "盤尼西林": "penicillin G",
    "維生素C": "ascorbic acid",
    "維他命C": "ascorbic acid",
    "尼古丁": "nicotine",
    "乙烯": "ethylene",
    "丙烯": "propylene",
    "甲苯": "toluene",
    "萘": "naphthalene",
    "蒽": "anthracene",
    "苯酚": "phenol",
    "甲醛": "formaldehyde",
    "氯化鈉": "sodium chloride",
    "碳酸鈣": "calcium carbonate",
    "硫酸": "sulfuric acid",
    "鹽酸": "hydrochloric acid",
    "氫氧化鈉": "sodium hydroxide",
    "氨": "ammonia",
    "尿素": "urea",
    "乙二醇": "ethylene glycol",
    "甘油": "glycerol",
    "丙三醇": "glycerol",
}

def query_pubchem(name):
    """查 PubChem，回傳 dict 或 None"""
    url = f"{PUBCHEM}/compound/name/{urllib.parse.quote(name)}/property/IsomericSMILES,MolecularFormula,MolecularWeight,IUPACName/JSON"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        props = r.json()["PropertyTable"]["Properties"][0]
        return {
            "cid": props.get("CID"),
            "smiles": props.get("IsomericSMILES", ""),
            "formula": props.get("MolecularFormula", ""),
            "mw": float(props.get("MolecularWeight", 0)),
            "iupac": props.get("IUPACName", ""),
        }
    except Exception:
        return None

def smiles_to_chemfig(smiles):
    """用 mol2chemfig 套件轉換（若已安裝）"""
    try:
        import mol2chemfig.mol2chemfig as m2c
        result = m2c.main(["--terse", smiles])
        return result
    except ImportError:
        return None
    except Exception:
        return None

def mhchem_latex(formula):
    """產生 mhchem 的 \\ce{} 代碼"""
    return f"\\ce{{{formula}}}"

def print_result(name, data, translated_from=None):
    print("\n" + "─" * 50)
    if translated_from:
        print(f"  查詢：{translated_from} → {name}")
    else:
        print(f"  查詢：{name}")
    print("─" * 50)
    print(f"  IUPAC 名稱  : {data['iupac']}")
    print(f"  分子式      : {data['formula']}")
    print(f"  分子量      : {data['mw']:.2f} g/mol")
    print(f"  PubChem CID : {data['cid']}")
    print()
    print(f"  SMILES      :")
    print(f"    {data['smiles']}")
    print()
    print(f"  mhchem LaTeX（方程式用）：")
    print(f"    {mhchem_latex(data['formula'])}")
    print()

    chemfig = smiles_to_chemfig(data["smiles"])
    if chemfig:
        print(f"  chemfig LaTeX（結構式用）：")
        print(f"    {chemfig}")
    else:
        print(f"  chemfig LaTeX：")
        print(f"    （需安裝 mol2chemfig：pip install mol2chemfig）")
        print(f"    或將 SMILES 貼到：")
        print(f"    https://www.cheminfo.org/Chemistry/2D_3D_Molecules/mol2chemfig/")

    print()
    print(f"  PubChem 頁面：")
    print(f"    https://pubchem.ncbi.nlm.nih.gov/compound/{data['cid']}")
    print("─" * 50)

def lookup(name):
    original = name
    translated = None

    # 先試繁中對照表
    if name in ZH_MAP:
        translated = ZH_MAP[name]
        print(f"  → 對照表查到：{name} = {translated}")
        name = translated

    # 直接查 PubChem
    data = query_pubchem(name)

    # 若失敗，且原始輸入是中文，試原文查一次
    if data is None and translated is None and any('\u4e00' <= c <= '\u9fff' for c in original):
        print(f"  → 直接查詢失敗，嘗試中文原文送 PubChem...")
        data = query_pubchem(original)
        if data:
            translated = None

    if data is None:
        print(f"\n  ✗ 找不到「{original}」，請嘗試：")
        print(f"    - 英文名稱（如 aspirin、glucose）")
        print(f"    - IUPAC 名稱")
        print(f"    - 分子式（如 C6H6）")
        return

    print_result(name, data, translated_from=original if translated else None)

def main():
    print("═" * 50)
    print("  化學結構式查詢工具")
    print("  輸入 q 或 Ctrl+C 離開")
    print("═" * 50)

    if len(sys.argv) > 1:
        # 支援命令列參數：python chem_lookup.py 苯
        name = " ".join(sys.argv[1:])
        lookup(name)
        return

    while True:
        try:
            name = input("\n  輸入化學名稱：").strip()
            if not name or name.lower() in ("q", "quit", "exit"):
                print("  Bye.")
                break
            lookup(name)
        except KeyboardInterrupt:
            print("\n  Bye.")
            break

if __name__ == "__main__":
    main()
