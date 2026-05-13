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

## 注意

房间和游戏状态目前全在内存里，重启后端数据就没了。
