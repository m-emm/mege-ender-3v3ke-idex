const headline = document.querySelector("#headline");
const updated = document.querySelector("#updated");
const events = document.querySelector("#events");
const calibrationChapter = document.querySelector("#calibration-chapter");
const calibrationState = document.querySelector("#calibration-state");
const calibrationTools = document.querySelector("#calibration-tools");
const calibrationOutcome = document.querySelector("#calibration-outcome");
const verificationChapter = document.querySelector("#verification-chapter");
const verificationState = document.querySelector("#verification-state");
const verificationTools = document.querySelector("#verification-tools");
const verificationOutcome = document.querySelector("#verification-outcome");
const empty = document.querySelector("#empty");
const plotModal = document.querySelector("#plot-modal");
const plotModalImage = document.querySelector("#plot-modal-image");
const plotModalClose = document.querySelector("#plot-modal-close");

// This is deliberately much flatter than a literal Z plot.  The probe only
// measures a shallow ball cap; preserving the former independent Z fit made
// millimetres in Z appear roughly 34 times larger than millimetres in XY.
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

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[character]));
}

function latestMeasurement(run) {
  return [...(run.records || [])].reverse().find((record) => record.status === "completed");
}

function summaryNumbers(run) {
  const summary = run.summary || {};
  if (summary.phase_2?.refined_center) {
    const center = summary.phase_2.refined_center;
    return [["Centre X", center.x], ["Centre Y", center.y], ["Summit Z", summary.phase_1?.summit?.trigger_z]];
  }
  if (summary.estimated_center) {
    const center = summary.estimated_center;
    return [["Centre X", center.x], ["Centre Y", center.y], ["Centre Z", center.trigger_z]];
  }
  const latest = latestMeasurement(run) || {};
  return [["Latest X", latest.commanded_x], ["Latest Y", latest.commanded_y], ["Trigger Z", latest.trigger_z]];
}

function calculationDetails(run) {
  const summary = run.summary || {};
  if (summary.phase_2?.harmonic) {
    const harmonic = summary.phase_2.harmonic;
    return `<dl class="calculation-details">
      <dt>Ring correction</dt><dd>ΔX ${format(harmonic.dx_mm, 4)} · ΔY ${format(harmonic.dy_mm, 4)} mm</dd>
      <dt>Sphere residual</dt><dd>RMSE ${format(summary.phase_2.sphere_residual_rmse_mm, 4)} · max ${format(summary.phase_2.sphere_residual_max_abs_mm, 4)} mm</dd>
    </dl>`;
  }
  if (summary.harmonic) {
    return `<dl class="calculation-details">
      <dt>Ring correction</dt><dd>ΔX ${format(summary.harmonic.dx_mm, 4)} · ΔY ${format(summary.harmonic.dy_mm, 4)} mm</dd>
      <dt>Periphery Z</dt><dd>mean ${format(summary.periphery_mean_z, 4)} · σ ${format(summary.periphery_z_standard_deviation, 4)} mm</dd>
    </dl>`;
  }
  return "";
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
  if (!points.length) return "<p>No contacts recorded yet.</p>";
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
      const [headX, headY] = point.status === "completed" ? project(Number(point.commanded_x), Number(point.commanded_y), Number(point.trigger_z)) : [baseX, baseY];
      const colour = contactColour(point.trigger_z, minZ, maxZ);
      const marker = point.status === "no_contact" ? "×" : "";
      return `${point.status === "completed" ? `<line class="stalk" stroke="${colour}" x1="${baseX}" y1="${baseY}" x2="${headX}" y2="${headY}"/>` : ""}
        <circle class="point ${index === latestIndex ? "latest" : ""}" cx="${headX}" cy="${headY}" r="${point.status === "no_contact" ? 5 : 4}" fill="${colour}"/>
        ${marker ? `<text x="${headX - 3}" y="${headY + 4}" fill="#fff" font-size="12">${marker}</text>` : ""}`;
    }).join("")}
  </svg>`;
}

function plotButton(source, alt) {
  return `<button class="plot-button" type="button" data-plot-src="${escapeHtml(source)}" data-plot-alt="${escapeHtml(alt)}"><img src="${escapeHtml(source)}" alt="${escapeHtml(alt)}; click to expand"></button>`;
}

function renderTool(tool, run, priors) {
  const [status, progress] = [run.state || "running", run.progress || {}];
  const numbers = summaryNumbers(run).map(([label, value]) => `<div class="number"><span>${label}</span><strong>${format(value)}</strong></div>`).join("");
  return `<article class="tool"><h2>${tool}</h2>
    <div class="state ${escapeHtml(status)}">${escapeHtml(status)} · ${progress.completed || 0}/${progress.total || "?"} contacts</div>
    <div class="numbers">${numbers}</div>
    ${calculationDetails(run)}
    ${isometricPlot(run.records || [], priors, run.workflow)}
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
    return `<tr><td>${axis}</td><td>${format(sourceOffset, 4)} mm</td><td>${format(appliedOffset, 4)} mm</td><td>${format(appliedOffset - sourceOffset, 4)} mm</td></tr>`;
  }).join("");
  return `<article class="outcome-card"><h2>T1−T0 endstop offsets</h2>
    <table class="offset-table"><thead><tr><th>Axis</th><th>Source</th><th>Applied</th><th>Change</th></tr></thead><tbody>${rows}</tbody></table>
    <p>Endstop offsets, not raw T1 values.</p></article>`;
}

function calibrationCards(entry) {
  const calibration = entry?.result?.data;
  if (!calibration) return "";
  const measured = calibration.measured_t1_minus_t0 || {};
  return `${renderOffsetCard(calibration)}
    <article class="outcome-card"><h2>Measured T1−T0 calibration</h2><dl>
      <dt>ΔX refined</dt><dd>${format(measured.x, 4)} mm</dd>
      <dt>ΔY refined</dt><dd>${format(measured.y, 4)} mm</dd>
      <dt>ΔZ physical summit</dt><dd>${format(measured.z, 4)} mm</dd>
    </dl></article>`;
}

function verificationCards(entry) {
  const verificationEntry = entry?.report;
  const verification = verificationEntry?.data;
  if (!verification) return "";
  const pass = Boolean(resultValue(verification, "passed", "pass"));
  const residual = resultValue(verification, "t1_minus_t0", "residuals", "residual") || verification;
  const zDiagnostics = verification.z_diagnostics || {};
  const components = verification.pass_components || {};
  const verificationCard = `<article class="outcome-card ${pass ? "pass" : "fail"}"><h2>Paired verification: ${pass ? "PASS" : "FAIL"}</h2><dl>
    <dt>ΔX ${components.x === false ? "✗" : ""}</dt><dd>${format(resultValue(residual, "x", "delta_x_mm", "delta_x"), 4)} mm</dd>
    <dt>ΔY ${components.y === false ? "✗" : ""}</dt><dd>${format(resultValue(residual, "y", "delta_y_mm", "delta_y"), 4)} mm</dd>
    <dt>Centre ΔZ ${components.z_center === false ? "✗" : ""}</dt><dd>${format(resultValue(zDiagnostics, "centre_delta_mm") ?? residual.z, 4)} mm</dd>
    <dt>Periphery mean</dt><dd>${format(zDiagnostics.periphery_mean_delta_mm, 4)} mm</dd>
    <dt>Periphery σ</dt><dd>${format(zDiagnostics.periphery_delta_standard_deviation_mm, 4)} mm</dd>
    <dt>Centre−periphery</dt><dd>${format(zDiagnostics.centre_minus_periphery_mean_mm, 4)} mm</dd>
    <dt>Radial XY</dt><dd>${format(resultValue(verification, "radial_xy_mm", "radial_xy_error_mm", "radial_xy_error"), 4)} mm</dd>
  </dl><p>Periphery Z is diagnostic only; the physical centre contact is authoritative.</p></article>`;
  const audit = entry?.audit?.data;
  if (!audit) return verificationCard;
  const auditPass = Boolean(audit.passed);
  const metrics = audit.metrics || {};
  return `${verificationCard}<article class="outcome-card ${auditPass ? "pass" : "fail"}"><h2>Z repeatability audit: ${auditPass ? "PASS" : "FAIL"}</h2><dl>
    <dt>T0 centre range</dt><dd>${format(metrics.t0_centre_z?.range_mm, 4)} mm</dd>
    <dt>T1 centre range</dt><dd>${format(metrics.t1_centre_z?.range_mm, 4)} mm</dd>
    <dt>Paired ΔZ range</dt><dd>${format(metrics.paired_centre_delta_z?.range_mm, 4)} mm</dd>
    <dt>Limit</dt><dd>${format(audit.limit_mm, 4)} mm</dd>
  </dl><p>${escapeHtml(audit.termination_reason || "Repeatability audit recorded")}</p></article>`;
}

function normaliseChapters(data) {
  if (data.chapters) return data.chapters;
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
  return chapters;
}

function renderChapter(chapterElement, stateElement, toolsElement, outcomeElement, entry, priors, outcomeHtml) {
  chapterElement.hidden = !entry;
  if (!entry) return;
  stateElement.textContent = entry.status || "recorded";
  const runs = entry.runs || {};
  toolsElement.innerHTML = ["t0", "t1"]
    .filter((tool) => runs[tool])
    .map((tool) => renderTool(tool.toUpperCase(), runs[tool], entry.configured_priors || priors))
    .join("");
  outcomeElement.innerHTML = outcomeHtml;
}

function render(data) {
  headline.textContent = `${data.status || "unknown"}: ${data.workflow || "multi-head-zero calibration"}${data.error ? ` — ${data.error}` : ""}`;
  updated.textContent = data.updated_at ? `Updated ${new Date(data.updated_at).toLocaleTimeString()}` : "";
  events.innerHTML = (data.events || []).slice(-6).reverse().map((event) => `<span class="event">${escapeHtml(event.message)}</span>`).join("");
  const chapters = normaliseChapters(data);
  const priors = data.configured_priors;
  renderChapter(calibrationChapter, calibrationState, calibrationTools, calibrationOutcome, chapters.calibration, priors, calibrationCards(chapters.calibration));
  renderChapter(verificationChapter, verificationState, verificationTools, verificationOutcome, chapters.verification, priors, verificationCards(chapters.verification));
  empty.hidden = Boolean(chapters.calibration || chapters.verification);
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
    const response = await fetch(`data/current.json?t=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
  } catch (error) {
    headline.textContent = `Calibration dashboard unavailable: ${error.message}`;
  }
}

refresh();
setInterval(refresh, 1000);
