// Chat card of the Analysis tab (llm/web.py): questions to a local model about the open analysis (its input file
// job.inp, an imported mesh file, the solver messages and files of the run folder) and about the reference documents.
// Added to the side panel of the Analysis tab, with a Chat button in its tool bar. Ctrl+Enter sends the question.
(function () {
  const pane = document.getElementById("tab-fea"), panel = document.getElementById("fa-panel");
  if (!pane || !panel) return;
  const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const conv = "c" + Math.random().toString(36).slice(2, 10);
  let job = null, timer = null;

  const css = document.createElement("style");
  css.textContent = `
#fa-llm-log { max-height: 420px; overflow-y: auto; margin-bottom: 8px; }
#fa-llm-log .llm-q { background: var(--bg); border: 1px solid var(--line); border-radius: 4px; padding: 5px 7px; margin: 8px 0 4px; white-space: pre-wrap; }
#fa-llm-log .llm-a { white-space: pre-wrap; padding: 2px 2px 6px; color: var(--text); }
#fa-llm-log .llm-a code, #fa-llm-log .llm-q code { font-family: Consolas, monospace; font-size: 12px; }
#fa-llm-log details { font-size: 12px; color: var(--muted); margin: 2px 0; }
#fa-llm-log details pre { white-space: pre-wrap; word-break: break-all; margin: 4px 0; font-size: 11px; }
#fa-llm-q { min-height: 52px; }`;
  document.head.appendChild(css);

  const card = document.createElement("section");
  card.className = "fa-card";
  card.id = "fa-llm-card";
  card.innerHTML = `<h2>Chat</h2><p class="hint" id="fa-llm-status">Model server: checking</p><div id="fa-llm-log"></div>` +
    `<textarea id="fa-llm-q" rows="3" placeholder="Question about the analysis, its input file, the solver messages or the reference documents (Ctrl+Enter)"></textarea>` +
    `<div class="row" style="margin-top:6px"><button type="button" id="fa-llm-ask" class="primary">Ask</button>` +
    `<button type="button" id="fa-llm-stop" disabled title="Stop after the current model request">Stop</button>` +
    `<button type="button" id="fa-llm-clear" title="Clear the conversation">Clear</button><span class="hint" id="fa-llm-state" style="margin:0"></span></div>`;
  (document.getElementById("fa-props") || panel).appendChild(card);
  const $ = id => document.getElementById(id);

  const bar = pane.querySelector(".ann-top");
  if (bar) {
    const b = document.createElement("button");
    b.type = "button";
    b.id = "fa-llm-show";
    b.textContent = "Chat";
    b.title = "Chat card: questions to the local model about this analysis and the reference documents";
    b.onclick = () => { card.scrollIntoView({ block: "start", behavior: "smooth" }); $("fa-llm-q").focus(); };
    bar.appendChild(b);
  }

  function fmt(t) {
    return esc(t).replace(/`([^`\n]+)`/g, "<code>$1</code>").replace(/\*\*([^*\n]+)\*\*/g, "$1");
  }
  function analysis() {
    const FA = window.__fea && window.__fea.FA;
    const d = FA && FA.doc;
    if (!d) return {};
    const s = d.source || {};
    return { name: d.name || "", solver: d.solver || "calculix", source: { type: s.type || "", path: s.path || "", name: s.name || "" } };
  }
  async function getJSON(url, opt) {
    const r = await fetch(url, opt);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || r.statusText);
    return j;
  }
  const post = (url, body) => getJSON(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

  async function checkStatus() {
    try {
      const s = await getJSON("/api/llm/status");
      const have = !s.models.length || s.models.includes(s.model);
      $("fa-llm-status").textContent = s.server
        ? `Model ${s.model} at ${s.url}${have ? "" : " (not downloaded: ollama pull " + s.model + ")"}; ${s.docs} reference document(s)`
        : `Model server not reachable at ${s.url}: start Ollama`;
      $("fa-llm-status").classList.toggle("err", !s.server || !have);
    } catch (e) {
      $("fa-llm-status").textContent = "Chat not available: " + e.message;
      $("fa-llm-status").classList.add("err");
    }
  }

  function busy(on) {
    $("fa-llm-ask").disabled = on;
    $("fa-llm-stop").disabled = !on;
    $("fa-llm-clear").disabled = on;
  }

  async function ask() {
    const q = $("fa-llm-q").value.trim();
    if (!q || job) return;
    const log = $("fa-llm-log");
    const item = document.createElement("div");
    item.innerHTML = `<div class="llm-q">${fmt(q)}</div><details><summary>Tool calls (0)</summary><pre></pre></details><div class="llm-a"></div>`;
    log.appendChild(item);
    log.scrollTop = log.scrollHeight;
    $("fa-llm-q").value = "";
    busy(true);
    try {
      job = (await post("/api/llm/ask", { conv, question: q, analysis: analysis() })).job;
    } catch (e) {
      item.querySelector(".llm-a").innerHTML = `<span class="hint err">${esc(e.message)}</span>`;
      busy(false);
      return;
    }
    const poll = async () => {
      let j;
      try { j = await getJSON("/api/llm/job/" + job); } catch (e) { j = { state: "error", error: e.message, events: [] }; }
      const ev = (j.events || []).filter(x => x.startsWith("[tool]") || x.startsWith("[index]"));
      item.querySelector("summary").textContent = `Tool calls (${ev.filter(x => x.startsWith("[tool]")).length})`;
      item.querySelector("pre").textContent = ev.join("\n");
      if (j.state === "running") {
        $("fa-llm-state").textContent = `Working ${Math.round(j.seconds || 0)} s`;
        timer = setTimeout(poll, 1000);
        return;
      }
      const timing = (j.events || []).filter(x => x.startsWith("[") && !x.startsWith("[tool]") && !x.startsWith("[index]")).pop() || "";
      item.querySelector(".llm-a").innerHTML = j.state === "done" ? fmt(j.answer || "") : `<span class="hint err">${esc(j.error || "error")}</span>`;
      $("fa-llm-state").textContent = timing;
      job = null;
      busy(false);
      log.scrollTop = log.scrollHeight;
      checkStatus();
    };
    poll();
  }

  $("fa-llm-ask").onclick = ask;
  $("fa-llm-q").addEventListener("keydown", e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); ask(); } });
  $("fa-llm-stop").onclick = () => { if (job) post("/api/llm/stop/" + job).catch(() => {}); $("fa-llm-state").textContent = "Stopping after the current model request"; };
  $("fa-llm-clear").onclick = async () => {
    try { await post("/api/llm/clear", { conv }); } catch (e) { /* conversation kept on the server */ }
    $("fa-llm-log").innerHTML = "";
    $("fa-llm-state").textContent = "";
  };
  document.querySelectorAll('.tab[data-tab="fea"]').forEach(t => t.addEventListener("click", checkStatus));
  checkStatus();
})();
