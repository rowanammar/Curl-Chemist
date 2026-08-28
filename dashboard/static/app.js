// ═══════════════════════════════════════════
// Curl Chemist — Dashboard JavaScript
// ═══════════════════════════════════════════

// Holds the latest scan result while user reviews it
let pendingScanResult = null;

// ── Tab Switching ──

function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById(`tab-${tabName}`).classList.add('active');

    // Hide scan results when switching tabs
    cancelScan();
}

// ── Scanning Methods ──

async function scanPhoto() {
    const fileInput = document.getElementById('photo-input');
    if (!fileInput.files.length) {
        showAlert('Please select a photo first.');
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    showLoading(true);
    try {
        const response = await fetch('/api/scan/photo', {
            method: 'POST',
            body: formData,
        });
        const data = await response.json();
        if (data.status === 'error') throw new Error(data.message);
        showScanResults(data);
    } catch (error) {
        showAlert('Scan failed: ' + error.message);
    } finally {
        showLoading(false);
    }
}

async function scanByName() {
    const nameInput = document.getElementById('name-input');
    const name = nameInput.value.trim();
    if (!name) {
        showAlert('Please enter a product name.');
        return;
    }

    showLoading(true);
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
        showAlert('Lookup failed: ' + error.message);
    } finally {
        showLoading(false);
    }
}

async function scanManual() {
    const nameInput = document.getElementById('manual-product-name');
    const ingredientsInput = document.getElementById('manual-ingredients');
    const name = nameInput.value.trim();
    const ingredients = ingredientsInput.value.trim();

    if (!name) { showAlert('Please enter a product name.'); return; }
    if (!ingredients) { showAlert('Please enter the ingredients.'); return; }

    showLoading(true);
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
        showAlert('Parse failed: ' + error.message);
    } finally {
        showLoading(false);
    }
}

// ── Display Scan Results for Review ──

function showScanResults(data) {
    pendingScanResult = data;

    document.getElementById('result-name').textContent = data.product_name || 'Unknown';
    document.getElementById('result-brand').textContent = data.brand || 'Unknown';
    document.getElementById('result-type').textContent = data.product_type || 'Unknown';

    // Hair product warning
    const warning = document.getElementById('not-hair-warning');
    if (data.is_hair_product === false) {
        document.getElementById('detected-category').textContent = data.product_category_detected || 'non-hair product';
        warning.classList.remove('hidden');
    } else {
        warning.classList.add('hidden');
    }

    // Render ingredients
    const container = document.getElementById('result-ingredients');
    const ingredients = data.ingredients || [];
    if (ingredients.length === 0) {
        container.innerHTML = '<p class="empty">No ingredients found.</p>';
    } else {
        container.innerHTML = `
            <p style="font-size:0.85rem;color:#8b7355;margin-bottom:8px">${ingredients.length} ingredients found:</p>
            <div class="ingredient-list">
                ${ingredients.map(i => `
                    <div class="ingredient-chip ${i.needs_review ? 'review' : ''}">
                        <span>${i.name || i.inci || 'Unknown'}</span>
                        <span class="category">${i.category || 'other'}${i.needs_review ? ' ⚠️' : ''}</span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    document.getElementById('scan-results').classList.remove('hidden');
}

// ── Confirm / Cancel ──

async function confirmProduct() {
    if (!pendingScanResult) return;

    try {
        const response = await fetch('/api/confirm-product', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(pendingScanResult),
        });
        const data = await response.json();

        if (data.status === 'error') throw new Error(data.message);

        let msg = `✅ ${data.product_name} added to your shelf!`;
        if (data.conflicts_found > 0) {
            msg += `\n\n⚠️ ${data.conflicts_found} conflict(s) found (${data.critical_conflicts} critical)`;
        }
        showAlert(msg);
        cancelScan();
        fetchDashboardData(); // Refresh everything
    } catch (error) {
        showAlert('Failed to save: ' + error.message);
    }
}

function cancelScan() {
    pendingScanResult = null;
    document.getElementById('scan-results').classList.add('hidden');
    document.getElementById('not-hair-warning').classList.add('hidden');
}

// ── Delete Product ──

async function deleteProduct(productId, productName) {
    if (!confirm(`Remove "${productName}" from your shelf?`)) return;

    try {
        const response = await fetch(`/api/products/${productId}`, { method: 'DELETE' });
        const data = await response.json();
        if (data.status === 'error') throw new Error(data.message);
        fetchDashboardData();
    } catch (error) {
        showAlert('Failed to delete: ' + error.message);
    }
}

// ── Wash Day Selfie ──

async function logWashDay() {
    const fileInput = document.getElementById('selfie-input');
    if (!fileInput.files.length) {
        showAlert('Please select a hair selfie first.');
        return;
    }

    const notes = document.getElementById('wash-notes').value.trim();
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('notes', notes);

    document.getElementById('wash-loading').classList.remove('hidden');
    document.getElementById('wash-result').classList.add('hidden');

    try {
        const response = await fetch('/api/wash-day', {
            method: 'POST',
            body: formData,
        });
        const data = await response.json();
        if (data.status === 'error') throw new Error(data.message);

        const a = data.analysis;
        document.getElementById('wash-result').innerHTML = `
            <div class="alert success">✅ Hair analysis saved!</div>
            <div class="wash-scores">
                <div class="wash-score"><div class="label">Frizz Level</div><div class="value">${a.frizz_level}/10</div></div>
                <div class="wash-score"><div class="label">Curl Definition</div><div class="value">${a.curl_definition}/10</div></div>
                <div class="wash-score"><div class="label">Shine</div><div class="value">${a.shine}/10</div></div>
                <div class="wash-score"><div class="label">Damage Visible</div><div class="value">${a.damage_visible}/10</div></div>
            </div>
            ${a.observations ? `<p style="margin-top:10px;font-size:0.85rem">${a.observations}</p>` : ''}
        `;
        document.getElementById('wash-result').classList.remove('hidden');
        fileInput.value = '';
        document.getElementById('wash-notes').value = '';
        fetchDashboardData();
    } catch (error) {
        showAlert('Analysis failed: ' + error.message);
    } finally {
        document.getElementById('wash-loading').classList.add('hidden');
    }
}

// ── Trigger Nightly Pipeline ──

async function triggerNightly() {
    try {
        const response = await fetch('/pipelines/nightly', { method: 'POST' });
        const data = await response.json();
        if (data.status === 'error') throw new Error(data.message || 'Pipeline failed');
        showAlert('✅ Routine generated!');
        fetchDashboardData();
    } catch (error) {
        showAlert('Pipeline failed: ' + error.message);
    }
}

// ── Dashboard Data Fetching ──

async function fetchDashboardData() {
    try {
        const response = await fetch('/api/dashboard-data');
        const data = await response.json();
        renderProducts(data.products);
        renderRoutine(data.routine);
        renderConflicts(data.conflicts);
        renderLogs(data.pipeline_logs);
    } catch (error) {
        console.error('Error fetching dashboard data:', error);
    }
}

function renderProducts(products) {
    const container = document.getElementById('products-list');
    const badge = document.getElementById('product-count');
    badge.textContent = products ? products.length : 0;

    if (!products || products.length === 0) {
        container.innerHTML = '<p class="empty">No products yet. Scan one above!</p>';
        return;
    }

    container.innerHTML = products.map(p => `
        <div class="product-item">
            <div class="product-info">
                <div class="product-name">${p.product_name || 'Unknown Product'}</div>
                <div class="product-meta">${p.brand || ''} · ${p.product_type || 'product'} · ${(p.ingredients || []).length} ingredients</div>
            </div>
            <button class="btn danger" onclick="deleteProduct('${p.id}', '${(p.product_name || 'this product').replace(/'/g, "\\'")}')">Remove</button>
        </div>
    `).join('');
}

function renderRoutine(routine) {
    const container = document.getElementById('routine-details');
    if (!routine || !routine.steps) {
        container.innerHTML = '<p class="empty">No routine generated yet. Add products and click Generate!</p>';
        return;
    }

    const steps = routine.steps || [];
    container.innerHTML = `
        <div class="routine-summary">${routine.summary || 'Your personalized routine'}</div>
        ${steps.map(s => `
            <div class="routine-step">
                <div class="step-number">${s.order || '?'}</div>
                <div>
                    <strong>${s.action || 'Step'}</strong> with ${s.product_name || 'product'}
                    ${s.amount ? ` — ${s.amount}` : ''}
                    ${s.technique ? `<br><span style="font-size:0.82rem;color:#8b7355">${s.technique}</span>` : ''}
                    ${s.wait_minutes ? `<br><span style="font-size:0.78rem;color:#b8860b">⏱ Wait ${s.wait_minutes} min</span>` : ''}
                </div>
            </div>
        `).join('')}
        ${routine.climate_notes && routine.climate_notes.length ?
            `<div style="margin-top:12px;font-size:0.82rem;color:#5c3d2e">
                <strong>Climate Notes:</strong>
                <ul style="margin-top:4px;padding-left:18px">${routine.climate_notes.map(n => `<li>${n}</li>`).join('')}</ul>
            </div>` : ''}
    `;
}

function renderConflicts(conflicts) {
    const container = document.getElementById('conflicts-list');
    const badge = document.getElementById('conflict-count');
    badge.textContent = conflicts ? conflicts.length : 0;

    if (!conflicts || conflicts.length === 0) {
        container.innerHTML = '<p class="empty">No conflicts detected. Your products are compatible!</p>';
        badge.classList.remove('danger');
        return;
    }

    badge.classList.add('danger');
    container.innerHTML = conflicts.map(c => `
        <div class="conflict-item">
            <span class="conflict-severity severity-${c.severity}">${c.severity}</span>
            ${c.product_a_name && c.product_b_name ?
                `<span style="font-size:0.82rem;color:#8b7355"> ${c.product_a_name} × ${c.product_b_name}</span>` :
                (c.product_name ? `<span style="font-size:0.82rem;color:#8b7355"> ${c.product_name}</span>` : '')}
            <div class="conflict-text">${c.explanation || 'Conflict detected'}</div>
            ${c.fix ? `<div class="conflict-fix">💡 ${c.fix}</div>` : ''}
        </div>
    `).join('');
}

function renderLogs(logs) {
    const container = document.getElementById('logs-list');
    if (!logs || logs.length === 0) {
        container.innerHTML = '<p class="empty">No activity yet.</p>';
        return;
    }

    container.innerHTML = logs.map(l => {
        const time = l.timestamp ? new Date(l.timestamp._seconds ? l.timestamp._seconds * 1000 : l.timestamp).toLocaleTimeString() : '';
        return `
            <div class="log-item">
                <div class="log-status ${l.status || 'info'}"></div>
                <span class="log-time">${time}</span>
                <span><strong>[${l.pipeline || '?'}]</strong> ${l.message || ''}</span>
            </div>
        `;
    }).join('');
}

// ── Helpers ──

function showLoading(visible) {
    document.getElementById('scan-loading').classList.toggle('hidden', !visible);
    // Disable all scan buttons while loading
    document.querySelectorAll('#add-product-section .btn.primary').forEach(b => b.disabled = visible);
}

function showAlert(message) {
    // Simple alert for now — you can replace with a toast notification in the UI/UX phase
    alert(message);
}

// ── Initialize ──
fetchDashboardData();
setInterval(fetchDashboardData, 10000); // Poll every 10 seconds (not 5 — less Firestore reads)
