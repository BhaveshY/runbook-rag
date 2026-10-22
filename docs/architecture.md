# Architecture and decisions

## Offline index

`data/sources.json` pins 28 Kubernetes documentation paths to a full upstream Git commit. Ingestion caches raw Markdown, removes presentation markup, groups lines under section headings, and splits long sections at paragraph boundaries. Fenced code blocks stay together. Titles and headings travel with each passage; there are no overlapping sliding windows.

Each passage retains its source checksum, document, section, version, and immutable GitHub line link. OpenAI `text-embedding-3-small` supplies 768-dimensional embeddings, normalized into a float32 NumPy matrix. No model runs locally.

An exclusive ingestion lock prevents competing writers. Raw-cache writes and index activation use atomic replacement. New artifacts are staged before a content-addressed generation is activated. Startup verifies checksums, metadata, distinct passage IDs, model/dimension compatibility, matrix shape, and normalized finite vectors. Reuse performs the same validation; a damaged generation cannot be republished as a successful ingestion. Remove the damaged generation directory and rerun ingestion to rebuild it. A failure never advances the current-index pointer.

## Retrieval

BM25 uses `k1=1.2`, `b=0.75`, title + heading + passage tokens, camel-case splitting, and a small English stop-word list. Sparse postings contain precomputed term contributions. Semantic retrieval uses an exact matrix-vector product. With 773 vectors, a vector database would add an unnecessary operational dependency.

Hybrid retrieval merges each method's top 40 candidates using equal-weight reciprocal rank fusion: `score(chunk) = Σ 1 / (60 + rank)`.

The default quality path asks `gpt-6-luna` to order up to 30 hybrid candidates, with four passages per document in that candidate pool. Every final strategy caps output at two passages per document. Duplicate indices are removed while preserving order if enough distinct valid results remain. Invalid indices, insufficient results, provider errors, and the 12-second reranking deadline trigger a visible hybrid fallback. Repairs and fallbacks are recorded separately.

Query embeddings use a bounded 256-entry in-memory LRU cache keyed by a query hash. Generation results are not cached. The benchmark requests cold embeddings and charges the same measured embedding latency to each semantic strategy.

## Answer contract

`gpt-6-luna` receives the incident and eight retrieved passages. It returns a strict schema containing a status, title, atomic observations, optional diagnostic checks, follow-up questions, and uncertainty. Each observation and check cites source IDs and exact quotations.

The release path has three steps:

1. Verify that each cited ID belongs to the retrieved context and that each 15–450-character quote occurs in that passage after whitespace normalization. Remove an item if any of its quotations fails.
2. Apply a conservative command/flag allowlist. Reject shell syntax, mutation verbs, connection overrides, attached short flags, and secret resource aliases or comma lists. Commands are displayed only; the application never executes them.
3. Make a separate `gpt-6-luna` request to review each remaining observation and check against its own quoted evidence. A check's purpose, command, and expected signal all need support. The reviewer may remove items, but cannot invent replacements. If no observations survive, return insufficient evidence. If review fails or exceeds 10 seconds, return a readable provider error with the already-streamed evidence still available.

The review is a fallible model judgment, not a proof. Its latency, model usage, and removal counts are exposed in the trace. The evaluation uses a separate `gpt-6.1-sol` invocation with low reasoning effort to score retained observations and diagnostic checks. Because review and evaluation use the same provider, their errors can be correlated; this is not independent expert adjudication. Neither invocation can establish an unobserved cluster's actual state.

## HTTP and UI

FastAPI serves the API and buildless browser UI from one origin. `/api/diagnose/stream` emits status, evidence, then the validated and reviewed answer. Streaming failures use explicit error events. The browser detects incomplete streams, preserves evidence on cancellation, restores form controls, and distinguishes timeout from user cancellation.

Navigation follows browser history and deep links. Citations group multiple quotations from the same source under one button; inspection moves keyboard focus to the source and displays every attached quote. Markdown exports retain the incident, citations, exact quoted excerpts, immutable URLs, and model/corpus provenance. Dynamic content is rendered as text nodes.

Request bodies are limited to 16 KiB, including chunked requests, with a 10-second upload deadline. Incidents are limited to 4,000 characters. The service uses four concurrent request slots, request deadlines, bounded provider retries, optional bearer-token authentication, a socket-peer rate limit, and a process-wide paid-request budget. Untrusted forwarding headers cannot change the rate-limit identity. API responses are not cached; security headers include a same-origin CSP. Incident text and credentials are not written to application logs or persistent browser storage.

The Evaluation screen compares the report's source-code digest, dataset digest, corpus, and model settings with the running instance. Mismatches are visibly labeled as historical measurements. Missing and unreadable reports have distinct states. The evaluator and API share the same configurable report path.

## Distribution and limits

The Python wheel includes UI assets and the pinned source/evaluation definitions. An installed wheel uses the current working directory for mutable corpus and report files. Source checkouts use the project directory. `RUNBOOK_DATA_DIR` and `RUNBOOK_EVAL_REPORT` override these locations. The Docker image runs as an unprivileged user.

The quota and cache are per process; multiple replicas need shared quotas. Eight concurrent synthetic requests verify the slot limit and cancellation behavior, not production throughput or an availability SLA. The next quality milestone is independent domain review and a larger blind incident dataset. Additional sources or models require a new evaluation.
