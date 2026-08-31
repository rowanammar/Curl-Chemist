// ═══════════════════════════════════════════
// Curl Chemist — Dashboard Application (v2.0)
// ═══════════════════════════════════════════

// ── State ──
let currentUser = null; // { username: string, ... }
let pendingScanResult = null;
let currentView = 'shelf';
let dashboardData = {
  products: [],
  conflicts: [],
  routine: null,
  pipeline_logs: [],
  wash_history: []
};

// ── Utilities ──
const escapeHTML = (str) => {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};

// ═══════════════════════════════════════════
// Initialization & Auth Checks
// ═══════════════════════════════════════════

function initApp() {
  const savedUser = localStorage.getItem('curlChemistUser');
  if (savedUser) {
    try {
      currentUser = JSON.parse(savedUser);
      updateUserDisplay();
      hideAuthOverlay();
      
      // Load initial view
      const hash = window.location.hash.replace('#', '');
      if (hash && document.getElementById(`view-${hash}`)) {
        navigateTo(hash);
      } else {
        navigateTo('shelf');
      }
      
      fetchDashboardData();
      // Start polling
      setInterval(fetchDashboardData, 10000);
      
    } catch (e) {
      console.error("Invalid saved user", e);
      showAuthOverlay();
    }
  } else {
    showAuthOverlay();
  }
}

// ═══════════════════════════════════════════
// API Wrapper (injects X-User-Id header)
// ═══════════════════════════════════════════

async function apiFetch(url, options = {}) {
  if (!options.headers) options.headers = {};
  const token = localStorage.getItem('curlChemistToken');
  if (token) {
    options.headers['Authorization'] = `Bearer ${token}`;
  }
  const response = await fetch(url, options);
  if (response.status === 401 && !url.includes('/api/auth/login') && !url.includes('/api/auth/signup')) {
    handleLogout();
    showToast('Session expired. Please log in again.', 'warning');
  }
  return response;
}

// ═══════════════════════════════════════════
// Auth UI / Login / Signup
// ═══════════════════════════════════════════

function showAuthOverlay() {
  document.getElementById('auth-overlay').classList.add('visible');
  document.getElementById('app-layout').classList.add('blurred');
  showLoginForm();
}

function hideAuthOverlay() {
  document.getElementById('auth-overlay').classList.remove('visible');
  document.getElementById('app-layout').classList.remove('blurred');
}

function showLoginForm() {
  document.getElementById('auth-login').classList.remove('hidden');
  document.getElementById('auth-signup').classList.add('hidden');
}

function showSignupFlow() {
  document.getElementById('auth-login').classList.add('hidden');
  document.getElementById('auth-signup').classList.remove('hidden');
  goToStep(1);
}

async function handleLogin() {
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password') ? document.getElementById('login-password').value : '';
  if (!username || !password) return;
  
  const btn = document.getElementById('btn-login');
  btn.disabled = true;
  btn.textContent = 'Logging in...';
  
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();
    
    if (data.status === 'success') {
      currentUser = data.user;
      localStorage.setItem('curlChemistUser', JSON.stringify(currentUser));
      localStorage.setItem('curlChemistToken', data.token);
      updateUserDisplay();
      hideAuthOverlay();
      navigateTo('shelf');
      fetchDashboardData();
      showToast(`Welcome back, ${username}!`, 'success');
    } else {
      showToast(data.message, 'error');
    }
  } catch (err) {
    showToast('Login failed', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Log In';
  }
}

function handleLogout() {
  currentUser = null;
  localStorage.removeItem('curlChemistUser');
  localStorage.removeItem('curlChemistToken');
  dashboardData = { products: [], conflicts: [], routine: null, pipeline_logs: [], wash_history: [] };
  
  // Immediately clear UI to prevent flashing old data for the next user
  renderProducts([]);
  renderConflicts([]);
  renderRoutine(null);
  renderWashHistory([]);
  renderLogs([]);

  // Clear Advisor Chat
  advisorChatHistory = [];
  const chatMessages = document.getElementById('advisor-chat-messages');
  if (chatMessages) {
    chatMessages.innerHTML = `
      <div class="chat-message bot">
        <div class="chat-bubble">
          Hi there! I'm your Curl Chemist Advisor. I'm connected to your shelf, your wash history, and your hair profile. Ask me anything about your hair care routine or products!
        </div>
      </div>
    `;
  }

  showAuthOverlay();
  document.getElementById('login-username').value = '';
  if(document.getElementById('login-password')) document.getElementById('login-password').value = '';
}

function updateUserDisplay() {
  if (!currentUser) return;
  document.getElementById('sidebar-username').textContent = currentUser.username;
  document.getElementById('sidebar-avatar').textContent = currentUser.username.charAt(0).toUpperCase();
}


// ═══════════════════════════════════════════
// Onboarding Flow
// ═══════════════════════════════════════════

let currentSignupStep = 1;

function goToStep(stepNumber) {
  document.querySelectorAll('.onboarding-step').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.step-dot').forEach(el => el.classList.remove('active'));
  
  document.getElementById(`signup-step-${stepNumber}`).classList.add('active');
  for (let i = 1; i <= stepNumber; i++) {
    const dot = document.querySelector(`.step-dot[data-step="${i}"]`);
    if(dot) dot.classList.add('active');
  }
  currentSignupStep = stepNumber;
}

// -- Step 1: Username Check --
let usernameTimeout;
document.getElementById('signup-username').addEventListener('input', (e) => {
  clearTimeout(usernameTimeout);
  const val = e.target.value.trim();
  const statusEl = document.getElementById('username-status');
  const btnNext = document.getElementById('btn-next-1');
  
  if (!val) {
    statusEl.innerHTML = '';
    btnNext.disabled = true;
    return;
  }
  
  statusEl.innerHTML = '<span style="color:#666">Checking...</span>';
  btnNext.disabled = true;
  
  usernameTimeout = setTimeout(async () => {
    try {
      const res = await fetch(`/api/auth/check-username/${val}`);
      const data = await res.json();
      if (data.available) {
        statusEl.innerHTML = `<span style="color:var(--color-success)">✓ ${data.reason}</span>`;
        btnNext.disabled = false;
      } else {
        statusEl.innerHTML = `<span style="color:var(--color-danger)">✗ ${data.reason}</span>`;
        btnNext.disabled = true;
      }
    } catch (e) {
      statusEl.innerHTML = `<span style="color:var(--color-danger)">Error checking username</span>`;
    }
  }, 500);
});

// -- Step 2: Hair Details --
let selectedHairType = "";
function selectHairType(btn) {
  document.querySelectorAll('.hair-type-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  selectedHairType = btn.dataset.value;
}

let selectedGoals = new Set();
function toggleGoal(btn) {
  btn.classList.toggle('selected');
  const val = btn.dataset.value;
  if (selectedGoals.has(val)) selectedGoals.delete(val);
  else selectedGoals.add(val);
}

// -- Step 3: Location Geocoding --
let geocodeTimeout;
let selectedLocation = null;
document.getElementById('signup-city').addEventListener('input', (e) => {
  clearTimeout(geocodeTimeout);
  const val = e.target.value.trim();
  const resultsEl = document.getElementById('city-results');
  const displayEl = document.getElementById('selected-location');
  
  if (val.length < 3) {
    resultsEl.innerHTML = '';
    return;
  }
  
  geocodeTimeout = setTimeout(async () => {
    try {
      const res = await fetch(`/api/auth/geocode?city=${encodeURIComponent(val)}`);
      const data = await res.json();
      
      if (data.results && data.results.length > 0) {
        resultsEl.innerHTML = data.results.map((r, i) => `
          <div class="city-result-item" onclick='selectCity(${JSON.stringify(r)})'>
            <strong>${r.name}</strong>, ${r.admin1 ? r.admin1 + ', ' : ''}${r.country}
          </div>
        `).join('');
      } else {
        resultsEl.innerHTML = '<div style="padding:8px;color:#666">No cities found</div>';
      }
    } catch (e) {
      console.error(e);
    }
  }, 500);
});

window.selectCity = function(cityData) {
  selectedLocation = {
    city: cityData.name,
    latitude: cityData.latitude,
    longitude: cityData.longitude,
    timezone: cityData.timezone || 'UTC'
  };
  document.getElementById('city-results').innerHTML = '';
  document.getElementById('signup-city').value = cityData.name;
  
  const display = document.getElementById('selected-location');
  display.classList.remove('hidden');
  document.getElementById('location-display').textContent = 
    `${cityData.name}, ${cityData.admin1 ? cityData.admin1+', ' : ''}${cityData.country}`;
};

// -- Step 4: Optional Photo Upload (Signup) --
setupUploadZone('signup-photo-zone', 'signup-photo-input', 'signup-photo-preview', 'signup-photo-preview-img', 'signup-photo-preview-name');

async function handleSignup() {
  const username = document.getElementById('signup-username').value.trim();
  const email = document.getElementById('signup-email').value.trim();
  const password = document.getElementById('signup-password') ? document.getElementById('signup-password').value : 'temp-password';
  const porosity = document.getElementById('signup-porosity').value;
  const protein = document.getElementById('signup-protein').value;
  const thickness = document.getElementById('signup-thickness').value;
  const color = document.getElementById('signup-color').value;
  
  const formData = new FormData();
  formData.append('username', username);
  formData.append('email', email);
  formData.append('password', password);
  formData.append('hair_type', selectedHairType);
  formData.append('porosity', porosity);
  formData.append('protein_sensitivity', protein);
  formData.append('thickness', thickness);
  formData.append('color_history', color);
  formData.append('goals', Array.from(selectedGoals).join(','));
  
  if (selectedLocation) {
    formData.append('city', selectedLocation.city);
    formData.append('latitude', selectedLocation.latitude);
    formData.append('longitude', selectedLocation.longitude);
    formData.append('timezone', selectedLocation.timezone || 'UTC');
  }
  
  const photoInput = document.getElementById('signup-photo-input');
  if (photoInput.files.length > 0) {
    formData.append('photo', photoInput.files[0]);
  }
  
  const btn = document.getElementById('btn-create-profile');
  const loading = document.getElementById('signup-loading');
  
  btn.disabled = true;
  loading.classList.remove('hidden');
  
  try {
    const res = await fetch('/api/auth/signup', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    
    if (data.status === 'success') {
      // Auto-login
      currentUser = { username: data.username };
      localStorage.setItem('curlChemistUser', JSON.stringify(currentUser));
      localStorage.setItem('curlChemistToken', data.token);
      updateUserDisplay();
      hideAuthOverlay();
      navigateTo('shelf');
      showToast(data.message, 'success');
      showToast("Welcome Email sent! We've dispatched your introduction to your inbox.", "info");
      
      if (data.photo_analysis) {
         showToast(`AI detected your hair as ${data.photo_analysis.suggested_hair_type}`, 'info');
      }
    } else {
      showToast(data.message, 'error');
    }
  } catch (err) {
    showToast('Failed to create profile', 'error');
  } finally {
    btn.disabled = false;
    loading.classList.add('hidden');
  }
}


// ═══════════════════════════════════════════
// Navigation & View Router
// ═══════════════════════════════════════════

function navigateTo(viewName) {
  if(!currentUser && viewName !== 'auth') return;
  
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  const target = document.getElementById(`view-${viewName}`);
  if (target) {
    target.classList.add('active');
  }

  document.querySelectorAll('.nav-link').forEach(link => {
    link.classList.toggle('active', link.dataset.view === viewName);
  });

  currentView = viewName;
  closeMobileSidebar();
  history.replaceState(null, '', `#${viewName}`);
}

document.querySelectorAll('.nav-link').forEach(link => {
  link.addEventListener('click', (e) => {
    e.preventDefault();
    navigateTo(link.dataset.view);
  });
});

const hamburgerBtn = document.getElementById('hamburger-btn');
const sidebarOverlay = document.getElementById('sidebar-overlay');
const sidebar = document.getElementById('sidebar');

if(hamburgerBtn) {
  hamburgerBtn.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    sidebarOverlay.classList.toggle('visible');
  });
}
if(sidebarOverlay) {
  sidebarOverlay.addEventListener('click', closeMobileSidebar);
}
function closeMobileSidebar() {
  if(sidebar) sidebar.classList.remove('open');
  if(sidebarOverlay) sidebarOverlay.classList.remove('visible');
}


// ═══════════════════════════════════════════
// Toast Notification System
// ═══════════════════════════════════════════

const TOAST_ICONS = {
  success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
  error: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
  warning: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
  info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
};

function showToast(message, type = 'info', title = '') {
  const container = document.getElementById('toast-container');
  if(!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  const autoTitle = title || {
    success: 'Done',
    error: 'Something went wrong',
    warning: 'Heads up',
    info: 'Info',
  }[type];

  toast.innerHTML = `
    ${TOAST_ICONS[type] || TOAST_ICONS.info}
    <div class="toast-body">
      <div class="toast-title">${autoTitle}</div>
      <div class="toast-message">${message}</div>
    </div>
    <button class="toast-close" aria-label="Close notification">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
    </button>
  `;

  toast.querySelector('.toast-close').addEventListener('click', () => removeToast(toast));
  container.appendChild(toast);
  setTimeout(() => removeToast(toast), 4000);
}

function removeToast(toast) {
  if (!toast || !toast.parentNode) return;
  toast.classList.add('removing');
  setTimeout(() => toast.remove(), 200);
}

// ═══════════════════════════════════════════
// Tab Switching (Scan View)
// ═══════════════════════════════════════════

function switchTab(tabName) {
  document.querySelectorAll('#scan-card .tab').forEach(t => {
    const isActive = t.dataset.tab === tabName;
    t.classList.toggle('active', isActive);
    t.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });

  document.querySelectorAll('#scan-card .tab-content').forEach(c => c.classList.remove('active'));
  const panel = document.getElementById(`tab-${tabName}`);
  if (panel) panel.classList.add('active');

  cancelScan();
}

// ═══════════════════════════════════════════
// File Upload Zones
// ═══════════════════════════════════════════

function setupUploadZone(zoneId, inputId, previewId, previewImgId, previewNameId) {
  const zone = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  if (!zone || !input) return;

  ['dragenter', 'dragover'].forEach(evt => {
    zone.addEventListener(evt, (e) => {
      e.preventDefault();
      zone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(evt => {
    zone.addEventListener(evt, (e) => {
      e.preventDefault();
      zone.classList.remove('dragover');
    });
  });

  zone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      input.files = files;
      showFilePreview(input, previewId, previewImgId, previewNameId);
    }
  });

  input.addEventListener('change', () => {
    showFilePreview(input, previewId, previewImgId, previewNameId);
  });
}

function showFilePreview(input, previewId, previewImgId, previewNameId) {
  const preview = document.getElementById(previewId);
  const previewImg = document.getElementById(previewImgId);
  const previewName = document.getElementById(previewNameId);
  if (!preview || !input.files.length) return;

  const file = input.files[0];
  const reader = new FileReader();
  reader.onload = (e) => {
    previewImg.src = e.target.result;
    previewName.textContent = file.name;
    preview.classList.add('visible');
  };
  reader.readAsDataURL(file);
}

setupUploadZone('photo-drop-zone', 'photo-input', 'photo-preview', 'photo-preview-img', 'photo-preview-name');
setupUploadZone('selfie-drop-zone', 'selfie-input', 'selfie-preview', 'selfie-preview-img', 'selfie-preview-name');


// ═══════════════════════════════════════════
// Scanning Methods
// ═══════════════════════════════════════════

async function scanPhoto() {
  const fileInput = document.getElementById('photo-input');
  if (!fileInput.files.length) {
    showToast('Please select a photo first.', 'warning');
    return;
  }
  const formData = new FormData();
  formData.append('file', fileInput.files[0]);

  showScanLoading(true);
  try {
    const response = await apiFetch('/api/scan/photo', { method: 'POST', body: formData });
    const data = await response.json();
    if (data.status === 'error') throw new Error(data.message);
    showScanResults(data);
  } catch (error) {
    showToast('Scan failed: ' + error.message, 'error');
  } finally {
    showScanLoading(false);
  }
}

async function scanByName() {
  const nameInput = document.getElementById('name-input');
  const name = nameInput.value.trim();
  if (!name) { showToast('Please enter a product name.', 'warning'); return; }

  showScanLoading(true);
  try {
    const response = await apiFetch('/api/scan/name', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_name: name }),
    });
    const data = await response.json();
    if (data.status === 'error') throw new Error(data.message);
    showScanResults(data);
  } catch (error) {
    showToast('Lookup failed: ' + error.message, 'error');
  } finally {
    showScanLoading(false);
  }
}

async function scanManual() {
  const nameInput = document.getElementById('manual-product-name');
  const ingredientsInput = document.getElementById('manual-ingredients');
  const name = nameInput.value.trim();
  const ingredients = ingredientsInput.value.trim();

  if (!name || !ingredients) { showToast('Please fill all fields.', 'warning'); return; }

  showScanLoading(true);
  try {
    const response = await apiFetch('/api/scan/manual', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_name: name, ingredients_text: ingredients }),
    });
    const data = await response.json();
    if (data.status === 'error') throw new Error(data.message);
    showScanResults(data);
  } catch (error) {
    showToast('Parse failed: ' + error.message, 'error');
  } finally {
    showScanLoading(false);
  }
}

function showScanResults(data) {
  pendingScanResult = data;
  document.getElementById('result-name').textContent = data.product_name || 'Unknown';
  document.getElementById('result-brand').textContent = data.brand || 'Unknown';
  document.getElementById('result-type').textContent = data.product_type || 'Unknown';

  const warning = document.getElementById('not-hair-warning');
  if (data.is_hair_product === false) {
    document.getElementById('detected-category').textContent = data.product_category_detected || 'non-hair product';
    warning.classList.remove('hidden');
  } else {
    warning.classList.add('hidden');
  }

  const container = document.getElementById('result-ingredients');
  const ingredients = data.ingredients || [];
  if (ingredients.length === 0) {
    container.innerHTML = `<div class="empty-state" style="padding: 24px 0"><div class="empty-state-text">No ingredients found.</div></div>`;
  } else {
    container.innerHTML = `
      <div style="font-size: 0.8125rem; color: var(--color-text-muted); margin-bottom: 12px;">
        ${ingredients.length} ingredient${ingredients.length !== 1 ? 's' : ''} found
      </div>
      <div class="ingredient-grid">
        ${ingredients.map(i => `
          <div class="ingredient-chip ${i.needs_review ? 'needs-review' : ''}">
            <span class="ingredient-chip-name">${i.name || i.inci || 'Unknown'}</span>
            <span class="ingredient-chip-category">${i.category || 'other'}${i.needs_review ? ' ·review' : ''}</span>
          </div>
        `).join('')}
      </div>`;
  }
  document.getElementById('scan-results').classList.remove('hidden');
}

async function confirmProduct() {
  if (!pendingScanResult) return;
  const btn = document.getElementById('btn-confirm');
  const originalHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `⏳ Analyzing Chemistry...`;

  try {
    const response = await apiFetch('/api/confirm-product', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pendingScanResult),
    });
    const data = await response.json();
    if (data.status === 'error') throw new Error(data.message);

    let msg = `${data.product_name} added.`;
    if (data.conflicts_found > 0) {
      showToast(msg, 'success');
      showToast(`${data.conflicts_found} conflict(s) found`, data.critical_conflicts > 0 ? 'warning' : 'info');
    } else {
      showToast(msg, 'success');
    }
    showToast("Agent is reviewing your shelf. A Shopping Alert email will be sent if necessities are missing.", "info");

    // The analyzing state is now synced via /api/dashboard-data polling.
    cancelScan();
    fetchDashboardData();
    navigateTo('shelf');
  } catch (error) {
    showToast('Save failed: ' + error.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

function cancelScan() {
  pendingScanResult = null;
  document.getElementById('scan-results').classList.add('hidden');
  document.getElementById('not-hair-warning').classList.add('hidden');
}

async function deleteProduct(productId, productName) {
  if (!confirm(`Remove "${productName}"?`)) return;
  try {
    const response = await apiFetch(`/api/products/${productId}`, { method: 'DELETE' });
    const data = await response.json();
    if (data.status === 'error') throw new Error(data.message);
    showToast(`${productName} removed.`, 'success');
    fetchDashboardData();
  } catch (error) {
    showToast('Delete failed: ' + error.message, 'error');
  }
}


// ═══════════════════════════════════════════
// Wash Day & Comparison
// ═══════════════════════════════════════════

async function logWashDay() {
  const fileInput = document.getElementById('selfie-input');
  if (!fileInput.files.length) {
    showToast('Select a photo first.', 'warning');
    return;
  }
  const notes = document.getElementById('wash-notes').value.trim();
  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  formData.append('notes', notes);

  document.getElementById('wash-loading').classList.remove('hidden');
  document.getElementById('wash-result').classList.add('hidden');
  document.getElementById('btn-wash').disabled = true;

  try {
    const response = await apiFetch('/api/wash-day', { method: 'POST', body: formData });
    const data = await response.json();
    if (data.status === 'error') throw new Error(data.message);

    const a = data.analysis;
    const c = data.comparison;
    
    let comparisonHtml = '';
    if (c) {
      comparisonHtml = `
        <div class="comparison-panel mt-4">
          <h4 class="comparison-title">Comparison vs. Past Washes</h4>
          
          <div class="comparison-trend badge ${c.trend === 'improving' ? 'badge-success' : (c.trend === 'declining' ? 'badge-danger' : 'badge-neutral')}">
             Trend: ${c.trend}
          </div>
          <p class="comparison-text mt-2">${c.vs_last_wash}</p>
          
          ${c.climate_adjusted_notes && c.climate_adjusted_notes.length ? `
             <div class="comparison-climate mt-2">
               <strong>🌤 Weather Factor:</strong> ${c.climate_adjusted_notes.join(' ')}
             </div>
          ` : ''}
          
          ${c.comparison_insights && c.comparison_insights.length ? `
             <ul class="comparison-list mt-3">
               ${c.comparison_insights.map(i => `<li>${i}</li>`).join('')}
             </ul>
          ` : ''}
          
          ${c.recommendations && c.recommendations.length ? `
             <div class="comparison-recommendations mt-3">
               <strong>💡 Recommendations:</strong>
               <ul>${c.recommendations.map(r => `<li>${r}</li>`).join('')}</ul>
             </div>
          ` : ''}
        </div>
      `;
    }

    document.getElementById('wash-result').innerHTML = `
      <div class="alert alert-success mb-4">Hair analysis and comparison complete!</div>
      <div class="wash-scores-grid">
        <div class="wash-score-card"><div class="wash-score-label">Frizz Level</div><div class="wash-score-value">${a.frizz_level}<small>/10</small></div></div>
        <div class="wash-score-card"><div class="wash-score-label">Definition</div><div class="wash-score-value">${a.curl_definition}<small>/10</small></div></div>
        <div class="wash-score-card"><div class="wash-score-label">Shine</div><div class="wash-score-value">${a.shine}<small>/10</small></div></div>
        <div class="wash-score-card"><div class="wash-score-label">Damage</div><div class="wash-score-value">${a.damage_visible}<small>/10</small></div></div>
      </div>
      ${a.observations ? `<div class="wash-observations mt-3">${a.observations}</div>` : ''}
      ${comparisonHtml}
    `;
    
    document.getElementById('wash-result').classList.remove('hidden');

    fileInput.value = '';
    document.getElementById('wash-notes').value = '';
    document.getElementById('selfie-preview').classList.remove('visible');
    
    showToast('Wash day logged successfully.', 'success');
    fetchDashboardData();
  } catch (error) {
    showToast('Analysis failed: ' + error.message, 'error');
  } finally {
    document.getElementById('wash-loading').classList.add('hidden');
    document.getElementById('btn-wash').disabled = false;
  }
}

// ═══════════════════════════════════════════
// Trigger Nightly Pipeline
// ═══════════════════════════════════════════
async function triggerNightly() {
  const btn = document.getElementById('btn-generate-routine');
  const originalHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner spinner-sm" style="display:inline-block; margin-right:8px; border-color:currentColor; border-right-color:transparent; width:14px; height:14px; border-width:2px"></div> Generating...';
  try {
    const response = await apiFetch('/pipelines/nightly', { method: 'POST' });
    const data = await response.json();
    if (data.status === 'error') throw new Error(data.message || 'Pipeline failed');
    
    showToast('Routine generated.', 'success');
    
    // Check for calendar/email scheduling issues in the summary
    const summaryStr = (data.summary || '').toLowerCase();
    if (summaryStr.includes("failed to schedule") || summaryStr.includes("error scheduling")) {
      showToast('Routine generated, but there was an issue scheduling the calendar event.', 'warning');
    } else {
      showToast('A Wash Day Calendar Invite has been sent to your email!', 'info');
    }
    
    fetchDashboardData();
  } catch (error) {
    showToast('Pipeline failed: ' + error.message, 'error');
  } finally {
    btn.innerHTML = originalHtml;
    btn.disabled = false;
  }
}

function showScanLoading(visible) {
  document.getElementById('scan-loading').classList.toggle('hidden', !visible);
  document.querySelectorAll('#scan-card .btn-primary').forEach(b => b.disabled = visible);
}

function toggleProduct(productId) {
  const detail = document.getElementById(`product-detail-${productId}`);
  const expand = document.getElementById(`product-expand-${productId}`);
  if (!detail) return;
  detail.classList.toggle('open');
  if (expand) expand.classList.toggle('expanded');
}

// ═══════════════════════════════════════════
// Dashboard Data Fetching & Rendering
// ═══════════════════════════════════════════

async function fetchDashboardData() {
  if (!currentUser) return;
  try {
    const response = await apiFetch('/api/dashboard-data');
    const data = await response.json();
    dashboardData = data;
    
    // Sync UI state with backend analyzing flag
    window.isAnalyzingConflicts = data.is_analyzing || false;
    
    renderProducts(data.products);
    renderRoutine(data.routine);
    renderConflicts(data.conflicts);
    renderLogs(data.pipeline_logs);
    renderWashHistory(data.wash_history);
    renderCalendarEvents(data.calendar_events);
    updateNavBadges(data);
  } catch (error) {
    console.error('Error fetching dashboard data:', error);
  }
}

function updateNavBadges(data) {
  document.getElementById('nav-product-count').textContent = data.products ? data.products.length : 0;
  const conflictCount = data.conflicts ? data.conflicts.length : 0;
  const cb = document.getElementById('nav-conflict-badge');
  cb.textContent = conflictCount;
  cb.classList.toggle('hidden', conflictCount === 0);
}

function renderProducts(products) {
  const list = document.getElementById('products-list');
  const empty = document.getElementById('shelf-empty');
  
  if (!products || products.length === 0) {
    list.innerHTML = '';
    empty.style.display = '';
    return;
  }
  empty.style.display = 'none';

  list.innerHTML = products.map(p => {
    const ic = (p.ingredients || []).length;
    const escapedName = escapeHTML(p.product_name || 'Unknown');
    const safeBrand = escapeHTML(p.brand || '');
    const safeType = escapeHTML(p.product_type || '');
    
    return `
      <div class="product-card">
        <div class="product-card-main" onclick="toggleProduct('${escapeHTML(p.id)}')">
          <div class="product-card-info">
            <div class="product-card-name">${escapedName}</div>
            <div class="product-card-meta">
              ${safeBrand ? `<span>${safeBrand}</span>` : ''}
              ${safeType ? `<span>${safeType}</span>` : ''}
              <span>${ic} ingredient${ic !== 1 ? 's' : ''}</span>
            </div>
          </div>
          <div class="product-card-actions">
            <button class="btn btn-danger btn-sm" onclick="event.stopPropagation(); deleteProduct('${escapeHTML(p.id)}', '${escapedName.replace(/'/g, "\\'")}')">Remove</button>
            <button class="product-card-expand" id="product-expand-${escapeHTML(p.id)}">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
          </div>
        </div>
        <div class="product-card-detail" id="product-detail-${escapeHTML(p.id)}">
          ${ic > 0 ? `
            <div class="ingredient-grid">
              ${(p.ingredients || []).map(i => `
                <div class="ingredient-chip ${i.needs_review ? 'needs-review' : ''}">
                  <span class="ingredient-chip-name">${escapeHTML(i.name || i.inci || 'Unknown')}</span>
                  <span class="ingredient-chip-category">${escapeHTML(i.category || 'other')}</span>
                </div>
              `).join('')}
            </div>
          ` : '<p style="font-size:0.8rem;">No ingredients listed.</p>'}
        </div>
      </div>`;
  }).join('');
}

function renderRoutine(routine) {
  const content = document.getElementById('routine-content');
  const empty = document.getElementById('routine-empty');
  if (!routine || !routine.steps) {
    content.classList.add('hidden');
    empty.style.display = '';
    return;
  }
  empty.style.display = 'none';
  content.classList.remove('hidden');

  content.innerHTML = `
    ${routine.summary ? `<div class="routine-summary-text">${routine.summary}</div>` : ''}
    <div class="routine-steps">
      ${(routine.steps || []).map(s => `
        <div class="routine-step">
          <div class="step-number">${s.order || '?'}</div>
          <div class="step-content">
            <div class="step-action">${s.action || 'Step'}</div>
            <div class="step-product">with ${s.product_name || 'product'}${s.amount ? ` — ${s.amount}` : ''}</div>
            ${s.technique ? `<div class="step-details">${s.technique}</div>` : ''}
            ${s.wait_minutes ? `<div class="step-wait">Wait ${s.wait_minutes} min</div>` : ''}
          </div>
        </div>
      `).join('')}
    </div>
    ${routine.climate_notes && routine.climate_notes.length ? `
      <div class="climate-notes">
        <div class="climate-notes-title">Climate Notes</div>
        <ul>${routine.climate_notes.map(n => `<li>${n}</li>`).join('')}</ul>
      </div>` : ''}
  `;
}

function renderConflicts(conflicts) {
  const list = document.getElementById('conflicts-list');
  const empty = document.getElementById('conflicts-empty');
  
  if (window.isAnalyzingConflicts) {
    empty.style.display = 'none';
    list.innerHTML = `
      <div class="empty-state" style="padding: 40px 0;">
        <div class="empty-state-icon">🧪</div>
        <div class="empty-state-text">The Agent is analyzing your shelf for chemical conflicts...</div>
      </div>`;
    return;
  }
  
  if (!conflicts || conflicts.length === 0) {
    list.innerHTML = '';
    empty.style.display = '';
    return;
  }
  empty.style.display = 'none';
  list.innerHTML = conflicts.map(c => {
    const sc = c.severity === 'critical' ? 'critical' : (c.severity === 'warning' ? 'warning' : '');
    const bc = c.severity === 'critical' ? 'badge-danger' : (c.severity === 'warning' ? 'badge-warning' : 'badge-neutral');
    
    const safeA = escapeHTML(c.product_a_name || '');
    const safeB = escapeHTML(c.product_b_name || '');
    const safeN = escapeHTML(c.product_name || '');
    const productsText = (safeA && safeB) ? `${safeA} × ${safeB}` : safeN;
    
    return `
      <div class="conflict-card ${sc}">
        <div class="conflict-card-header">
          <span class="badge ${bc}">${escapeHTML(c.severity || 'unknown')}</span>
          <span class="conflict-card-products">
            ${productsText}
          </span>
        </div>
        <div class="conflict-card-explanation">${escapeHTML(c.explanation || 'Conflict')}</div>
        ${c.fix ? `<div class="conflict-card-fix"><span>${escapeHTML(c.fix)}</span></div>` : ''}
      </div>`;
  }).join('');
}

function renderWashHistory(history) {
   const container = document.getElementById('wash-history-gallery');
   const empty = document.getElementById('wash-history-empty');
   
   if (!history || history.length === 0) {
       if (empty) empty.style.display = '';
       if (container) container.innerHTML = '';
       if (empty) container.appendChild(empty);
       return;
   }
   
   if (empty) empty.style.display = 'none';
   
   container.innerHTML = history.map(entry => {
       const a = entry.analysis || {};
       const w = entry.weather_that_day || {};
       const date = new Date(entry.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
       
       return `
          <div class="history-card">
             <div class="history-card-header">
                <strong>${date}</strong>
                <span class="badge badge-neutral" style="font-size: 0.7rem">
                   💧 ${w.humidity || '?'}%
                </span>
             </div>
             <div class="history-card-scores">
                <div><span>Frizz:</span> <strong>${a.frizz_level || '?'}</strong>/10</div>
                <div><span>Def:</span> <strong>${a.curl_definition || '?'}</strong>/10</div>
                <div><span>Shine:</span> <strong>${a.shine || '?'}</strong>/10</div>
             </div>
             ${entry.products_used && entry.products_used.length ? `
                <div class="history-card-products">
                   ${entry.products_used.length} products used
                </div>
             ` : ''}
          </div>
       `;
   }).join('');
}

function renderLogs(logs) {
  const list = document.getElementById('logs-list');
  const empty = document.getElementById('activity-empty');
  if (!logs || logs.length === 0) {
    list.innerHTML = '';
    empty.style.display = '';
    return;
  }
  empty.style.display = 'none';
  list.innerHTML = `<div class="log-list">${logs.map(l => {
    const t = l.timestamp ? new Date(l.timestamp._seconds ? l.timestamp._seconds * 1000 : l.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
    const st = l.status || 'info';
    return `<div class="log-entry"><div class="log-dot ${escapeHTML(st)}"></div><span class="log-time">${escapeHTML(t)}</span><span class="log-message"><strong>[${escapeHTML(l.pipeline || '?')}]</strong> ${escapeHTML(l.message || '')}</span></div>`;
  }).join('')}</div>`;
}

// ═══════════════════════════════════════════
// Alerts & Calendar Events
// ═══════════════════════════════════════════

function renderAlerts(alerts) {
  const container = document.getElementById('alerts-container');
  if (!container) return;
  
  if (!alerts || alerts.length === 0) {
    container.innerHTML = '';
    return;
  }
  
  const activeAlerts = alerts.filter(a => !a.acknowledged);
  if (activeAlerts.length === 0) {
    container.innerHTML = '';
    return;
  }
  
  container.innerHTML = activeAlerts.map(a => `
    <div class="alert-banner ${a.urgency === 'high' ? 'danger' : 'warning'}" id="alert-${escapeHTML(a.id)}">
      <div class="alert-banner-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/>
          <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
      </div>
      <div class="alert-banner-content">
        <h4>${escapeHTML(a.title || '')}</h4>
        <p>${escapeHTML(a.body || '')}</p>
        <p><strong>Recommended:</strong> ${escapeHTML(a.recommended_product_type || '')}</p>
      </div>
      <button class="alert-banner-close" onclick="acknowledgeAlert('${escapeHTML(a.id)}')">Dismiss</button>
    </div>
  `).join('');
}

async function acknowledgeAlert(alertId) {
  try {
    await apiFetch('/api/alerts/' + alertId + '/acknowledge', { method: 'POST' });
    const alertEl = document.getElementById('alert-' + alertId);
    if (alertEl) alertEl.remove();
    fetchDashboardData();
  } catch (e) {
    console.error(e);
  }
}

function renderCalendarEvents(events) {
  const section = document.getElementById('calendar-events-section');
  const list = document.getElementById('calendar-events-list');
  if (!section || !list) return;
  
  if (!events || events.length === 0) {
    section.classList.add('hidden');
    return;
  }
  
  section.classList.remove('hidden');
  
  list.innerHTML = events.map(e => `
    <div class="calendar-event-card">
      <div class="calendar-event-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
      </div>
      <div class="calendar-event-info">
        <div class="calendar-event-title">${escapeHTML(e.title || '')}</div>
        <div class="calendar-event-time">${new Date(e.start_time).toLocaleString()} (${e.duration_minutes} min)</div>
      </div>
      <button class="btn btn-primary btn-sm" onclick="downloadIcs('${encodeURIComponent(e.ics_content || '').replace(/'/g, "%27")}', 'wash_day.ics')">Download .ics</button>
    </div>
  `).join('');
}

function downloadIcs(content, filename) {
  const decoded = decodeURIComponent(content);
  const blob = new Blob([decoded], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ═══════════════════════════════════════════
// Toast Notifications
// ═══════════════════════════════════════════


// ═══════════════════════════════════════════
// Advisor Chat
// ═══════════════════════════════════════════
let advisorChatHistory = [];

async function sendAdvisorMessage() {
  const input = document.getElementById('advisor-chat-input');
  const message = input.value.trim();
  if (!message) return;
  
  // Clear input
  input.value = '';
  
  // Append user message to UI
  appendChatMessage(message, 'user');
  
  // Append typing indicator for bot
  const typingId = appendTypingIndicator();
  
  // Build payload with history
  const payload = {
    message: message,
    history: advisorChatHistory
  };
  
  // Update local history
  advisorChatHistory.push({ role: 'user', content: message });
  
  try {
    const res = await apiFetch('/api/advisor/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    const data = await res.json();
    removeTypingIndicator(typingId);
    
    if (data.status === 'success') {
      const reply = data.reply;
      appendChatMessage(reply, 'bot');
      advisorChatHistory.push({ role: 'model', content: reply });
      fetchDashboardData(); // Refresh activity log immediately
    } else {
      appendChatMessage("I'm sorry, I encountered an error. Please try again.", 'bot');
    }
  } catch (err) {
    console.error(err);
    removeTypingIndicator(typingId);
    appendChatMessage("Network error. Please try again later.", 'bot');
  }
}

function appendChatMessage(text, sender) {
  const container = document.getElementById('advisor-chat-messages');
  const div = document.createElement('div');
  div.className = `chat-message ${sender}`;
  
  // Sanitize HTML and apply basic formatting
  let safeText = escapeHTML(text || '');
  let formattedText = safeText
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
    
  div.innerHTML = `<div class="chat-bubble">${formattedText}</div>`;
  container.appendChild(div);
  
  // Scroll to bottom
  container.scrollTop = container.scrollHeight;
}

function appendTypingIndicator() {
  const container = document.getElementById('advisor-chat-messages');
  const div = document.createElement('div');
  const id = 'typing-' + Date.now();
  div.id = id;
  div.className = 'chat-message bot';
  div.innerHTML = `
    <div class="chat-bubble">
      <div class="typing-indicator">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    </div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return id;
}

function removeTypingIndicator(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

// Allow Enter key to send message
document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('advisor-chat-input');
  if (input) {
    input.addEventListener('keypress', function(e) {
      if (e.key === 'Enter') {
        sendAdvisorMessage();
      }
    });
  }
});

// Kick off
initApp();
