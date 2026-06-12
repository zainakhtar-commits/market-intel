# Market Intel

A market-research **aggregation & intelligence** platform. It ingests from
multiple sources in near-real-time, links each item to the right company/ticker,
ranks it by how *material* it looks, scores sentiment, summarizes it, and pushes
it live to clients over a WebSocket — with links back to the original source.

> **What it is:** an information tool. It surfaces and explains what the sources
> are saying so a human can decide faster.
> **What it is not:** it does **not** tell you what to buy or sell, and makes no
> price predictions. That boundary is deliberate — it's what a real fintech tool
> actually ships.

## Why it's interesting (the engineering)

- **Multi-source ingestion** behind one pluggable adapter interface — add a
  source by writing one class; nothing downstream changes.
- **Near-real-time, producer/consumer core** — each source is an async producer
  feeding a shared queue; a consumer runs the pipeline and broadcasts. Slow
  sources never block fast ones.
- **Entity resolution** — EDGAR filings are resolved precisely via CIK →
  ticker using SEC's official mapping; news text via a lookup table (the seam
  where a real NER model goes).
- **Materiality ranking** — an 8-K (material-event filing) outranks a routine
  insider-ownership form; acquisition/guidance keywords bump the score.
- **Grounded summaries** — extractive baseline now; LLM-with-citations later.

## Sources

| Source | Status | Key needed |
|--------|--------|-----------|
| **SEC EDGAR** (latest filings) | ✅ real (Milestone 2) | none |
| Mock generator | ✅ built-in demo | none |
| News API / market data | 🔜 Milestone 3 | yes |

EDGAR is the first real source: it polls the public "latest filings" Atom feed,
dedupes entries, and resolves each filing's CIK to a ticker. It needs **no API
key** — only a descriptive `User-Agent` (already set; put your real email in
`app/sources/edgar.py` before deploying, per SEC's fair-access policy).

## Run it

```bash
cd market-intel
pip install -r requirements.txt
pytest -q                              # 11 tests
uvicorn app.api.main:app --reload      # live EDGAR + mock by default
```

Then:

```bash
curl "http://localhost:8000/health"
curl "http://localhost:8000/events?min_materiality=0.6&limit=10"
# live feed:  ws://localhost:8000/ws/events
```

Want a no-internet demo (mock only)? `ENABLE_EDGAR=false uvicorn app.api.main:app`.

## API

- `GET /health` — status, stored event count, active sources.
- `GET /events?ticker=&source=&min_materiality=&limit=` — query stored events.
- `WS /ws/events` — every newly processed event, pushed live.

## Roadmap

- **M1 ✅** Async event-driven core, pipeline, store, API, WebSocket, mock source.
- **M2 ✅** Real SEC EDGAR adapter with CIK→ticker entity resolution.
- **M3** Persistence (Postgres + vector DB) for semantic search & durability;
  add a news + market-data source.
- **M4** AI upgrade: LLM grounded summaries with citations, ML materiality ranker.
- **M5** React dashboard + public deploy (doubles as cloud-cert practice).

## Tests

`pytest -q` — covers the pipeline (sentiment, materiality ordering, entity
resolution), the store (dedupe, filtering, ordering), and the **EDGAR parser**
(form/company/CIK extraction + ticker resolution) against a captured real Atom
sample, so it runs offline.
