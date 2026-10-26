# Architecture and decisions

## Ingestion builds the index offline

[data/sources.json](../data/sources.json) pins 28 documentation paths to one full `kubernetes/website` commit. `ingest` caches the raw Markdown, strips Hugo shortcodes and comments, and groups lines under their section headings. It splits a long section at the first blank line after 1,500 characters, or at 2,400 characters if no blank line comes first. It never splits inside a fenced code block. Each passage carries its page title and heading path, and passages do not overlap.

Each passage keeps its document ID, section, version, raw-source checksum, and a GitHub link to its exact lines. `BAAI/bge-small-en-v1.5` runs on the CPU through fastembed and produces 384-dimensional vectors, which `ingest` normalizes into a float32 NumPy matrix. A local model means anyone can rebuild the index without an account, and query embeddings cost nothing.

`ingest` names the index directory after a hash of its passages and embedding settings. `ingest` writes a new generation to a staging directory, renames it into place, and only then rewrites `index/current.json`. A file lock stops two ingestions from running at once. On startup and on reuse, the loader checks file checksums, passage metadata, unique IDs, embedding model and dimensions, matrix shape, and vector norms. If any check fails, `ingest` exits with an error and leaves `index/current.json` unchanged, and the server answers 503. To rebuild a damaged generation, delete its directory and run `ingest` again.

## Four retrieval modes share one corpus

BM25 uses `k1=1.2` and `b=0.75` over title, heading, and passage tokens, with camel-case splitting and a short stop-word list. Postings store precomputed term weights, so a query is a few array additions.

Semantic search is an exact matrix-vector product. A vector database would add a service to run, and at 1.1 MiB the matrix fits in memory.

Hybrid search fuses the top 40 results of each method with reciprocal rank fusion, `score = Σ 1 / (60 + rank)`. The constants live at the top of [retrieval.py](../runbook/retrieval.py), and the evaluation report reads the same values.

The default mode sends 30 hybrid candidates, at most four per page, to the serving model and asks for the 16 most useful in order. The server removes duplicate indices if enough distinct ones remain. If the reranker returns an invalid order or too few results, the request fails, or 12 seconds pass, the server falls back to hybrid order. The trace records duplicate removals and fallbacks separately. Every mode returns at most two passages per page.

A 256-entry LRU cache keyed by query hash holds query embeddings. The server never caches generated answers. The evaluator bypasses the cache and charges the same embedding latency to semantic, hybrid, and reranked search.

## Answers pass three checks before the user sees them

The serving model receives the incident and eight passages and returns a strict schema: a status, a title, up to four statements, up to three diagnostic checks, follow-up questions, and a limitation. Every statement and check cites a passage ID and an exact quote.

The server then runs three checks in order.

1. It confirms each quote is 15 to 450 characters and occurs in the cited passage after whitespace normalization. It removes any item with a failing quote.
2. It filters commands through a read-only `kubectl` allowlist. Shell syntax, mutating verbs, connection overrides, attached short flags, and any reference to secrets fail. The app displays commands and never runs them.
3. It sends the remaining items to a separate model request that sees only each item's own quotes. A check needs support for its purpose, its command, and its expected signal. The reviewer can remove items but not add them.

If no statement survives, the answer becomes a refusal. If the review fails or takes longer than 10 seconds, the user gets an error, and the evidence already streamed to the page stays visible.

The review is a model's judgment. In the current report it removed one check that the quote and command checks had kept. It can remove items, but it does not prove the remaining ones. The trace shows its latency, token use, and removals.

## Two backends serve model calls

`RUNBOOK_BACKEND=codex`, the default, runs each model call as `codex exec` with the request's JSON schema passed as `--output-schema`. The subprocess runs in an empty temporary directory with a read-only sandbox and ignores the user's Codex configuration, so the call answers from the prompt alone. Calls bill to the signed-in ChatGPT plan, which is what lets the project run without an API key. Each call carries about 16,000 tokens of Codex's own instructions and takes a few seconds to start.

`RUNBOOK_BACKEND=openai` sends the same requests to the Responses API with strict JSON schemas, `store: false`, and up to three attempts with backoff. Use it for deployments, where a server cannot hold a personal login.

Both clients expose the same `structured()` call, so retrieval, answer checks, and evaluation do not know which one runs.

## One origin serves the API and the UI

FastAPI serves the API and the static UI from one origin. `/api/diagnose/stream` sends server-sent events in a fixed order: status, evidence, status, then the answer or an error. The browser detects a stream that ends early, keeps the evidence when the user cancels, and tells a timeout apart from a cancellation.

The UI supports browser history and deep links. Citations from the same passage share one button, and opening one moves keyboard focus to the passage. Markdown export keeps the incident, every quote, the GitHub links, and the model and corpus IDs. The UI inserts all dynamic content as text nodes.

The server enforces these request limits.

- It rejects bodies over 16 KiB, including chunked uploads, and uploads that take longer than 10 seconds.
- It rejects incidents over 4,000 characters.
- It runs four requests at once. The rest wait.
- It allows each client 20 requests per minute, keyed on the socket address. `runbook serve` starts uvicorn with `proxy_headers=False`, so a forwarded header cannot change that address.
- It caps paid requests per day for the whole process.
- It requires a bearer token when `RUNBOOK_ACCESS_TOKEN` is set.

API responses carry `Cache-Control: no-store` and a same-origin content security policy. The server writes no incident text or credentials to logs or browser storage.

The Evaluation screen compares the report's source hash, dataset hash, corpus ID, and model settings with the running instance and labels any mismatch as historical.

## Packaging

The wheel bundles `web/`, `data/sources.json`, and `eval/cases.json`. An installed wheel keeps its index and report in the current directory. A source checkout uses the project directory. `RUNBOOK_DATA_DIR` overrides the index location, and `RUNBOOK_EVAL_REPORT` overrides the report path. The Docker image runs as UID 10001.

## Known limits

Quotas and caches live in process memory, so replicas need a shared quota service. The next quality step is review by someone who runs Kubernetes in production, and a larger blind set of real incidents. New sources or models need a new evaluation.
