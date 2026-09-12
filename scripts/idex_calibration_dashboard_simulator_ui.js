(() => {
  if (!window.__IDEX_SIMULATOR__) return;

  const scenarios = [
    "idle", "active-step-1", "active-step-2", "active-step-3", "active-step-4",
    "active-step-5", "active-step-6", "active-step-7", "delayed-heartbeat",
    "stale-heartbeat", "failed-bed", "failed-tool", "failed-mesh",
    "accepted-bed-active-tool", "failed-tool-rerun", "stale-mesh", "ready", "invalid-mixed-state",
  ];
  const panel = document.createElement("aside");
  panel.id = "idex-simulator-controls";
  panel.setAttribute("aria-label", "Local simulator controls");
  panel.innerHTML = `
    <style>
      #idex-simulator-controls{position:fixed;z-index:50;right:16px;bottom:16px;width:min(360px,calc(100vw - 32px));max-height:calc(100vh - 32px);overflow:auto;background:#152131;color:#e8f0f8;border:1px solid #4f90c5;border-radius:10px;padding:14px;box-shadow:0 12px 36px #0009;font:13px/1.35 system-ui,sans-serif}
      #idex-simulator-controls h2{margin:0 0 5px;font-size:16px}#idex-simulator-controls p{margin:4px 0 10px;color:#b7c8d9}#idex-simulator-controls section{border-top:1px solid #2f4660;margin-top:10px;padding-top:10px}
      #idex-simulator-controls button{margin:3px;padding:5px 7px;border:1px solid #597a99;border-radius:5px;background:#22374d;color:inherit;cursor:pointer}#idex-simulator-controls button:hover{background:#315674}
      #idex-simulator-controls input{width:74px;margin:3px;padding:5px;border:1px solid #597a99;border-radius:5px;background:#0d1824;color:inherit}#idex-simulator-controls .danger{border-color:#b95555}#idex-simulator-controls code{display:block;overflow-wrap:anywhere;color:#a9cdf0}.sim-ok{color:#6ee7a2}.sim-error{color:#ff9a9a}
      #idex-sim-log{margin:6px 0 0;padding-left:18px;max-height:96px;overflow:auto;color:#b7c8d9}#idex-sim-log li{margin:2px 0}
    </style>
    <h2>Local simulator</h2><p>Controls affect only localhost simulation state.</p>
    <section><strong>Scenarios</strong><div id="sim-scenarios"></div></section>
    <section><strong>Events</strong><div id="sim-events">
      <div>Start: <button data-action="start" data-scope="full">full</button><button data-action="start" data-scope="bed_reference">bed</button><button data-action="start" data-scope="tool_alignment">tool</button><button data-action="start" data-scope="mesh_refresh">mesh</button><button data-action="restart">Restart</button></div>
      <div>Set step: ${[1, 2, 3, 4, 5, 6, 7].map((number) => `<button data-action="step" data-number="${number}">${number}</button>`).join("")}</div>
      <div>Progress <input id="sim-progress" value="1/47" aria-label="Contact progress"><button data-action="progress">Apply</button><button data-action="heartbeat">Heartbeat</button></div>
      <div>Finish step: ${[1, 2, 3, 4, 5, 6, 7].map((number) => `<button data-action="complete-step" data-number="${number}">${number}</button>`).join("")}</div>
      <div>Finish chapter: <button data-action="complete-chapter" data-chapter="bed_reference">bed</button><button data-action="complete-chapter" data-chapter="tool_alignment">tool</button><button data-action="complete-chapter" data-chapter="mesh">mesh</button></div>
      <div>Fail step <input id="sim-fail-step" value="4" aria-label="Fail step"><input id="sim-fail-reason" value="Simulated limit failed" aria-label="Failure reason"><button class="danger" data-action="fail-step">Fail</button></div>
      <div>Heartbeat age <input id="sim-heartbeat-age" value="20" aria-label="Heartbeat age seconds"><button data-action="set-heartbeat-age">Apply</button><button data-action="set-printer" data-state="ready">Printer ready</button><button data-action="set-printer" data-state="not_homed">Not homed</button><button data-action="set-printer" data-state="error">Printer error</button><button data-action="reset">Reset</button></div>
    </div></section>
    <section><strong>State</strong><code id="sim-state">Loading…</code><div id="sim-diagnostics"></div><strong>Event log</strong><ol id="idex-sim-log"></ol></section>`;
  document.body.append(panel);
  const scenarioRoot = panel.querySelector("#sim-scenarios");
  scenarios.forEach((name) => {
    const button = document.createElement("button");
    button.textContent = name.replaceAll("-", " ");
    button.dataset.scenario = name;
    scenarioRoot.append(button);
  });

  async function post(body) {
    const response = await fetch("/__sim__/event", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || response.statusText);
    await refresh(payload);
  }
  function render(payload) {
    const attempt = payload.current?.attempt || {};
    const activity = payload.activity || {};
    const heartbeat = Date.parse(activity.heartbeat_at || "");
    const age = Number.isFinite(heartbeat) ? Math.max(0, Math.floor((Date.now() - heartbeat) / 1000)) : "—";
    panel.querySelector("#sim-state").textContent = `scenario=${payload.scenario}\nattempt_id=${attempt.attempt_id || "—"}\nstatus=${attempt.status || payload.current?.status || "idle"}\nactivity_id=${activity.activity_id || "—"}\nactivity=${activity.state || "idle"} step=${activity.step || "—"}\nheartbeat_age_s=${age}\nheartbeat=${activity.heartbeat_at || "—"}`;
    const diagnostics = panel.querySelector("#sim-diagnostics");
    diagnostics.className = payload.diagnostics?.length ? "sim-error" : "sim-ok";
    diagnostics.textContent = payload.diagnostics?.length ? `Inconsistent: ${payload.diagnostics.join("; ")}` : "Consistency checks: OK";
    const log = panel.querySelector("#idex-sim-log");
    log.innerHTML = (payload.events || []).slice(-10).reverse().map((event) => `<li>${String(event).replace(/[&<>]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[char]))}</li>`).join("");
  }
  async function refresh(payload = null) {
    try { render(payload || await (await fetch("/__sim__/state", {cache: "no-store"})).json()); }
    catch (error) { panel.querySelector("#sim-diagnostics").className = "sim-error"; panel.querySelector("#sim-diagnostics").textContent = error.message; }
  }
  panel.addEventListener("click", (event) => {
    const button = event.target.closest("button"); if (!button) return;
    if (button.dataset.scenario) post({action: "scenario", name: button.dataset.scenario}).catch(() => refresh());
    else if (button.dataset.action) {
      const body = {action: button.dataset.action};
      ["scope", "number", "chapter", "seconds"].forEach((key) => { if (button.dataset[key] !== undefined) body[key] = key === "number" || key === "seconds" ? Number(button.dataset[key]) : button.dataset[key]; });
      if (body.action === "progress") {
        const [completed, total] = panel.querySelector("#sim-progress").value.split("/", 2).map(Number);
        body.completed = completed; body.total = total;
      }
      if (body.action === "fail-step") {
        body.number = Number(panel.querySelector("#sim-fail-step").value);
        body.reason = panel.querySelector("#sim-fail-reason").value;
      }
      if (body.action === "set-heartbeat-age") body.seconds = Number(panel.querySelector("#sim-heartbeat-age").value);
      post(body).catch(() => refresh());
    }
  });
  refresh();
  setInterval(refresh, 1000);
})();
