![[天文攝影疊圖.py]]

這份程式碼出自學生之手，寫得相當工整，且具備了一般「天文攝影（美觀取向）」的處理架構。

但若目標是**「變星光度測量（科學取向）」**，這份程式碼存在**一個致命的物理順序錯誤**，以及**幾個潛在的風險**。如果不修正，後續算出來的星等數據會是錯誤的。

以下是我的詳細 Code Review（代碼審查）：

---

### 🔴 致命錯誤：校正與解碼的順序顛倒 (The Fatal Flaw)

這是最需要修正的地方。

*   **現狀**：學生使用 `rawpy.postprocess()`（在 CR2）或 `cv2.cvtColor(Bayer2RGB)`（在 FITS）將影像轉為彩色 RGB。**接著**才進行 Dark 減算和 Flat 除算。
*   **物理問題**：
    *   相機感光元件是單色的 Bayer 陣列（R-G-G-B）。
    *   **暗電流（Hot Pixel）** 是發生在單一像素上的。
    *   **平場（灰塵陰影）** 也是對應到單一像素的光路遮蔽。
 一旦執行「轉彩色（Demosaicing/Debayering）」，程式會利用鄰近像素進行插值運算。這會把原本只在一個像素上的「熱噪點」或「灰塵邊緣」，**抹開（Smear）到周圍的像素去**。
    *   **後果**：此時再去減 Master Dark，因為位置已經對不準（被抹開了），根本減不乾淨，甚至會產生奇怪的黑圈或雜訊。

*   **正確流程**：
    1.  讀取 Raw Bayer Data (保持灰階馬賽克狀態)。
    2.  運算：`(Light_Bayer - Dark_Bayer) / Flat_Bayer`。
    3.  **校正完畢後**，才進行拆色（Split Channels）或轉彩色（Debayer）。

---

### 🟠 記憶體爆炸風險 (Memory Leak)

*   **現狀**：
    ```python
    calibrated_stack.append(aligned)
    # ...
    final_image = np.median(np.array(calibrated_stack), axis=0)
    ```
*   **問題**：學生把所有校正後的照片（如果是 6D2，一張 26MP 的 32-bit float 圖約佔 100MB 記憶體）全部存進一個 List。
    *   如果你拍了 100 張，這會瞬間吃掉 10GB以上的 RAM。
    *   如果你拍了 300 張，一般電腦會直接當機（MemoryError）。
*   **建議**：對於科學疊圖，通常建議分批處理，或使用 Welford 演算法進行逐張平均（雖然 Median 比較難逐張做，但在光度測量中，我們其實**不需要疊圖**，而是要**單張測量**）。

---

### 🟡 針對光度測量的特定問題

由於你的目標是做變星分析（Photometry），這份代碼還有以下不適用之處：

1.  **FITS 標頭 (Header) 遺失**：
    *   程式碼讀取 FITS `data` 後，完全丟棄了 `header`。
    *   **後果**：觀測時間 (`DATE-OBS`)、曝光時間 (`EXPTIME`) 全部不見了。做光變曲線需要 X 軸（時間），這份程式跑完出的圖，時間資訊就斷了。

2.  **OpenCV 對齊 (Alignment) 的隱憂**：
    *   學生用 `cv2.warpAffine` 進行疊圖對齊。
    *   這會對像素進行「重採樣 (Resampling/Interpolation)」。
    *   對於「美圖」沒問題，但對於「測光」，重採樣會改變星點的通量分佈（Flux conservation issue），雖然影響可能在 1% 以內，但能避免則避免。
    *   **正確做法**：光度測量通常**不對齊影像**。而是每一張影像獨立解出座標（WCS），然後去那個座標抓星星。

---

### ✅ 寫得好的地方 (值得嘉獎)

1.  **Rawpy 參數設定正確**：
    `gamma=(1,1), no_auto_bright=True, output_bps=16`
    這表示學生知道要獲取「線性數據 (Linear Data)」，這是科學分析的基礎。
2.  **平場歸一化 (Normalization)**：
    `master_flat /= np.mean(master_flat)`
    觀念正確，知道 Flat 只能修整相對亮度，不能改變整體數值大小。
3.  **使用 tqdm**：
    有考慮到使用者體驗，加入了進度條。

---

### 給學生的修改建議 (科學版)

如果是為了你的「變星分析專案」，請讓學生修改 `load_cr2_rgb` 和 `main` 的邏輯。

**修改後的邏輯虛擬碼：**

```python
def load_raw_bayer(f):
    """讀取原始 Bayer 數據，不轉彩色"""
    with rawpy.imread(f) as raw:
        # user_sat=None 不裁切高光
        # use_camera_wb=False 不套用白平衡
        # half_size=False 保持原解析度
        # 關鍵：直接存取 raw_image，這是 2D 陣列 (H, W)
        return raw.raw_image.copy().astype(np.float32)

# 主流程修正
# 1. 計算 Master Dark/Flat 時，全部使用 load_raw_bayer
# 2. 校正時：
light_raw = load_raw_bayer(f)
calibrated_raw = (light_raw - master_dark) / master_flat

# 3. 校正後，針對變星分析，我們直接提取綠色通道
# 6D2 的 Bayer 排列通常是 RGGB
# R = calibrated_raw[0::2, 0::2]
# G1 = calibrated_raw[0::2, 1::2] <--- 用這個做 V 波段
# G2 = calibrated_raw[1::2, 0::2]
# B = calibrated_raw[1::2, 1::2]

# 4. 將 G1 存為 FITS，並保留原始 Header
```

### 結論

這份程式碼是用來**「出漂亮的彩色圖」**用的，**不能**直接拿來做你的步驟 1（科學校正）。

如果你要使用這份代碼的架構，必須請學生：
1.  **移除所有轉彩色 (Demosaicing) 的步驟**，改為全流程處理單色 Bayer Data。
2.  **加入 FITS Header 的讀取與寫入**，確保時間資訊不流失。
3.  (選用) 改為只提取綠色通道輸出，因為彩色對光度測量是干擾。

**是否需要我提供修正後的「科學用校正代碼」？**