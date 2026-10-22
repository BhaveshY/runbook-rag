# Resume wording and interview notes

A defensible bullet, using the committed measurement rather than a target:

> Built Runbook, a Kubernetes RAG troubleshooting tool with BM25–semantic retrieval, reciprocal rank fusion, and LLM reranking over 773 versioned documentation passages; measured 87.5% evidence recall@5 versus 70.3% for BM25 on a 32-question curated benchmark, with 1.71-second p95 retrieval.

A second bullet if space permits:

> Implemented streamed evidence, source-linked diagnostics, exact-quote validation, and bounded provider fallback; verified live API and browser flows and evaluated 22 generated answers, with 35/36 claims supported by a separate model judge.

The word **curated** matters. These are small development measurements with explicit limitations, not production customer results or an independently certified model ranking. The 35/36 score is model-judged cited support, not factual accuracy.

Be prepared to explain:

1. Why BM25 beat semantic retrieval on this dataset, and why combining rankings alone barely improved recall.
2. How the reranking stage trades approximately one extra second for passage-level precision, and why a result cap per document affects that tradeoff.
3. Why a valid verbatim quote can still fail to support every assertion in a claim. H06 in the report is a concrete example.
4. Why exact vector search is appropriate for a 773-vector corpus, and when its operational tradeoff would change.
5. Why the bootstrap interval and the non-blind holdout prevent a broad superiority claim.
6. How immutable source revisions, checksums, atomic index activation, and recorded model/configuration metadata make regressions diagnosable.
