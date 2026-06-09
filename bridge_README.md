# Hermes Bridge — 單一檔案即時通訊

## 目錄
```
~/.hermes/bridge/
```

## 檔案

| 檔案 | 用途 |
|------|------|
| `bridge.jsonl` | **唯一訊息檔**。TYTO 跟 BUBO 都 append 寫入 |
| `bubo_pos.txt` | BUBO 游標：最後處理到的 `from: tyto` message ID |
| `tyto_pos.txt` | TYTO 游標：最後轉發給 Jin Lin 的 `from: bubo` message ID |
| `needs_agent.flag` | 有複雜訊息需要 agent 處理時自動產生 |

## 觸發機制

- **TYTO 寫入 → 即時觸發 BUBO**：`bridge_watcher.sh`（背景 daemon）用 inotify 監視 bridge.jsonl
- **BUBO 回覆 → TYTO 輪詢**：每 30 分鐘檢查一次，有新的 from:bubo 就轉發給 Jin Lin

## 訊息格式

```json
{"id":"唯一ID","from":"tyto|bubo","to":"bubo|tyto","text":"內容","timestamp":"ISO時間"}
```

## 支援指令（BUBO 端，即時處理）

| 指令 | 行為 |
|------|------|
| `STATUS` | 回報待辦數量 |
| `TODO 完成/ADD <項目>` | 標記完成 / 新增待辦 |
| `NOTIFY <訊息>` | 純通知 |
| 其他 | 寫 needs_agent.flag，下一 WSL 工作階段處理 |
