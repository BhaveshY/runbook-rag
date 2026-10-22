# Architecture and decisions

## Offline index

`data/sources.json` pins 28 Kubernetes documentation paths to a full upstream Git commit. Ingestion caches the raw Markdown, removes presentation markup, groups lines under section headings, and splits long sections at paragraph boundaries. Fenced code blocks stay together. The chunker does not use overlapping sliding windows; it carries the document title and heading into the retrieval representation.

Each chunk has an ID derived from its document, line range, and normalized content. It also retains a raw-source SHA-256 and a GitHub URL with the pinned commit and original line range. The vector provider is `text-embedding-3-small`, with 768 dimensions. Vectors are normalized and persisted as a float32 NumPy array.

An ingestion lock prevents competing writers. New artifacts are written to a temporary generation directory, then moved into a content-addressed index. An atomic pointer replacement activates the generation. A failure during fetching or embedding cannot replace a working index. Startup verifies both the passage file and embedding file against the manifest. A model or dimensionality mismatch requires rebuilding.

## Retrieval

BM25 uses `k1=1.2`, `b=0.75`, title + heading + passage tokens, camel-case splitting, and a small English stop-word list. The sparse postings contain precomputed term contributions. Semantic retrieval uses an exact matrix-vector product over normalized vectors. At this corpus size, that operation is well below network latency and has no approximate-search recall loss.

Hybrid retrieval combines the top 40 results from each using equal-weight reciprocal rank fusion:

`score(chunk) = Σ 1 / (60 + rank)`

The fast path returns a diversified context immediately. The default quality path takes up to 30 fused candidates, allowing four passages per document during candidate collection, then asks `gpt-5.4-nano` for a constrained ordering. All final modes permit two passages per document. Reranking has a 12-second deadline; a timeout, invalid ordering, or provider error triggers a visible hybrid fallback.

Query embeddings have a bounded 256-entry in-memory LRU cache, keyed by a SHA-256 of the query. Generation results are not cached. The benchmark explicitly avoids query cache advantages.

## Answer contract

`gpt-5.4-mini` receives the incident and eight retrieved passages. It returns a strict schema with a status, short title, atomic claims, optional read-only checks, follow-up questions, and a limitation. Each claim and check has one or more source IDs and exact quotations.

The application checks that cited IDs belong to the supplied context and each 15–450-character quote exists in that source after whitespace normalization. A claim or check with an invalid quotation is removed. Displayed commands must pass a conservative syntax/verb filter. If no valid claims remain, the answer becomes an abstention.

**This is a provenance check, not an entailment proof.** The benchmark records an example where an accurate quote did not justify every part of its attached claim. The separate evaluation judge measures that remaining gap. Adding a production entailment verifier would introduce another model call and another fallible component; it is not silently presented as a solved problem.

## HTTP and UI

FastAPI serves the API and static UI from one origin. `/api/diagnose/stream` emits status, evidence, then a validated answer. Errors after streaming begins are explicit SSE events. The browser parses incremental UTF-8 frames, preserves evidence on cancellation/failure, and shows a readable error if the stream ends without an answer. Dynamic model output is rendered with DOM text nodes; inline code spans are constructed without HTML interpretation.

The API caps actual request bodies, including chunked requests, at 16 KiB and incidents at 4,000 characters. It uses four concurrent request slots, deadlines, bounded retry/backoff on transient upstream failures, optional instance-token authentication, a per-peer request limit, and a process-wide daily budget for paid requests. Forwarding headers are not trusted by default.

## Deliberate boundaries

- No cluster credentials, shell execution, or automatic remediation.
- No persistent incident history; evidence and response traces live in the requesting browser tab.
- No distributed database, queue, or orchestration framework at this scale.
- No claim of zero hallucinations, industry SOTA, production reliability, or load-test coverage.
- The default model names are configurable. A new model or source revision requires re-running the evaluation.

At a larger corpus size, the next step is measuring exact-search cost before introducing an approximate vector index. For multiple replicas, the first operational addition is a shared budget/rate-limit store. For evidence quality, the next step is independent domain review of labels and a larger genuinely blind evaluation set.
