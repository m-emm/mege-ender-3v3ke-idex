(() => {
  const summary = document.querySelector('#summary');
  const updated = document.querySelector('#updated');
  const plot = document.querySelector('#plot');
  const plotEmpty = document.querySelector('#plot-empty');

  const number = (value, digits = 3) => {
    if (value === null || value === undefined || value === '') return '—';
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed.toFixed(digits) : String(value);
  };

  function render(data) {
    const failed = data.status === 'failed';
    const statusClass = failed ? 'failed' : 'ok';
    const reference = data.reference || {};
    summary.innerHTML = `
      <dl>
        <dt>Status</dt><dd class="${statusClass}">${data.status || 'unknown'}</dd>
        <dt>Run</dt><dd>${data.run_id || '—'}</dd>
        <dt>Reference</dt><dd>X=${number(reference.x)} Y=${number(reference.y)} mm</dd>
        <dt>Taps</dt><dd>${data.tap_count_recorded ?? 0}/${data.count_requested ?? 0}</dd>
        <dt>Threshold</dt><dd>${number(data.threshold, 3)}</dd>
        ${data.error ? `<dt>Error</dt><dd class="failed">${data.error}</dd>` : ''}
        ${data.plot_error ? `<dt>Plot</dt><dd class="failed">${data.plot_error}</dd>` : ''}
      </dl>`;
    updated.textContent = data.created_at
      ? `Last updated ${new Date(data.created_at).toLocaleString()}`
      : 'No trace published yet.';
    if (data.artifacts && data.artifacts.plot) {
      plot.src = `${data.artifacts.plot}?run=${encodeURIComponent(data.run_id || '')}`;
      plot.hidden = false;
      plotEmpty.hidden = true;
    } else {
      plot.hidden = true;
      plotEmpty.hidden = false;
    }
  }

  async function refresh() {
    try {
      const response = await fetch(`latest.json?ts=${Date.now()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      render(await response.json());
    } catch (error) {
      updated.textContent = `Waiting for Eddy trace data (${error.message})`;
    }
  }

  refresh();
  window.setInterval(refresh, 1000);
})();
