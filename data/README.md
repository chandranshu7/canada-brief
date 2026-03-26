# Canada locations (`canadian_cities.json`)

- **Canonical copy:** `data/canadian_cities.json` (repo root).
- **Frontend bundle:** `frontend/data/canadian_cities.json` — keep in sync when you expand the list (or replace `frontend/data` with a symlink/copy step in CI).

Fields: `city`, `province`, `province_code`, `slug`, `lat`, `lon`, `population_rank`, `strong_local_coverage`.

Replace `canadian_cities.json` with a larger GeoNames/StatsCan export over time; the app and backend read the same shape.
