# Architecture

This is the document an interviewer will probe. It explains *why* the pieces are
shaped the way they are — the decisions, not just the boxes.

## The flow

```
 ┌──────────┐   ┌──────────┐         producers
 │  EDGAR   │   │   Mock   │   ...   (one async task each)
 └────┬─────┘   └────┬─────┘
      │  Event       │  Event
      └──────┬───────┘
             ▼
      ┌─────────────┐   bounded asyncio.Queue (back-pressure)
      │    Queue    │
      └──────┬──────┘
             ▼  single consumer
   ┌──────────────────────┐
   │      Pipeline        │  entity → sentiment → materiality → summary
   └──────────┬───────────┘
              ▼
   ┌─────────────────┐        ┌──────────────────────┐
   │   EventStore    │──────▶ │  Broadcast to WS subs │
   │ (dedupe+query)  │        └──────────────────────┘
   └─────────────────┘
              ▲
        GET /events (REST)
```

## Key decisions

**One normalized `Event` schema (`app/schema.py`).** Sources are wildly
different — SEC filings, news articles, market ticks — but everything downstream
speaks one shape. This is what makes sources pluggable and the pipeline generic.

**Sources are async generators (`app/sources/base.py`).** A source is "a thing
that yields Events." The engine `async for`s over each one concurrently. Adding a
source = writing one class; the engine, pipeline, store, and API are untouched.
This is the open/closed principle doing real work.

**Producer/consumer over a bounded queue (`app/engine.py`).** Near-real-time
means a slow source (EDGAR polling every 30s) must not stall a fast one, and a
burst of filings must not overwhelm processing. A bounded `asyncio.Queue`
decouples ingestion from processing and gives natural back-pressure.

**Dedupe at the store boundary (`app/store.py`).** EDGAR re-serves the same
entries every poll; the store is the single chokepoint that decides "is this
new?" — so no source has to track global state, and we only broadcast genuinely
new events.

**Honest baselines, swappable seams.** Sentiment (lexicon), materiality (rules),
and summary (extractive) are deliberately simple but *complete* — the pipeline
runs and is testable today. Each lives behind a stable function signature, so
Milestone 4 swaps in an ML/LLM version with no ripple. Shipping a working
baseline first, then upgrading, is the opposite of the common student mistake of
a half-built "smart" component that never runs.

## Entity resolution: the genuinely hard part

Mapping a messy mention to the right company is a real NLP problem. We split it
by source confidence:

- **EDGAR** carries a **CIK** (SEC's permanent company id). We map CIK → ticker
  using SEC's official `company_tickers.json`. This is *exact*, not fuzzy — the
  right way to resolve filings.
- **News** has no CIK, so we fall back to a name→ticker lookup. This is the seam
  where production would add NER + fuzzy matching + disambiguation (e.g. "Apple"
  the company vs. the fruit, ticker collisions, subsidiaries).

The pipeline trusts a source-provided ticker first and only falls back to text
lookup — precision where we can get it, recall where we can't.

## Materiality ranking

The question is "how likely is this to actually matter?" Filings get a base
weight by **form type** — an `8-K` exists specifically to disclose material
events, so it outranks a routine `Form 4` insider transaction. Keywords
(acquisition, guidance, bankruptcy…) and sharp sentiment bump the score. It's
rules today; Milestone 4 replaces `materiality.score()` with a learned ranker
trained on, e.g., subsequent price/volume moves — same signature.

## What's deliberately deferred

- **Persistence** — in-memory `deque` now; Postgres + a vector DB in M3, which
  also unlocks semantic search ("every company that flagged supply-chain risk").
- **Grounded LLM summaries with citations** — M4; the summary seam already exists.
- **Frontend + deploy** — M5; the REST + WS API is already the contract a React
  dashboard would consume.

## Testing strategy

Tests run **offline and fast** (~0.15s). The EDGAR adapter is tested by feeding
its parser a captured real Atom payload, so we verify form/company/CIK extraction
and CIK→ticker resolution without hitting the network — the network call itself
is thin and isolated in `events()`.
