/**
 * PT Management - Core API and utility functions
 */

const API_URL = '/api';

/**
 * Make an API request
 */
async function apiRequest(endpoint, method = 'GET', data = null) {
    const options = {
        method,
        headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
    };

    if (data && (method === 'POST' || method === 'PUT')) {
        options.body = JSON.stringify(data);
    }

    try {
        const response = await fetch(`${API_URL}${endpoint}`, options);
        
        if (!response.ok) {
            if (response.status === 401) {
                showNotification('Session expired. Please login again.', 'error');
                setTimeout(() => window.location.href = '/login', 1500);
                return null;
            }
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        showNotification(`Error: ${error.message}`, 'error');
        return null;
    }
}

/**
 * Show notification message
 */
function showNotification(message, type = 'info') {
    const alertType = {
        'success': 'alert-success',
        'error': 'alert-danger',
        'warning': 'alert-warning',
        'info': 'alert-info'
    }[type] || 'alert-info';

    const html = `
        <div class="alert ${alertType} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;

    const container = document.getElementById('notifications');
    if (container) {
        container.insertAdjacentHTML('beforeend', html);
        
        // Auto dismiss after 5 seconds
        setTimeout(() => {
            const alert = container.querySelector('.alert');
            if (alert) {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            }
        }, 5000);
    }
}

/**
 * Load users from API and populate table
 */
async function loadUsers() {
    const result = await apiRequest('/users');
    
    if (!result || !result.success) {
        document.getElementById('users-table').style.display = 'none';
        document.getElementById('users-empty').style.display = 'block';
        document.getElementById('users-loading').style.display = 'none';
        return;
    }

    const users = result.users || [];
    const tbody = document.getElementById('users-tbody');
    tbody.innerHTML = '';

    if (users.length === 0) {
        document.getElementById('users-table').style.display = 'none';
        document.getElementById('users-empty').style.display = 'block';
        document.getElementById('users-loading').style.display = 'none';
        return;
    }

    users.forEach(user => {
        const row = document.createElement('tr');
        row.setAttribute('data-username', user.username);
        row.style.cursor = 'pointer';
        
        const adminBadge = user.is_admin 
            ? '<span class="badge bg-danger ms-2" title="Admin user"><i class="bi bi-shield-check"></i> Admin</span>'
            : '';
        
        row.innerHTML = `
            <td><input type="checkbox" class="user-checkbox" onchange="updateUserSelectionCount()"></td>
            <td><strong>${user.username}</strong>${adminBadge}</td>
            <td><span class="badge bg-info">${(user.connections || []).length}</span></td>
            <td>
                <button class="btn btn-sm btn-danger" onclick="deleteUser('${user.username}')">
                    <i class="bi bi-trash"></i> Delete
                </button>
            </td>
        `;
        
        // Make row clickable to open user menu
        row.addEventListener('click', function(e) {
            if (e.target.closest('input[type="checkbox"]') || e.target.closest('button')) {
                return; // Don't open menu if clicking checkbox or button
            }
            openUserMenu(user);
        });
        
        tbody.appendChild(row);
    });

    document.getElementById('users-table').style.display = 'table';
    document.getElementById('users-empty').style.display = 'none';
    document.getElementById('users-loading').style.display = 'none';
    
    // Show bulk actions if there are users
    if (users.length > 0) {
        document.getElementById('users-bulk-actions').style.display = 'block';
        // Setup select all/deselect all buttons
        document.getElementById('users-select-all').onclick = () => {
            document.querySelectorAll('.user-checkbox').forEach(cb => cb.checked = true);
            updateUserSelectionCount();
        };
        document.getElementById('users-deselect-all').onclick = () => {
            document.querySelectorAll('.user-checkbox').forEach(cb => cb.checked = false);
            updateUserSelectionCount();
        };
    } else {
        document.getElementById('users-bulk-actions').style.display = 'none';
    }
}

/**
 * Delete a user
 */
async function deleteUser(username) {
    if (!confirm(`Are you sure you want to delete user "${username}"?`)) {
        return;
    }

    const result = await apiRequest(`/users/${username}`, 'DELETE');
    
    if (result && result.success) {
        showNotification(`User ${username} deleted successfully`, 'success');
        loadUsers();
    } else {
        showNotification(`Failed to delete user ${username}`, 'error');
    }
}

/**
 * Load containers from API and populate table
 */
async function loadContainers() {
    const result = await apiRequest('/containers');
    
    if (!result || !result.success) {
        document.getElementById('containers-table').style.display = 'none';
        document.getElementById('containers-empty').style.display = 'block';
        document.getElementById('containers-loading').style.display = 'none';
        return;
    }

    const containers = result.containers || [];
    const tbody = document.getElementById('containers-tbody');
    tbody.innerHTML = '';

    if (containers.length === 0) {
        document.getElementById('containers-table').style.display = 'none';
        document.getElementById('containers-empty').style.display = 'block';
        document.getElementById('containers-loading').style.display = 'none';
        return;
    }

    containers.forEach(container => {
        const statusBadge = container.status === 'running'
            ? '<span class="badge badge-status-running">Running</span>'
            : '<span class="badge badge-status-stopped">Stopped</span>';
        
        const row = document.createElement('tr');
        row.setAttribute('data-container-name', container.name);
        const users = (container.users || []).join(', ') || '-';
        const memory = container.memory || 'N/A';
        const cpus = container.cpus || 'N/A';
        
        row.innerHTML = `
            <td><input type="checkbox" class="container-checkbox" onchange="updateContainerSelectionCount()"></td>
            <td><strong>${container.name}</strong></td>
            <td>${statusBadge}</td>
            <td>
                <span class="badge bg-info">${memory}</span>
            </td>
            <td>
                <span class="badge bg-success">${cpus}</span>
            </td>
            <td><code>${container.image}</code></td>
            <td>${container.ports.join(', ') || '-'}</td>
            <td>
                <div class="btn-group btn-group-sm" role="group">
                    <button class="btn btn-info" onclick="viewLogs('${container.name}')" title="View Logs">
                        <i class="bi bi-file-text"></i>
                    </button>
                    ${container.status === 'running' 
                        ? `<button class="btn btn-warning" onclick="stopContainer('${container.name}')" title="Stop">
                            <i class="bi bi-stop-circle"></i>
                        </button>` 
                        : `<button class="btn btn-success" onclick="startContainer('${container.name}')" title="Start">
                            <i class="bi bi-play-circle"></i>
                        </button>`
                    }
                    ${container.status === 'running' 
                        ? `<button class="btn btn-secondary" onclick="restartContainer('${container.name}')" title="Restart">
                            <i class="bi bi-arrow-clockwise"></i>
                        </button>` 
                        : ''
                    }
                    <button class="btn btn-danger" onclick="deleteContainer('${container.name}')" title="Delete">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });

    document.getElementById('containers-table').style.display = 'table';
    document.getElementById('containers-empty').style.display = 'none';
    document.getElementById('containers-loading').style.display = 'none';
    
    // Show bulk actions if there are containers
    if (containers.length > 0) {
        document.getElementById('containers-bulk-actions').style.display = 'block';
        // Setup select all/deselect all buttons
        document.getElementById('containers-select-all').onclick = () => {
            document.querySelectorAll('.container-checkbox').forEach(cb => cb.checked = true);
            updateContainerSelectionCount();
        };
        document.getElementById('containers-deselect-all').onclick = () => {
            document.querySelectorAll('.container-checkbox').forEach(cb => cb.checked = false);
            updateContainerSelectionCount();
        };
    } else {
        document.getElementById('containers-bulk-actions').style.display = 'none';
    }
}



/**
 * View container logs in a modal
 */
async function viewLogs(containerName) {
    const result = await apiRequest(`/containers/${containerName}/logs`);
    
    if (result && result.success) {
        const logs = (result.logs || []).join('\n') || 'No logs available';
        
        // Create modal for logs
        const modalHtml = `
            <div class="modal fade" id="logsModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Logs for ${containerName}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <pre style="background: #f5f5f5; padding: 15px; border-radius: 5px; max-height: 400px; overflow-y: auto; font-size: 12px;">${logs}</pre>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Remove old modal if exists
        const oldModal = document.getElementById('logsModal');
        if (oldModal) oldModal.remove();
        
        // Add new modal to DOM
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('logsModal'));
        modal.show();
    } else {
        showNotification(`Failed to load logs for ${containerName}`, 'error');
    }
}

/**
 * Start a stopped container
 */
async function startContainer(containerName) {
    if (!confirm(`Start container ${containerName}?`)) {
        return;
    }

    const result = await apiRequest(`/containers/${containerName}/start`, 'POST');
    
    if (result && result.success) {
        showNotification(`Container ${containerName} started`, 'success');
        loadContainers();
    } else {
        showNotification(`Failed to start container ${containerName}`, 'error');
    }
}

/**
 * Stop a running container
 */
async function stopContainer(containerName) {
    if (!confirm(`Stop container ${containerName}? This will stop the Packet Tracer instance.`)) {
        return;
    }

    const result = await apiRequest(`/containers/${containerName}/stop`, 'POST');
    
    if (result && result.success) {
        showNotification(`Container ${containerName} stopped`, 'success');
        loadContainers();
    } else {
        showNotification(`Failed to stop container ${containerName}`, 'error');
    }
}

/**
 * Delete a container
 */
async function deleteContainer(containerName) {
    if (!confirm(`Delete container ${containerName}? This action cannot be undone.`)) {
        return;
    }

    const result = await apiRequest(`/containers/${containerName}`, 'DELETE');
    
    if (result && result.success) {
        showNotification(`Container ${containerName} deleted`, 'success');
        loadContainers();
    } else {
        showNotification(`Failed to delete container ${containerName}`, 'error');
    }
}

/**
 * Restart a container
 */
async function restartContainer(containerName) {
    if (!confirm(`Restart container ${containerName}?`)) {
        return;
    }

    const result = await apiRequest(`/containers/${containerName}/restart`, 'POST');
    
    if (result && result.success) {
        showNotification(`Container ${containerName} restarted`, 'success');
        loadContainers();
    } else {
        showNotification(`Failed to restart container ${containerName}`, 'error');
    }
}

/**
 * Load statistics
 */
async function loadStats() {
    const result = await apiRequest('/stats');
    
    if (!result || !result.success) {
        return;
    }

    document.getElementById('stat-users').textContent = result.users.total || 0;
    document.getElementById('stat-containers').textContent = result.containers.total || 0;
    document.getElementById('stat-running').textContent = result.containers.running || 0;
    document.getElementById('stat-stopped').textContent = result.containers.stopped || 0;
}

/**
 * Load and display logs
 */
async function refreshLogs() {
    const lines = document.getElementById('logLines').value;
    const container = document.getElementById('logs-container');
    
    try {
        const result = await apiRequest(`/logs?lines=${lines}`);
        
        if (!result || !result.success) {
            container.innerHTML = '<div class="text-danger">Failed to load logs</div>';
            return;
        }
        
        // Format logs with syntax highlighting for log levels
        const logs = result.logs || '';
        const logLines = logs.split('\n');
        
        let html = '';
        logLines.forEach(line => {
            if (!line.trim()) {
                html += '\n';
                return;
            }
            
            // Color code by log level
            let className = '';
            if (line.includes(' - ERROR') || line.includes('✗')) {
                className = 'text-danger';
            } else if (line.includes(' - WARNING') || line.includes('⚠')) {
                className = 'text-warning';
            } else if (line.includes(' - INFO') || line.includes('✓')) {
                className = 'text-success';
            } else if (line.includes(' - DEBUG')) {
                className = 'text-info';
            }
            
            if (className) {
                html += `<div class="${className}">${escapeHtml(line)}</div>`;
            } else {
                html += `<div>${escapeHtml(line)}</div>`;
            }
        });
        
        container.innerHTML = html;
        container.scrollTop = container.scrollHeight; // Scroll to bottom
    } catch (error) {
        console.error('Error loading logs:', error);
        container.innerHTML = '<div class="text-danger">Error loading logs</div>';
    }
}

/**
 * Escape HTML special characters
 */
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

/**
 * Clear logs display
 */
function clearLogs() {
    document.getElementById('logs-container').innerHTML = '<div class="text-center text-muted py-4">Logs cleared</div>';
}

/**
 * Run health check and display results
 */
async function runHealthCheck() {
    const resultsDiv = document.getElementById('health-check-results');
    const idleDiv = document.getElementById('health-check-idle');
    const outputDiv = document.getElementById('health-check-output');
    const passedDiv = document.getElementById('health-tests-passed');
    const failedDiv = document.getElementById('health-tests-failed');
    const statusBadge = document.getElementById('health-status-badge');
    const runBtn = event.target.closest('button');
    
    // Show results area and hide idle message
    resultsDiv.style.display = 'block';
    idleDiv.style.display = 'none';
    outputDiv.innerHTML = '<div class="text-center text-muted">Running health check... (this may take a minute)</div>';
    runBtn.disabled = true;
    runBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Running...';
    
    try {
        const result = await apiRequest('/health-check', 'POST');
        
        if (!result || !result.success) {
            outputDiv.innerHTML = `<div class="text-danger">Error: ${result?.error || 'Unknown error'}</div>`;
            return;
        }
        
        // Update summary stats
        passedDiv.textContent = result.tests_passed;
        failedDiv.textContent = result.tests_failed;
        
        // Update status badge
        statusBadge.textContent = result.overall_status.toUpperCase();
        if (result.overall_status === 'healthy') {
            statusBadge.className = 'badge bg-success';
        } else if (result.overall_status === 'degraded') {
            statusBadge.className = 'badge bg-warning text-dark';
        } else {
            statusBadge.className = 'badge bg-danger';
        }
        
        // Display full output with syntax highlighting
        let highlightedOutput = result.output
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/✅ PASS/g, '<span style="color: #28a745;">✅ PASS</span>')
            .replace(/❌ FAIL/g, '<span style="color: #dc3545;">❌ FAIL</span>')
            .replace(/⚠️/g, '<span style="color: #ffc107;">⚠️</span>')
            .replace(/ℹ️/g, '<span style="color: #17a2b8;">ℹ️</span>')
            .replace(/━━━━━━━━━/g, '<span style="color: #6c757d;">━━━━━━━━━</span>');
        
        outputDiv.innerHTML = highlightedOutput;
    } catch (error) {
        console.error('Health check error:', error);
        outputDiv.innerHTML = `<div class="text-danger">Error: ${error.message}</div>`;
    } finally {
        runBtn.disabled = false;
        runBtn.innerHTML = '<i class="bi bi-play-circle"></i> Run Tests';
    }
}

/**
 * Refresh all data
 */
async function refreshAll() {
    await loadStats();
    await loadUsers();
    await loadContainers();
    await refreshLogs();
}

// Load data on page ready
document.addEventListener('DOMContentLoaded', () => {
    refreshAll();
    
    // Refresh every 10 seconds
    setInterval(refreshAll, 10000);
    
    // Setup auto-refresh for logs
    let logsRefreshInterval = null;
    const autoRefreshCheckbox = document.getElementById('autoRefresh');
    
    if (autoRefreshCheckbox) {
        autoRefreshCheckbox.addEventListener('change', (e) => {
            if (e.target.checked) {
                // Start auto-refresh
                logsRefreshInterval = setInterval(() => {
                    refreshLogs();
                }, 5000);
            } else {
                // Stop auto-refresh
                if (logsRefreshInterval) {
                    clearInterval(logsRefreshInterval);
                    logsRefreshInterval = null;
                }
            }
        });
        
        // Start auto-refresh by default
        logsRefreshInterval = setInterval(() => {
            refreshLogs();
        }, 5000);
    }
});
