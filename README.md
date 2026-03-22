# Canada Brief

**Canada Brief** is a minimal, fast news app focused on **Canadian headlines**. It presents **one story at a time**—a calm, readable experience without endless feeds or clutter. The stack is built for clarity and performance: a FastAPI backend, a Next.js reader, and content filtered and ranked for relevance.

## Live demo

**[canada-brief.vercel.app](https://canada-brief.vercel.app/)**

## Features

- **One story at a time** — Full-screen reading, one headline per view; simple **Previous** / **Next** navigation  
- **Clean UI** — Distraction-free layout built for focus  
- **Fast API** — **FastAPI** backend with efficient pagination and caching-friendly reads  
- **Smart ordering** — Stories ranked after ingest so the feed stays coherent  
- **Lazy summaries** — Summaries generated on demand to keep ingest fast and costs predictable  
- **Canada-focused** — Ingest and filtering emphasize Canadian sources and topics  

## Tech stack

| Layer      | Technology                                      |
| ---------- | ----------------------------------------------- |
| Frontend   | **Next.js**, **TypeScript**, **Tailwind CSS**   |
| Backend    | **FastAPI** (Python), **Uvicorn**               |
| Database   | **PostgreSQL** (production); SQLite optional locally |
| Clustering | **scikit-learn**                                |
| Summaries  | **OpenAI** (optional) + fast local fallback     |
| Deployment | **Vercel** (frontend), **Render** (backend)     |

## How it works

1. **Fetch** — Canadian RSS feeds are pulled and normalized.  
2. **Cluster** — Related pieces are grouped so readers see one clear story.  
3. **Rank** — Stories are scored for feed order.  
4. **Serve** — The API returns paginated JSON for the app.  
5. **Summarize lazily** — Full summaries are filled in when stories are viewed, not all at ingest time.  

## Repository layout

```
news_app/
├── backend/           # FastAPI, database, RSS ingest, clustering, summaries
│   ├── main.py
│   ├── database.py
│   ├── requirements.txt
│   └── services/
├── frontend/          # Next.js app
├── README.md
└── .gitignore
```

## Prerequisites

- **Python 3.10+**
- **Node.js 18+**

## Backend (local)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # optional: DATABASE_URL, OPENAI_API_KEY
uvicorn main:app --reload --port 8000
```

- API: <http://localhost:8000>  
- Docs: <http://localhost:8000/docs>  
- `GET /health` — health check  
- `GET /news` — JSON feed with articles and pagination metadata  

Set `DATABASE_URL` for PostgreSQL; otherwise the app can use a local SQLite file for development.

## Frontend (local)

From the **repository root**:

```bash
npm install --prefix frontend
npm run dev
```

Open <http://localhost:3000>. Point `NEXT_PUBLIC_API_URL` at your API if it is not `http://localhost:8000`.

## OpenAI (optional)

1. Copy `backend/.env.example` → `backend/.env`  
2. Set `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`)  
3. Restart the backend  

If the key is missing or the API errors, summaries use a local fallback.

## Future improvements

- Faster initial load  
- Better story personalization  
- UI polish and animations  
- Docker Compose for one-command local runs  
- Automated tests (API + UI)  

## License

Use freely for learning and portfolio demos; respect the terms of the underlying news sources and OpenAI.
