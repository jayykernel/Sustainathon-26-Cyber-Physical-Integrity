# PhysiGuard — live battery integrity bench

The Three.js interface in this folder is the primary frontend. It connects to the
FastAPI backend for scenario discovery, session creation, streamed telemetry,
detector events, pause/resume, speed changes, and mid-run attack injection. The
scene, HUD, chart, and event log are driven by the same backend WebSocket frames.

## Run backend and frontend together

From the repository root on Windows PowerShell, install dependencies once, then
start both services:

```powershell
python -m venv backend/.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock
backend\.venv\Scripts\python.exe -m pip install --no-deps -e backend
npm ci --prefix static-website
backend\.venv\Scripts\python.exe scripts\dev.py
```

With GNU Make installed, `make setup` and `make dev` are equivalent. Open
<http://localhost:4173>. The Vite development server forwards `/api` and
WebSocket requests to FastAPI on port 8000. Choose a scenario, set a seed and
playback speed, then select **Start live run**. The attack selector can inject AT1
through AT6 during an active session.

For a production-style local server, build this frontend and start the backend:

```bash
npm ci --prefix static-website
npm --prefix static-website run build
backend/.venv/Scripts/python.exe -m uvicorn physiguard.api.app:app --app-dir backend/src --host 127.0.0.1 --port 8000
```

On macOS or Linux, use `backend/.venv/bin/python` in the final command. FastAPI
serves `static-website/dist` at `/` when that build directory exists.

## Checks

```bash
npm --prefix static-website test
npm --prefix static-website run typecheck
npm --prefix static-website run build
```

The static site requires WebGL for its 3D scene. All telemetry and scenarios are
simulated by the backend; this prototype has no hardware connection or real vehicle
data.
