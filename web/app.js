const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = {
  result: null,
  sources: [],
  controller: null,
  timer: null,
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function link(text, url, className = "") {
  const node = element("a", className, text);
  node.href = url;
  node.target = "_blank";
  node.rel = "noopener noreferrer";
  return node;
}
function inlineCode(parent, text) {
  const parts = text.split(/(`[^`]+`)/g);
  for (const part of parts)
    parent.append(
      part.startsWith("`") && part.endsWith("`")
        ? element("code", "", part.slice(1, -1))
        : document.createTextNode(part),
    );
}
function notify(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  setTimeout(() => {
    $("#toast").hidden = true;
  }, 2600);
}
function setView(view) {
  if (!["investigate", "benchmark", "sources"].includes(view))
    view = "investigate";
  for (const node of $$(".view")) node.hidden = node.id !== `view-${view}`;
  for (const node of $$(".nav-item")) {
    node.classList.toggle("active", node.dataset.view === view);
    if (node.dataset.view === view) node.setAttribute("aria-current", "page");
    else node.removeAttribute("aria-current");
  }
  $("#page-label").textContent = {
    investigate: "Investigate",
    benchmark: "Evaluation",
    sources: "Source library",
  }[view];
  document.title = `${$("#page-label").textContent} | Runbook`;
  if (view === "benchmark") loadBenchmark();
}
window.addEventListener("hashchange", () => setView(location.hash.slice(1)));
$$(".nav-item").forEach((button) =>
  button.addEventListener("click", () => {
    const hash =
      button.dataset.view === "investigate" ? "" : `#${button.dataset.view}`;
    if (location.hash === hash) setView(button.dataset.view);
    else location.hash = hash;
  }),
);
$$("[data-query]").forEach((button) =>
  button.addEventListener("click", () => {
    $("#incident").value = button.dataset.query;
    $("#incident").focus();
  }),
);
$("#incident").addEventListener("keydown", (event) => {
  if (
    (event.metaKey || event.ctrlKey) &&
    event.key === "Enter" &&
    !state.controller
  )
    $("#incident-form").requestSubmit();
});

function renderEvidence(sources) {
  state.sources = sources;
  $("#evidence-count").textContent = String(sources.length);
  $("#evidence-placeholder").hidden = sources.length > 0;
  const list = $("#evidence-list");
  list.replaceChildren();
  sources.forEach((source, index) => {
    const card = element("article", "source-card");
    card.id = `source-${index}`;
    card.tabIndex = -1;
    const top = element("div", "source-top");
    top.append(
      element("span", "source-number", String(index + 1).padStart(2, "0")),
      element("h4", "", source.title),
    );
    const details = element("details");
    const passage = element("pre", "", source.text);
    passage.tabIndex = 0;
    passage.setAttribute("aria-label", `${source.title} source passage`);
    details.append(element("summary", "", "Read passage"), passage);
    card.append(
      top,
      element("p", "source-heading", source.heading),
      details,
      link(
        `Original · lines ${source.line_start}–${source.line_end}`,
        source.source_url,
        "source-link",
      ),
    );
    list.append(card);
  });
}

function citations(parent, items) {
  const grouped = new Map();
  for (const citation of items) {
    if (!grouped.has(citation.source_id))
      grouped.set(citation.source_id, new Set());
    grouped.get(citation.source_id).add(citation.quote);
  }
  for (const [sourceId, quotes] of grouped) {
    const index = state.sources.findIndex((s) => s.id === sourceId);
    if (index < 0) continue;
    const button = element("button", "citation", String(index + 1));
    button.type = "button";
    button.setAttribute(
      "aria-label",
      `Inspect citation ${index + 1}: ${state.sources[index].title}`,
    );
    button.addEventListener("click", () => {
      $$(".source-card").forEach((node) => node.classList.remove("highlight"));
      $$(".source-quote").forEach((node) => node.remove());
      const card = $(`#source-${index}`);
      card.classList.add("highlight");
      for (const quote of quotes)
        card.append(element("blockquote", "source-quote", quote));
      card.querySelector("details").open = true;
      card.focus({ preventScroll: true });
      card.scrollIntoView({
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
        block: "nearest",
      });
    });
    parent.append(button);
  }
}

function renderAnswer(result) {
  state.result = result;
  $("#answer-panel").hidden = false;
  $("#empty-state").hidden = true;
  const body = element("div", "answer-body");
  const supported = result.answer.status === "supported";
  body.append(
    element(
      "div",
      `answer-status${supported ? "" : " unsupported"}`,
      supported
        ? "● SOURCES FOUND · REVIEW BEFORE ACTING"
        : "○ INSUFFICIENT EVIDENCE",
    ),
  );
  body.append(element("h2", "", result.answer.title));
  for (const claim of result.answer.claims) {
    const paragraph = element("p", "claim");
    inlineCode(paragraph, claim.text);
    citations(paragraph, claim.citations);
    body.append(paragraph);
  }
  if (result.answer.checks.length)
    body.append(element("h3", "answer-subheading", "READ-ONLY CHECKS"));
  for (const check of result.answer.checks) {
    const card = element("div", "check");
    const heading = element("h4", "", check.purpose);
    citations(heading, check.citations);
    const code = element("div", "code-line");
    const copy = element("button", "copy-button", "Copy");
    copy.type = "button";
    copy.setAttribute("aria-label", `Copy command: ${check.command}`);
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(check.command);
        notify("Command copied. Replace placeholders before running.");
      } catch {
        notify("Clipboard unavailable. Select and copy the command.");
      }
    });
    code.append(element("code", "", check.command), copy);
    card.append(heading, code, element("p", "", check.expected_signal));
    body.append(card);
  }
  if (result.answer.follow_up.length) {
    body.append(element("h3", "answer-subheading", "TO NARROW THIS DOWN"));
    const list = element("ul", "follow-ups");
    for (const question of result.answer.follow_up)
      list.append(element("li", "", question));
    body.append(list);
  }
  if (result.answer.limitation.trim())
    body.append(element("p", "limitation", result.answer.limitation));
  $("#answer-content").replaceChildren(body);
  $("#completion-status").textContent = supported
    ? "Diagnostic note ready. Inspect its citations before acting."
    : "Investigation complete: insufficient evidence.";
  const trace = $("#trace");
  trace.replaceChildren(
    element(
      "span",
      "",
      `Retrieval ${Math.round(result.trace.retrieval_ms)} ms`,
    ),
    element("span", "", `Total ${(result.trace.total_ms / 1000).toFixed(1)} s`),
    element(
      "span",
      "",
      `${result.trace.usage.input_tokens + result.trace.usage.output_tokens} generation tokens`,
    ),
  );
  if (result.trace.rerank_fallback)
    trace.append(
      element(
        "span",
        "trace-warning",
        "Reranker unavailable · used hybrid ordering",
      ),
    );
  const details = element("details");
  details.append(
    element("summary", "", "Inspect retrieval & validation trace"),
    element(
      "pre",
      "",
      JSON.stringify({ corpus_id: result.corpus_id, ...result.trace }, null, 2),
    ),
  );
  trace.append(details);
}

function downloadNote() {
  if (!state.result) return;
  const result = state.result;
  const numbering = new Map(result.sources.map((s, i) => [s.id, i + 1]));
  const refs = (items) =>
    [...new Set(items.map((c) => `[${numbering.get(c.source_id)}]`))].join(" ");
  const lines = [
    `# ${result.answer.title}`,
    "",
    `Incident: ${result.query}`,
    "",
    `Status: ${result.answer.status}`,
    `Documentation: Kubernetes ${result.version}`,
    "",
  ];
  for (const claim of result.answer.claims)
    lines.push(`${claim.text} ${refs(claim.citations)}`, "");
  for (const check of result.answer.checks)
    lines.push(
      `## ${check.purpose}`,
      "",
      "```sh",
      check.command,
      "```",
      "",
      `${check.expected_signal} ${refs(check.citations)}`,
      "",
    );
  if (result.answer.limitation.trim() || result.answer.follow_up.length)
    lines.push(
      "## Limits",
      "",
      result.answer.limitation,
      "",
      ...result.answer.follow_up.map((q) => `- ${q}`),
      "",
    );
  lines.push("## Sources", "");
  result.sources.forEach((s, i) =>
    lines.push(`${i + 1}. [${s.title} > ${s.heading}](${s.source_url})`),
  );
  lines.push("", "## Cited excerpts", "");
  const seen = new Set();
  for (const item of [...result.answer.claims, ...result.answer.checks]) {
    for (const citation of item.citations) {
      const identity = `${citation.source_id}:${citation.quote}`;
      if (seen.has(identity)) continue;
      seen.add(identity);
      lines.push(
        `[${numbering.get(citation.source_id)}]`,
        "",
        ...citation.quote.split("\n").map((line) => `> ${line}`),
        "",
      );
    }
  }
  lines.push(
    "",
    `Corpus: ${result.corpus_id}`,
    `Model: ${result.trace.usage.model}`,
    "",
    "Runbook suggests checks; it does not access or modify clusters.",
  );
  const url = URL.createObjectURL(
    new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "runbook-diagnosis.md";
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$("#export").addEventListener("click", downloadNote);

async function readEvents(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += done
        ? decoder.decode()
        : decoder.decode(value, { stream: true });
      if (buffer.length > 524288)
        throw new Error("The server response is too large. Please retry.");
      buffer = buffer.replace(/\r\n/g, "\n");
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const record = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const name = record
          .split("\n")
          .find((line) => line.startsWith("event:"))
          ?.slice(6)
          .trim();
        const data = record
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (name && data) onEvent(name, JSON.parse(data));
      }
      if (done) break;
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

$("#cancel").addEventListener("click", () => state.controller?.abort());
$("#incident-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.controller) return;
  const query = $("#incident").value.trim();
  if (query.length < 8) {
    $("#incident").focus();
    return;
  }
  state.controller = new AbortController();
  const controller = state.controller;
  state.result = null;
  $("#completion-status").textContent = "";
  $("#incident").readOnly = true;
  $("#mode").disabled = true;
  $$("[data-query]").forEach((button) => {
    button.disabled = true;
  });
  $("#error").hidden = true;
  $("#answer-panel").hidden = true;
  $("#empty-state").hidden = true;
  $("#progress").hidden = false;
  $("#progress-text").textContent = "Finding relevant evidence…";
  $("#elapsed").textContent = "0.0s";
  $("#submit").hidden = true;
  $("#cancel").hidden = false;
  renderEvidence([]);
  const started = performance.now();
  state.timer = setInterval(() => {
    $("#elapsed").textContent =
      `${((performance.now() - started) / 1000).toFixed(1)}s`;
  }, 100);
  let complete = false;
  const timeout = setTimeout(() => controller.abort("timeout"), 75000);
  try {
    const headers = { "Content-Type": "application/json" };
    if ($("#access-token").value)
      headers.Authorization = `Bearer ${$("#access-token").value}`;
    const response = await fetch("/api/diagnose/stream", {
      method: "POST",
      headers,
      body: JSON.stringify({ query, mode: $("#mode").value }),
      signal: controller.signal,
    });
    if (!response.ok) {
      if (response.status === 401) $("#access-row").hidden = false;
      const payload = await response.json().catch(() => ({}));
      throw new Error(
        typeof payload.detail === "string"
          ? payload.detail
          : "The request failed. Please try again.",
      );
    }
    await readEvents(response, (name, payload) => {
      if (name === "evidence") renderEvidence(payload.sources);
      if (name === "status" && payload.stage === "generating")
        $("#progress-text").textContent =
          "Writing and reviewing a note against these passages…";
      if (name === "answer") {
        renderAnswer(payload);
        complete = true;
      }
      if (name === "error") {
        throw new Error(payload.message);
      }
    });
    if (!complete)
      throw new Error(
        "The connection ended before an answer arrived. Please retry.",
      );
  } catch (error) {
    $("#error").textContent = controller.signal.aborted
      ? controller.signal.reason === "timeout"
        ? "The investigation timed out. Retrieved evidence remains available; please retry."
        : "Investigation stopped. Retrieved evidence remains available."
      : error.message;
    $("#error").hidden = false;
  } finally {
    clearInterval(state.timer);
    clearTimeout(timeout);
    state.controller = null;
    $("#incident").readOnly = false;
    $("#mode").disabled = false;
    $$("[data-query]").forEach((button) => {
      button.disabled = false;
    });
    $("#progress").hidden = true;
    $("#submit").hidden = false;
    $("#cancel").hidden = true;
    if (!state.sources.length && !complete) $("#empty-state").hidden = false;
  }
});

const pct = (value) => `${(100 * value).toFixed(1)}%`;
function metric(label, value, description) {
  const card = element("div", "metric");
  card.append(
    element("div", "metric-label", label),
    element("div", "metric-value", value),
    element("div", "metric-description", description),
  );
  return card;
}
function panel(title, description) {
  const box = element("section", "panel");
  const header = element("div", "panel-body");
  header.append(element("h2", "", title));
  if (description) header.append(element("p", "", description));
  box.append(header);
  return box;
}
function renderBenchmark(report) {
  const root = $("#benchmark-content");
  root.replaceChildren();
  if (report.status === "not_run") {
    root.append(element("p", "method-note", report.message));
    return;
  }
  if (report.compatibility && !report.compatibility.matches_running_instance) {
    const warning = element(
      "p",
      "error-box",
      `Historical measurement: this report differs from the running instance (${report.compatibility.differences.join(", ")}). Rerun evaluation before using these numbers for this instance.`,
    );
    warning.setAttribute("role", "status");
    root.append(warning);
  }
  const primaryMode = report.configuration.default_mode || "hybrid";
  const hybrid = report.retrieval[primaryMode];
  const metrics = element("div", "metric-grid");
  metrics.append(
    metric(
      "EVIDENCE RECALL @ 5",
      pct(hybrid.evidence_recall_at_5),
      `95% bootstrap interval ${hybrid.evidence_recall_ci95.map(pct).join("–")}`,
    ),
    metric(
      "RECIPROCAL RANK @ 5",
      hybrid.mrr_at_5.toFixed(3),
      `${primaryMode} · first relevant passage`,
    ),
    metric(
      "RETRIEVAL P95",
      `${Math.round(hybrid.p95_search_ms)} ms`,
      "Includes embedding and reranking, when used",
    ),
    metric(
      "LABELED CASES",
      String(report.cases.length),
      `${report.answerable_cases} answerable · ${report.unanswerable_cases} abstention cases`,
    ),
  );
  root.append(metrics);
  const meta = element("div", "meta-line");
  meta.append(
    element("span", "", `RUN ${new Date(report.created_at).toLocaleString()}`),
    element("span", "", `CORPUS ${report.corpus_id}`),
    element("span", "", `SPLIT ${report.split.toUpperCase()}`),
  );
  root.append(meta);
  const comparison = panel(
    "Retrieval modes",
    "Every mode returns its top five passages from the same corpus, with at most two per page. Reranking asks a model to order 30 hybrid candidates, and its latency counts.",
  );
  const wrap = element("div", "table-wrap"),
    table = element("table"),
    thead = element("thead"),
    header = element("tr");
  wrap.tabIndex = 0;
  wrap.setAttribute("role", "region");
  wrap.setAttribute("aria-label", "Retrieval strategy comparison");
  for (const label of [
    "Strategy",
    "Evidence recall @ 5",
    "Document recall @ 5",
    "MRR @ 5",
    "P95 search",
  ])
    header.append(element("th", "", label));
  thead.append(header);
  table.append(thead);
  const tbody = element("tbody");
  for (const mode of Object.keys(report.retrieval)) {
    const row = element("tr"),
      values = report.retrieval[mode];
    const name = element(
      "td",
      "",
      {
        bm25: "BM25",
        dense: "Semantic",
        hybrid: "Hybrid · RRF",
        reranked: "Hybrid + reranking",
      }[mode],
    );
    if (mode === primaryMode)
      name.append(element("span", "mode-badge", "DEFAULT"));
    row.append(name);
    const score = element("td"),
      bar = element("div", "metric-bar"),
      meter = element("meter", "meter");
    meter.min = 0;
    meter.max = 1;
    meter.value = values.evidence_recall_at_5;
    meter.setAttribute("aria-label", `${mode} evidence recall`);
    bar.append(element("span", "", pct(values.evidence_recall_at_5)), meter);
    score.append(bar);
    row.append(
      score,
      element("td", "", pct(values.document_recall_at_5)),
      element("td", "", values.mrr_at_5.toFixed(3)),
      element("td", "", `${Math.round(values.p95_search_ms)} ms`),
    );
    tbody.append(row);
  }
  table.append(tbody);
  wrap.append(table);
  comparison.append(wrap);
  root.append(comparison);
  if (report.answers) {
    const a = report.answers,
      box = panel(
        "Answer evaluation",
        "The server keeps only statements whose quotes match their passages and pass a support review. A separate judge model then grades each kept statement and check. A favorable grade is a model's opinion, not proof.",
      );
    const cards = element("div", "metric-grid panel-body");
    cards.append(
      metric(
        "EXACT QUOTE VALIDITY",
        pct(a.raw_quote_validity),
        `${a.raw_citations} citations before filtering`,
      ),
      metric(
        "JUDGED CLAIM SUPPORT",
        a.judged_claim_support === null ? "—" : pct(a.judged_claim_support),
        `${a.judged_claims} retained claims · ${a.judge_model}`,
      ),
      metric(
        "ABSTENTION ACCURACY",
        pct(a.abstention_accuracy),
        `${a.attempted} attempted cases · ${a.failures} failures`,
      ),
      metric(
        "ANSWER LATENCY P95",
        `${(a.p95_ms / 1000).toFixed(1)} s`,
        "Retrieval + generation + review; one evaluation run",
      ),
    );
    box.append(cards);
    if (a.judged_checks !== undefined) {
      const coverage = element(
        "p",
        "method-note",
        `Diagnostic check support: ${a.judged_check_support === null ? "not measured" : pct(a.judged_check_support)} across ${a.judged_checks} checks. ${a.addresses_question}/${a.judged_answers} judged answers address the question. Judge failures: ${a.judge_failures}.`,
      );
      box.append(coverage);
    }
    root.append(box);
  } else {
    root.append(
      element(
        "p",
        "method-note",
        "This run measures retrieval only. Answer quality and abstention were not evaluated.",
      ),
    );
  }
  const note = panel("What these numbers establish", report.methodology);
  const noteBody = element("div", "panel-body");
  const list = element("ul", "follow-ups");
  report.limitations.forEach((item) => list.append(element("li", "", item)));
  noteBody.append(list);
  note.append(noteBody);
  root.append(note);
  const cases = panel(
    "Inspect every question",
    "Failed retrievals and abstentions remain in the report. Expand a row to compare the retrieved passages.",
  );
  const filter = element("div", "results-filter");
  const rows = element("div");
  function showCases(split) {
    rows.replaceChildren();
    for (const item of report.cases.filter(
      (item) => split === "all" || item.split === split,
    )) {
      const details = element("details", "result-row");
      const summary = element("summary");
      summary.append(
        element("span", "", item.question),
        element(
          "span",
          "case-category",
          `${item.split} · ${item.answerable ? pct(item.retrieval[primaryMode].evidence_recall_at_5) : "abstain"}`,
        ),
      );
      const content = element("div", "panel-body");
      for (const mode of Object.keys(item.retrieval)) {
        const scores = item.retrieval[mode];
        content.append(
          element(
            "p",
            "",
            `${mode.toUpperCase()} · ${item.answerable ? `evidence recall ${pct(scores.evidence_recall_at_5)}` : "not scored for retrieval"} · ${scores.top_sources.map((s) => s.title + " / " + s.heading).join(" → ")}`,
          ),
        );
      }
      if (item.answer)
        content.append(
          element(
            "p",
            "",
            `Answer: ${item.answer.status} · ${item.answer.judge?.note || item.answer.error || "Quote validation recorded in raw results."}`,
          ),
        );
      details.append(summary, content);
      rows.append(details);
    }
  }
  for (const split of ["all", "dev", "holdout"]) {
    const button = element(
      "button",
      split === "all" ? "active" : "",
      split === "all"
        ? "All cases"
        : split === "dev"
          ? "Development"
          : "Holdout",
    );
    button.addEventListener("click", () => {
      [...filter.children].forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-pressed", "false");
      });
      button.classList.add("active");
      button.setAttribute("aria-pressed", "true");
      showCases(split);
    });
    button.setAttribute("aria-pressed", String(split === "all"));
    filter.append(button);
  }
  showCases("all");
  cases.append(filter, rows);
  root.append(cases);
}

async function loadBenchmark() {
  $("#benchmark-content").textContent = "Loading measured results…";
  try {
    const response = await fetch("/api/benchmark");
    if (!response.ok) throw new Error("Could not load the evaluation report.");
    renderBenchmark(await response.json());
  } catch (error) {
    $("#benchmark-content").textContent = error.message;
  }
}
function renderSources(corpus) {
  const root = $("#source-content");
  const note = element(
    "p",
    "method-note",
    `${corpus.documents} documents · ${corpus.chunks} heading-aware passages · Kubernetes ${corpus.version}. Source text and embeddings are checksummed at startup. This snapshot is deliberately bounded; newer versions and third-party operators are outside its scope.`,
  );
  const meta = element("div", "meta-line");
  meta.append(
    link(
      `Upstream commit ${corpus.revision.slice(0, 12)}`,
      `https://github.com/kubernetes/website/commit/${corpus.revision}`,
    ),
    element("span", "", `INDEX ${corpus.corpus_id}`),
  );
  const grid = element("div", "source-library");
  for (const source of corpus.sources) {
    const card = element("article", "library-card");
    card.append(
      element("h3", "", source.title),
      element(
        "p",
        "",
        `${source.chunks} passages · SHA256 ${source.sha256.slice(0, 16)}`,
      ),
      link(
        "View immutable source",
        `https://github.com/kubernetes/website/blob/${corpus.revision}/${source.path}`,
      ),
    );
    grid.append(card);
  }
  root.replaceChildren(note, meta, grid);
}

async function initialize() {
  const [healthResult, corpusResult] = await Promise.allSettled([
    fetch("/api/health").then((r) => r.json()),
    fetch("/api/corpus").then(async (r) => {
      if (!r.ok) throw new Error();
      return r.json();
    }),
  ]);
  if (healthResult.status === "fulfilled") {
    const health = healthResult.value;
    $("#service-status").replaceChildren(
      element("span", "status-dot"),
      document.createTextNode(
        health.status === "ready" && health.provider_configured
          ? "Ready to investigate"
          : "Setup required",
      ),
    );
    $("#access-row").hidden = !health.access_required;
    if (!health.provider_configured) {
      $("#error").textContent =
        health.backend === "codex"
          ? "The Codex CLI is not installed on this server. Install it and run codex login."
          : "OpenAI is not configured on this instance. Ask the operator to set the server API key.";
      $("#error").hidden = false;
    }
  } else {
    $("#service-status").textContent = "Service unavailable";
  }
  if (corpusResult.status === "fulfilled") {
    const corpus = corpusResult.value;
    $("#version-tag").textContent = `KUBERNETES ${corpus.version}`;
    $("#sidebar-version").textContent = `v${corpus.version} · official docs`;
    $("#corpus-summary").textContent =
      `${corpus.documents} docs · ${corpus.chunks} indexed passages`;
    renderSources(corpus);
  } else {
    $("#corpus-summary").textContent = "Corpus not indexed yet";
    $("#source-content").textContent =
      "The corpus is unavailable. Ask the operator to run ingestion.";
    $("#error").textContent =
      "The documentation index is unavailable. Ask the operator to run ingestion.";
    $("#error").hidden = false;
  }
}
setView(location.hash.slice(1));
initialize();
