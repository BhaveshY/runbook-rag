# Evaluation card

## Dataset

[cases.json](../eval/cases.json) holds 40 cases: 32 answerable questions and 8 that Runbook should refuse. Every answerable case lists the exact source passages that answer it and their document IDs. The cases cover error states, paraphrases, configuration semantics, one two-page comparison, questions about cluster state Runbook cannot see, secrets, unsupported versions and products, and prompt injection.

I wrote the questions and labels with AI help and checked each label against the pinned corpus. I changed no label to turn a miss into a hit. I split the cases into 20 development and 20 holdout cases before the first measurement, but I looked at holdout results before adding reranking, so the holdout is not blind. No real incident data or outside expert review went into the set.

## Retrieval metrics

A retrieved passage counts as a match when its document ID matches and it contains the labeled text after whitespace normalization and case folding.

- **Evidence recall@5** is the share of a question's labeled passages found in the top five, averaged over answerable questions.
- **Document recall@5** counts the right page even when the passage differs.
- **MRR@5** is the reciprocal rank of the first match.
- **nDCG@5** credits the first match for each label and gives nothing for repeats.

Every strategy uses the same index, the same top five, and the same two-per-page cap. Reranking also uses a 30-candidate pool with up to four passages per page, so the measured gain belongs to that whole configuration, not only to the reranking model.

The evaluator embeds each question once without a cache and charges that latency to semantic, hybrid, and reranked search alike. BM25 makes no API call. Bootstrap intervals use 2,000 fixed-seed resamples of questions, and the gain interval pairs each question with its own BM25 score. Refusal cases appear in the report but not in retrieval averages.

The default mode reaches 84.4% evidence recall@5 (95% interval 71.9% to 96.9%) with a 4.75-second p95, measured through the Codex CLI. Recall is 93.8% on development and 75.0% on holdout. The misses are D05, H05, H08, H11, and H12. All five retrieved the right page but not the labeled passage, so some may have found another passage that answers the question. The gain over BM25 is 14.1 points, with a 95% interval of -3.1 to 31.3 points, so a set this small cannot show that reranking wins in general.

## Answer metrics

Twenty-two preselected cases, 14 answerable and all 8 refusals, go through generation with eight context passages. Generation and support review both use `gpt-5.6-luna` through the Codex CLI. The evaluator measures quote validity before any filtering and counts review removals, so stricter filtering lowers the reported numbers instead of hiding failures.

A separate `gpt-5.6-sol` call, with low reasoning effort, judges each retained statement against the passages it cites. For each check, the judge rates the purpose, the command, and the expected signal. The evaluator requires exactly one verdict per item. The judge also records whether the answer addresses the question. Failed generations and failed judgments stay in the denominators.

The current run produced these results.

- 22 of 22 answers completed.
- 32 of 35 quotes matched their passages exactly. The quote check removed the 2 statements and 1 check that cited the other 3.
- The support review removed 1 more check.
- The judge found 20 of 21 kept statements and 1 of 2 kept checks supported.
- 14 of 14 judged answers addressed the question.
- All 8 refusal cases were refused, and all 14 answerable cases were answered.
- Full-pipeline p95 was 14.0 seconds. Codex start-up and its own instructions account for much of that.

The reviewer and the judge come from the same provider, so their errors may correlate. A favorable verdict is one model's opinion, not proof. The two also see different context. The reviewer sees only each item's quotes. The judge sees the full cited passages. Their rules differ too. The reviewer accepts a namespace flag added to a documented command. The judge does not, so the judge rejected the D01 check.

## History

The first answer evaluation judged only 3 of 15 diagnostic checks supported (`3017d38`). That run showed that a correct quote does not justify a command or its expected output. A support review with `gpt-5.4-mini` left 1 of 7 supported (`9f3dda9`). Switching the reviewer to `gpt-5.5` left 1 of 2 (`e79238f`). The generator prompt now allows only commands that a cited passage shows. Next, I moved reranking, generation, and review to `gpt-6-luna` and the judge to `gpt-6.1-sol`. With no reasoning effort set, all 14 judge calls failed with HTTP 400 (`595b33e`), so the judge now runs with `RUNBOOK_JUDGE_REASONING=low`. The resulting API run (`4a95aef`) used OpenAI `text-embedding-3-small` embeddings and reached 87.5% reranked recall, 59.4% semantic recall, 22 of 22 supported statements, and a 7.3-second answer p95.

The current run replaces API embeddings with local `bge-small-en-v1.5` and runs every model call through the Codex CLI, so the project needs no API key. A ChatGPT login cannot use the `gpt-6` models through Codex, so serving moved to `gpt-5.6-luna` and the judge to `gpt-5.6-sol`. Semantic recall fell from 59.4% to 57.8% and reranked recall from 87.5% to 84.4%, while hybrid recall rose from 71.9% to 73.4%. Embeddings, models, and transport all changed at once, so none of these differences is a controlled comparison.

Rejected items in the current run:

- D01's check added `-n NAMESPACE` to `kubectl describe pod`, which the quoted passage does not show.
- H02's second statement added a claim about the scheduler that its quote did not make.

## Reproduce

The [full report](../eval/results/latest.json) records dataset and source-code hashes, the corpus revision, model IDs, retrieval settings, Python and NumPy versions, and every query with its timings, review counts, and verdicts. Commit `c575410` produced it. Run `make evaluate` while signed in to Codex to produce a new one.
