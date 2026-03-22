# Canada Brief — Frontend

Next.js UI for the Canada Brief API (`GET /news`).

## Prerequisites

- Node.js 18+
- Backend running at `http://localhost:8000` (CORS already allows browser requests)

## Setup

```bash
cd frontend
npm install
cp .env.example .env.local   # optional
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Scripts

| Command       | Description        |
| ------------- | ------------------ |
| `npm run dev` | Development server |
| `npm run build` | Production build |
| `npm run start` | Run production server |
| `npm run lint` | ESLint |

## Environment

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | FastAPI base URL |

## Project structure

```
frontend/
├── app/
│   ├── globals.css      # Tailwind entry
│   ├── layout.tsx       # Root layout + fonts
│   └── page.tsx         # Home → NewsFeed
├── components/
│   ├── ArticleCard.tsx  # Feed row (thumb + text)
│   ├── categoryStyles.ts
│   ├── Filters.tsx      # Category pills + search
│   ├── Header.tsx
│   ├── LoadingSkeleton.tsx
│   └── NewsFeed.tsx     # Client: fetch, state, layout
├── lib/
│   ├── api.ts           # fetch /news
│   ├── filterArticles.ts
│   └── types.ts
├── package.json
├── postcss.config.mjs
├── tailwind.config.ts
├── tsconfig.json
└── next.config.ts
```

## Notes

- Article images use plain `<img>` so any remote `image_url` from the API works without extra image-domain config.
- Filters apply client-side to the loaded list (category + search).
