// ═══════════════════════════════════════════
// Curl Chemist — Dashboard Application
// ═══════════════════════════════════════════

// ── State ──
let pendingScanResult = null;
let currentView = 'shelf';
let dashboardData = {
  products: [],
  conflicts: [],
  routine: null,
  pipeline_logs: [],
};


// ═══════════════════════════════════════════
// Navigation & View Router
// ═══════════════════════════════════════════

function navigateTo(viewName) {
  // Update view visibility
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  const target = document.getElementById(`view-${viewName}`);
  if (target) {
    target.classList.add('active');
  }

  // Update nav links
  document.querySelectorAll('.nav-link').forEach(link => {
    link.classList.toggle('active', link.dataset.view === viewName);
  });

  currentView = viewName;

  // Close mobile sidebar
  closeMobileSidebar();

  // Update URL hash without scroll
  history.replaceState(null, '', `#${viewName}`);
}

// Nav link click handlers
document.querySelectorAll('.nav-link').forEach(link => {
  link.addEventListener('click', (e) => {
    e.preventDefault();
    navigateTo(link.dataset.view);
  });
});


// ═══════════════════════════════════════════
// Mobile Sidebar
// ═══════════════════════════════════════════

const hamburgerBtn = document.getElementById('hamburger-btn');
const sidebarOverlay = document.getElementById('sidebar-overlay');
const sidebar = document.getElementById('sidebar');

hamburgerBtn.addEventListener('click', () => {
  sidebar.classList.toggle('open');
  sidebarOverlay.classList.toggle('visible');
});

sidebarOverlay.addEventListener('click', closeMobileSidebar);

function closeMobileSidebar() {
  sidebar.classList.remove('open');
  sidebarOverlay.classList.remove('visible');
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

  // Close button
  toast.querySelector('.toast-close').addEventListener('click', () => removeToast(toast));

  container.appendChild(toast);

  // Auto-dismiss after 4 seconds
  setTimeout(() => removeToast(toast), 4000);
}

function removeToast(toast) {
  if (!toast || !toast.parentNode) return;
  toast.classList.add('removing');
  setTimeout(() => toast.remove(), 200);
}


// ═══════════════════════════════════════════
// Tab Switching
// ═══════════════════════════════════════════

function switchTab(tabName) {
  // Update tab buttons
  document.querySelectorAll('#scan-card .tab').forEach(t => {
    const isActive = t.dataset.tab === tabName;
    t.classList.toggle('active', isActive);
    t.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });

  // Update tab content
  document.querySelectorAll('#scan-card .tab-content').forEach(c => c.classList.remove('active'));
  const panel = document.getElementById(`tab-${tabName}`);
  if (panel) panel.classList.add('active');

  // Hide scan results when switching tabs
  cancelScan();
}


// ═══════════════════════════════════════════
// File Upload — Drag & Drop + Preview
// ═══════════════════════════════════════════

function setupUploadZone(zoneId, inputId, previewId, previewImgId, previewNameId) {
  const zone = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  if (!zone || !input) return;

  // Drag events
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

  // File input change
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

// Initialize upload zones
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
    const response = await fetch('/api/scan/photo', {
      method: 'POST',
      body: formData,
    });
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
  if (!name) {
    showToast('Please enter a product name.', 'warning');
    return;
  }

  showScanLoading(true);
  try {
    const response = await fetch('/api/scan/name', {
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

  if (!name) { showToast('Please enter a product name.', 'warning'); return; }
  if (!ingredients) { showToast('Please enter the ingredients.', 'warning'); return; }

  showScanLoading(true);
  try {
    const response = await fetch('/api/scan/manual', {
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


// ═══════════════════════════════════════════
// Display Scan Results for Review
// ═══════════════════════════════════════════

function showScanResults(data) {
  pendingScanResult = data;

  document.getElementById('result-name').textContent = data.product_name || 'Unknown';
  document.getElementById('result-brand').textContent = data.brand || 'Unknown';
  document.getElementById('result-type').textContent = data.product_type || 'Unknown';

  // Hair product warning
  const warning = document.getElementById('not-hair-warning');
  if (data.is_hair_product === false) {
    document.getElementById('detected-category').textContent =
      data.product_category_detected || 'non-hair product';
    warning.classList.remove('hidden');
  } else {
    warning.classList.add('hidden');
  }

  // Render ingredients
  const container = document.getElementById('result-ingredients');
  const ingredients = data.ingredients || [];
  if (ingredients.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="padding: 24px 0">
        <div class="empty-state-text">No ingredients found in this scan.</div>
      </div>`;
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


// ═══════════════════════════════════════════
// Confirm / Cancel
// ═══════════════════════════════════════════

async function confirmProduct() {
  if (!pendingScanResult) return;

  const btn = document.getElementById('btn-confirm');
  btn.disabled = true;

  try {
    const response = await fetch('/api/confirm-product', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pendingScanResult),
    });
    const data = await response.json();

    if (data.status === 'error') throw new Error(data.message);

    let msg = `${data.product_name} added to your shelf.`;
    if (data.conflicts_found > 0) {
      showToast(msg, 'success', 'Product Added');
      showToast(
        `${data.conflicts_found} conflict${data.conflicts_found !== 1 ? 's' : ''} found (${data.critical_conflicts} critical).`,
        data.critical_conflicts > 0 ? 'warning' : 'info',
        'Conflicts Detected'
      );
    } else {
      showToast(msg, 'success', 'Product Added');
    }

    cancelScan();
    fetchDashboardData();
    navigateTo('shelf');
  } catch (error) {
    showToast('Failed to save: ' + error.message, 'error');
  } finally {
    btn.disabled = false;
  }
}

function cancelScan() {
  pendingScanResult = null;
  document.getElementById('scan-results').classList.add('hidden');
  document.getElementById('not-hair-warning').classList.add('hidden');
}


// ═══════════════════════════════════════════
// Delete Product
// ═══════════════════════════════════════════

async function deleteProduct(productId, productName) {
  if (!confirm(`Remove "${productName}" from your shelf?`)) return;

  try {
    const response = await fetch(`/api/products/${productId}`, { method: 'DELETE' });
    const data = await response.json();
    if (data.status === 'error') throw new Error(data.message);
    showToast(`${productName} removed from your shelf.`, 'success', 'Removed');
    fetchDashboardData();
  } catch (error) {
    showToast('Failed to delete: ' + error.message, 'error');
  }
}


// ═══════════════════════════════════════════
// Wash Day Selfie
// ═══════════════════════════════════════════

async function logWashDay() {
  const fileInput = document.getElementById('selfie-input');
  if (!fileInput.files.length) {
    showToast('Please select a hair selfie first.', 'warning');
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
    const response = await fetch('/api/wash-day', {
      method: 'POST',
      body: formData,
    });
    const data = await response.json();
    if (data.status === 'error') throw new Error(data.message);

    const a = data.analysis;
    document.getElementById('wash-result').innerHTML = `
      <div class="alert alert-success mb-4">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
        <div>Hair analysis complete and saved.</div>
      </div>
      <div class="wash-scores-grid">
        <div class="wash-score-card">
          <div class="wash-score-label">Frizz Level</div>
          <div class="wash-score-value">${a.frizz_level}<small>/10</small></div>
        </div>
        <div class="wash-score-card">
          <div class="wash-score-label">Curl Definition</div>
          <div class="wash-score-value">${a.curl_definition}<small>/10</small></div>
        </div>
        <div class="wash-score-card">
          <div class="wash-score-label">Shine</div>
          <div class="wash-score-value">${a.shine}<small>/10</small></div>
        </div>
        <div class="wash-score-card">
          <div class="wash-score-label">Damage Visible</div>
          <div class="wash-score-value">${a.damage_visible}<small>/10</small></div>
        </div>
      </div>
      ${a.observations ? `<div class="wash-observations mt-3">${a.observations}</div>` : ''}
    `;
    document.getElementById('wash-result').classList.remove('hidden');

    // Reset form
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
  btn.disabled = true;

  try {
    const response = await fetch('/pipelines/nightly', { method: 'POST' });
    const data = await response.json();
    if (data.status === 'error') throw new Error(data.message || 'Pipeline failed');
    showToast('Routine generated successfully.', 'success', 'Routine Ready');
    fetchDashboardData();
  } catch (error) {
    showToast('Pipeline failed: ' + error.message, 'error');
  } finally {
    btn.disabled = false;
  }
}


// ═══════════════════════════════════════════
// Loading States
// ═══════════════════════════════════════════

function showScanLoading(visible) {
  document.getElementById('scan-loading').classList.toggle('hidden', !visible);
  // Disable all scan buttons while loading
  document.querySelectorAll('#scan-card .btn-primary').forEach(b => b.disabled = visible);
}


// ═══════════════════════════════════════════
// Expand / Collapse Product Ingredients
// ═══════════════════════════════════════════

function toggleProduct(productId) {
  const detail = document.getElementById(`product-detail-${productId}`);
  const expand = document.getElementById(`product-expand-${productId}`);
  if (!detail) return;

  const isOpen = detail.classList.contains('open');
  detail.classList.toggle('open');
  if (expand) expand.classList.toggle('expanded');
}


// ═══════════════════════════════════════════
// Dashboard Data Fetching & Rendering
// ═══════════════════════════════════════════

async function fetchDashboardData() {
  try {
    const response = await fetch('/api/dashboard-data');
    const data = await response.json();
    dashboardData = data;
    renderProducts(data.products);
    renderRoutine(data.routine);
    renderConflicts(data.conflicts);
    renderLogs(data.pipeline_logs);
    updateNavBadges(data);
  } catch (error) {
    console.error('Error fetching dashboard data:', error);
  }
}

function updateNavBadges(data) {
  // Product count
  const productBadge = document.getElementById('nav-product-count');
  productBadge.textContent = data.products ? data.products.length : 0;

  // Conflict badge
  const conflictBadge = document.getElementById('nav-conflict-badge');
  const conflictCount = data.conflicts ? data.conflicts.length : 0;
  conflictBadge.textContent = conflictCount;
  conflictBadge.classList.toggle('hidden', conflictCount === 0);
}


// ── Render Products ──

function renderProducts(products) {
  const list = document.getElementById('products-list');
  const empty = document.getElementById('shelf-empty');

  // Preserve open states
  const openProductIds = new Set();
  document.querySelectorAll('.product-card-detail.open').forEach(el => {
    const idMatch = el.id.match(/^product-detail-(.+)$/);
    if (idMatch) openProductIds.add(idMatch[1]);
  });

  if (!products || products.length === 0) {
    list.innerHTML = '';
    empty.style.display = '';
    return;
  }

  empty.style.display = 'none';

  list.innerHTML = products.map(p => {
    const ingredientCount = (p.ingredients || []).length;
    const escapedName = (p.product_name || 'this product').replace(/'/g, "\\'");
    
    const isOpen = openProductIds.has(p.id);

    return `
      <div class="product-card">
        <div class="product-card-main" onclick="toggleProduct('${p.id}')">
          <div class="product-card-info">
            <div class="product-card-name">${p.product_name || 'Unknown Product'}</div>
            <div class="product-card-meta">
              ${p.brand ? `<span>${p.brand}</span>` : ''}
              ${p.product_type ? `<span>${p.product_type}</span>` : ''}
              <span>${ingredientCount} ingredient${ingredientCount !== 1 ? 's' : ''}</span>
            </div>
          </div>
          <div class="product-card-actions">
            <button class="btn btn-danger btn-sm" onclick="event.stopPropagation(); deleteProduct('${p.id}', '${escapedName}')" aria-label="Remove ${escapedName}">Remove</button>
            <button class="product-card-expand ${isOpen ? 'expanded' : ''}" id="product-expand-${p.id}" aria-label="Expand ingredients">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
          </div>
        </div>
        <div class="product-card-detail ${isOpen ? 'open' : ''}" id="product-detail-${p.id}">
          ${ingredientCount > 0 ? `
            <div class="ingredient-grid">
              ${(p.ingredients || []).map(i => `
                <div class="ingredient-chip ${i.needs_review ? 'needs-review' : ''}">
                  <span class="ingredient-chip-name">${i.name || i.inci || 'Unknown'}</span>
                  <span class="ingredient-chip-category">${i.category || 'other'}</span>
                </div>
              `).join('')}
            </div>
          ` : '<p style="font-size:0.8125rem; color:var(--color-text-faint);">No ingredients listed.</p>'}
        </div>
      </div>
    `;
  }).join('');
}


// ── Render Routine ──

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

  const steps = routine.steps || [];
  content.innerHTML = `
    ${routine.summary ? `<div class="routine-summary-text">${routine.summary}</div>` : ''}
    <div class="routine-steps">
      ${steps.map(s => `
        <div class="routine-step">
          <div class="step-number">${s.order || '?'}</div>
          <div class="step-content">
            <div class="step-action">${s.action || 'Step'}</div>
            <div class="step-product">with ${s.product_name || 'product'}${s.amount ? ` — ${s.amount}` : ''}</div>
            ${s.technique ? `<div class="step-details">${s.technique}</div>` : ''}
            ${s.wait_minutes ? `
              <div class="step-wait">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M12 6v6l4 2"/></svg>
                Wait ${s.wait_minutes} min
              </div>` : ''}
          </div>
        </div>
      `).join('')}
    </div>
    ${routine.climate_notes && routine.climate_notes.length ? `
      <div class="climate-notes">
        <div class="climate-notes-title">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>
          Climate Notes
        </div>
        <ul>
          ${routine.climate_notes.map(n => `<li>${n}</li>`).join('')}
        </ul>
      </div>` : ''}
  `;
}


// ── Render Conflicts ──

function renderConflicts(conflicts) {
  const list = document.getElementById('conflicts-list');
  const empty = document.getElementById('conflicts-empty');

  if (!conflicts || conflicts.length === 0) {
    list.innerHTML = '';
    empty.style.display = '';
    return;
  }

  empty.style.display = 'none';

  list.innerHTML = conflicts.map(c => {
    const severityClass = c.severity === 'critical' ? 'critical' : (c.severity === 'warning' ? 'warning' : '');
    const badgeClass = c.severity === 'critical' ? 'badge-danger' : (c.severity === 'warning' ? 'badge-warning' : 'badge-neutral');

    return `
      <div class="conflict-card ${severityClass}">
        <div class="conflict-card-header">
          <span class="badge ${badgeClass}">${c.severity}</span>
          <span class="conflict-card-products">
            ${c.product_a_name && c.product_b_name
              ? `${c.product_a_name} × ${c.product_b_name}`
              : (c.product_name || '')}
          </span>
        </div>
        <div class="conflict-card-explanation">${c.explanation || 'Conflict detected'}</div>
        ${c.fix ? `
          <div class="conflict-card-fix">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            <span>${c.fix}</span>
          </div>` : ''}
      </div>
    `;
  }).join('');
}


// ── Render Logs ──

function renderLogs(logs) {
  const list = document.getElementById('logs-list');
  const empty = document.getElementById('activity-empty');

  if (!logs || logs.length === 0) {
    list.innerHTML = '';
    empty.style.display = '';
    return;
  }

  empty.style.display = 'none';

  list.innerHTML = `
    <div class="log-list">
      ${logs.map(l => {
        const time = l.timestamp
          ? new Date(l.timestamp._seconds ? l.timestamp._seconds * 1000 : l.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          : '';
        const status = l.status || 'info';
        return `
          <div class="log-entry">
            <div class="log-dot ${status}"></div>
            <span class="log-time">${time}</span>
            <span class="log-message"><strong>[${l.pipeline || '?'}]</strong> ${l.message || ''}</span>
          </div>
        `;
      }).join('')}
    </div>
  `;
}


// ═══════════════════════════════════════════
// Initialize
// ═══════════════════════════════════════════

// Handle initial hash
(function() {
  const hash = window.location.hash.replace('#', '');
  if (hash && document.getElementById(`view-${hash}`)) {
    navigateTo(hash);
  }
})();

fetchDashboardData();
setInterval(fetchDashboardData, 10000);
