const socket = io();

let charts = {};

// --- SocketIO Events ---
socket.on('experiment_started', (data) => {
  showToast('info', 'Experiment Started', `Scenario "${data.scenario}" is now running.`);
  loadStats();
});

socket.on('experiment_finished', (data) => {
  showToast('success', 'Experiment Finished', `Scenario "${data.scenario}" completed with status: ${data.status}`);
  loadResults();
  loadStats();
});

socket.on('anomaly_detected', (data) => {
  showToast('danger', 'Anomaly Detected', `Scenario "${data.scenario}": ${data.details || 'Unknown anomaly'}`);
  loadResults();
  loadStats();
});

socket.on('session_revoked', (data) => {
  showToast('warning', 'Session Revoked', `Session for "${data.scenario}" was revoked.`);
  loadStats();
});

// --- Toast ---
function showToast(type, title, message) {
  const container = document.getElementById('toast-container');
  const icons = { success: '✓', danger: '✗', warning: '⚠', info: 'ℹ' };
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || 'ℹ'}</span>
    <div class="toast-body">
      <div class="toast-title">${title}</div>
      <div class="toast-message">${message}</div>
    </div>
    <button class="toast-close" onclick="this.parentElement.classList.add('toast-exit'); setTimeout(() => this.parentElement.remove(), 300)">✕</button>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('toast-exit');
    setTimeout(() => toast.remove(), 300);
  }, 5000);
}

// --- Run Experiment ---
function runExperiment(scenario) {
  const btn = event.target.closest('.btn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Running...';
  }

  fetch('/api/experiment/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario })
  })
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        showToast('danger', 'Error', data.error);
      } else {
        showToast('info', 'Experiment Queued', `Scenario "${scenario}" has been queued.`);
      }
    })
    .catch(err => {
      showToast('danger', 'Network Error', 'Could not reach the server.');
    })
    .finally(() => {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '▶ Run';
      }
    });
}

// --- Check Services ---
function checkServices() {
  fetch('/api/status')
    .then(res => res.json())
    .then(data => {
      Object.keys(data).forEach(service => {
        const dot = document.getElementById(`dot-${service}`);
        if (dot) {
          const isUp = data[service] === true || data[service] === 'up';
          dot.classList.toggle('active', isUp);
          dot.classList.toggle('inactive', !isUp);
        }
      });
    })
    .catch(() => {
      document.querySelectorAll('.service-dot').forEach(dot => {
        dot.classList.remove('active');
        dot.classList.add('inactive');
      });
    });
}

// --- Load Results ---
function loadResults() {
  fetch('/api/experiment/results')
    .then(res => res.json())
    .then(data => {
      const tbody = document.getElementById('results-table-body');
      if (!tbody) return;
      tbody.innerHTML = '';

      if (!data || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No results yet. Run an experiment to see data here.</td></tr>';
        return;
      }

      data.forEach(row => {
        const statusClass = row.status === 'success' ? 'badge-success' : 'badge-danger';
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${row.scenario}</td>
          <td>${row.status}</td>
          <td>${row.latency_ms ?? 'N/A'} ms</td>
          <td>${row.anomalies ?? 0}</td>
          <td>${row.created_at}</td>
        `;
        tbody.appendChild(tr);
      });
    })
    .catch(() => {});
}

// --- Load Stats ---
function loadStats() {
  fetch('/api/experiment/stats')
    .then(res => res.json())
    .then(data => {
      const el = (id) => document.getElementById(id);
      if (el('stat-total')) el('stat-total').textContent = data.total_runs ?? 0;
      if (el('stat-success')) el('stat-success').textContent = data.success_count ?? 0;
      if (el('stat-failed')) el('stat-failed').textContent = data.failed_count ?? 0;
      if (el('stat-anomalies')) el('stat-anomalies').textContent = data.anomaly_count ?? 0;
      if (el('stat-latency')) el('stat-latency').textContent = (data.avg_latency_ms ?? 0) + ' ms';
    })
    .catch(() => {});
}

// --- Charts ---
function initCharts() {
  const baseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: { color: '#8892b0', font: { size: 12 } }
      }
    },
    scales: {
      x: {
        ticks: { color: '#8892b0' },
        grid: { color: 'rgba(30,42,74,0.5)' }
      },
      y: {
        ticks: { color: '#8892b0' },
        grid: { color: 'rgba(30,42,74,0.5)' }
      }
    }
  };

  const doughnutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: { color: '#8892b0', font: { size: 12 }, padding: 15 }
      }
    }
  };

  // Chart 1: Bar - Experiments per Scenario
  const ctx1 = document.getElementById('chart-scenarios');
  if (ctx1) {
    charts.scenarios = new Chart(ctx1, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [{
          label: 'Runs',
          data: [],
          backgroundColor: 'rgba(0, 212, 170, 0.6)',
          borderColor: '#00d4aa',
          borderWidth: 1,
          borderRadius: 6
        }]
      },
      options: { ...baseOptions, plugins: { ...baseOptions.plugins, title: { display: true, text: 'Runs per Scenario', color: '#fff' } } }
    });
  }

  // Chart 2: Grouped Bar - Success vs Fail
  const ctx2 = document.getElementById('chart-success-fail');
  if (ctx2) {
    charts.successFail = new Chart(ctx2, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [
          {
            label: 'Success',
            data: [],
            backgroundColor: 'rgba(0, 212, 170, 0.6)',
            borderColor: '#00d4aa',
            borderWidth: 1,
            borderRadius: 4
          },
          {
            label: 'Failed',
            data: [],
            backgroundColor: 'rgba(255, 71, 87, 0.6)',
            borderColor: '#ff4757',
            borderWidth: 1,
            borderRadius: 4
          }
        ]
      },
      options: { ...baseOptions, plugins: { ...baseOptions.plugins, title: { display: true, text: 'Success vs Failed', color: '#fff' } } }
    });
  }

  // Chart 3: Doughnut - Status Distribution
  const ctx3 = document.getElementById('chart-status');
  if (ctx3) {
    charts.status = new Chart(ctx3, {
      type: 'doughnut',
      data: {
        labels: ['Success', 'Failed', 'Anomalies'],
        datasets: [{
          data: [0, 0, 0],
          backgroundColor: ['#00d4aa', '#ff4757', '#ffa502'],
          borderColor: '#111631',
          borderWidth: 3
        }]
      },
      options: doughnutOptions
    });
  }

  // Chart 4: Line - Latency Over Time
  const ctx4 = document.getElementById('chart-latency');
  if (ctx4) {
    charts.latency = new Chart(ctx4, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          label: 'Avg Latency (ms)',
          data: [],
          borderColor: '#5f9df7',
          backgroundColor: 'rgba(95, 157, 247, 0.1)',
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointBackgroundColor: '#5f9df7'
        }]
      },
      options: { ...baseOptions, plugins: { ...baseOptions.plugins, title: { display: true, text: 'Latency Over Time', color: '#fff' } } }
    });
  }

  updateCharts();
}

function updateCharts() {
  fetch('/api/experiment/stats')
    .then(res => res.json())
    .then(data => {
      if (!data || !data.by_scenario) return;
      const scenarios = Object.keys(data.by_scenario);

      if (charts.scenarios) {
        charts.scenarios.data.labels = scenarios;
        charts.scenarios.data.datasets[0].data = scenarios.map(s => data.by_scenario[s].total || 0);
        charts.scenarios.update();
      }

      if (charts.successFail) {
        charts.successFail.data.labels = scenarios;
        charts.successFail.data.datasets[0].data = scenarios.map(s => data.by_scenario[s].success || 0);
        charts.successFail.data.datasets[1].data = scenarios.map(s => data.by_scenario[s].failed || 0);
        charts.successFail.update();
      }

      if (charts.status) {
        charts.status.data.datasets[0].data = [data.success_count || 0, data.failed_count || 0, data.anomaly_count || 0];
        charts.status.update();
      }

      if (charts.latency && data.latency_history) {
        charts.latency.data.labels = data.latency_history.map((_, i) => `#${i + 1}`);
        charts.latency.data.datasets[0].data = data.latency_history;
        charts.latency.update();
      }
    })
    .catch(() => {});
}

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
  checkServices();
  loadResults();
  loadStats();
  initCharts();

  setInterval(() => {
    checkServices();
    loadResults();
    loadStats();
    updateCharts();
  }, 5000);
});
