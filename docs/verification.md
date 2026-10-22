# End-to-end verification

Verification was performed against the running FastAPI service with real OpenAI embeddings, reranking, generation, and evaluation requests. Browser interaction used Chromium through Playwright at 1440px desktop and 390px mobile widths. No unit-test or integration-test suite was added.

Machine-readable records:

- [HTTP scenarios](http-verification.json)
- [Browser scenarios](browser-verification.json)
- [Container verification](container-verification.json)
- [Full evaluation](../eval/results/latest.json)

The HTTP scenarios cover readiness, a self-hosted API reference, local BM25 retrieval, invalid input and retrieval modes, oversized declared and chunked bodies, unknown-secret abstention, peer rate limiting, instance-token authentication, provider unavailability, and the paid-request budget.

The browser scenarios cover a live reranked incident; evidence arriving before the validated answer; clickable citations with exact quotation and source expansion; copying a diagnostic command; downloading a Markdown note with source URLs; the four-mode evaluation table; fixed-holdout filtering and per-question inspection; the 28-document source library; abstention; cancellation; mobile overflow; and API documentation. Browser JavaScript exceptions were captured.

The unavailable-provider check points a separate running server at a closed local port. It observes the actual HTTP error and also confirms that BM25 remains usable. It does not mock application functions or replace the retrieval/generation pipeline.

Additional HTTP checks use an invalid reranker model to exercise real provider rejection and verify hybrid fallback, and a temporary corrupted copy of the embedding index to verify startup integrity enforcement. Repeated ingestion reused the same corpus generation without an embedding request.

The Docker image was built and started as the non-root `runbook` user. Container readiness, UI serving, BM25 retrieval, the unavailable-provider path, and its Docker health check were exercised. Live model calls were verified on the native service; container generation against OpenAI was not exercised.

Screenshots in this directory are captured from the working app. The benchmark evaluation uses 32 positive and 8 negative questions; 22 are exercised through generation and the claim-support judge. This verification does not measure a real Kubernetes cluster, concurrent production load, or long-term availability.
