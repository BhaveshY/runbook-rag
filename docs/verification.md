# Verification

## Automated test

[tests/test_e2e.py](../tests/test_e2e.py) runs on every push. It starts the real `ingest` and `serve` commands against a three-page fixture corpus, with a local HTTP server standing in for the OpenAI API, and checks:

- ingestion activates an index, a second run reuses it, and the server reports ready
- all four retrieval modes return passages, and BM25 ranks the obvious passage first
- the streamed diagnosis sends evidence before the answer, and its quote occurs in a retrieved passage
- the server rejects a missing bearer token, a too-short query, and an oversized body

It checks behavior, not model quality. The [evaluation card](evaluation.md) covers quality.

## Manual runs before 1.0

Before the automated test existed, scripted runs that were never committed checked the running application in more depth. The JSON records below hold every scenario and its result.

| Record | Passed |
|---|---:|
| [Live HTTP with hosted models](http-verification.json) | 16/16 |
| [Browser interaction](browser-verification.json) | 49/49 |
| [Failure and concurrency scenarios](reliability-verification.json) | 76/76 |
| [Accessibility scans and keyboard use](accessibility-verification.json) | 12/12 |
| [Installed wheel](package-verification.json) | 7/7 |
| [Container](container-verification.json) | 10/10 |

**Live models.** The live HTTP run used real OpenAI embeddings and `gpt-6-luna`. It covered all four retrieval modes, embedding cache hits, exact citations with line links, a refusal for a secrets question, input limits, security headers, and report compatibility.

**Browser.** Chromium covered the streamed request, evidence before the answer, citation focus, export, mobile layout, Back and Forward, deep links, cancellation, keyboard submission, clipboard, and 15 overflow checks across five widths. Intercepted responses covered truncated streams, auth errors, and failed readiness. No JavaScript exceptions occurred.

**Failures.** A controlled stand-in provider returned malformed JSON, bad vectors, retryable errors, quota errors, disconnects, incomplete generations, invalid rerank orders, invalid citations, unsafe commands, and review rejections and timeouts. Request checks covered tokens, budgets, rate limits, spoofed forwarding headers, oversized and chunked bodies, and the upload deadline. Eight concurrent requests confirmed the four-slot limit and that cancellation frees a slot. A missing index returned "Index unavailable; run python -m runbook ingest." and a corrupt index returned the index validation error.

**Accessibility.** axe-core 4.10.3 with WCAG 2.1 A and AA rules reported no violations on desktop and mobile after contrast and keyboard-scrolling fixes. An automated scan is not a full audit.

**Packaging.** The wheel installed into a clean virtual environment and served the UI, API reference, BM25 search, and report from a temporary directory. The Docker image ran as UID 10001 with a read-only root filesystem on a loopback-only port, and passed its health check. The container run made no OpenAI calls.
