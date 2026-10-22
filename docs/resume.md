# Resume wording and interview notes

Use the committed measurements, with their scope:

> Built Runbook, a Kubernetes troubleshooting RAG application combining BM25, semantic search, reciprocal rank fusion, and LLM reranking over 773 versioned documentation passages; measured 87.5% evidence recall@5 versus 70.3% for BM25 on a 32-question curated benchmark, with 3.13-second p95 retrieval.

A second bullet if space permits:

> Implemented streamed evidence, exact-quote validation, command filtering, and separate citation-support review; evaluated 22 answers and verified API, browser, package, failure, and cancellation flows end to end without local models.

The word **curated** matters. These are development measurements with explicit limitations. Model-judged support is not factual accuracy; the production reviewer and evaluation judge can share biases.

Be prepared to explain:

1. Why BM25 outperformed semantic retrieval here, and why ranking fusion alone improved little.
2. How reranking trades latency for passage precision and how the document cap affects that tradeoff.
3. Why valid quotations did not justify many generated diagnostic checks, how measurement revealed it, and why a separate reviewer still cannot prove correctness.
4. Why exact vector search fits a 773-vector corpus.
5. Why a small non-blind dataset and wide confidence intervals prevent a SOTA claim.
6. How provider shape validation, index integrity, atomic activation, request budgets, and cancellation affect reliability.
7. Why actual distribution and browser verification uncovered issues that a successful local import would miss.
