# Canada Brief

**Canada Brief** is a portfolio-grade, AI-assisted news aggregator for Canadian and world headlines. It ingests multiple RSS sources, clusters related stories, ranks them, and serves short summaries through a FastAPI API and a Next.js reader UI.

## Features

- **Multi-source feeds** — Canadian and international RSS sources in one ranked feed  
- **AI summaries** — Optional OpenAI summaries; automatic local fallback without an API key  
- **Story clustering** — Groups overlapping coverage (e.g. same event, multiple outlets)  
- **Pagination** — `GET /news` with `page` / `page_size` (default **5** stories per page, capped server-side)  
- **Spotlight strip** — Top stories on the home page with a dedicated “More stories” list  

## Tech stack

| Layer    | Technology                          |
| -------- | ----------------------------------- |
| API      | **FastAPI**, **Uvicorn**            |
| Data     | **SQLite** (file `backend/news.db`) |
| ML       | **scikit-learn** (clustering)       |
| Summaries| **OpenAI** (optional) + local rules |
| UI       | **Next.js 15**, **Tailwind CSS**    |

## Repository layout

```
news_app/
├── backend/           # FastAPI app, SQLite, RSS ingest, clustering, summarization
│   ├── main.py
│   ├── database.py
│   ├── requirements.txt
│   └── services/
├── frontend/          # Next.js app
├── README.md
├── package.json       # npm run dev → frontend
└── .gitignore
```

## Prerequisites

- **Python 3.10+**
- **Node.js 18+**

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # optional: add OPENAI_API_KEY
uvicorn main:app --reload --port 8000
```

- API: <http://localhost:8000>  
- Docs: <http://localhost:8000/docs>  
- `GET /health` — health check  
- `GET /news` — JSON `{ "articles": [...], "top_stories": [...] }` + header `X-Total-Count`  
- `GET /news?refresh=true` — re-fetch RSS and rebuild the database  

Each article in JSON includes: `id`, `title`, `summary`, `source`, `link`, `published`, `category`, `region`, `image_url`, plus `sources`, `related_links`, and `cluster_id` when clustered.

## Frontend

From the **repository root**:

```bash
npm install --prefix frontend
npm run dev
```

Open <http://localhost:3000>. Set `NEXT_PUBLIC_API_URL` if the API is not at `http://localhost:8000`.

## OpenAI (optional)

1. Copy `backend/.env.example` → `backend/.env`  
2. Set `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`)  
3. Restart the backend  

If the key is missing or the API errors, summaries use a fast local fallback.

## Future improvements

- User accounts and saved articles  
- Push notifications or email digests  
- Stronger deduplication and entity linking  
- Docker Compose for one-command local runs  
- Automated tests (API + UI)  

## License

Use freely for learning and portfolio demos; respect the terms of the underlying news sources and OpenAI.
