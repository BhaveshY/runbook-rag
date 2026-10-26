# Architecture and decisions

## Build the index offline

[data/sources.json](../data/sources.json) pins 28 documentation paths to one full `kubernetes/website` commit. `ingest` caches the raw Markdown, strips Hugo shortcodes and comments, and groups lines under their section headings. It splits a long section at the first blank line after 1,500 characters, or at 2,400 characters if no blank line comes first. It never splits inside a fenced code block. Each passage carries its page title and heading path, and windows do not overlap.

Each passage keeps its document ID, section, version, raw-source checksum, and a GitHub link to its exact lines. OpenAI `text-embedding-3-small` produces 768-dimensional vectors, which `ingest` normalizes into a float32 NumPy matrix.

The index directory is named by a hash of its passages and embedding settings. `ingest` writes a new generation to a staging directory, renames it into place, and only then rewrites `index/current.json`. A file lock stops two ingestions from running at once. On startup and on reuse, the loader checks file checksums, passage metadata, unique IDs, embedding model and dimensions, matrix shape, and vector norms. A damaged generation fails loudly and never becomes current. To rebuild it, delete its directory and run `ingest` again.

## Retrieve with four strategies

BM25 uses `k1=1.2` and `b=0.75` over title, heading, and passage tokens, with camel-case splitting and a short stop-word list. Postings store precomputed term weights, so a query is a few array additions.

Semantic search is an exact matrix-vector product. A vector database would add a service to run for a 2.3 MiB matrix.

Hybrid search fuses the top 40 results of each method with reciprocal rank fusion, `score = Σ 1 / (60 + rank)`. The constants live at the top of [retrieval.py](../runbook/retrieval.py), and the evaluation report reads the same values.

The default mode sends 30 hybrid candidates, at most four per page, to `gpt-6-luna` and asks for the 16 most useful in order. The server removes duplicate indices if enough distinct ones remain. An invalid order, too few results, a provider error, or the 12-second deadline makes it fall back to hybrid order. The trace records repairs and fallbacks separately. Every mode returns at most two passages per page.

A 256-entry LRU cache keyed by query hash holds query embeddings. The server never caches generated answers. The evaluator bypasses the cache and charges the same embedding latency to each semantic mode.

## Check every answer before release

`gpt-6-luna` receives the incident and eight passages and returns a strict schema: a status, a title, up to four statements, up to three diagnostic checks, follow-up questions, and a limitation. Every statement and check cites a passage ID and an exact quote.

The server then runs three checks in order.

1. It confirms each quote is 15 to 450 characters and occurs in the cited passage after whitespace normalization. An item with any failing quote is removed.
2. It filters commands through a read-only `kubectl` allowlist. Shell syntax, mutating verbs, connection overrides, attached short flags, and any reference to secrets fail. The app displays commands and never runs them.
3. It sends the remaining items to a separate `gpt-6-luna` request that sees only each item's own quotes. A check needs support for its purpose, its command, and its expected signal. The reviewer can remove items but not add them.

If no statement survives, the answer becomes a refusal. If the review fails or takes longer than 10 seconds, the user gets an error, and the evidence already streamed to the page stays visible.

The review is a model's judgment. It lowers the rate of unsupported statements but does not prove any of them. The trace shows its latency, token use, and removals.

## Serve the API and UI

FastAPI serves the API and the static UI from one origin. `/api/diagnose/stream` sends server-sent events in a fixed order: status, evidence, status, then the answer or an error. The browser detects a stream that ends early, keeps the evidence when the user cancels, and tells a timeout apart from a cancellation.

The UI supports browser history and deep links. Citations from the same passage share one button, and opening one moves keyboard focus to the passage. Markdown export keeps the incident, every quote, the GitHub links, and the model and corpus IDs. The UI inserts all dynamic content as text nodes.

Request limits:

- Bodies are capped at 16 KiB, including chunked uploads, with a 10-second upload deadline.
- Incidents are capped at 4,000 characters.
- Four requests run at once. The rest wait.
- Each client gets 20 requests per minute, keyed on the socket address so forwarded headers cannot change it.
- A daily budget caps paid requests for the whole process.
- An optional bearer token protects the instance.

API responses carry `Cache-Control: no-store` and a same-origin content security policy. The server writes no incident text or credentials to logs or browser storage.

The Evaluation screen compares the report's source hash, dataset hash, corpus ID, and model settings with the running instance and labels any mismatch as historical.

## Package and limits

The wheel bundles the UI and the pinned source and evaluation definitions. An installed wheel keeps its index and report in the current directory. A source checkout uses the project directory. `RUNBOOK_DATA_DIR` and `RUNBOOK_EVAL_REPORT` override both. The Docker image runs as UID 10001.

Quotas and caches live in process memory, so replicas need a shared quota service. The next quality step is review by someone who runs Kubernetes in production, and a larger blind set of real incidents. New sources or models need a new evaluation.
