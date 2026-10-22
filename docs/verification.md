# End-to-end verification

**170/170 recorded checks passed.** These are individual scenarios and assertions against running applications, not 170 independent workloads. Temporary E2E drivers use real HTTP, Chromium, the installed distribution, and Docker. No unit/integration test suite, test framework, or test files were added to the repository.

| Recorded checks | Passed |
|---|---:|
| [Live HTTP and Luna models](http-verification.json) | 16/16 |
| [Browser interaction](browser-verification.json) | 49/49 |
| [HTTP failure and concurrency scenarios](reliability-verification.json) | 76/76 |
| [Accessibility scans and keyboard interactions](accessibility-verification.json) | 12/12 |
| [Installed wheel](package-verification.json) | 7/7 |
| [Container](container-verification.json) | 10/10 |

## Live hosted models

The final HTTP checks use real OpenAI embeddings and GPT-6 Luna for reranking, generation, and support review. They exercise all four retrieval modes, repeated-query embedding caching, exact citations and immutable source links, unknown-secret abstention, input limits, security headers, and report compatibility with the running code and models.

The browser record contains 38 checks from before the model migration plus a fresh Luna pass. That pass verifies the complete streaming request, actual model IDs in the trace, evidence arriving before the reviewed answer, citation focus, export provenance, mobile layout, and the current benchmark. The original interaction pass also covers Back/Forward and deep links, cancellation and recovery, keyboard submission, clipboard, holdout filtering, and 15 overflow combinations across five widths and three screens. Three explicitly intercepted browser responses cover truncated streams, authorization errors, and failed readiness requests. Two additional replays check that empty optional text leaves no blank notice or export section. No browser JavaScript exceptions were observed.

The [full quality evaluation](../eval/results/latest.json) is separate from these functional checks: 40 retrieval cases and 22 answer cases with a source-conditioned GPT-6.1 Sol judge. It records failures and denominators. E2E success does not establish factual accuracy; the [evaluation card](evaluation.md) describes quality and dataset limitations.

## Controlled failure scenarios

The 76 reliability checks run the real application against a controlled external HTTP provider. They do not replace application functions and do not claim to measure hosted-model quality. Scenarios include malformed JSON and vectors, nonfinite/zero embeddings, retries, quota responses, disconnects, incomplete generation, reranking fallback and duplicate repair, invalid citations, command filtering, and support-review rejection or failure.

Request checks cover bearer authentication, budgets, peer rate limits, spoofed forwarding headers, declared/chunked oversized bodies, and the 10-second upload deadline. Corrupt or missing indexes fail clearly; cache reuse cannot silently reactivate damaged artifacts. Missing/unreadable reports have explicit responses and historical measurements are labeled.

Eight concurrent synthetic requests verify the four-request slot limit while readiness remains responsive. Cancellation releases slots, including during support review. A deliberately slow reviewer exercises its 10-second deadline. This is bounded concurrency verification, not a production throughput measurement or availability SLA.

## Accessibility and distribution

Chromium ran axe-core 4.10.3 with WCAG 2 A/AA and 2.1 AA tags on desktop and mobile screens, including the API reference. Scans reported no violations after contrast and scroll-region keyboard fixes. The answer fixture replays a measured answer and adds a second real source quote to exercise grouped citations and export. CSP bypass was enabled only to inject the scanner. Automated scans are not a complete accessibility audit.

The built wheel was installed with dependencies in a separate virtual environment and launched from a temporary working directory. Checks verify the installed import, CLI, bundled source manifest, index reuse, UI assets, API reference, BM25, and workspace report loading.

A fresh Docker image was launched as UID 10001 with a read-only root filesystem, dropped capabilities, and a loopback-only host port. Its readiness, UI, local retrieval, missing-provider error, matching benchmark provenance, and Docker health check passed. Hosted model requests were verified on the native service; this container run did not call OpenAI.

Screenshots show the working application after the Luna switch. The diagnostic and mobile captures replay the actual live response to omit a transient clipboard notice. Runtime data and temporary drivers are excluded from the source checkout. The downloadable ZIP additionally includes the checksummed prebuilt index, while the Git bundle preserves earlier measurements and their source snapshots.
