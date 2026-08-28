async function fetchDashboardData() {
    try {
        const response = await fetch('/api/dashboard-data');
        const data = await response.json();
        
        renderProducts(data.products);
        renderRoutine(data.routine);
        renderConflicts(data.conflicts);
    } catch (error) {
        console.error("Error fetching data:", error);
    }
}

function renderProducts(products) {
    const list = document.getElementById('products-list');
    if (!products || products.length === 0) {
        list.innerHTML = "<p>Your shelf is empty.</p>";
        return;
    }
    list.innerHTML = `<ul>${products.map(p => `<li>${p.product_name || 'Unknown'} (${p.product_type || 'Product'})</li>`).join('')}</ul>`;
}

function renderRoutine(routine) {
    const details = document.getElementById('routine-details');
    if (!routine || !routine.steps) {
        details.innerHTML = "<p>No routine generated yet.</p>";
        return;
    }
    details.innerHTML = `
        <p><strong>${routine.summary || ''}</strong></p>
        <ol>
            ${routine.steps.map(s => `<li>${s.action} with ${s.product_name} - ${s.technique}</li>`).join('')}
        </ol>
    `;
}

function renderConflicts(conflicts) {
    const list = document.getElementById('conflicts-list');
    if (!conflicts || conflicts.length === 0) {
        list.innerHTML = "<p>No active conflicts! You're good to go.</p>";
        return;
    }
    list.innerHTML = `<ul>${conflicts.map(c => `<li><strong>${c.severity.toUpperCase()}:</strong> ${c.explanation}</li>`).join('')}</ul>`;
}

async function uploadProduct() {
    const fileInput = document.getElementById('product-upload');
    if (fileInput.files.length === 0) {
        alert("Please select a file first.");
        return;
    }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    try {
        const response = await fetch('/api/upload-product', {
            method: 'POST',
            body: formData
        });
        const result = await response.json();
        alert(result.message);
        fileInput.value = ""; // Clear input
        fetchDashboardData(); // Refresh data
    } catch (error) {
        console.error("Upload failed:", error);
        alert("Failed to upload product.");
    }
}

// Initial fetch and poll every 5 seconds
fetchDashboardData();
setInterval(fetchDashboardData, 5000);
