# Poker Friends

Desktop-first online Texas Hold'em for private friend rooms. This MVP uses a Python FastAPI backend with WebSockets and a React frontend.

## Run Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Run Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open the frontend URL shown by Vite. The backend defaults to `http://localhost:8000`.

## Deploy To Zeabur

Deploy this project as two services in the same Zeabur project.

### 1. Backend service

- Service root: `backend`
- Runtime: Python
- Install command:

```powershell
pip install -r requirements.txt
```

- Start command:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

- Environment variable:

```text
ALLOWED_ORIGINS=https://your-frontend-domain.zeabur.app
```

After deployment, verify:

- `https://your-backend-domain/health`

### 2. Frontend service

- Service root: `frontend`
- Runtime: Node.js
- Install command:

```powershell
npm install
```

- Build command:

```powershell
npm run build
```

- Output directory:

```text
dist
```

- Environment variables:

```text
VITE_API_BASE_URL=https://your-backend-domain.zeabur.app
VITE_WS_BASE_URL=wss://your-backend-domain.zeabur.app
```

### 3. Notes

- Frontend must use `https://...` for API and `wss://...` for WebSocket.
- If your Zeabur backend domain changes, update both frontend env vars and redeploy the frontend.
- This project currently stores room state in memory. Restarting the backend clears all rooms and games.
