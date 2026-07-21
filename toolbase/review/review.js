"use strict";

const state = { proposal: null, ledger: null, decisions: new Map(), filter: "pending" };
const $ = (selector, root = document) => root.querySelector(selector);

function formatKey(value) {
  return value.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());
}

function factValue(fact) {
  if (fact.value_text !== undefined) return fact.value_text;
  if (fact.value_number !== undefined) return `${fact.value_number}${fact.unit ? ` ${fact.unit}` : ""}`;
  return "—";
}

function decisionStorageKey() {
  return `toolbase-review:${state.ledger.proposal_sha256}`;
}

function persist() {
  localStorage.setItem(decisionStorageKey(), JSON.stringify([...state.decisions.values()]));
}

function setDecision(row, decision, card) {
  const reviewer = $(".reviewer", card).value.trim();
  const notes = $(".notes", card).value.trim();
  if (!reviewer) {
    $(".reviewer", card).focus();
    alert("Enter the reviewer name before recording a decision.");
    return;
  }
  if (decision === "quarantined" && !notes) {
    $(".notes", card).focus();
    alert("Explain why this record is being quarantined.");
    return;
  }
  state.decisions.set(row.proposal_row_id, {
    proposal_row_id: row.proposal_row_id,
    tool_id: row.tool_lookup.tool_id,
    decision,
    reviewer,
    decided_at: new Date().toISOString().slice(0, 10),
    capture_method: "local_review_screen",
    notes: notes || (decision === "approved" ? "Exact proposal approved against the displayed manufacturer catalog page." : null),
  });
  persist();
  render();
}

function clearDecision(row) {
  const original = state.ledger.decisions.find(item => item.proposal_row_id === row.proposal_row_id);
  state.decisions.set(row.proposal_row_id, { ...original, decision: "pending", reviewer: null, decided_at: null, notes: null });
  persist();
  render();
}

function addDefinition(list, label, value) {
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = value ?? "—";
  list.append(term, description);
}

function renderCard(row, position) {
  const fragment = $("#row-template").content.cloneNode(true);
  const card = $(".review-card", fragment);
  const decision = state.decisions.get(row.proposal_row_id);
  const proposed = row.proposed;
  $(".row-number", card).textContent = `Tool ${position + 1} of ${state.proposal.rows.length}`;
  $(".tool-id", card).textContent = row.tool_lookup.tool_id;
  const badge = $(".decision-badge", card);
  badge.textContent = formatKey(decision.decision);
  badge.className = `decision-badge ${decision.decision}`;

  const currentList = $(".current-data", card);
  Object.entries(row.current_summary).forEach(([key, value]) => addDefinition(currentList, formatKey(key), value));
  $(".proposed-description", card).textContent = proposed.tool_updates.description;
  const factList = $(".proposed-facts", card);
  proposed.facts.forEach(fact => addDefinition(factList, formatKey(fact.fact_key), factValue(fact)));
  const gradeList = $(".grade-list", card);
  proposed.grade_options.forEach(option => {
    const grade = document.createElement("span");
    grade.className = "grade";
    grade.textContent = option.code;
    gradeList.append(grade);
  });

  const firstAssertion = proposed.facts[0] || proposed.grade_options[0];
  const cited = firstAssertion.evidence;
  const source = state.proposal.sources.find(item => item.source_id === cited.source_id);
  const imageUrl = `/api/source-page?source_id=${encodeURIComponent(cited.source_id)}&page=${cited.pdf_page}`;
  $(".source-ref", card).textContent = `${source.title} · ${source.document_edition} · PDF page ${cited.pdf_page}`;
  $(".source-image", card).src = imageUrl;
  $(".open-page", card).href = imageUrl;
  $(".source-excerpt", card).textContent = `Extracted row: ${cited.source_raw_text}`;

  const cautions = $(".conflicts ul", card);
  row.conflicts.forEach(conflict => {
    const item = document.createElement("li");
    item.textContent = conflict;
    cautions.append(item);
  });
  $(".reviewer", card).value = decision.reviewer || localStorage.getItem("toolbase-reviewer") || "";
  $(".notes", card).value = decision.notes || "";
  $(".reviewer", card).addEventListener("change", event => localStorage.setItem("toolbase-reviewer", event.target.value.trim()));
  $(".approve", card).addEventListener("click", () => setDecision(row, "approved", card));
  $(".quarantine", card).addEventListener("click", () => setDecision(row, "quarantined", card));
  $(".clear", card).addEventListener("click", () => clearDecision(row));
  return card;
}

function visibleForFilter(decision) {
  if (state.filter === "all") return true;
  if (state.filter === "pending") return decision === "pending";
  if (state.filter === "approved") return decision.startsWith("approved");
  return decision === state.filter;
}

function render() {
  const list = $("#review-list");
  list.replaceChildren();
  const sorted = [...state.proposal.rows].sort((a, b) => {
    const aPending = state.decisions.get(a.proposal_row_id).decision === "pending" ? 0 : 1;
    const bPending = state.decisions.get(b.proposal_row_id).decision === "pending" ? 0 : 1;
    return aPending - bPending;
  });
  sorted.forEach(row => {
    const decision = state.decisions.get(row.proposal_row_id).decision;
    if (visibleForFilter(decision)) list.append(renderCard(row, state.proposal.rows.indexOf(row)));
  });
  const values = [...state.decisions.values()];
  const pending = values.filter(item => item.decision === "pending").length;
  $("#pending-count").textContent = pending;
  $("#reviewed-count").textContent = values.length - pending;
  $("#batch-count").textContent = values.length;
  $("#export").disabled = false;
}

function exportLedger() {
  const decisions = state.proposal.rows.map(row => state.decisions.get(row.proposal_row_id));
  const complete = decisions.every(item => item.decision !== "pending");
  const payload = {
    ...state.ledger,
    status: complete ? "complete" : "pending",
    review_completed_at: complete ? new Date().toISOString().slice(0, 10) : null,
    import_allowed: complete,
    decisions,
  };
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${state.proposal.proposal_id}.decisions.json`;
  link.click();
  URL.revokeObjectURL(link.href);
}

async function initialize() {
  const [proposalResponse, ledgerResponse] = await Promise.all([fetch("/api/proposal"), fetch("/api/ledger")]);
  state.proposal = await proposalResponse.json();
  state.ledger = await ledgerResponse.json();
  const stored = JSON.parse(localStorage.getItem(decisionStorageKey()) || "null");
  (stored || state.ledger.decisions).forEach(item => state.decisions.set(item.proposal_row_id, item));
  $("#batch-title").textContent = state.proposal.title;
  $("#batch-purpose").textContent = state.proposal.purpose;
  $("#filter").addEventListener("change", event => { state.filter = event.target.value; render(); });
  $("#export").addEventListener("click", exportLedger);
  render();
}

initialize().catch(error => {
  $("#batch-title").textContent = "Review screen could not load";
  $("#batch-purpose").textContent = error.message;
});
