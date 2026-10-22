# Evaluation card

## Dataset and provenance

[cases.json](../eval/cases.json) has 40 author-curated cases: 32 answerable questions and 8 unanswerable/adversarial requests. Every positive has one or more exact source-passage anchors and a document ID. Cases include errors, paraphrased symptoms, configuration semantics, a two-source comparison, out-of-scope domains, unavailable cluster state, unknown secrets, version mismatch, and prompt injection.

Labels were authored with AI assistance from the pinned documentation and validated for existence before scoring. The 20/20 development/holdout partition was fixed before the first run. Initial holdout scores were inspected before reranking was introduced, so **the partition is not a blinded generalization estimate**. No externally curated benchmark, human adjudication study, or real incident workload is claimed.

## Retrieval metrics

For each positive question, a retrieved passage matches a gold item only if it has the same document ID and contains the labeled text after whitespace normalization and case folding.

- **Evidence recall@5:** fraction of that question's gold evidence items recovered in its first five passages; macro-averaged over questions.
- **Document recall@5:** fraction of its labeled document IDs recovered, regardless of exact passage.
- **MRR@5:** reciprocal rank of the first matching passage, zero if none.
- **nDCG@5:** binary gain for first recovery of a gold evidence item; redundant retrieval of the same evidence has no additional gain. The current multi-source case has gold items in separate documents.
- **Latency:** serial cold-query embedding plus local ranking; reranking adds its own measured request latency. Embeddings are shared across methods for fair cost/latency accounting, not fetched independently under different provider conditions.
- **Uncertainty:** 2,000 bootstrap samples of question-level scores with a fixed seed. The uplift interval is a paired bootstrap against BM25.

Unanswerable cases have no relevant passages and are excluded from retrieval aggregates. Their retrieval output is still retained. Their important outcome is whether the answer pipeline abstains.

All strategies use the same index and a five-passage evaluation budget. Reranking uses 30 hybrid candidates with a four-per-document candidate cap; the final output uses the same two-per-document cap as the baselines. This changes both ordering and candidate diversity, so the observed improvement belongs to the combined reranked configuration, not exclusively to the model.

## Answer metrics

Twenty-two cases have `answer_eval: true`: 14 answerable and all 8 unanswerable cases. The full pipeline generates each answer using eight passages. This deliberately differs from the top-five retrieval measurement and is recorded in the report.

The exact-quote metric is measured **before** filtering so that invalid generations remain visible. A separate `gpt-5.5` request receives the question, answer, and cited source passages. It evaluates each retained claim for support and returns an indexed verdict and reason. The judge is instructed to score the evidence actually cited, rather than granting credit for an uncited fact elsewhere in the context.

The judge is an imperfect proxy. It has no ground-truth access to a cluster, and may share biases with the answer model. The support score applies to claim text; diagnostic check purposes and expected signals are not independently judged. Answer/abstention accuracy compares the returned status with the dataset label; it is not a factual answer-correctness metric.

Provider failures count as failed answer decisions rather than disappearing from the denominator. Judge failures are separately recorded. No external calls failed in the committed final run.

## Observed limits

The default retrieval configuration recovered every gold passage on development questions and 75% on the fixed holdout partition. Four holdout questions missed their exact evidence anchor: NoExecute eviction (H05), readiness/EndpointSlice behavior (H09), namespace-relative DNS (H11), and Service port mapping (H12). These are visible in the report. Some have other relevant passages, which explains the gap between exact-passage and document recall; the labels were left unchanged.

One of 36 retained claims failed the judge in H06. It said PDBs limit voluntary disruption and cannot prevent involuntary disruption, while its attached citation established only the latter. This illustrates why valid quote matching alone is insufficient to claim complete grounding.

The 95% paired interval for recall uplift over BM25 includes zero. The measured improvement is useful for this implementation, but the sample does not establish a general superiority claim. Network latency is from one environment and one run; it is not a throughput or availability SLA.

## Artifacts

- [Final four-mode run](../eval/results/latest.json)
- [Initial three-mode run](../eval/results/initial-hybrid.json)
- [Development reranking experiment](../eval/results/rerank-dev-experiment.json)
- [Pinned source manifest](../data/sources.json)

The raw report includes dataset and implementation digests, the immutable corpus ID, model identifiers, retrieval settings, Python/NumPy versions, BLAS thread configuration, per-query results, timings, and model verdicts. A rerun is expected to show some variation because remote model generation is nondeterministic.

The exact Python source snapshot used for the committed evaluation is Git commit `220b1b62e949f92330f72ce92979f91ab7e9126f`. Subsequent Python formatting only removed trailing blank lines; AST equivalence was verified. The raw report retains the original implementation digest. The supplied Git bundle preserves that snapshot and the complete project history.
