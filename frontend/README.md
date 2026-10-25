# SENTINEL-X — Dashboard (frontend)

Next.js 16 (App Router) + React 19 + TypeScript + Tailwind CSS v4 + Lucide.

This is the security-operations UI for the SENTINEL-X gateway. **See the project
[README](../README.md)** for full setup, and:

- `src/lib/api.ts` — typed API client (base URL: `NEXT_PUBLIC_API_URL`,
  default `http://127.0.0.1:8010`)
- `src/lib/usePolling.ts` — polling hook (2.5–6 s) used by every view
- `src/components/ui.tsx` — dark UI kit (cards, decision/risk badges, tables, empty states)
- `src/app/*` — Overview, Live Action Stream, Incidents (+ detail), Approvals,
  Scenario Lab, Evaluation

Views render **live backend responses only**; there is no static mock data layer.

```bash
npm install
NEXT_PUBLIC_API_URL=http://127.0.0.1:8010 npm run dev -- --port 3010
npm run lint    # 0 problems
npm run build   # production build
```
