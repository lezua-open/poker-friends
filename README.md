# Poker Friends

朋友间在线德州扑克，桌面端优先。前端 React + 后端 FastAPI + WebSocket 实时通信。

## 本地运行

**后端**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**前端**

```powershell
cd frontend
npm install
npm run dev
```

打开 Vite 输出的地址即可，前端默认连接 `http://localhost:8000`。

## 部署到 Zeabur

项目使用 Docker 单服务方案，后端同时托管前端静态文件，无需处理跨域问题。

1. 将项目推送到 GitHub
2. 在 Zeabur 控制台新建项目，导入该仓库
3. Zeabur 自动检测到项目根目录的 `Dockerfile`，构建并部署
4. 部署完成后，通过 Zeabur 分配的域名即可访问

Dockerfile 是多阶段构建：先用 Node.js 构建前端，再将产物复制到 Python 容器中由 FastAPI 托管。端口会自动适配 Zeabur 的 `PORT` 环境变量。

## 注意

房间和游戏状态目前全在内存里，重启后端数据就没了。
