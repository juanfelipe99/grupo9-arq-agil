// --- Toast ---
function showToast(type, title, message) {
  const container = document.getElementById('toast-container');
  if (!container) return;
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

// --- Auth Forms ---
function initAuthForms() {
  const registerForm = document.getElementById('register-form');
  if (registerForm) {
    registerForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const data = {
        username: registerForm.querySelector('[name="username"]').value,
        password: registerForm.querySelector('[name="password"]').value
      };

      fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })
        .then(res => res.json())
        .then(result => {
          if (result.error) {
            showToast('danger', 'Registration Failed', result.error);
          } else {
            showToast('success', 'Registered', 'Account created successfully.');
            registerForm.reset();
          }
        })
        .catch(() => {
          showToast('danger', 'Network Error', 'Could not reach the server.');
        });
    });
  }

  const loginForm = document.getElementById('login-form');
  if (loginForm) {
    loginForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const data = {
        username: loginForm.querySelector('[name="username"]').value,
        password: loginForm.querySelector('[name="password"]').value
      };

      fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })
        .then(res => res.json())
        .then(result => {
          if (result.error) {
            showToast('danger', 'Login Failed', result.error);
          } else {
            showToast('success', 'Welcome', `Logged in as ${result.username || data.username}`);
            if (result.redirect) {
              window.location.href = result.redirect;
            }
          }
        })
        .catch(() => {
          showToast('danger', 'Network Error', 'Could not reach the server.');
        });
    });
  }
}

// --- Services Check ---
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

// --- Load Users Table ---
function loadUsers() {
  const tbody = document.getElementById('users-table-body');
  if (!tbody) return;

  fetch('/api/users')
    .then(res => res.json())
    .then(data => {
      tbody.innerHTML = '';

      if (!data || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No users registered yet.</td></tr>';
        return;
      }

      data.forEach(user => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${user.id}</td>
          <td>${user.username}</td>
          <td><span class="badge badge-success">Active</span></td>
          <td>${user.created_at || 'N/A'}</td>
        `;
        tbody.appendChild(tr);
      });
    })
    .catch(() => {
      tbody.innerHTML = '<tr><td colspan="4" class="text-center text-danger">Failed to load users.</td></tr>';
    });
}

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
  initAuthForms();
  checkServices();
  loadUsers();

  setInterval(() => {
    checkServices();
    loadUsers();
  }, 10000);
});
