# FunnelTrace UI

Next.js approval inbox, live trace panel and demo-lead launcher. It talks to the FastAPI backend.

```bash
npm install
cp .env.example .env.local   # only if the API is not on http://localhost:8000
npm run dev                  # http://localhost:3000
npm test                     # vitest, no network
```

The backend must allow the UI's origin (`FRONTEND_ORIGINS`, default `http://localhost:3000`).
