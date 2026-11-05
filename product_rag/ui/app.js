/* =====================================================================
   FlowDesk Product Assistant — pipeline UI
   Streams each LangGraph node's output from /api/ask and renders it.
   ===================================================================== */

const STEPS = [
  { id: "input_guardrail",  label: "Input guardrail",  panel: "panel-input_guardrail" },
  { id: "research_agent",   label: "Research agent",   panel: "panel-research_agent" },
  { id: "rerank",           label: "Rerank",           panel: "panel-rerank" },
  { id: "grade_context",    label: "Grade context",    panel: "panel-grade_context" },
  { id: "generate",         label: "Generate",         panel: "panel-generate" },
  { id: "output_guardrail", label: "Output guardrail", panel: "panel-output_guardrail" },
  { id: "human_review",     label: "Human review",     panel: "panel-human_review" },
  { id: "finalise",         label: "Finalise",         panel: "panel-final" },
];

const state = {
  cfg: null,
  run: null,      // data for the current run
  es: null,       // active EventSource
  busy: false,
};

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtMs = (ms) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`);

init();

/* ------------------------------------------------------------------ */
/* Boot                                                                */
/* ------------------------------------------------------------------ */
async function init() {
  initTheme();
  renderSteps();
  try {
    state.cfg = await (await fetch("/api/config")).json();
  } catch (e) {
    showError("Could not reach the API. Start it with:  uvicorn api:app --reload");
    return;
  }
  $(".k-rr").textContent = state.cfg.rerank_top_k;
  $(".k-tools").textContent = state.cfg.max_tool_calls;
  renderChips();

  $("#queryForm").addEventListener("submit", (e) => { e.preventDefault(); startRun(); });
  $("#drawerClose").addEventListener("click", closeDrawer);
  $("#drawer").addEventListener("click", (e) => { if (e.target.id === "drawer") closeDrawer(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
  $("#copyAudit").addEventListener("click", copyAudit);
}

function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("rag-theme"); } catch {}
  if (saved) document.documentElement.dataset.theme = saved;
  $("#themeToggle").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("rag-theme", next); } catch {}
  });
}

function renderChips() {
  const groups = {};
  for (const q of state.cfg.sample_questions) (groups[q.group] ||= []).push(q);
  $("#samples").innerHTML = Object.entries(groups).map(([g, qs]) => `
    <span class="chip-group">${esc(g)}</span>
    ${qs.map((q) => `<button type="button" class="chip" title="${esc(q.question)}">${esc(`${q.id} · ${q.question}`)}</button>`).join("")}
  `).join("");
  $$("#samples .chip").forEach((b) => b.addEventListener("click", () => {
    $("#question").value = b.title;
    $("#question").focus();
  }));
}

/* ------------------------------------------------------------------ */
/* Stepper                                                             */
/* ------------------------------------------------------------------ */
function renderSteps() {
  $("#steps").innerHTML = STEPS.map((s, i) => `
    <li class="step" data-step="${s.id}" title="Jump to ${esc(s.label)}">
      <span class="label"><span class="dot"></span>${i + 1}. ${esc(s.label)}</span>
      <span class="meta"></span>
    </li>`).join("");
  $$(".step").forEach((el) => el.addEventListener("click", () => {
    const step = STEPS.find((s) => s.id === el.dataset.step);
    const panel = document.getElementById(step.panel);
    if (!panel || panel.classList.contains("hidden")) return;
    panel.scrollIntoView();
    flash(panel);
  }));
}

function setStep(id, status, meta) {
  const el = $(`.step[data-step="${id}"]`);
  if (!el) return;
  el.classList.remove("running", "done", "blocked", "paused", "skipped");
  if (status) el.classList.add(status);
  if (meta !== undefined) $(".meta", el).textContent = meta;
}

function flash(panel) {
  panel.classList.add("active");
  setTimeout(() => panel.classList.remove("active"), 1200);
}

function timing(node, ms) {
  const el = $(`.timing[data-for="${node}"]`);
  if (el) el.textContent = fmtMs(ms);
  return fmtMs(ms);
}

/* ------------------------------------------------------------------ */
/* Run                                                                 */
/* ------------------------------------------------------------------ */
function startRun() {
  if (state.busy) return;
  const question = $("#question").value.trim();
  if (!question) { $("#question").focus(); return; }
  const rerank = $("#rerankToggle").checked;

  resetPanels(question, rerank);
  state.busy = true;
  setFormDisabled(true);
  $("#runBtn").textContent = "Running...";

  const url = `/api/ask?question=${encodeURIComponent(question)}&rerank=${rerank}`;
  const es = new EventSource(url);
  state.es = es;
  es.addEventListener("stage", (e) => handleEvent("stage", JSON.parse(e.data)));
  es.addEventListener("paused", (e) => { handleEvent("paused", JSON.parse(e.data)); finishRun(); });
  es.addEventListener("done", (e) => { handleEvent("done", JSON.parse(e.data)); finishRun(); });
  es.addEventListener("error", (e) => {
    if (e.data !== undefined) {                 // server-sent error (MessageEvent)
      try { handleEvent("error", JSON.parse(e.data)); } catch { showError("server error"); }
    } else if (!state.run.ended) {              // transport failure
      showError("connection lost");
    }
    finishRun();
  });
}

function setFormDisabled(disabled) {
  $("#question").disabled = disabled;
  $("#rerankToggle").disabled = disabled;
  $$("#samples .chip").forEach((b) => (b.disabled = disabled));
}

function finishRun() {
  if (state.es) { state.es.close(); state.es = null; }
  state.busy = false;
  setFormDisabled(false);
  $("#runBtn").textContent = "Ask ▸";
}

function resetPanels(question, rerank) {
  state.run = {
    question, rerank, ended: false,
    loopRound: 0, draft: null, threadId: null,
    guardrailReport: null, grounding: null, reviewDecision: null, reviewEdited: null,
    chunkIndex: {}, keptIndex: {},
  };
  hideError();
  $("#stages").classList.remove("hidden");

  for (const s of STEPS) setStep(s.id, null, "");
  setStep("input_guardrail", "running", "checking...");
  $$(".timing").forEach((t) => (t.textContent = ""));

  const waiting = `<div class="placeholder">Waiting...</div>`;
  $("#guardrailBody").innerHTML = waiting;
  $("#researchRounds").innerHTML = waiting;
  $("#rerankRounds").innerHTML = waiting;
  $("#gradeRounds").innerHTML = waiting;
  $("#generateBody").innerHTML = waiting;
  $("#guardrailOut").innerHTML = waiting;
  $(".final").className = "card body final";
  $(".final").innerHTML = waiting;

  for (const id of ["panel-research_agent", "panel-rerank", "panel-grade_context", "panel-generate",
                     "panel-output_guardrail", "panel-final"]) document.getElementById(id).classList.remove("hidden");
  $("#panel-human_review").classList.add("hidden");
  $("#panel-audit").classList.add("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function handleEvent(event, payload) {
  if (event === "stage") return onStage(payload.node, payload.data, payload.ms);
  if (event === "paused") return onPaused(payload);
  if (event === "done") return onDone(payload);
  if (event === "error") { state.run.ended = true; return showError(payload.message); }
}

function onStage(node, data, ms) {
  const t = timing(node, ms);
  const round = state.run.loopRound;
  const scrollTo = (id) => { const p = document.getElementById(id); p.scrollIntoView(); flash(p); };

  switch (node) {
    case "input_guardrail":
      renderInputGuardrail(data);
      if (data.allowed) {
        setStep(node, "done", `allowed · ${t}`);
        setStep("research_agent", "running", "researching...");
      } else {
        setStep(node, "blocked", `blocked · ${t}`);
        for (const s of STEPS.slice(1)) setStep(s.id, "skipped", "skipped");
        for (const id of ["panel-research_agent", "panel-rerank", "panel-grade_context",
                          "panel-generate", "panel-output_guardrail", "panel-human_review"])
          document.getElementById(id).classList.add("hidden");
        renderFinal(data.final_answer, "bad", "Refused by the input guardrail — no search or LLM call was made.");
        scrollTo("panel-input_guardrail");
      }
      break;

    case "research_agent":
      state.run.loopRound = data.round;
      renderResearchRound(data);
      setStep(node, "done", `${data.round > 1 ? `round ${data.round} · ` : ""}${data.chunk_count} chunks · ${t}`);
      setStep("rerank", "running", "reranking...");
      scrollTo("panel-research_agent");
      break;

    case "rerank":
      renderRerankRound(data);
      setStep(node, "done", `${round > 1 ? `round ${round} · ` : ""}${data.kept.length} kept · ${t}`);
      setStep("grade_context", "running", "grading...");
      scrollTo("panel-rerank");
      break;

    case "grade_context":
      renderGradeRound(data);
      if (data.will_retry) {
        setStep(node, "done", `${round > 1 ? `round ${round} · ` : ""}insufficient · ${t}`);
        setStep("research_agent", "running", `round ${data.attempts + 1}...`);
      } else {
        setStep(node, "done", `${round > 1 ? `round ${round} · ` : ""}${data.grade.toLowerCase()} · ${t}`);
        setStep("generate", "running", "writing...");
      }
      scrollTo("panel-grade_context");
      break;

    case "generate":
      state.run.draft = data.draft_answer;
      renderGenerate(data);
      setStep(node, "done", t);
      setStep("output_guardrail", "running", "verifying...");
      scrollTo("panel-generate");
      break;

    case "output_guardrail":
      state.run.grounding = data;
      renderOutputGuardrail(data);
      setStep(node, "done", data.needs_review ? "needs review · " + t : "passed · " + t);
      setStep(data.needs_review ? "human_review" : "finalise", "running", "...");
      scrollTo("panel-output_guardrail");
      break;

    case "finalise":
      setStep("finalise", "done", t);
      setStep("human_review", "skipped", "not needed");
      renderFinal(data.final_answer, "ok", "Grounded — sent straight to the user.");
      scrollTo("panel-final");
      break;

    case "human_review":
      state.run.reviewDecision = data.decision;
      setStep("human_review", "done", `${data.decision} · ${t}`);
      const cls = data.decision === "reject" ? "bad" : data.decision === "edit" ? "warn" : "ok";
      const note = data.decision === "reject"
        ? "Rejected by the reviewer — a safe fallback message is shown."
        : data.decision === "edit"
          ? "Approved with edits by the reviewer."
          : "Approved as written by the reviewer.";
      renderFinal(data.final_answer, cls, note);
      $("#reviewBody").innerHTML =
        `<div class="verdict"><span class="badge ${cls}">${esc(data.decision)}</span>
         <span>Graph resumed from its checkpoint and ran <code>human_review</code>.</span></div>`;
      scrollTo("panel-final");
      break;
  }
}

function onPaused(p) {
  state.run.ended = true;
  state.run.threadId = p.thread_id;
  if (p.draft_answer) state.run.draft = p.draft_answer;
  state.run.guardrailReport = p.guardrail_report || null;
  setStep("output_guardrail", "done");
  setStep("finalise", "skipped", "not taken");
  setStep("human_review", "paused", "waiting for you");
  renderReview();
  renderFinal(null, "warn", "Awaiting human review — nothing has been shown to the user yet.");
  const panel = $("#panel-human_review");
  panel.classList.remove("hidden");
  panel.scrollIntoView();
  flash(panel);
}

function onDone(p) {
  state.run.ended = true;
  for (const s of STEPS) {
    const el = $(`.step[data-step="${s.id}"]`);
    const claimed = ["running", "done", "blocked", "paused", "skipped"].some((c) => el.classList.contains(c));
    if (!claimed) setStep(s.id, "skipped", "skipped");
  }
  renderAudit(p);
}

/* ------------------------------------------------------------------ */
/* Stage renderers                                                     */
/* ------------------------------------------------------------------ */
function renderInputGuardrail(d) {
  $("#guardrailBody").innerHTML = d.allowed
    ? `<div class="verdict"><span class="badge ok">Allowed</span>
        <span class="pill ${d.intent !== "none" ? "badge warn" : ""}">intent ${esc(d.intent)}</span>
        <span>Question passed into the research agent.</span></div>
       ${d.reason ? `<dl class="kv"><dt>Reason</dt><dd>${esc(d.reason)}</dd></dl>` : ""}`
    : `<div class="verdict"><span class="badge bad">Blocked</span>
        <span>Stopped before any retrieval or generation cost was spent.</span></div>
       <dl class="kv"><dt>Reason</dt><dd>${esc(d.reason)}</dd></dl>`;
}

function renderResearchRound(d) {
  const box = $("#researchRounds");
  if (box.firstElementChild && box.firstElementChild.classList.contains("placeholder")) box.innerHTML = "";
  for (const c of d.chunks) state.run.chunkIndex[c.id] = c;

  const searches = d.searches.map((s) => `
    <li class="search-row">
      <span class="doc-pill" data-doc="${esc(s.doc_type === "all" ? "prd" : s.doc_type)}">${esc(s.doc_type)}</span>
      <span class="q">${esc(s.query)}</span>
    </li>`).join("");

  const rows = d.chunks.map((c) => chunkRow(c)).join("");

  const round = document.createElement("div");
  round.className = "card";
  round.innerHTML = `
    <div class="round-head">Round ${d.round}</div>
    ${d.feedback ? `<div class="callout"><b>Retry with grader feedback:</b> ${esc(d.feedback)}</div>` : ""}
    <ul class="search-list">${searches || `<li class="placeholder">No searches</li>`}</ul>
    <button type="button" class="ghost small chunk-toggle">Show chunks (${d.chunk_count}, ${d.unique_count} unique) ▸</button>
    <ul class="chunk-list hidden">${rows || `<li class="placeholder">No chunks</li>`}</ul>
    <div class="round-meta">${d.chunk_count} chunks (${d.unique_count} unique) retrieved this round</div>`;
  box.appendChild(round);
  bindRoundEvents(round);
}

function chunkRow(c) {
  return `
    <li class="chunk" data-chunk="${esc(c.id)}">
      <div class="chunk-top">
        <span class="doc-pill" data-doc="${esc(c.doc_type)}">${esc(c.doc_type)}</span>
        <span class="score">p.${esc(c.page)}${c.doc_date ? ` · ${esc(c.doc_date)}` : ""}</span>
        <span class="bar" title="embedding similarity"><span style="width:${barWidth(c.score)}%"></span></span>
        <span class="score">${(+c.score).toFixed(4)}</span>
      </div>
      <div class="chunk-text">${esc(c.text)}</div>
    </li>`;
}

function barWidth(score) {
  return Math.max(4, Math.min(100, Math.round((+(score || 0)) * 100)));
}

function bindRoundEvents(round) {
  const toggle = $(".chunk-toggle", round);
  if (toggle) toggle.addEventListener("click", () => {
    const list = $(".chunk-list", round);
    const open = list.classList.toggle("hidden") === false;
    toggle.textContent = open ? "Hide chunks ▾" : `Show chunks (${list.children.length}) ▸`;
  });
  $$(".chunk", round).forEach((el) => el.addEventListener("click", () => openDrawer(el.dataset.chunk)));
}

function renderRerankRound(d) {
  const box = $("#rerankRounds");
  if (box.firstElementChild && box.firstElementChild.classList.contains("placeholder")) box.innerHTML = "";
  for (const k of d.kept) state.run.keptIndex[k.id] = k;

  const rows = d.kept.map((k, i) => rrRow(k, i + 1, d.reranker_on)).join("");
  const round = document.createElement("div");
  round.className = "card";
  round.innerHTML = `
    <div class="round-head">Round ${state.run.loopRound}</div>
    <div class="round-meta">${d.candidates_total} candidates (${d.candidates_unique} unique) → kept ${d.kept.length} ·
      reranker ${d.reranker_on ? "ON" : "OFF"} · model <code>${esc(d.model)}</code></div>
    ${d.reranker_on ? "" : `<div class="callout">Reranker OFF — sorted by embedding score</div>`}
    <ul class="chunk-list rr">${rows || `<li class="placeholder">No chunks kept</li>`}</ul>
    <div class="rr-summary">top ${d.top_k} of the reranked order reach the generator.</div>`;
  box.appendChild(round);
  $$(".chunk", round).forEach((el) => el.addEventListener("click", () => openDrawer(el.dataset.chunk)));
}

function rrRow(k, rank, rerankerOn) {
  const moved = k.moved;
  const move = moved == null ? `<span class="move same">＝</span>`
    : moved > 0 ? `<span class="move up" title="moved up ${moved}">▲ ${moved}</span>`
    : moved < 0 ? `<span class="move down" title="moved down ${-moved}">▼ ${-moved}</span>`
    : `<span class="move same">＝</span>`;
  return `
    <li class="chunk" data-chunk="${esc(k.id)}">
      <div class="chunk-top">
        <span class="rank">#${rank}</span>
        <span class="doc-pill" data-doc="${esc(k.doc_type)}">${esc(k.doc_type)}</span>
        <span class="score">p.${esc(k.page)}${k.doc_date ? ` · ${esc(k.doc_date)}` : ""}</span>
        ${rerankerOn
          ? `<span class="score">rr ${k.rerank_score != null ? (+k.rerank_score).toFixed(4) : "—"}</span>
             <span class="score">sim ${(+k.score).toFixed(4)}</span>
             <span class="score">was #${k.embed_rank ?? "?"}</span>${move}`
          : `<span class="score">sim ${(+k.score).toFixed(4)}</span>`}
      </div>
      <div class="chunk-text">${esc(k.text)}</div>
    </li>`;
}

function renderGradeRound(d) {
  const box = $("#gradeRounds");
  if (box.firstElementChild && box.firstElementChild.classList.contains("placeholder")) box.innerHTML = "";
  const verdict = d.grade.toUpperCase() === "INSUFFICIENT" ? "warn" : "ok";
  const prose = d.will_retry
    ? `→ retrying research (round ${d.attempts + 1} of ${d.max_rounds})`
    : d.grade.toUpperCase() === "INSUFFICIENT"
      ? "→ out of retries, answering with what we have"
      : "→ answering";
  const round = document.createElement("div");
  round.className = "card";
  round.innerHTML = `
    <div class="round-head">Round ${state.run.loopRound}</div>
    <div class="verdict">
      <span class="badge ${verdict}">${esc(d.grade)}</span>
      <span>${esc(prose)}</span>
    </div>
    ${d.missing ? `<dl class="kv"><dt>Missing</dt><dd>${esc(d.missing)}</dd></dl>` : ""}`;
  box.appendChild(round);
}

function renderGenerate(d) {
  $("#generateBody").innerHTML =
    `<div class="answer-meta">Draft from <b>${esc(d.model)}</b> · temperature 0</div>
     <div class="answer">${md(d.draft_answer)}</div>`;
}

function renderOutputGuardrail(d) {
  const r = d.report;
  const grounded = (r.grounding ?? 1) >= d.threshold;
  const intentOk = (r.sensitive_intent || "none") === "none";
  const pct = Math.round((r.grounding ?? 1) * 100);
  const color = !grounded ? "var(--bad)" : intentOk ? "var(--ok)" : "var(--warn)";
  const cls = d.needs_review ? "warn" : "ok";
  const reasons = [];
  if (!intentOk) reasons.push(`sensitive intent: ${esc(r.sensitive_intent)}`);
  if (!grounded) reasons.push(`grounding ${Number(r.grounding ?? 1).toFixed(2)} below threshold ${d.threshold}`);
  const ungrounded = r.ungrounded_numbers || [];

  $("#guardrailOut").innerHTML = `
    <div class="verdict">
      <span class="badge ${cls}">${d.needs_review ? "Needs Human Review" : "Passed"}</span>
      <span>${d.needs_review ? "Routed to <b>human review</b> — the graph will pause." : "Routed to <b>finalise</b> — no review needed."}</span>
    </div>
    ${reasons.length ? `<ul class="unsupported" style="margin-top:10px">${reasons.map((x) => `<li>${x}</li>`).join("")}</ul>` : ""}
    <div class="meter" title="grounding score ${pct}%">
      <div class="fill" style="width:${pct}%;background:${color}"></div>
      <div class="thresh" style="left:${d.threshold * 100}%" data-label="threshold ${Math.round(d.threshold * 100)}%"></div>
    </div>
    <dl class="kv">
      <dt>Grounding score</dt><dd>${Number(r.grounding ?? 1).toFixed(2)}</dd>
      <dt>PII masked</dt><dd>${r.pii_masked ? `${r.pii_masked} item(s)` : "none"}</dd>
      <dt>Sensitive intent</dt><dd>${esc(r.sensitive_intent || "none")}</dd>
      <dt>Ungrounded numbers</dt><dd>${ungrounded.length ? "" : "none"}</dd>
    </dl>
    ${ungrounded.length ? `<ul class="unsupported">${ungrounded.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}`;
}

function renderReview() {
  const r = state.run.guardrailReport || {};
  const reasons = [];
  const intent = r.sensitive_intent || "none";
  if (intent !== "none") reasons.push(`Sensitive intent flagged: <b>${esc(intent)}</b>`);
  const thresh = state.cfg.grounding_threshold;
  if (r.grounding != null && r.grounding < thresh)
    reasons.push(`Grounding score ${Number(r.grounding).toFixed(2)} is below the ${thresh} threshold`);
  for (const n of r.ungrounded_numbers || []) reasons.push(`Number <code>${esc(n)}</code> not found in the context`);
  if (r.pii_masked) reasons.push(`${r.pii_masked} PII item(s) were masked`);

  $("#reviewBody").innerHTML = `
    <div class="paused-banner">⏸ Graph paused before <code>human_review</code> · state saved under thread
      <code>${esc(state.run.threadId)}</code></div>
    <p>${reasons.length
      ? `Why this needs a human: ${reasons.join("; ")}. Check the draft against the reranked extracts above, then decide.`
      : "Check the draft against the reranked extracts above, then decide."}</p>
    <textarea id="reviewText">${esc(state.run.draft || "")}</textarea>
    <input type="text" id="reviewNote" placeholder="Note for the log (optional)">
    <div class="actions">
      <button class="btn-ok" id="approveBtn">Approve</button>
      <button class="btn-edit" id="saveEditBtn" disabled>Save edit</button>
      <button class="btn-bad" id="rejectBtn">Reject</button>
    </div>`;

  $("#reviewText").addEventListener("input", () => {
    $("#saveEditBtn").disabled = $("#reviewText").value === (state.run.draft || "");
  });
  $("#approveBtn").addEventListener("click", () => submitReview("approve", false));
  $("#saveEditBtn").addEventListener("click", () => submitReview("edit", true));
  $("#rejectBtn").addEventListener("click", () => submitReview("reject", false));
}

async function submitReview(decision, edited) {
  const threadId = state.run.threadId;
  const note = $("#reviewNote").value.trim();
  const body = { decision, note };
  if (edited) body.edited = $("#reviewText").value;
  setStep("human_review", "running", "resuming...");
  $$("#reviewBody button, #reviewBody input, #reviewBody textarea").forEach((b) => (b.disabled = true));
  try {
    const resp = await fetch(`/api/review/${encodeURIComponent(threadId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`${resp.status} ${await resp.text()}`);
    const { events } = await resp.json();
    events.forEach((e) => handleEvent(e.event, e.data));
  } catch (e) {
    showError(e.message);
    $$("#reviewBody button, #reviewBody input, #reviewBody textarea").forEach((b) => (b.disabled = false));
    $("#saveEditBtn").disabled = $("#reviewText").value === (state.run.draft || "");
    setStep("human_review", "paused", "waiting for you");
  }
}

function renderFinal(text, cls, note) {
  const el = $(".final");
  el.className = `card body final ${cls}`;
  el.innerHTML = `<div class="answer-meta">${esc(note)}</div>
                  ${text ? `<div class="answer">${md(text)}</div>` : ""}`;
}

/* ------------------------------------------------------------------ */
/* Audit trail                                                         */
/* ------------------------------------------------------------------ */
function auditText(p) {
  const steps = (p.steps || []).map((s) => `    ${s}`).join("\n");
  const searches = (p.search_log || []).map((s) => `    ${s}`).join("\n");
  return `## ${p.question}\n\n**Steps**\n${steps}\n\n**Searches**\n${searches}\n\n**Answer**\n${p.final_answer}`;
}

function renderAudit(p) {
  const text = auditText(p);
  $("#auditPre").textContent = text;
  $("#panel-audit").classList.remove("hidden");
}

function copyAudit() {
  const text = $("#auditPre").textContent;
  const done = () => {
    const b = $("#copyAudit");
    b.textContent = "Copied ✓";
    setTimeout(() => (b.textContent = "Copy"), 1800);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => selectAuditAndCopy(text, done));
  } else {
    selectAuditAndCopy(text, done);
  }
}

function selectAuditAndCopy(text, done) {
  const pre = $("#auditPre");
  const range = document.createRange();
  range.selectNodeContents(pre);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  try { document.execCommand("copy"); done(); } catch { showError("copy failed"); }
}

/* ------------------------------------------------------------------ */
/* Drawer                                                              */
/* ------------------------------------------------------------------ */
function openDrawer(id) {
  const c = state.run.keptIndex[id] || state.run.chunkIndex[id];
  if (!c) return;
  $("#drawerTitle").innerHTML = `
    <span class="doc-pill" data-doc="${esc(c.doc_type)}">${esc(c.doc_type)}</span>
    <b>p.${esc(c.page)}</b>${c.doc_date ? `<span class="score"> · ${esc(c.doc_date)}</span>` : ""}
    <span class="score">sim ${(+c.score).toFixed(4)}</span>
    ${c.rerank_score != null ? `<span class="score"> · rr ${(+c.rerank_score).toFixed(4)}</span>` : ""}
    ${c.embed_rank ? `<span class="score"> · was #${c.embed_rank}</span>` : ""}
    ${c.rerank_rank ? `<span class="score"> · rerank #${c.rerank_rank}</span>` : ""}`;
  $("#drawerBody").textContent = c.text;
  $("#drawer").classList.remove("hidden");
}
function closeDrawer() { $("#drawer").classList.add("hidden"); }

/* ------------------------------------------------------------------ */
/* Answer rendering                                                    */
/* ------------------------------------------------------------------ */
function md(src) {
  const lines = esc(src).split("\n");
  let html = "", list = null;
  const close = () => { if (list) { html += `</${list}>`; list = null; } };
  const inline = (s) => {
    s = s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    s = s.replace(/\[(prd|pricing|releases|competitive|insights)\s+p\.\d+\]/gi,
      (m) => `<span class="doc-pill" data-doc="${m.slice(1, m.indexOf(" ")).toLowerCase()}">${m}</span>`);
    s = s.replace(/\[EMAIL REDACTED\]/g, '<span class="redact">[EMAIL REDACTED]</span>');
    s = s.replace(/\[PHONE REDACTED\]/g, '<span class="redact">[PHONE REDACTED]</span>');
    return s;
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    let m;
    if ((m = line.match(/^\s*[-*•]\s+(.*)/))) { if (list !== "ul") { close(); html += "<ul>"; list = "ul"; } html += `<li>${inline(m[1])}</li>`; }
    else if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) { if (list !== "ol") { close(); html += "<ol>"; list = "ol"; } html += `<li>${inline(m[1])}</li>`; }
    else if (!line.trim()) { }
    else { close(); html += `<p>${inline(line)}</p>`; }
  }
  close();
  return html;
}

/* ------------------------------------------------------------------ */
/* Misc                                                                */
/* ------------------------------------------------------------------ */
function showError(msg) { const b = $("#errorBox"); b.textContent = msg; b.classList.remove("hidden"); }
function hideError() { $("#errorBox").classList.add("hidden"); }
