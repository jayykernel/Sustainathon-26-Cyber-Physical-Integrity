# PhysiGuard — cyber-physical integrity bench

PhysiGuard is a simulated battery cybersecurity prototype. The primary user
interface is the Three.js live scene in [`static-website`](static-website/README.md),
connected to the FastAPI simulation backend.

## Start the application

Requirements: Python 3.11+ and Node.js 18+.

```powershell
python -m venv backend/.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock
backend\.venv\Scripts\python.exe -m pip install --no-deps -e backend
npm ci --prefix static-website
backend\.venv\Scripts\python.exe scripts\dev.py
```

With GNU Make installed, `make setup` followed by `make dev` does the same. Open
<http://localhost:4173>. Select a scenario, choose a seed and playback speed, then
start a live run. The controls also support pause/resume and attack injection.

To build and run the backend-hosted production frontend:

```bash
npm ci --prefix static-website
npm --prefix static-website run build
backend/.venv/Scripts/python.exe -m uvicorn physiguard.api.app:app --app-dir backend/src --host 127.0.0.1 --port 8000
```

Use `backend/.venv/bin/python` on macOS or Linux. FastAPI serves the built
`static-website/dist` at `/`. The API health endpoint is `/api/health`.

## Verify

```bash
make check
```

The separate `frontend` folder is not used by the normal launcher or backend
static hosting. All demonstrations are simulated and do not establish real-cell
safety or deployment readiness.
