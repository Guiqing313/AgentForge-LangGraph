# C1 Docker 硬化

日期：2026-09-11 ｜ 状态：文件已硬化 ✅ ｜ 本地构建 ⏸（本机未装 Docker）｜ CI 构建：推送后校验

## 1. 决策：Ollama 与 embedding 留在宿主机
8GB 显存 + Windows GPU 直通成本高，因此只容器化 API 与前端；容器通过 host.docker.internal 访问：
- Ollama `http://host.docker.internal:11434/v1`
- bge-m3 embedding `http://host.docker.internal:11435`

## 2. 硬化内容
| 项 | 做法 |
|---|---|
| 非 root | API/前端镜像均创建 app 用户并 USER app |
| 依赖锁定 | API 安装 requirements-lock.txt |
| 健康检查 | API /health；前端 /_stcore/health；compose 用 service_healthy 控制顺序 |
| 密钥/数据隔离 | .dockerignore 排除 .env、venv、data、models、*.db、*.sqlite |
| 持久化 | ./data:/app/data；./docs/kb:/app/docs/kb:ro |
| 重启 | restart: unless-stopped |
| Linux 兼容 | extra_hosts: host.docker.internal:host-gateway |
| CI | ci.yml 新增 docker job：build API + build frontend + docker compose config |

## 3. 使用（需本机 Docker Desktop）
```powershell
cp .env.example .env
docker compose up --build
# API http://localhost:8000/docs ; UI http://localhost:8501
docker compose ps      # 两个服务应 healthy
docker compose down
```

## 4. 边界
- 镜像与 compose 已通过 CI docker job 校验（build API + build frontend + docker compose config）。
- 若 Ollama 仅监听 127.0.0.1，容器可能访问不到；可将 OLLAMA_HOST=0.0.0.0:11434 后重启 Ollama（可选排查）。
