# Evaluation card

## Dataset and provenance

[cases.json](../eval/cases.json) contains 40 author-curated cases: 32 answerable and 8 unsupported/adversarial requests. Each positive has exact source-passage anchors and document IDs. It covers errors, paraphrases, configuration semantics, a two-source comparison, unknown cluster state, secrets, unsupported domains/versions, and prompt injection.

Labels were authored with AI assistance, validated against the pinned corpus, and have not been changed to turn observed misses into hits. The 20/20 development/holdout partition predates the first measurement. Initial holdout results were inspected before reranking was introduced; **it is not a blinded generalization estimate**. There is no claim of a real incident workload or independent expert adjudication.

## Retrieval metrics

A match requires the gold document ID and labeled text after whitespace normalization and case folding. Evidence recall@5 is the fraction of each question's gold anchors recovered, macro-averaged over positive questions. Document recall@5 ignores which passage was recovered. MRR@5 measures first matching rank. nDCG@5 credits the first recovery of each evidence item, with no gain for redundant evidence; the current multi-source case has anchors in different documents.

All strategies use the same index, top-five output budget, and two-per-document output cap. Reranking adds a 30-candidate hybrid pool with four passages per document. Its measured improvement belongs to the combined configuration, not solely to the reranking model.

Query embeddings are requested once per case, without a cache, and their measured latency is charged equally to dense, hybrid, and reranked search. BM25 makes no API call. Reranking adds its measured API latency. Bootstrap intervals use 2,000 fixed-seed question-level resamples; uplift uses paired resampling against BM25. Negative cases stay in the report but are excluded from retrieval aggregates.

The current default achieves **87.5%** recall@5 (95% interval **75.0%–96.9%**), with **3.13 s** retrieval p95. Development recall is 100.0%; holdout recall is 75.0%. Exact-anchor misses: **H05, H09, H11, H12**. A different valid passage may still be scored as a miss. The paired uplift interval is 0.0–34.4 percentage points, so this small sample cannot establish broad superiority.

## Answer evaluation

Twenty-two preselected cases exercise generation: 14 positive and all 8 negative cases. They use eight context passages, deliberately differing from retrieval's top-five measurement. Generation uses `gpt-6-luna`; production support review uses `gpt-6-luna`. Exact-quote validity is measured before filtering. Review rejection counts are retained, so stricter filtering is visible.

A separate `gpt-6.1-sol` invocation with low reasoning effort receives the question, retained answer, and sources. It judges every observation and every check's purpose, command, and expected signal against their own cited passages. It must return exactly one indexed verdict per item. The judge also records whether the answer addresses the question. Generation and judge failures have explicit denominators rather than disappearing from scores.

Current measurements: 21/22 complete answers; 27/27 exact quotations; 22/22 supported observations; 1/2 supported diagnostic checks; 13/13 judged positive answers address the question. All 8 negative cases abstained. Full-pipeline p95 is 7.33 s. Support review removed 0 observations and 0 checks after quote/command filtering. A check may be omitted even when an explanation is supported.

**Review and evaluation use different models from the same provider. Their errors can still be correlated.** A favorable score is a model judgment, not proof of truth. The reviewer sees each item's exact quotes; the evaluator sees the cited passages. Different context and nondeterminism can produce different decisions. The release reviewer explicitly allows example-name substitution and a namespace flag; the stricter evaluation judge rejected a check for an undocumented namespace flag. That rubric difference remains visible in the reported score. Status agreement measures answering versus abstention, not complete factual correctness. Latency is a single serial run; it is not a production SLA.

## What changed after measurement

The first evaluation of diagnostic checks found only 3/15 supported checks (`3017d38`). A small-model production review still left only 1/7 supported checks in the next run (`9f3dda9`). A stronger reviewer left 1/2 supported checks (`e79238f`). These runs remain in Git history. They exposed the distinction between a correct quotation and a justified command or expected result. The generator prompt requires explicitly documented procedures. The current run moves all serving model calls to GPT-6 Luna and the separate evaluator to GPT-6.1 Sol. Its judge needed low reasoning effort; the failed compatibility run is retained in `595b33e`. Because both serving models and the evaluator changed, support scores across these versions are not a controlled model comparison. These are exploratory iterations on a known dataset, not independent experiments.

Failures and rejected items in the current evaluation:

- H02 / request failure: The evidence review could not complete. Retrieved passages remain available; please retry.
- H10 / checks: The passage supports the purpose, expected log output, and command through --previous, but does not document the added -n NAMESPACE option.

## Artifacts

- [Current full report](../eval/results/latest.json)
- [Pinned source manifest](../data/sources.json)
- [End-to-end verification](verification.md)

The report records dataset and implementation digests, corpus/revision, model identifiers, retrieval settings, Python/NumPy versions, BLAS threads, every query, timing, review count, and judge verdict. Its Python source snapshot is commit `4a95aef03bd9af351c5a42ef1609f74fc113a593`. Subsequent documentation or browser-only changes do not alter that Python digest. The supplied Git bundle preserves prior experiments and source snapshots.
