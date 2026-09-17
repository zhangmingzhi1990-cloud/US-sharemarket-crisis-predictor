/* Historical chart and descriptive validation. All calculations are in data/backtest.json. */
(() => {
  const chart = document.getElementById('backtestChart');
  const slider = document.getElementById('backtestSlider');
  const readout = document.getElementById('backtestReadout');
  const dateLabel = document.getElementById('backtestDate');
  const metricBox = document.getElementById('backtestMetrics');
  const verdict = document.getElementById('backtestVerdict');
  let data, visible = [], selected = 0, range = 'all', plot = {};
  const fmt = (value, digits = 2) => value == null ? '样本不足' : Number(value).toFixed(digits);
  const pct = value => value == null ? '样本不足' : (100 * value).toFixed(1) + '%';

  function chooseRange() {
    if (!data) return;
    const all = data.days;
    const last = new Date(all[all.length - 1].date + 'T00:00:00Z');
    const cutoff = new Date(last);
    if (range === '1y') cutoff.setUTCFullYear(cutoff.getUTCFullYear() - 1);
    if (range === '3y') cutoff.setUTCFullYear(cutoff.getUTCFullYear() - 3);
    visible = range === 'all' ? all : all.filter(row => new Date(row.date + 'T00:00:00Z') >= cutoff);
    selected = visible.length - 1;
    slider.max = String(selected);
    slider.value = String(selected);
    document.querySelectorAll('[data-range]').forEach(button => {
      button.classList.toggle('active', button.dataset.range === range);
      button.setAttribute('aria-pressed', button.dataset.range === range ? 'true' : 'false');
    });
    renderChart();
  }

  function renderChart() {
    if (!visible.length) return;
    const mobile = window.matchMedia('(max-width: 600px)').matches;
    const width = mobile ? 430 : 960;
    const height = mobile ? 310 : 350;
    const left = mobile ? 39 : 50, right = mobile ? 42 : 51, top = 24, bottom = 38;
    const pw = width - left - right, ph = height - top - bottom;
    const base = visible[0].spy_close;
    const normalized = visible.map(row => 100 * row.spy_close / base);
    let lo = Math.min(...normalized), hi = Math.max(...normalized);
    const pad = Math.max(3, (hi - lo) * 0.08);
    lo -= pad; hi += pad;
    const x = i => left + pw * i / Math.max(1, visible.length - 1);
    const sy = score => top + ph * (1 - score / 10);
    const py = value => top + ph * (hi - value) / (hi - lo);
    plot = { x, sy, py, normalized, top, ph };
    const scorePoints = visible.map((row, i) => `${x(i).toFixed(1)},${sy(row.score).toFixed(1)}`).join(' ');
    const spyPoints = normalized.map((value, i) => `${x(i).toFixed(1)},${py(value).toFixed(1)}`).join(' ');
    const grids = [0, 2, 4, 6, 8, 10].map(tick => {
      const y = sy(tick).toFixed(1);
      return `<line x1="${left}" x2="${width - right}" y1="${y}" y2="${y}" stroke="#273452" stroke-width="1"/><text x="${left - 8}" y="${Number(y) + 4}" text-anchor="end" fill="#aebbd4" font-size="12">${tick}</text>`;
    }).join('');
    const rightTicks = [0, .25, .5, .75, 1].map(fraction => {
      const value = hi - (hi - lo) * fraction;
      const y = top + ph * fraction;
      return `<text x="${width - right + 7}" y="${y + 4}" fill="#aebbd4" font-size="12">${value.toFixed(0)}</text>`;
    }).join('');
    const positions = mobile ? [0, .5, 1] : [0, .25, .5, .75, 1];
    const xTicks = positions.map(fraction => {
      const index = Math.round(fraction * (visible.length - 1));
      return `<text x="${x(index).toFixed(1)}" y="${height - 10}" text-anchor="middle" fill="#aebbd4" font-size="12">${visible[index].date.slice(0, 7)}</text>`;
    }).join('');
    chart.setAttribute('viewBox', `0 0 ${width} ${height}`);
    chart.innerHTML = `${grids}${rightTicks}${xTicks}<line x1="${left}" x2="${width - right}" y1="${sy(7)}" y2="${sy(7)}" stroke="#a98248" stroke-dasharray="5 5" opacity=".65"/><polyline fill="none" stroke="#7aa2ff" stroke-width="2.4" stroke-linejoin="round" points="${spyPoints}"/><polyline fill="none" stroke="#f4c95d" stroke-width="2.4" stroke-linejoin="round" points="${scorePoints}"/><line id="backtestMarker" y1="${top}" y2="${top + ph}" stroke="#dbe5f9" stroke-width="1" stroke-dasharray="3 4"/><circle id="backtestScorePoint" r="4" fill="#f4c95d" stroke="#0d1529" stroke-width="2"/><circle id="backtestSpyPoint" r="4" fill="#7aa2ff" stroke="#0d1529" stroke-width="2"/>`;
    showSelected();
  }

  function showSelected() {
    if (!visible.length) return;
    selected = Math.max(0, Math.min(visible.length - 1, Number(slider.value)));
    const row = visible[selected], x = plot.x(selected);
    document.getElementById('backtestMarker').setAttribute('x1', x);
    document.getElementById('backtestMarker').setAttribute('x2', x);
    document.getElementById('backtestScorePoint').setAttribute('cx', x);
    document.getElementById('backtestScorePoint').setAttribute('cy', plot.sy(row.score));
    document.getElementById('backtestSpyPoint').setAttribute('cx', x);
    document.getElementById('backtestSpyPoint').setAttribute('cy', plot.py(plot.normalized[selected]));
    readout.textContent = `${row.date} · 回调指数 ${fmt(row.score)} / 10 · SPY ${fmt(plot.normalized[selected], 1)}（区间首日=100） · 宏观 ${fmt(row.macro_score)} · 投机/广度 ${fmt(row.spec_score)}`;
  }

  function renderMetrics() {
    const cards = [5, 10, 20].map(horizon => {
      const m = data.metrics[String(horizon)];
      return `<div class="metric"><b>未来 ${horizon} 个交易日</b><span>指数 vs 未来最大跌幅：Spearman ${fmt(m.score_vs_future_drop_spearman)}</span><span>指数 vs 期末回报：Pearson ${fmt(m.score_vs_future_return_pearson)}</span><span>预测 ≥5% 跌幅：AUC ${fmt(m.drawdown_5pct_auc)}</span><span>≥7 分后跌幅事件：${pct(m.risk7_5pct_rate)}（${m.risk7_days} 天）/ 全样本 ${pct(m.base_5pct_rate)}</span></div>`;
    });
    metricBox.innerHTML = cards.join('');
    const m = data.metrics['20'];
    verdict.textContent = `回测结论：20 日前瞻跌幅相关系数 ${fmt(m.score_vs_future_drop_spearman)}，区分未来 ≥5% 跌幅的 AUC ${fmt(m.drawdown_5pct_auc)}（0.50 约等于随机）。≥7 分且有完整 20 日后续数据的日期只有 ${m.risk7_days} 天；≥9.3 分红色预警 ${m.risk93_days} 天。因此目前不能认为这个指数的预测能力已经得到验证。`;
  }

  async function loadBacktest() {
    try {
      const response = await fetch('data/backtest.json', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      data = await response.json();
      if (!Array.isArray(data.days) || data.days.length < 100 || !data.metrics?.['20']) throw new Error('历史数据不完整');
      dateLabel.textContent = `${data.start_date}—${data.end_date} · ${data.days.length} 个交易日`;
      chooseRange();
      renderMetrics();
    } catch (error) {
      dateLabel.textContent = '回测数据暂不可用';
      readout.textContent = '请稍后刷新页面。';
      verdict.textContent = '历史回测尚未成功加载，不能据此判断指数表现。';
    }
  }
  document.querySelectorAll('[data-range]').forEach(button => button.addEventListener('click', () => {
    range = button.dataset.range;
    chooseRange();
  }));
  slider.addEventListener('input', showSelected);
  window.addEventListener('resize', () => { if (visible.length) renderChart(); });
  loadBacktest();
})();
