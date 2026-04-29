# NAS Docker 部署指南（Runtime Clone）

## 部署方式說明

此專案在 NAS 上使用 **runtime clone** 方式部署：
- 不使用 Dockerfile / docker-compose build
- 直接用 `python:3.13-slim` 基礎映像檔
- 容器啟動時自動從 GitHub clone 或同步最新程式碼
- 每次重啟容器會自動拉取最新版本

## Docker Compose YAML

```yaml
version: "3.8"
services:
  mf-dailytradingtool:
    image: python:3.13-slim
    container_name: mf-dailytradingtool
    ports:
      - "8601:8601"
    restart: unless-stopped
    working_dir: /app
    volumes:
      - mf-dailytradingtool-data:/app
    command: >
      bash -c '
      apt-get update && apt-get install -y git curl &&
      if [ ! -d /app/.git ]; then
        git clone https://github.com/adrianamlmc1230/mf_dailytradingtool.git /tmp/repo &&
        cp -r /tmp/repo/* /tmp/repo/.* /app/ 2>/dev/null || true &&
        rm -rf /tmp/repo;
      else
        cd /app && git fetch origin master && git reset --hard origin/master;
      fi &&
      pip install --no-cache-dir -r requirements.txt &&
      streamlit run app.py
        --server.port=8601
        --server.address=0.0.0.0
        --server.headless=true
        --browser.gatherUsageStats=false
      '

volumes:
  mf-dailytradingtool-data:
```

## 啟動命令邏輯

```
容器啟動
  ├─ 安裝 git + curl
  ├─ 判斷 /app/.git 是否存在
  │   ├─ 不存在（首次）→ git clone 到 /app
  │   └─ 已存在（重啟）→ git fetch + reset --hard（強制同步到 remote 最新）
  ├─ pip install 依賴
  └─ 啟動 streamlit（port 8601）
```

## 常用操作

### 更新到最新程式碼
直接重啟容器即可，會自動 `git fetch + reset --hard`：
```bash
docker restart mf-dailytradingtool
```

### 完全重建（如果遇到奇怪問題）
刪除容器和 volume，重新建立：
```bash
docker stop mf-dailytradingtool
docker rm mf-dailytradingtool
docker volume rm mf-dailytradingtool-data
# 然後重新用上面的 YAML 建立容器
```

### 進入容器除錯
```bash
docker exec -it mf-dailytradingtool bash
```

## 注意事項

- `git reset --hard` 會強制覆蓋本地變更，確保和 GitHub 完全一致
- 即使做了 force push 也不會卡住（不像 `git pull` 會報 divergent branches）
- volume 用於持久化 /app 目錄，避免每次重啟都重新 clone
- 如果 GitHub repo 地址變更，需要刪除 volume 重建
