const headline = document.querySelector("#headline");
const lastSuccessful = document.querySelector("#last-successful");
const updated = document.querySelector("#updated");
const calibrationChapter = document.querySelector("#calibration-chapter");
const calibrationHeading = document.querySelector("#calibration-heading");
const calibrationState = document.querySelector("#calibration-state");
const calibrationTools = document.querySelector("#calibration-tools");
const calibrationOutcome = document.querySelector("#calibration-outcome");
const verificationChapter = document.querySelector("#verification-chapter");
const verificationState = document.querySelector("#verification-state");
const verificationTools = document.querySelector("#verification-tools");
const verificationOutcome = document.querySelector("#verification-outcome");
const readiness = document.querySelector("#readiness");
const activity = document.querySelector("#activity");
const activityTitle = document.querySelector("#activity-title");
const activityDetail = document.querySelector("#activity-detail");
const activitySignal = document.querySelector("#activity-signal");
const printerState = document.querySelector("#printer-state");
const printerX = document.querySelector("#printer-x");
const printerY = document.querySelector("#printer-y");
const printerZ = document.querySelector("#printer-z");
const printerHomed = document.querySelector("#printer-homed");
const printerPrintState = document.querySelector("#printer-print-state");
const printerTemperatures = document.querySelector("#printer-temperatures");
const printerCamera = document.querySelector("#printer-camera-image");
const consoleState = document.querySelector("#console-state");
const printerConsole = document.querySelector("#printer-console");
const bedReferenceChapter = document.querySelector("#bed-reference-chapter");
const bedReferenceState = document.querySelector("#bed-reference-state");
const toolAlignmentChapter = document.querySelector("#tool-alignment-chapter");
const toolAlignmentState = document.querySelector("#tool-alignment-state");
const bedMeshChapter = document.querySelector("#bed-mesh-chapter");
const bedMeshState = document.querySelector("#bed-mesh-state");
const bedReferenceRoadmap = document.querySelector("#bed-reference-roadmap");
const toolAlignmentRoadmap = document.querySelector("#tool-alignment-roadmap");
const bedMeshRoadmap = document.querySelector("#bed-mesh-roadmap");
const bedReference = document.querySelector("#bed-reference");
const bedMesh = document.querySelector("#bed-mesh");
const empty = document.querySelector("#empty");
const plotModal = document.querySelector("#plot-modal");
const plotModalImage = document.querySelector("#plot-modal-image");
const plotModalClose = document.querySelector("#plot-modal-close");
const provenanceElements = {
  bed_reference: document.querySelector("#bed-reference-provenance"),
  tool_alignment: document.querySelector("#tool-alignment-provenance"),
  mesh: document.querySelector("#bed-mesh-provenance"),
};

const WORKFLOW_STEPS = Object.freeze([
  {
    number: 1,
    chapter: "bed-reference",
    title: "Bed Center Z=0 measurement",
    description: "Find the rough bed reference at the centre with overlapping guarded Eddy bands.",
  },
  {
    number: 2,
    chapter: "bed-reference",
    title: "Bed Center Z=0 calibration update",
    description: "Apply one common Z correction to both toolheads and deploy the new datum.",
  },
  {
    number: 3,
    chapter: "bed-reference",
    title: "Bed Center Z=0 verification",
    description: "Verify five T0 centre taps from Z=2 mm toward Z=-1 mm; no discovery is repeated.",
  },
  {
    number: 4,
    chapter: "tool-alignment",
    title: "T0/T1 toolhead alignment",
    description: "Align X/Y/Z with 47-contact ball calibration and 13-contact verification.",
  },
  {
    number: 5,
    chapter: "bed-mesh",
    title: "Acquire and save the Tap mesh",
    description: "Measure the bed surface and persist the accepted matrix to calib.yaml.",
  },
  {
    number: 6,
    chapter: "bed-mesh",
    title: "Redeploy and verify the mesh",
    description: "Regenerate, redeploy, reload, and prove the active mesh matches the accepted matrix.",
  },
  {
    number: 7,
    chapter: "bed-mesh",
    title: "Accepted calibration chain readiness",
    description: "Declare READY TO PRINT when the compatible accepted bed, tool, and mesh chapters are deployed and verified.",
  },
]);

const WORKFLOW_STATUS_LABELS = Object.freeze({
  pending: "Pending",
  running: "In progress",
  passed: "Passed",
  failed: "Failed",
  blocked: "Blocked",
  remeasuring: "Re-measuring",
});

let dashboardContentHash = "";
let activityContentHash = "";
let printerStatusContentHash = "";
let printerConsoleContentHash = "";
let currentDashboardData = null;
let currentActivityData = null;
let cameraRetryTimer = null;

async function startCameraStream() {
  if (!printerCamera || printerCamera.src) return;
  // The webcam endpoint is an MJPEG stream.  Let the browser's native image
  // decoder consume it, as Mainsail does; a fetch/read loop would hold a
  // connection open and can delay the dashboard's JSON polls.
  printerCamera.src = printerCamera.dataset.streamUrl || "/webcam/?action=stream";
  printerCamera.onerror = () => {
    if (cameraRetryTimer) clearTimeout(cameraRetryTimer);
    cameraRetryTimer = setTimeout(() => {
      if (printerCamera) {
        printerCamera.removeAttribute("src");
        startCameraStream();
      }
    }, 2000);
  };
}

function stopCameraStream() {
  if (cameraRetryTimer) clearTimeout(cameraRetryTimer);
  cameraRetryTimer = null;
}

// Z is intentionally exaggerated for readability.  Ball-cap heights vary by
// only a few hundred microns, so a literal 1:1 projection makes every contact
// appear coplanar even though the measured trigger_z values are present.
const ISOMETRIC_VIEW = Object.freeze({
  width: 540,
  height: 390,
  xySpanPixels: 247.5,
  zToXyScale: 1.0,
  rotationDegrees: 10,
  gridDivisions: 6,
});

function format(value, digits = 3) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "—";
}

function formatMillimetres(value, digits = 3) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(digits)} mm` : "—";
}

function formatMicrometres(value, digits = 1) {
  return Number.isFinite(Number(value))
    ? `${(Number(value) * 1000).toFixed(digits)} µm`
    : "—";
}

function formatTemperature(value) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)} °C` : "—";
}

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function contentHash(value) {
  let hash = 2166136261;
  for (const character of stableStringify(value)) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

function conciseError(error) {
  if (!error) return "";
  const text = String(error);
  const jsonStart = text.indexOf("{");
  if (jsonStart >= 0) {
    try {
      const payload = JSON.parse(text.slice(jsonStart));
      const message = payload?.error?.message;
      if (message) return String(message);
    } catch (_) {
      // Fall back to the first line below for non-JSON failures.
    }
  }
  const firstLine = text.split("\n", 1)[0].trim();
  return firstLine.length > 180 ? `${firstLine.slice(0, 177)}…` : firstLine;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[character]));
}

function latestMeasurement(run) {
  return [...(run.records || [])].reverse().find((record) => record.status === "completed");
}

function verificationCentreContacts(run) {
  return (run.records || []).filter(
    (record) => record.phase === "verification_centre" && record.status === "completed",
  );
}

function centreTapStats(run) {
  const records = verificationCentreContacts(run);
  const values = records.map((record) => Number(record.trigger_z)).filter(Number.isFinite);
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const sigma = Math.sqrt(values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length);
  return { count: values.length, median, sigma };
}

function summaryNumbers(run) {
  const summary = run.summary || {};
  if (summary.phase_3?.refined_center || summary.phase_2?.refined_center) {
    const center = summary.phase_3?.refined_center || summary.phase_2.refined_center;
    return [["Centre X", center.x, "mm"], ["Centre Y", center.y, "mm"], ["Centre Z median", summary.phase_4?.statistics?.median, "mm"]];
  }
  if (summary.estimated_center) {
    const center = summary.estimated_center;
    return [["Centre X", center.x, "mm"], ["Centre Y", center.y, "mm"], ["Centre Z", center.trigger_z, "mm"]];
  }
  const verificationCentre = centreTapStats(run);
  if (verificationCentre) {
    return [["Centre X", run.records?.[0]?.commanded_x, "mm"], ["Centre Y", run.records?.[0]?.commanded_y, "mm"], ["Centre Z median", verificationCentre.median, "mm"]];
  }
  const latest = latestMeasurement(run) || {};
  return [["Latest X", latest.commanded_x, "mm"], ["Latest Y", latest.commanded_y, "mm"], ["Trigger Z", latest.trigger_z, "mm"]];
}

function calculationDetails(run) {
  const summary = run.summary || {};
  if (summary.phase_3?.harmonic) {
    const first = summary.phase_2 || {};
    const final = summary.phase_3;
    return `<dl class="calculation-details">
      <dt>First ring correction</dt><dd>ΔX ${formatMicrometres(first.harmonic?.dx_mm)} · ΔY ${formatMicrometres(first.harmonic?.dy_mm)}</dd>
      <dt>Final ring correction</dt><dd>ΔX ${formatMicrometres(final.harmonic.dx_mm)} · ΔY ${formatMicrometres(final.harmonic.dy_mm)}</dd>
      <dt>Refined ring</dt><dd>${Number(final.ring_round_count || 1)} rounds · ${Number(final.ring_contact_count || 8)} raw taps</dd>
      <dt>Final centre σ</dt><dd>${formatMicrometres(summary.phase_4?.statistics?.standard_deviation)} · 5/5 taps</dd>
    </dl>`;
  }
  if (summary.phase_2?.harmonic) {
    const harmonic = summary.phase_2.harmonic;
    return `<dl class="calculation-details">
      <dt>Ring correction</dt><dd>ΔX ${formatMicrometres(harmonic.dx_mm)} · ΔY ${formatMicrometres(harmonic.dy_mm)}</dd>
      <dt>Final centre</dt><dd>Five taps are stored after the refined XY centre.</dd>
    </dl>`;
  }
  if (summary.harmonic) {
    return `<dl class="calculation-details">
      <dt>Ring correction</dt><dd>ΔX ${formatMicrometres(summary.harmonic.dx_mm)} · ΔY ${formatMicrometres(summary.harmonic.dy_mm)}</dd>
      <dt>Centre taps</dt><dd>Five final-centre taps are required.</dd>
    </dl>`;
  }
  return "";
}

function calibrationContactCount(entry) {
  if (!entry) return 47;
  const totals = Object.values(entry.runs || {})
    .map((run) => Number(run?.progress?.total))
    .filter((value) => Number.isFinite(value) && value > 0);
  if (totals.length) return Math.max(...totals);
  const result = entry.result?.data || entry.data || {};
  const procedure = result.calibration_procedure || result.procedure || {};
  const procedureCount = Number(procedure.contact_count);
  if (Number.isFinite(procedureCount) && procedureCount > 0) return procedureCount;
  // Immutable 31-contact artifacts remain valid history and are deliberately
  // labelled as such rather than being relabelled as the new procedure.
  return 31;
}

function contactColour(z, minZ, maxZ) {
  if (!Number.isFinite(Number(z))) return "#d9534f";
  const fraction = (Number(z) - minZ) / Math.max(maxZ - minZ, .001);
  return `hsl(${215 - 150 * fraction} 70% 55%)`;
}

function plotBounds(records, priors, workflow) {
  if (workflow === "calibration" && ["seed_x_min", "seed_x_max", "seed_y_min", "seed_y_max"].every((key) => Number.isFinite(Number(priors?.[key])))) {
    return {
      minX: Number(priors.seed_x_min), maxX: Number(priors.seed_x_max),
      minY: Number(priors.seed_y_min), maxY: Number(priors.seed_y_max),
    };
  }
  const centre = records.find((record) => String(record.phase || "").includes("centre")) || records[0];
  const radius = Number(priors?.ring_radius_mm);
  if (workflow === "verification" && centre && Number.isFinite(radius) && radius > 0) {
    return {
      minX: Number(centre.commanded_x) - radius, maxX: Number(centre.commanded_x) + radius,
      minY: Number(centre.commanded_y) - radius, maxY: Number(centre.commanded_y) + radius,
    };
  }
  const xs = records.map((record) => Number(record.commanded_x));
  const ys = records.map((record) => Number(record.commanded_y));
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const padding = Math.max(Math.max(maxX - minX, maxY - minY, 1) * .12, .5);
  return { minX: minX - padding, maxX: maxX + padding, minY: minY - padding, maxY: maxY + padding };
}

function isometricPlot(records, priors, workflow) {
  const points = records.filter((record) => Number.isFinite(Number(record.commanded_x)) && Number.isFinite(Number(record.commanded_y)));
  if (!points.length) return "<p>No contacts available yet.</p>";
  const completed = points.filter((record) => record.status === "completed" && Number.isFinite(Number(record.trigger_z)));
  const { minX, maxX, minY, maxY } = plotBounds(points, priors, workflow);
  const minZ = completed.length ? Math.min(...completed.map((point) => Number(point.trigger_z))) : 0;
  const maxZ = completed.length ? Math.max(...completed.map((point) => Number(point.trigger_z))) : minZ + 1;
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;
  const xyScale = ISOMETRIC_VIEW.xySpanPixels / Math.max(maxX - minX, maxY - minY, 1);
  const zScale = xyScale * ISOMETRIC_VIEW.zToXyScale;
  const rotation = ISOMETRIC_VIEW.rotationDegrees * Math.PI / 180;
  const project = (x, y, z = minZ) => {
    const deltaX = x - centerX;
    const deltaY = y - centerY;
    const rotatedX = deltaX * Math.cos(rotation) - deltaY * Math.sin(rotation);
    const rotatedY = deltaX * Math.sin(rotation) + deltaY * Math.cos(rotation);
    return [
      ISOMETRIC_VIEW.width / 2
        + (rotatedX - rotatedY) * Math.cos(Math.PI / 6) * xyScale,
      235 + (rotatedX + rotatedY) * Math.sin(Math.PI / 6) * xyScale
        - (z - minZ) * zScale,
    ];
  };
  const baseCorners = [[minX, minY], [maxX, minY], [maxX, maxY], [minX, maxY]].map(([x, y]) => project(x, y));
  const polygon = baseCorners.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const gridLines = Array.from({ length: ISOMETRIC_VIEW.gridDivisions - 1 }, (_, index) => {
    const fraction = (index + 1) / ISOMETRIC_VIEW.gridDivisions;
    const x = minX + (maxX - minX) * fraction;
    const y = minY + (maxY - minY) * fraction;
    const xStart = project(x, minY), xEnd = project(x, maxY);
    const yStart = project(minX, y), yEnd = project(maxX, y);
    return `<line class="grid-line" x1="${xStart[0]}" y1="${xStart[1]}" x2="${xEnd[0]}" y2="${xEnd[1]}"/>
      <line class="grid-line" x1="${yStart[0]}" y1="${yStart[1]}" x2="${yEnd[0]}" y2="${yEnd[1]}"/>`;
  }).join("");
  const latestIndex = points.length - 1;
  return `<svg viewBox="0 0 ${ISOMETRIC_VIEW.width} ${ISOMETRIC_VIEW.height}" role="img" aria-label="Live isometric contact map; vertical stalks begin at the run's lowest measured contact">
    <polygon class="reference-plane" points="${polygon}"/>
    ${gridLines}
    <text class="reference-label" x="10" y="18">Logical XYZ · stalk base Z=${format(minZ)} mm · compact Z scale</text>
    <text class="reference-label" x="10" y="${ISOMETRIC_VIEW.height - 8}">X ${format(minX, 1)}–${format(maxX, 1)} · Y ${format(minY, 1)}–${format(maxY, 1)} · Z visual scale ${ISOMETRIC_VIEW.zToXyScale}× XY</text>
    ${points.map((point, index) => {
      const [baseX, baseY] = project(Number(point.commanded_x), Number(point.commanded_y));
      const hasMeasuredZ = point.status === "completed" && Number.isFinite(Number(point.trigger_z));
      const [headX, headY] = hasMeasuredZ ? project(Number(point.commanded_x), Number(point.commanded_y), Number(point.trigger_z)) : [baseX, baseY];
      const colour = hasMeasuredZ ? contactColour(point.trigger_z, minZ, maxZ) : "#6d839a";
      const marker = point.status === "no_contact" ? "×" : "";
      return `${hasMeasuredZ ? `<line class="stalk" stroke="${colour}" x1="${baseX}" y1="${baseY}" x2="${headX}" y2="${headY}"/>` : ""}
        <circle class="point ${index === latestIndex ? "latest" : ""}" cx="${headX}" cy="${headY}" r="${point.status === "no_contact" ? 5 : 4}" fill="${colour}"/>
        ${marker ? `<text x="${headX - 3}" y="${headY + 4}" fill="#fff" font-size="12">${marker}</text>` : ""}`;
    }).join("")}
  </svg>`;
}

function plotButton(source, alt) {
  return `<button class="plot-button" type="button" data-plot-src="${escapeHtml(source)}" data-plot-alt="${escapeHtml(alt)}"><img src="${escapeHtml(source)}" alt="${escapeHtml(alt)}; click to expand"></button>`;
}

function normaliseStatus(value, fallback = "pending") {
  const status = String(value || "").toLowerCase().replaceAll("-", "_");
  if (["accepted", "completed", "passed", "recorded"].includes(status)) return "passed";
  if (["running", "in_progress", "inprogress"].includes(status)) return "running";
  if (["failed", "aborted", "error"].includes(status)) return "failed";
  if (["blocked", "stale"].includes(status)) return "blocked";
  if (["remeasuring", "re-measuring", "rechecking"].includes(status)) return "remeasuring";
  if (status === "pending") return "pending";
  return fallback;
}

function displayStatus(value, fallback = "pending") {
  const status = normaliseStatus(value, fallback);
  return WORKFLOW_STATUS_LABELS[status] || WORKFLOW_STATUS_LABELS.pending;
}

function setDisplayStatus(element, value, fallback = "pending") {
  if (!element) return;
  const status = normaliseStatus(value, fallback);
  element.className = `status-label ${status}`;
  element.textContent = WORKFLOW_STATUS_LABELS[status] || WORKFLOW_STATUS_LABELS.pending;
}

function displayRunStatus(value) {
  const status = String(value || "idle").toLowerCase();
  return {
    idle: "Idle",
    preparing: "Preparing",
    running: "In progress",
    completed: "Completed",
    failed: "Failed",
    aborted: "Aborted",
  }[status] || "In progress";
}

function displayStage(data) {
  const stage = String(data.stage || data.workflow || "calibration").toLowerCase();
  if (stage.includes("tool_alignment") || stage.includes("verification")) return "Toolhead alignment";
  if (stage.includes("mesh")) return "Mesh and readiness";
  if (stage.includes("reference") || stage.includes("bed_calibration")) return "Bed Z reference";
  return "Calibration workflow";
}

function activeStepNumber(data, chapters, passed, activitySource = null) {
  const activityStep = Number(activitySource?.step ?? data.attempt?.activity?.step ?? data.activity?.step);
  if (Number.isInteger(activityStep) && activityStep >= 1 && activityStep <= 7) return activityStep;
  return stepFromStage(data, chapters, passed);
}

function elapsedSince(iso) {
  const timestamp = Date.parse(iso || "");
  if (!Number.isFinite(timestamp)) return "No signal yet";
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  return seconds < 2 ? "Last signal just now" : `Last signal ${seconds}s ago`;
}

function renderActivity(data, chapters, passed, activitySource = null) {
  if (!activity) return;
  const source = activitySource || data.attempt?.activity || data.activity || {};
  const heartbeat = source.heartbeat_at || data.updated_at;
  const age = Date.parse(heartbeat || "") ? (Date.now() - Date.parse(heartbeat)) / 1000 : Infinity;
  const matching = !source.attempt_id || source.attempt_id === data.attempt?.attempt_id || source.attempt_id === data.batch_id || source.attempt_id === data.run_id;
  const sourceState = String(source.state || "").toLowerCase();
  const effectiveState = sourceState === "idle" ? String(data.status || "idle").toLowerCase() : sourceState || String(data.status || "idle").toLowerCase();
  const terminalRun = ["failed", "completed", "aborted"].includes(String(data.status || "").toLowerCase());
  // A stale volatile activity record must never resurrect a terminal ledger
  // state as BUSY. This is especially important after a coordinator crash,
  // where activity.json is intentionally preserved for diagnosis.
  const active = matching && !terminalRun && ["busy", "preparing", "running"].includes(effectiveState);
  const terminalState = String(data.status || "idle").toLowerCase();
  const state = active ? (age < 15 ? "busy" : age <= 60 ? "delayed" : "stale") : (terminalRun ? terminalState : effectiveState);
  activity.className = `activity ${state}`;
  if (active) {
    const step = activeStepNumber(data, chapters, passed, source);
    const signalLabel = state === "busy" ? "BUSY · Step" : state === "delayed" ? "DELAYED · Step" : "NO RECENT SIGNAL · Step";
    activityTitle.textContent = `${signalLabel} ${step || "?"} — ${WORKFLOW_STEPS.find((item) => item.number === step)?.title || displayStage(data)}`;
    activityDetail.textContent = source.operation || source.progress || "Calibration is still progressing.";
  } else if (state === "failed") {
    activityTitle.textContent = "Calibration stopped";
    activityDetail.textContent = data.error || "The last calibration attempt failed.";
  } else if (state === "completed") {
    activityTitle.textContent = "Calibration attempt complete";
    activityDetail.textContent = "The accepted calibration chain determines readiness.";
  } else {
    activityTitle.textContent = "No calibration activity";
    activityDetail.textContent = "Waiting for a workflow to start.";
  }
  activitySignal.textContent = active && age > 60 ? `NO RECENT SIGNAL · ${elapsedSince(heartbeat)}` : elapsedSince(heartbeat);
}

function renderTool(tool, run, priors) {
  const [status, progress] = [normaliseStatus(run.state, "running"), run.progress || {}];
  const numbers = summaryNumbers(run).map(([label, value, unit]) => `<div class="number"><span>${label}</span><strong>${format(value)} <small>${unit}</small></strong></div>`).join("");
  // Keep every measured contact height in the isometric view.  Ring and seed
  // taps are part of the height map too; hiding their Z values makes the
  // contact geometry look flat and removes the most useful visual cue.
  const plotRecords = run.records || [];
  return `<article class="tool"><h2>${tool}</h2>
    <div class="state ${escapeHtml(status)}">${escapeHtml(displayStatus(status, "running"))} · ${progress.completed || 0}/${progress.total || "?"} contacts</div>
    <div class="numbers">${numbers}</div>
    ${calculationDetails(run)}
    ${isometricPlot(plotRecords, priors, run.workflow)}
    ${run.plot ? plotButton(run.plot, `${tool} completed plot`) : ""}
  </article>`;
}

function resultValue(data, ...names) {
  for (const name of names) if (data && data[name] !== undefined) return data[name];
  return undefined;
}

function endstopOffset(endstops, axis) {
  const key = `${axis.toLowerCase()}_endstop`;
  return Number(endstops?.t1?.[key]) - Number(endstops?.t0?.[key]);
}

function renderOffsetCard(calibration) {
  const source = calibration.source_endstops || {};
  const applied = calibration.target_endstops || {};
  const rows = ["X", "Y", "Z"].map((axis) => {
    const sourceOffset = endstopOffset(source, axis);
    const appliedOffset = endstopOffset(applied, axis);
    return `<tr><td>${axis}</td><td>${format(sourceOffset)}</td><td>${format(appliedOffset)}</td><td>${format(appliedOffset - sourceOffset)}</td></tr>`;
  }).join("");
  return `<article class="outcome-card"><h2>T1−T0 endstop offsets</h2>
    <table class="offset-table"><thead><tr><th>Axis</th><th>Source (mm)</th><th>Applied (mm)</th><th>Change (mm)</th></tr></thead><tbody>${rows}</tbody></table>
    <p>Endstop offsets, not raw T1 values.</p></article>`;
}

function calibrationCards(entry) {
  const calibration = entry?.result?.data;
  if (!calibration) return "";
  const measured = calibration.measured_t1_minus_t0 || {};
  const target = calibration.target_center || {};
  const centres = calibration.measured_centers || {};
  const errors = calibration.target_error_before_mm || {};
  return `${renderOffsetCard(calibration)}
    <article class="outcome-card"><h2>Absolute ball target</h2><dl>
      <dt>Target</dt><dd>X=${format(target.x, 3)}, Y=${format(target.y, 3)} mm</dd>
      <dt>T0 measured</dt><dd>X=${format(centres.t0?.x, 3)}, Y=${format(centres.t0?.y, 3)} mm</dd>
      <dt>T0 target error</dt><dd>X=${formatMicrometres(errors.t0?.x)}, Y=${formatMicrometres(errors.t0?.y)}</dd>
      <dt>T1 measured</dt><dd>X=${format(centres.t1?.x, 3)}, Y=${format(centres.t1?.y, 3)} mm</dd>
      <dt>T1 target error</dt><dd>X=${formatMicrometres(errors.t1?.x)}, Y=${formatMicrometres(errors.t1?.y)}</dd>
    </dl></article>
    <article class="outcome-card"><h2>Measured T1−T0 calibration</h2><dl>
      <dt>ΔX refined</dt><dd>${formatMicrometres(measured.x)}</dd>
      <dt>ΔY refined</dt><dd>${formatMicrometres(measured.y)}</dd>
      <dt>ΔZ centre median</dt><dd>${formatMicrometres(measured.z)}</dd>
    </dl></article>`;
}

function verificationCentreProgressCard(entry) {
  const runs = entry?.runs || {};
  const t0 = centreTapStats(runs.t0 || {});
  const t1 = centreTapStats(runs.t1 || {});
  if (!t0 && !t1) return "";
  const delta = t0 && t1 ? Number(t1.median) - Number(t0.median) : undefined;
  return `<article class="outcome-card"><h2>Live physical centre-Z comparison</h2><dl>
    <dt>T0 centre median</dt><dd>${t0 ? `${formatMillimetres(t0.median)} · σ ${formatMicrometres(t0.sigma)} · ${t0.count}/5` : "waiting for centre taps"}</dd>
    <dt>T1 centre median</dt><dd>${t1 ? `${formatMillimetres(t1.median)} · σ ${formatMicrometres(t1.sigma)} · ${t1.count}/5` : "waiting for centre taps"}</dd>
    <dt>T1−T0 centre ΔZ</dt><dd>${formatMicrometres(delta)}</dd>
  </dl></article>`;
}

function verificationCards(entry) {
  const verificationEntry = entry?.report;
  const verification = verificationEntry?.data;
  if (!verification) return "";
  const pass = Boolean(resultValue(verification, "passed", "pass"));
  const residual = resultValue(verification, "t1_minus_t0", "residuals", "residual") || verification;
  const target = verification.target_center || {};
  const checks = verification.checks || {};
  const checkRows = Object.entries(checks).map(([name, check]) => {
    const value = Number(check.value_mm);
    const limit = Number(check.limit_mm);
    const passMark = check.passed === true;
    return `<li class="verification-check ${passMark ? "pass" : "fail"}"><span>${escapeHtml(check.label || name.replaceAll("_", " "))}</span><strong>${formatMicrometres(value)} / limit ${formatMicrometres(limit)} — ${passMark ? "PASS" : "FAIL"}</strong></li>`;
  }).join("");
  const failedCount = Object.values(checks).filter((check) => check.passed !== true).length;
  const verificationCard = `<article class="outcome-card ${pass ? "pass" : "fail"}"><h2>Paired verification: ${pass ? "PASS" : `FAIL · ${failedCount} checks failed`}</h2><dl>
    <dt>Target</dt><dd>X=${format(target.x, 3)}, Y=${format(target.y, 3)} mm</dd>
    <dt>T0 centre median</dt><dd>${formatMillimetres(verification.measurements?.t0?.centre_z)} · σ ${formatMicrometres(verification.measurements?.t0?.centre_statistics?.standard_deviation)} · 5/5 taps</dd>
    <dt>T1 centre median</dt><dd>${formatMillimetres(verification.measurements?.t1?.centre_z)} · σ ${formatMicrometres(verification.measurements?.t1?.centre_statistics?.standard_deviation)} · 5/5 taps</dd>
    <dt>Paired centre ΔZ</dt><dd>${formatMicrometres(residual.z_center ?? residual.z)}</dd>
  </dl><ul class="verification-checks">${checkRows}</ul></article>`;
  const audit = entry?.audit?.data;
  if (!audit) return verificationCard;
  const auditPass = Boolean(audit.passed);
  const metrics = audit.metrics || {};
  return `${verificationCard}<article class="outcome-card ${auditPass ? "pass" : "fail"}"><h2>Z repeatability audit: ${auditPass ? "PASS" : "FAIL"}</h2><dl>
    <dt>T0 centre range</dt><dd>${formatMicrometres(metrics.t0_centre_z?.range_mm)}</dd>
    <dt>T1 centre range</dt><dd>${formatMicrometres(metrics.t1_centre_z?.range_mm)}</dd>
    <dt>Paired ΔZ range</dt><dd>${formatMicrometres(metrics.paired_centre_delta_z?.range_mm)}</dd>
    <dt>Limit</dt><dd>${formatMicrometres(audit.limit_mm)}</dd>
  </dl><p>${escapeHtml(audit.termination_reason || "Repeatability audit complete")}</p></article>`;
}

function normaliseChapters(data) {
  if (data.chapters?.tool_alignment) return data.chapters;
  if (data.chapters) {
    return {
      tool_alignment: {
        calibration: data.chapters.calibration,
        verification: data.chapters.verification,
      },
      bed_calibration: data.chapters.bed_calibration,
    };
  }
  const completed = data.status === "completed" ? data : (data.last_completed || data);
  const chapters = {};
  const workflow = completed.workflow || data.workflow;
  if (workflow === "calibration" || workflow === "verification") {
    chapters[workflow] = { status: completed.status || data.status, runs: completed.runs || data.runs || {} };
  }
  if (data.calibration_result || completed.calibration_result) {
    chapters.calibration ||= { runs: {} };
    chapters.calibration.result = data.calibration_result || completed.calibration_result;
  }
  if (data.verification || completed.verification) {
    chapters.verification ||= { runs: {} };
    chapters.verification.report = data.verification || completed.verification;
  }
  return { tool_alignment: chapters };
}

function acceptedChapters(data) {
  const accepted = data.accepted || {};
  const chapters = {};
  const bed = accepted.bed_reference?.data;
  const tools = accepted.tool_alignment?.status === "stale"
    ? undefined
    : accepted.tool_alignment?.data;
  const mesh = accepted.mesh?.data;
  if (bed || mesh) chapters.bed_calibration = {...(bed || {})};
  if (mesh) chapters.bed_calibration.mesh = mesh.mesh || mesh;
  if (tools) chapters.tool_alignment = tools;
  return chapters;
}

function chapterForStep(chapters, chapter) {
  if (chapter === "bed-reference" || chapter === "bed-mesh") {
    return chapters.bed_calibration || {};
  }
  return chapters.tool_alignment || {};
}

function stepEvidence(data, chapters) {
  const bed = chapters.bed_calibration || {};
  const reference = bed.reference || {};
  const before = reference.before_rebase || {};
  const after = reference.after_rebase || {};
  const rebase = reference.rebase || {};
  const alignment = chapters.tool_alignment || {};
  const calibration = alignment.calibration || {};
  const verification = alignment.verification || {};
  const calibrationData = calibration.result?.data || calibration.data || calibration;
  const verificationData = verification.report?.data || {};
  const mesh = bed.mesh || {};
  const meshProgress = mesh.progress || {};
  const meshComplete = Number(meshProgress.completed || 0) >= Number(meshProgress.total || 1);
  const afterTapCount = Math.max(
    Number(after.progress?.completed || 0),
    Array.isArray(after.samples) ? after.samples.length : 0,
  );
  const beforeTapCount = Math.max(
    Number(before.progress?.completed || 0),
    Array.isArray(before.samples) ? before.samples.length : 0,
  );
  const beforeComplete = beforeTapCount >= 5;
  const afterComplete = afterTapCount >= 5;

  const evidence = [
    Boolean((before.summary || before.discovery) && beforeComplete),
    Boolean(rebase.target_endstops || rebase.target_config_fingerprint),
    Boolean(after.summary && afterComplete),
    (calibration.status === "completed" || calibration.result || calibrationData.workflow) && (verificationData.passed === true || verificationData.pass === true),
    mesh.status === "completed" || mesh.status === "passed" || meshComplete,
    mesh.verification?.status === "passed" && mesh.verification?.active === true,
  ];
  return [...evidence, data.run_scope === "full" && data.readiness?.printable === true && evidence.every(Boolean)];
}

function stepFromStage(data, chapters, passed) {
  const stage = String(data.stage || "").toLowerCase();
  if (stage.includes("mesh_deployment")) return 6;
  if (stage.includes("mesh_acquisition")) return 5;
  if (stage.includes("tool_alignment")) return 4;
  if (stage.includes("reference_deployment")) return 2;
  if (stage.includes("bed_calibration.reference")) {
    return passed[1] ? 3 : (passed[0] ? 2 : 1);
  }
  if (stage.includes("completed")) return 7;

  const bed = chapters.bed_calibration || {};
  const reference = bed.reference || {};
  const before = reference.before_rebase || {};
  const beforeTapCount = Math.max(
    Number(before.progress?.completed || 0),
    Array.isArray(before.samples) ? before.samples.length : 0,
  );
  const after = reference.after_rebase || {};
  const afterTapCount = Math.max(
    Number(after.progress?.completed || 0),
    Array.isArray(after.samples) ? after.samples.length : 0,
  );
  if (reference.rebase && afterTapCount < 5) return 3;
  if (reference.before_rebase && !reference.rebase) return beforeTapCount >= 5 ? 2 : 1;
  if (bed.mesh?.verification && !passed[5]) return 6;
  if (Object.keys(bed.mesh || {}).length && !passed[4]) return 5;
  return passed.findIndex((value) => !value) + 1 || 7;
}

function runScopeIncludesStep(scope, number) {
  if (!scope || scope === "full") return true;
  if (scope === "bed_reference") return number <= 3;
  if (scope === "tool_alignment") return number === 4;
  if (scope === "mesh_refresh") return number >= 5 && number <= 6;
  return false;
}

function deriveWorkflowSteps(data, chapters) {
  const accepted = acceptedChapters(data);
  const passed = stepEvidence(data, accepted);
  const activeStep = ["running", "preparing"].includes(data.status) ? activeStepNumber(data, chapters, passed) : null;
  const failedStep = data.status === "failed" ? stepFromStage(data, chapters, passed) : null;
  const staleMesh = chapters.bed_calibration?.mesh?.status === "stale";
  return WORKFLOW_STEPS.map((step) => {
    let status = passed[step.number - 1] ? "passed" : "pending";
    if (failedStep && step.number === failedStep) status = "failed";
    else if (failedStep && step.number > failedStep) status = "blocked";
    else if (staleMesh && step.number >= 5) status = "blocked";
    else if (activeStep === step.number) status = "running";
    let note = "";
    if (status === "passed") note = "Accepted in the calibration chain.";
    if (status === "running") note = "This is the active stage.";
    if (status === "failed") note = [conciseError(data.error || chapterForStep(chapters, step.chapter).error) || "The current run stopped here.", data.attempt?.rollback].filter(Boolean).join(" · ");
    if (status === "blocked") note = `Waiting for step ${failedStep} to pass before continuing.`;
    if (activeStep && runScopeIncludesStep(data.run_scope, step.number) && step.number > activeStep && passed[step.number - 1]) {
      status = "remeasuring";
      note = "Previously accepted evidence is retained as history; this run is re-measuring it.";
    }
    if (staleMesh && step.number >= 5) note = "Accepted mesh is stale after a T0 frame change; refresh the mesh.";
    if (status === "pending" && data.status !== "idle" && !runScopeIncludesStep(data.run_scope, step.number)) {
      note = `Not part of this ${String(data.run_scope || "partial").replaceAll("_", " ")} run; another compatible chapter attempt is required.`;
    }
    return {...step, status, note};
  });
}

function roadmapChapterStatus(chapter, steps) {
  const states = steps.filter((step) => step.chapter === chapter).map((step) => step.status);
  if (states.includes("failed")) return "failed";
  if (states.includes("running")) return "running";
  if (states.includes("remeasuring")) return "remeasuring";
  if (states.length && states.every((state) => state === "passed")) return "passed";
  if (states.length && states.every((state) => state === "blocked")) return "blocked";
  return "pending";
}

function renderRoadmap(data, chapters, steps = deriveWorkflowSteps(data, chapters)) {
  const containers = {
    "bed-reference": bedReferenceRoadmap,
    "tool-alignment": toolAlignmentRoadmap,
    "bed-mesh": bedMeshRoadmap,
  };
  const roadmapSteps = steps;
  Object.entries(containers).forEach(([chapter, container]) => {
    container.innerHTML = roadmapSteps.filter((step) => step.chapter === chapter).map((step) => `
      <article class="workflow-step ${step.status}" data-step="${step.number}" aria-label="Step ${step.number}: ${escapeHtml(step.title)} — ${WORKFLOW_STATUS_LABELS[step.status]}">
        <div class="workflow-step-heading"><span class="workflow-step-number">Step ${step.number}</span><strong>${WORKFLOW_STATUS_LABELS[step.status]}</strong></div>
        <h3>${escapeHtml(step.title)}</h3>
        <p>${escapeHtml(step.description)}</p>
        ${step.note ? `<small>${escapeHtml(step.note)}</small>` : ""}
      </article>`).join("");
  });
}

function renderLiveChapterStatuses(data, chapters, steps) {
  // Activity-only polls must update the chapter summaries as well as the
  // highlighted card. Keep detailed measurement DOM untouched so plots,
  // scroll positions, and copy/paste state remain stable.
  setDisplayStatus(bedReferenceState, roadmapChapterStatus("bed-reference", steps));
  setDisplayStatus(toolAlignmentState, roadmapChapterStatus("tool-alignment", steps));
  setDisplayStatus(bedMeshState, roadmapChapterStatus("bed-mesh", steps));
}

function referenceCard(reference) {
  if (!reference || !Object.keys(reference).length) return "";
  const before = reference.before_rebase?.summary || {};
  const after = reference.after_rebase?.summary || {};
  const rebase = reference.rebase || {};
  return `<article class="outcome-card"><h2>Absolute bed Z datum</h2><dl>
    <dt>Bed centre</dt><dd>(150, 150), target Z=0 mm</dd>
    <dt>Discovery median</dt><dd>${formatMillimetres(before.median)}</dd>
    <dt>Discovery span</dt><dd>${formatMicrometres(before.span)}</dd>
    <dt>Common T0/T1 correction</dt><dd>${formatMillimetres(rebase.common_delta_mm)}</dd>
    <dt>Verification median</dt><dd>${formatMicrometres(after.median)}</dd>
    <dt>Verification span</dt><dd>${formatMicrometres(after.span)}</dd>
    <dt>Relative Z preserved</dt><dd>${rebase.difference_preserved === true ? "YES" : "—"}</dd>
  </dl></article>`;
}

function referenceSamples(reference) {
  return ["before_rebase", "after_rebase"].map((name) => {
    const item = reference?.[name];
    if (!item) return "";
    const discovery = name === "before_rebase";
    const rows = (item.samples || []).map((sample) => `<tr><td>${sample.index}</td><td>${discovery ? format(sample.z) : format(Number(sample.z) * 1000, 1)}</td></tr>`).join("");
    return `<article class="outcome-card"><h2>${discovery ? "Initial discovery taps" : "Post-correction verification taps"}</h2>
      <p class="measurement-note">${discovery ? "Banded descent finds the rough bed height; values are absolute Z in mm." : "Five fixed-window taps confirm logical Z=0; residuals are shown in µm."}</p>
      <table class="offset-table"><thead><tr><th>Tap</th><th>Z (${discovery ? "mm" : "µm"})</th></tr></thead><tbody>${rows}</tbody></table></article>`;
  }).join("");
}

function meshCard(mesh) {
  if (!mesh || !Object.keys(mesh).length) return "";
  const progress = mesh.progress || {};
  const complete = Number(progress.completed || 0);
  const total = Number(progress.total || 0);
  const percent = total ? Math.min(100, 100 * complete / total) : 0;
  const verification = mesh.verification || {};
  return `<article class="outcome-card"><h2>Persistent Tap mesh</h2>
    <p>${escapeHtml(mesh.status || "preparing")} · ${complete}/${total || "?"} points${mesh.latest_point ? ` · latest X=${format(mesh.latest_point.x)} mm · Y=${format(mesh.latest_point.y)} mm` : ""}</p>
    <div class="mesh-progress"><span style="width:${percent}%"></span></div><dl>
      <dt>Minimum</dt><dd>${formatMillimetres(mesh.minimum)}</dd>
      <dt>Maximum</dt><dd>${formatMillimetres(mesh.maximum)}</dd>
      <dt>Peak to peak</dt><dd>${formatMillimetres(mesh.range)}</dd>
      <dt>Zero reference</dt><dd>${Array.isArray(mesh.zero_reference_position) ? mesh.zero_reference_position.join(", ") : "—"}</dd>
      <dt>Matrix hash</dt><dd>${escapeHtml(String(mesh.matrix_sha256 || "—").slice(0, 12))}</dd>
      <dt>Deployed and active</dt><dd>${verification.active === true ? "YES" : "—"}</dd>
    </dl>${mesh.plot ? plotButton(mesh.plot, "Eddy Tap bed mesh") : ""}</article>`;
}

function renderBedChapters(entry, referenceStatus = "pending", meshStatus = "pending") {
  const hasReference = Boolean(entry && Object.keys(entry.reference || {}).length);
  const hasMesh = Boolean(entry && Object.keys(entry.mesh || {}).length);
  bedReferenceChapter.hidden = false;
  bedMeshChapter.hidden = false;
  setDisplayStatus(bedReferenceState, referenceStatus);
  setDisplayStatus(bedMeshState, meshStatus);
  if (hasReference) {
    bedReference.innerHTML = `${referenceCard(entry.reference)}${referenceSamples(entry.reference)}`;
  } else {
    bedReference.innerHTML = "";
  }
  if (hasMesh) {
    bedMesh.innerHTML = meshCard(entry.mesh);
  } else {
    bedMesh.innerHTML = "";
  }
}

function renderAcceptedProvenance(data) {
  const sources = data.accepted_sources || {};
  Object.entries(provenanceElements).forEach(([chapter, element]) => {
    if (!element) return;
    const source = sources[chapter];
    if (!source) {
      element.textContent = "No accepted result yet";
      return;
    }
    element.innerHTML = `Accepted from attempt ${escapeHtml(source.attempt_id || "—")} · ${escapeHtml(source.accepted_at ? new Date(source.accepted_at).toLocaleString() : "time unknown")} · ${escapeHtml(source.compatibility?.state || source.status || "accepted")}${source.artifact ? ` · <a href="${escapeHtml(source.artifact)}">artifact</a>` : ""}`;
  });
}

function renderChapter(chapterElement, stateElement, toolsElement, outcomeElement, entry, priors, outcomeHtml) {
  chapterElement.hidden = !entry;
  if (!entry) return;
  setDisplayStatus(stateElement, entry.status, "passed");
  const runs = entry.runs || {};
  toolsElement.innerHTML = ["t0", "t1"]
    .filter((tool) => runs[tool])
    .map((tool) => renderTool(tool.toUpperCase(), runs[tool], entry.configured_priors || priors))
    .join("");
  outcomeElement.innerHTML = outcomeHtml;
}

function render(data) {
  const error = conciseError(data.error);
  headline.textContent = `${displayRunStatus(data.status)}: ${displayStage(data)}${error ? ` — ${error}` : ""}`;
  updated.textContent = data.updated_at ? `Updated ${new Date(data.updated_at).toLocaleTimeString()}` : "";
  const chapters = normaliseChapters(data);
  renderAcceptedProvenance(data);
  // Current and activity snapshots are polled independently.  Always fold
  // the latest cached activity into the initial render as well; otherwise a
  // current.json update can briefly treat an accepted chapter as complete
  // until the following activity poll marks it as re-measuring/running.
  const roadmapSteps = deriveWorkflowSteps({...data, activity: currentActivityData}, chapters);
  renderActivity(data, chapters, stepEvidence(data, acceptedChapters(data)), currentActivityData);
  renderRoadmap(data, chapters, roadmapSteps);
  const alignment = chapters.tool_alignment || {};
  const priors = data.configured_priors;
  const hasAlignment = Boolean(alignment.calibration || alignment.verification);
  toolAlignmentChapter.hidden = false;
  if (calibrationHeading) {
    calibrationHeading.textContent = `Ball alignment · ${calibrationContactCount(alignment.calibration)} contacts per tool`;
  }
  setDisplayStatus(toolAlignmentState, roadmapChapterStatus("tool-alignment", roadmapSteps));
  renderChapter(calibrationChapter, calibrationState, calibrationTools, calibrationOutcome, alignment.calibration, priors, calibrationCards(alignment.calibration));
  renderChapter(verificationChapter, verificationState, verificationTools, verificationOutcome, alignment.verification, priors, `${verificationCentreProgressCard(alignment.verification)}${verificationCards(alignment.verification)}`);
  renderBedChapters(
    chapters.bed_calibration,
    roadmapChapterStatus("bed-reference", roadmapSteps),
    roadmapChapterStatus("bed-mesh", roadmapSteps),
  );
  const activeAttempt = ["preparing", "running"].includes(String(data.status || "").toLowerCase());
  const printable = data.readiness?.printable === true && !activeAttempt;
  const partial = data.status === "completed" && !printable;
  const failed = !activeAttempt && (data.status === "failed" || partial || (data.readiness?.reasons || []).length > 0);
  readiness.className = `readiness ${printable ? "ready" : (failed ? "failed" : "calibrating")}`;
  readiness.textContent = printable ? "READY TO PRINT" : (failed ? "NOT READY TO PRINT" : "CALIBRATING");
  empty.hidden = Boolean(hasAlignment || chapters.bed_calibration || data.status !== "idle");
  const previous = data.last_successful_batch_id;
  lastSuccessful.textContent = previous && previous !== data.batch_id
    ? `Last fully verified printable calibration chain: ${previous}`
    : "";
}

function setPrinterText(element, value) {
  if (element) element.textContent = value;
}

function renderPrinterStatus(payload) {
  const status = payload?.result?.status || {};
  const webhooks = status.webhooks || {};
  const toolhead = status.toolhead || {};
  const motion = status.gcode_move || {};
  const printStats = status.print_stats || {};
  const position = motion.gcode_position || motion.position || toolhead.position || [];
  const state = webhooks.state || "unknown";
  const temperatures = [
    ["T0", status.extruder?.temperature],
    ["T1", status.extruder1?.temperature],
    ["Bed", status.heater_bed?.temperature],
  ].filter(([, value]) => Number.isFinite(Number(value)));
  const view = {
    state,
    stateMessage: webhooks.state_message || "",
    position: position.slice(0, 3).map((value) => format(value)),
    homedAxes: toolhead.homed_axes || "not homed",
    printState: printStats.state || "standby",
    temperatures: temperatures.map(([name, value]) => [name, Number(value).toFixed(1)]),
  };
  const statusHash = contentHash(view);
  if (statusHash === printerStatusContentHash) return;
  printerStatusContentHash = statusHash;
  setPrinterText(printerState, `${state}${webhooks.state_message ? ` · ${webhooks.state_message}` : ""}`);
  setPrinterText(printerX, `${format(position[0])} mm`);
  setPrinterText(printerY, `${format(position[1])} mm`);
  setPrinterText(printerZ, `${format(position[2])} mm`);
  setPrinterText(printerHomed, toolhead.homed_axes || "not homed");
  setPrinterText(printerPrintState, printStats.state || "standby");
  setPrinterText(printerTemperatures, temperatures.length
    ? temperatures.map(([name, value]) => `${name} ${formatTemperature(value)}`).join(" · ")
    : "—");
}

function formatConsoleTimestamp(value) {
  const milliseconds = Number(value) * 1000;
  if (!Number.isFinite(milliseconds)) return "—:—:—";
  return new Date(milliseconds).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function humaniseConsoleMessage(message) {
  let text = String(message ?? "").replace(/\r/g, "").trim();
  const respond = text.match(/^RESPOND TYPE=echo MSG="([\s\S]*)"$/);
  if (respond) text = `echo: ${respond[1].replace(/\\"/g, '"')}`;
  return text
    .replaceAll("before_rebase", "initial discovery")
    .replaceAll("after_rebase", "post-correction verification");
}

function consoleLines(entries) {
  const normalised = (entries || []).flatMap((entry) => {
    const message = humaniseConsoleMessage(entry.message);
    return message.split("\n").map((line) => ({
      line: line.trim(),
      type: entry.type || "response",
      time: entry.time,
    })).filter((item) => item.line);
  });
  const seenResponses = new Set();
  return normalised.filter((item, index) => {
    const next = normalised[index + 1];
    if (item.type === "command" && item.line.startsWith("echo: ") && next?.line === item.line) return false;
    if (item.type !== "command" && item.line.startsWith("echo: ")) {
      if (seenResponses.has(item.line)) return false;
      seenResponses.add(item.line);
    }
    return index === 0 || normalised[index - 1].line !== item.line;
  });
}

function renderPrinterConsole(payload) {
  const entries = payload?.result?.gcode_store || [];
  // The gcode store is chronological (oldest first), while Mainsail presents
  // the newest console entry at the top. Keep the bounded window, then invert
  // it for the operator-facing view.
  const lines = consoleLines(entries).slice(-60).reverse();
  const consoleHash = contentHash(lines);
  if (consoleHash === printerConsoleContentHash) return;
  printerConsoleContentHash = consoleHash;
  setPrinterText(consoleState, `${lines.length} recent lines`);
  if (printerConsole) {
    printerConsole.innerHTML = lines.length
      ? lines.map((item) => `<span class="console-line ${item.type === "command" ? "command" : "response"}"><span class="console-time">${escapeHtml(formatConsoleTimestamp(item.time))}</span><span>${escapeHtml(item.line)}</span></span>`).join("")
      : "No console output yet.";
    // Newest entries are at the top, so keep the viewport anchored there.
    printerConsole.scrollTop = 0;
  }
}

async function refreshPrinterContext() {
  const [statusResult, consoleResult] = await Promise.allSettled([
    fetch("/printer/objects/query?webhooks&toolhead&gcode_move&print_stats&extruder&extruder1&heater_bed", { cache: "no-store" }).then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    }),
    fetch("/server/gcode_store?count=80", { cache: "no-store" }).then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    }),
  ]);
  if (statusResult.status === "fulfilled") {
    renderPrinterStatus(statusResult.value);
  } else {
    setPrinterText(printerState, "Unavailable");
  }
  if (consoleResult.status === "fulfilled") {
    renderPrinterConsole(consoleResult.value);
  } else {
    setPrinterText(consoleState, "Unavailable");
    setPrinterText(printerConsole, "Moonraker console unavailable.");
  }
}

function closePlot() { plotModal.close(); }

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-plot-src]");
  if (button) {
    plotModalImage.src = button.dataset.plotSrc;
    plotModalImage.alt = button.dataset.plotAlt;
    plotModal.showModal();
  }
});
plotModalClose.addEventListener("click", closePlot);
plotModal.addEventListener("click", (event) => { if (event.target === plotModal) closePlot(); });
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && plotModal.open) closePlot(); });

async function refresh() {
  try {
    const [currentResult, activityResult] = await Promise.allSettled([
      fetch(`data/current.json?t=${Date.now()}`, { cache: "no-store" }).then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      }),
      fetch(`data/activity.json?t=${Date.now()}`, { cache: "no-store" }).then((response) => response.ok ? response.json() : null),
    ]);
    if (currentResult.status !== "fulfilled") throw currentResult.reason;
    const current = currentResult.value;
    const separateActivity = activityResult.status === "fulfilled" ? activityResult.value : null;
    try {
      const previousResponse = await fetch(`data/last_successful.json?t=${Date.now()}`, { cache: "no-store" });
      if (previousResponse.ok) {
        const previous = await previousResponse.json();
        if (previous.batch_id && previous.batch_id !== current.batch_id) current.last_successful_batch_id = previous.batch_id;
      }
    } catch (_) {
      // The current snapshot remains useful when no successful history exists.
    }
    const currentHash = contentHash(current);
    const activityCandidate = separateActivity || current.attempt?.activity || current.activity || {};
    const nextActivityHash = contentHash(activityCandidate);
    if (currentHash !== dashboardContentHash) {
      dashboardContentHash = currentHash;
      currentDashboardData = current;
      currentActivityData = activityCandidate;
      render(current);
    }
    if (nextActivityHash !== activityContentHash) {
      activityContentHash = nextActivityHash;
      currentActivityData = activityCandidate;
      if (currentDashboardData && currentHash === dashboardContentHash) {
        const chapters = normaliseChapters(currentDashboardData);
        const liveSteps = deriveWorkflowSteps({...currentDashboardData, activity: currentActivityData}, chapters);
        renderActivity(currentDashboardData, chapters, stepEvidence(currentDashboardData, acceptedChapters(currentDashboardData)), currentActivityData);
        renderRoadmap(currentDashboardData, chapters, liveSteps);
        renderLiveChapterStatuses(currentDashboardData, chapters, liveSteps);
      }
    }
  } catch (error) {
    headline.textContent = `Calibration dashboard unavailable: ${error.message}`;
  }
}

refresh();
setInterval(refresh, 1000);
refreshPrinterContext();
setInterval(refreshPrinterContext, 1000);
startCameraStream();
window.addEventListener("beforeunload", stopCameraStream);
