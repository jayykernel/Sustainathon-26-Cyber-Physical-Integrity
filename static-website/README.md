# PhysiGuard — live battery integrity bench

The Three.js interface in this folder is the primary frontend. It connects to the
FastAPI backend for scenario discovery, session creation, streamed telemetry,
detector events, pause/resume, speed changes, and mid-run attack injection. The
scene, HUD, chart, and event log are driven by the same backend WebSocket frames.

## Run backend and frontend together

From the repository root on Windows PowerShell, install dependencies once, then
start both services. This setup uses `uv` for Python and supports either `bun`
or `npm` for the frontend:

```powershell
uv venv backend/.venv --python 3.12
uv pip install --python backend\.venv\Scripts\python.exe -r backend\requirements.lock
uv pip install --python backend\.venv\Scripts\python.exe --no-deps -e backend
cd static-website; bun install; cd ..      # or: cd static-website; npm ci; cd ..
backend\.venv\Scripts\python.exe scripts\dev.py           # auto: bun, then npm
backend\.venv\Scripts\python.exe scripts\dev.py --pm bun  # force bun
backend\.venv\Scripts\python.exe scripts\dev.py --pm npm  # force npm
```

With GNU Make installed, `make setup` and `make dev` are equivalent. Choose the
frontend package manager with `JS_PM` (default `bun`):

```powershell
make dev                 # bun
make dev JS_PM=npm       # npm
make setup JS_PM=npm     # npm ci instead of bun install
make test JS_PM=npm      # npm run test
```

Open <http://localhost:4173>. The Vite development server forwards `/api` and
WebSocket requests to FastAPI on port 8000. Choose a scenario, set a seed and
playback speed, then select **Start live run**. The attack selector can inject AT1
through AT6 during an active session.

For a production-style local server, build this frontend and start the backend:

```powershell
cd static-website; bun run build; cd ..     # or: npm run build
backend\.venv\Scripts\python.exe -m uvicorn physiguard.api.app:app --app-dir backend/src --host 127.0.0.1 --port 8000
```

On macOS or Linux, use `backend/.venv/bin/python` in the final command. FastAPI
serves `static-website/dist` at `/` when that build directory exists.

## Checks

```powershell
cd static-website; bun run test; bun run typecheck; bun run build
# npm equivalents:
cd static-website; npm run test; npm run typecheck; npm run build
```

The static site requires WebGL for its 3D scene. All telemetry and scenarios are
simulated by the backend; this prototype has no hardware connection or real vehicle
data.
