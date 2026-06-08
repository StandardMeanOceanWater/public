這是一個非常明智的決定。
在本地端（Local）進行解星，不僅速度快（不用上傳幾十 MB 的檔案），而且沒有網路也不會斷線。

AstroImageJ (AIJ) 的本地解星是基於 **Astrometry.net** 的引擎。在 Windows 上安裝這個引擎稍顯複雜（因为它原本是 Linux 軟體），AIJ 設計了一套自動化流程來簡化它。

請**嚴格依照以下步驟**操作，不要跳過任何一步。

---

### 第一階段：環境與硬碟準備

1.  **硬碟空間**：請確保你的安裝磁碟（通常是 C 槽或 D 槽）至少有 **30GB ~ 50GB** 的剩餘空間。星圖索引檔（Index Files）非常巨大。
2.  **路徑名稱**：AstroImageJ 對路徑非常敏感。請確保你的安裝路徑**完全沒有中文**，也**不可以有空格**。
    *   ❌ `C:\Program Files\AstroImageJ` (有空格，容易出事)
    *   ❌ `C:\天文軟體\AIJ` (有中文，絕對報錯)
    *   ✅ `C:\AIJ` 或 `D:\AIJ_v5` (推薦)

---

### 第二階段：安裝 Cygwin 與 Astrometry.net 引擎

AIJ 透過一個叫做 Cygwin 的模擬層在 Windows 上運行 Linux 程式。

1.  **開啟 AstroImageJ**。
2.  在上方選單列，點選 **`WCS`** $\rightarrow$ **`Plate Solve`** $\rightarrow$ **`Plate Solve Setup...`**。
3.  會跳出一個設定視窗。請找到 **"Local astrometry.net"** 區塊（通常在右上角）。
4.  點擊按鈕 **`Install/Update local astrometry.net`**。
5.  **系統會跳出提示**，詢問你要安裝在哪裡。
    *   建議選擇：`C:\cygwin` 或 `C:\AIJ\cygwin`。
    *   **再次強調：路徑不能有空格或中文。**
6.  **等待下載**：AIJ 會自動下載 Cygwin 安裝包和 Astrometry.net 的二進位檔案。這過程取決於你的網速，可能需要 10-20 分鐘。
    *   *注意：如果安裝失敗，通常是因為 Windows 防火牆擋住了，請暫時關閉防火牆。*

---

### 第三階段：下載星圖索引檔 (Index Files) —— 最關鍵的一步

只有引擎（程式）是無法解星的，你必須下載「地圖（索引檔）」。

1.  在剛剛的 **`Plate Solve Setup`** 視窗中，點擊 **`Index Manager`** 按鈕。
2.  這時會跳出一個複雜的表格，列出 `4200`, `4100` 等系列。這些是不同大小的天空特徵。
3.  **如何選擇要下載哪些檔案？**
    這取決於你的**視場大小 (Field of View, FOV)**。
    *   **你的設備估計**：Canon 6D2 (全片幅) + 望遠鏡。
    *   假設焦距 600mm ~ 1000mm，你的視場大約是 $3^\circ \times 2^\circ$ 到 $2^\circ \times 1.3^\circ$ 左右。
    *   **下載策略**：你需要下載 **覆蓋你視場大小 10% ~ 100%** 的索引檔。

4.  **建議勾選清單 (針對 DSLR + 望遠鏡)**：
    請在 Index Manager 中勾選以下系列（Series 4200 是目前標準）：
    *   **`4210` 到 `4219`** (對應大視場，比較小檔) —— **務必下載**。
    *   **`4204` 到 `4209`** (對應中視場) —— **強烈建議下載**。
    *   `4200` 到 `4203` (對應極小視場/長焦) —— 檔案極大，你的 6D2 暫時不需要，除非你用長焦鏡頭拍很小的星系。

5.  勾選後，點擊 **`Download Selected`**。
    *   **警告**：這會下載好幾 GB 的數據，請耐心等待直到進度條跑完。
    *   *如果下載一直失敗，請檢查你的磁碟空間是否滿了。*

---

### 第四階段：設定 AIJ 使用本地引擎

1.  回到 **`Plate Solve Setup`** 視窗。
2.  確認 **`Blind Solve Method`** (盲解方式) 選項。
    *   請選擇 **`Local Astrometry.net`**。
    *   (預設可能是 `Astrometry.net (online)`，一定要改過來)。
3.  檢查路徑設定：
    *   **`Cygwin bash shell`**：應該會自動填入類似 `C:\cygwin\bin\bash.exe`。
    *   **`solve-field`**：應該會自動填入 `/usr/local/astrometry/bin/solve-field`。
    *   如果這些欄位是空的，代表第二階段安裝失敗，請重新安裝。
4.  點擊 **`Save`** 儲存設定。

---

### 第五階段：實際測試 (驗證時刻)

現在來測試是否能成功解星。

1.  在 AIJ 主視窗，將你的 **綠色通道 FITS (G1)** 拖進去開啟。
2.  點擊選單 **`WCS`** $\rightarrow$ **`Plate Solve`** $\rightarrow$ **`Blind Solve`** (盲解)。
    *   或者直接點工具列上有一個 **紅色靶心圖示** (Plate Solve)。
3.  跳出設定視窗，確認參數：
    *   **Pixel Size**：Canon 6D2 是 **5.76** microns。
    *   **Focal Length**：輸入你望遠鏡的焦距 (例如 600mm)。如果不確定，可以留空讓它自己猜，但填入會解得比較快。
    *   **Approximate Center**：如果知道大概座標（例如參宿四），填進去 RA/Dec 會秒解。不知道也沒關係（Blind Solve 會搜全天，但會比較久）。
4.  點擊 **`Start`**。
5.  **觀察 Log 視窗**：
    *   你應該會看到程式開始跑一堆文字（Reading input file... Loading index...）。
    *   如果看到 **"Solved"** 字樣，並且圖片上出現了黃色的座標網格和北方指示線。
    *   **恭喜你！本地解星系統建置成功。**

---

### 常見錯誤排除 (Troubleshooting)

*   **錯誤：`Cygwin shell not found`**
    *   原因：路徑設錯，或安裝被防毒軟體吃掉了。
    *   解法：去設定裡手動指派 `bash.exe` 的位置。

*   **錯誤：`Did not solve (Time out)`**
    *   原因 1：**索引檔沒下載對**。你的視場不在你下載的檔案範圍內。請回去多下載 `4207`~`4212` 這些範圍。
    *   原因 2：**Pixel Size 設錯**。請確認 6D2 的像素大小是 5.76。
    *   原因 3：**照片星星太少或太拖線**。如果照片品質太差，軟體會找不到足夠的星點特徵。

請先試著執行這些步驟。如果在「下載索引檔」或「測試」時卡住，請告訴我顯示的錯誤訊息。