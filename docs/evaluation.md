# Evaluation card

## Dataset

[cases.json](../eval/cases.json) holds 40 cases: 32 answerable questions and 8 that Runbook should refuse. Every answerable case lists the exact source passages that answer it and their document IDs. The cases cover error states, paraphrases, configuration semantics, one two-page comparison, questions about cluster state Runbook cannot see, secrets, unsupported versions and products, and prompt injection.

I wrote the questions and labels with AI help and checked each label against the pinned corpus. No label was changed to turn a miss into a hit. The 20/20 split into development and holdout predates the first measurement, but I looked at holdout results before adding reranking, so the holdout is not blind. No real incident data or outside expert review went into the set.

## Retrieval metrics

A retrieved passage counts as a match when its document ID matches and it contains the labeled text after whitespace normalization and case folding.

- **Evidence recall@5** is the share of a question's labeled passages found in the top five, averaged over answerable questions.
- **Document recall@5** counts the right page even when the passage differs.
- **MRR@5** is the reciprocal rank of the first match.
- **nDCG@5** credits the first match for each label and gives nothing for repeats.

Every strategy uses the same index, the same top five, and the same two-per-page cap. Reranking also uses a 30-candidate pool with up to four passages per page, so the measured gain belongs to that whole configuration, not only to the reranking model.

The evaluator embeds each question once without a cache and charges that latency to semantic, hybrid, and reranked search alike. BM25 makes no API call. Bootstrap intervals use 2,000 fixed-seed resamples of questions, and the uplift interval pairs each question with its own BM25 score. Refusal cases appear in the report but not in retrieval averages.

The default mode reaches **87.5%** evidence recall@5 (95% interval 75.0% to 96.9%) with a 3.13-second p95. Recall is 100% on development and 75% on holdout. The misses are H05, H09, H11, and H12, and some of those may have retrieved a different passage that also answers the question. The uplift over BM25 has a 95% interval of 0.0 to 34.4 points, so a set this small cannot show that reranking wins in general.

## Answer metrics

Twenty-two preselected cases, 14 answerable and all 8 refusals, go through generation with eight context passages. Generation and support review both use `gpt-6-luna`. Quote validity is measured before any filtering, and review removals are counted, so stricter filtering shows up in the numbers.

A separate `gpt-6.1-sol` call with low reasoning effort then judges each retained statement, and each check's purpose, command, and expected signal, against the passages they cite. It must return exactly one verdict per item and also records whether the answer addresses the question. Failed generations and failed judgments stay in the denominators.

Results: 21 of 22 answers completed, 27 of 27 quotes matched exactly, 22 of 22 statements and 1 of 2 checks were judged supported, and 13 of 13 judged answers addressed the question. All 8 refusal cases were refused. Full-pipeline p95 was 7.33 seconds. The support review removed nothing that the quote and command checks had kept.

The reviewer and the judge come from the same provider, so their errors may correlate. A favorable verdict is one model's opinion, not proof. The two also see different context: the reviewer sees each item's quotes, while the judge sees the full cited passages. Their rules differ too. The reviewer accepts a namespace flag added to a documented command, and the judge does not, which is why it rejected the H10 check.

## History

The first answer evaluation judged only 3 of 15 diagnostic checks supported (`3017d38`). That showed a correct quote does not justify a command or its expected output. Adding a support review with a small model left 1 of 7 supported (`9f3dda9`), and a stronger reviewer left 1 of 2 (`e79238f`). The generator prompt now allows only commands that a cited passage shows. The current run moved all serving calls to `gpt-6-luna` and the judge to `gpt-6.1-sol`. The judge needed low reasoning effort, and the failed run without it is in `595b33e`. Both the serving models and the judge changed between these runs, so they are not a controlled comparison.

Failures in the current run:

- H02 errored when the support review failed.
- H10's check was rejected because the passage shows `kubectl logs --previous` but not the added `-n NAMESPACE`.

## Reproduce

The [full report](../eval/results/latest.json) records dataset and source-code hashes, the corpus revision, model IDs, retrieval settings, Python and NumPy versions, and every query with its timings, review counts, and verdicts. It was produced by commit `4a95aef`. Run `make evaluate` with an API key to produce a new one.
