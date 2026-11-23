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
    if (window.showToast) {
        window.showToast(message, type);
        return;
    }

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

// In-memory cache for live client-side filtering
window._loadedUsers = [];
window._loadedContainers = [];

/**
 * Filter users based on search input
 */
function filterUsers() {
    const q = (document.getElementById('users-search')?.value || '').toLowerCase().trim();
    if (!q) {
        renderUsersTable(window._loadedUsers || []);
        return;
    }
    const filtered = (window._loadedUsers || []).filter(u => {
        const username = (u.username || '').toLowerCase();
        const connections = (u.connections || []).map(c => typeof c === 'object' ? (c.connection_name || '') : c).join(' ').toLowerCase();
        return username.includes(q) || connections.includes(q);
    });
    renderUsersTable(filtered);
}

/**
 * Render users into table
 */
function renderUsersTable(users) {
    const tbody = document.getElementById('users-tbody');
    const table = document.getElementById('users-table');
    const empty = document.getElementById('users-empty');
    const loading = document.getElementById('users-loading');
    if (!tbody) return;

    tbody.innerHTML = '';
    if (loading) loading.style.display = 'none';

    if (!users || users.length === 0) {
        if (table) table.style.display = 'none';
        if (empty) {
            empty.style.display = 'block';
            empty.innerHTML = `
                <div class="empty-state">
                    <i class="bi bi-people empty-state-icon"></i>
                    <div class="empty-state-title">No Users Found</div>
                    <div class="empty-state-subtitle">No student or administrator accounts match your criteria.</div>
                </div>
            `;
        }
        return;
    }

    if (empty) empty.style.display = 'none';
    if (table) table.style.display = 'table';

    users.forEach(user => {
        const row = document.createElement('tr');
        row.setAttribute('data-username', user.username);
        row.style.cursor = 'pointer';
        
        const adminBadge = user.is_admin 
            ? '<span class="badge bg-danger-subtle text-danger border border-danger-subtle ms-2" title="Admin user"><i class="bi bi-shield-check"></i> Admin</span>'
            : '';
        
        const connectionsList = (user.connections || []).map(c => {
            const name = typeof c === 'object' ? (c.connection_name || c.name || c.connection_id || JSON.stringify(c)) : c;
            return `<span class="badge bg-primary-subtle text-primary border border-primary-subtle me-1"><i class="bi bi-display me-1"></i>${name}</span>`;
        }).join('') || '<span class="text-muted small">None</span>';

        row.innerHTML = `
            <td><input type="checkbox" class="user-checkbox" onchange="updateUserSelectionCount()"></td>
            <td><strong>${user.username}</strong>${adminBadge}</td>
            <td>${connectionsList}</td>
            <td class="text-end">
                <div class="btn-group btn-group-sm">
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteUser('${user.username}')" title="Delete User">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </td>
        `;
        
        // Make row clickable to open user menu
        row.addEventListener('click', function(e) {
            if (e.target.closest('input[type="checkbox"]') || e.target.closest('button') || e.target.closest('a')) {
                return;
            }
            openUserMenu(user);
        });
        
        tbody.appendChild(row);
    });

    // Update count indicator if present
    const countBadge = document.getElementById('users-count-badge');
    if (countBadge) {
        countBadge.textContent = `${users.length} of ${window._loadedUsers.length}`;
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

    window._loadedUsers = result.users || [];
    filterUsers();
    
    // Wire up bulk actions handlers and update visibility
    const selectAllBtn = document.getElementById('users-select-all');
    if (selectAllBtn) {
        selectAllBtn.onclick = () => {
            document.querySelectorAll('.user-checkbox').forEach(cb => cb.checked = true);
            if (typeof updateUserSelectionCount === 'function') updateUserSelectionCount();
        };
    }
    const deselectAllBtn = document.getElementById('users-deselect-all');
    if (deselectAllBtn) {
        deselectAllBtn.onclick = () => {
            document.querySelectorAll('.user-checkbox').forEach(cb => cb.checked = false);
            if (typeof updateUserSelectionCount === 'function') updateUserSelectionCount();
        };
    }
    if (typeof updateUserSelectionCount === 'function') {
        updateUserSelectionCount();
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
 * Filter containers based on search input & status filter
 */
function filterContainers() {
    const q = (document.getElementById('containers-search')?.value || '').toLowerCase().trim();
    const statusFilter = document.getElementById('containers-status-filter')?.value || 'all';
    
    let list = window._loadedContainers || [];
    if (statusFilter !== 'all') {
        list = list.filter(c => c.status === statusFilter);
    }
    if (q) {
        list = list.filter(c => {
            const name = (c.name || '').toLowerCase();
            const img = (c.image || '').toLowerCase();
            const ports = (c.ports || []).join(' ').toLowerCase();
            return name.includes(q) || img.includes(q) || ports.includes(q);
        });
    }
    renderContainersTable(list);
}

/**
 * Render containers into table
 */
function renderContainersTable(containers) {
    const tbody = document.getElementById('containers-tbody');
    const table = document.getElementById('containers-table');
    const empty = document.getElementById('containers-empty');
    const loading = document.getElementById('containers-loading');
    if (!tbody) return;

    tbody.innerHTML = '';
    if (loading) loading.style.display = 'none';

    if (!containers || containers.length === 0) {
        if (table) table.style.display = 'none';
        if (empty) {
            empty.style.display = 'block';
            empty.innerHTML = `
                <div class="empty-state">
                    <i class="bi bi-boxes empty-state-icon"></i>
                    <div class="empty-state-title">No Containers Found</div>
                    <div class="empty-state-subtitle">No Packet Tracer container instances match your criteria.</div>
                </div>
            `;
        }
        return;
    }

    if (empty) empty.style.display = 'none';
    if (table) table.style.display = 'table';

    containers.forEach(container => {
        const isRunning = container.status === 'running';
        const statusBadge = isRunning
            ? '<span class="badge status-pill bg-success-subtle text-success border border-success-subtle"><span class="status-dot status-dot-running"></span> Running</span>'
            : '<span class="badge status-pill bg-secondary-subtle text-secondary border border-secondary-subtle"><span class="status-dot status-dot-stopped"></span> Stopped</span>';
        
        const row = document.createElement('tr');
        row.setAttribute('data-container-name', container.name);
        const memory = container.memory || '512MB';
        const cpus = container.cpus || '1.0';
        const portStr = (container.ports && container.ports.length > 0) ? container.ports.join(', ') : '-';
        
        const guacAssistUrl = container.client_token 
            ? `${window.location.protocol}//${window.location.hostname}/#/client/${container.client_token}`
            : (container.guacamole_url ? `${window.location.protocol}//${window.location.hostname}${container.guacamole_url}` : null);

        row.innerHTML = `
            <td><input type="checkbox" class="container-checkbox" onchange="updateContainerSelectionCount()"></td>
            <td>
                <div class="d-flex align-items-center gap-2">
                    <strong>${container.name}</strong>
                    ${container.connection_name ? `<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle font-monospace"><i class="bi bi-display me-1"></i>${container.connection_name}</span>` : ''}
                </div>
            </td>
            <td>${statusBadge}</td>
            <td>
                <span class="badge bg-light text-dark border">${memory}</span>
            </td>
            <td>
                <span class="badge bg-light text-dark border">${cpus} CPU</span>
            </td>
            <td><code class="small text-secondary">${container.image}</code></td>
            <td><span class="small text-muted">${portStr}</span></td>
            <td>
                <div class="btn-group btn-group-sm" role="group">
                    ${isRunning && guacAssistUrl 
                        ? `<a href="${guacAssistUrl}" target="_blank" class="btn btn-outline-primary" title="Assist Student (Open Live Screen in Guacamole)">
                            <i class="bi bi-display"></i>
                        </a>` 
                        : ''
                    }
                    <button class="btn btn-outline-secondary" onclick="viewLogs('${container.name}')" title="View Logs">
                        <i class="bi bi-file-earmark-text"></i>
                    </button>
                    ${isRunning 
                        ? `<button class="btn btn-outline-warning" onclick="stopContainer('${container.name}')" title="Stop Container">
                            <i class="bi bi-stop-circle"></i>
                        </button>` 
                        : `<button class="btn btn-outline-success" onclick="startContainer('${container.name}')" title="Start Container">
                            <i class="bi bi-play-circle"></i>
                        </button>`
                    }
                    ${isRunning 
                        ? `<button class="btn btn-outline-secondary" onclick="restartContainer('${container.name}')" title="Restart">
                            <i class="bi bi-arrow-clockwise"></i>
                        </button>` 
                        : ''
                    }
                    <button class="btn btn-outline-danger" onclick="deleteContainer('${container.name}')" title="Delete">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });

    // Update count indicator if present
    const countBadge = document.getElementById('containers-count-badge');
    if (countBadge) {
        countBadge.textContent = `${containers.length} of ${window._loadedContainers.length}`;
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

    window._loadedContainers = result.containers || [];
    filterContainers();
    
    // Wire up bulk actions handlers and update visibility
    const selectAllBtn = document.getElementById('containers-select-all');
    if (selectAllBtn) {
        selectAllBtn.onclick = () => {
            document.querySelectorAll('.container-checkbox').forEach(cb => cb.checked = true);
            if (typeof updateContainerSelectionCount === 'function') updateContainerSelectionCount();
        };
    }
    const deselectAllBtn = document.getElementById('containers-deselect-all');
    if (deselectAllBtn) {
        deselectAllBtn.onclick = () => {
            document.querySelectorAll('.container-checkbox').forEach(cb => cb.checked = false);
            if (typeof updateContainerSelectionCount === 'function') updateContainerSelectionCount();
        };
    }
    if (typeof updateContainerSelectionCount === 'function') {
        updateContainerSelectionCount();
    }
}

/**
 * Get list of currently checked container names
 */
function getSelectedContainerNames() {
    return Array.from(document.querySelectorAll('.container-checkbox:checked'))
        .map(cb => cb.closest('tr')?.getAttribute('data-container-name'))
        .filter(Boolean);
}

/**
 * Start all stopped containers
 */
async function startAllContainers() {
    const stopped = (window._loadedContainers || []).filter(c => c.status !== 'running');
    if (stopped.length === 0) {
        showNotification('All containers are already running', 'info');
        return;
    }
    if (!confirm(`Start all ${stopped.length} stopped container(s)?`)) return;

    showNotification(`Starting ${stopped.length} container(s)...`, 'info');
    const result = await apiRequest('/containers/bulk/start', 'POST', {
        names: stopped.map(c => c.name)
    });
    if (result && result.success) {
        showNotification(result.message || `Started ${result.started.length} container(s)`, 'success');
        await loadContainers();
        await loadStats();
    } else {
        showNotification('Failed to start containers', 'error');
    }
}

/**
 * Stop all running containers
 */
async function stopAllContainers() {
    const running = (window._loadedContainers || []).filter(c => c.status === 'running');
    if (running.length === 0) {
        showNotification('No containers are currently running', 'info');
        return;
    }
    if (!confirm(`Stop all ${running.length} running container(s)? This will pause student lab sessions.`)) return;

    showNotification(`Stopping ${running.length} container(s)...`, 'info');
    const result = await apiRequest('/containers/bulk/stop', 'POST', {
        names: running.map(c => c.name)
    });
    if (result && result.success) {
        showNotification(result.message || `Stopped ${result.stopped.length} container(s)`, 'success');
        await loadContainers();
        await loadStats();
    } else {
        showNotification('Failed to stop containers', 'error');
    }
}

/**
 * Start selected containers
 */
async function startSelectedContainers() {
    const names = getSelectedContainerNames();
    if (names.length === 0) {
        showNotification('No containers selected', 'warning');
        return;
    }
    showNotification(`Starting ${names.length} container(s)...`, 'info');
    const result = await apiRequest('/containers/bulk/start', 'POST', { names });
    if (result && result.success) {
        showNotification(`Started ${result.started.length} container(s)`, 'success');
        await loadContainers();
        await loadStats();
    } else {
        showNotification('Failed to start selected containers', 'error');
    }
}

/**
 * Stop selected containers
 */
async function stopSelectedContainers() {
    const names = getSelectedContainerNames();
    if (names.length === 0) {
        showNotification('No containers selected', 'warning');
        return;
    }
    if (!confirm(`Stop ${names.length} selected container(s)?`)) return;
    showNotification(`Stopping ${names.length} container(s)...`, 'info');
    const result = await apiRequest('/containers/bulk/stop', 'POST', { names });
    if (result && result.success) {
        showNotification(`Stopped ${result.stopped.length} container(s)`, 'success');
        await loadContainers();
        await loadStats();
    } else {
        showNotification('Failed to stop selected containers', 'error');
    }
}

/**
 * Restart all running containers
 */
async function restartAllContainers() {
    const running = (window._loadedContainers || []).filter(c => c.status === 'running');
    if (running.length === 0) {
        showNotification('No containers are currently running to restart', 'info');
        return;
    }
    if (!confirm(`Restart all ${running.length} running container(s)? This will briefly reset student lab sessions.`)) return;

    showNotification(`Restarting ${running.length} container(s)...`, 'info');
    const result = await apiRequest('/containers/bulk/restart', 'POST', {
        names: running.map(c => c.name)
    });
    if (result && result.success) {
        showNotification(result.message || `Restarted ${result.restarted.length} container(s)`, 'success');
        await loadContainers();
        await loadStats();
    } else {
        showNotification('Failed to restart containers', 'error');
    }
}

/**
 * Restart selected containers
 */
async function restartSelectedContainers() {
    const names = getSelectedContainerNames();
    if (names.length === 0) {
        showNotification('No containers selected', 'warning');
        return;
    }
    if (!confirm(`Restart ${names.length} selected container(s)?`)) return;
    showNotification(`Restarting ${names.length} container(s)...`, 'info');
    const result = await apiRequest('/containers/bulk/restart', 'POST', { names });
    if (result && result.success) {
        showNotification(`Restarted ${result.restarted.length} container(s)`, 'success');
        await loadContainers();
        await loadStats();
    } else {
        showNotification('Failed to restart selected containers', 'error');
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
 * Convert ANSI escape sequences into styled HTML
 */
function ansiToHtml(text) {
    if (!text) return '';

    let escaped = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    const colorMap = {
        '30': '#64748b', '31': '#ef4444', '32': '#10b981', '33': '#f59e0b',
        '34': '#3b82f6', '35': '#d946ef', '36': '#06b6d4', '37': '#f8fafc',
        '90': '#94a3b8', '91': '#f87171', '92': '#34d399', '93': '#fde047',
        '94': '#60a5fa', '95': '#e879f9', '96': '#67e8f9', '97': '#ffffff'
    };

    let openSpans = 0;
    const ansiRegex = /(?:\x1b|\u001b|\\e|\\033)?\[([0-9;]*)m/g;

    let html = escaped.replace(ansiRegex, (match, p1) => {
        const codes = (p1 || '0').split(';').map(c => c.trim()).filter(Boolean);
        if (codes.length === 0 || codes.includes('0')) {
            let closeTags = '';
            while (openSpans > 0) {
                closeTags += '</span>';
                openSpans--;
            }
            return closeTags;
        }

        let styles = [];
        codes.forEach(code => {
            if (code === '1') styles.push('font-weight: 600;');
            else if (code === '4') styles.push('text-decoration: underline;');
            else if (colorMap[code]) styles.push(`color: ${colorMap[code]};`);
        });

        if (styles.length > 0) {
            openSpans++;
            return `<span style="${styles.join(' ')}">`;
        }
        return '';
    });

    while (openSpans > 0) {
        html += '</span>';
        openSpans--;
    }

    // Clean up any remaining raw artifacts if escape byte was omitted
    html = html.replace(/\[(?:[0-9]{1,2};?)+m/g, '');

    // Highlight key pass/fail badges
    html = html
        .replace(/✅ PASS/g, '<span style="color: #10b981; font-weight: 600;">✅ PASS</span>')
        .replace(/✔ PASS/g, '<span style="color: #10b981; font-weight: 600;">✔ PASS</span>')
        .replace(/❌ FAIL/g, '<span style="color: #ef4444; font-weight: 600;">❌ FAIL</span>')
        .replace(/━━━━━━━━━/g, '<span style="color: #475569;">━━━━━━━━━</span>');

    return html;
}

/**
 * Format bytes to readable string (B, KB, MB, GB)
 */
function formatBytes(bytes, decimals = 1) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

/**
 * Load host CPU and Memory system telemetry
 */
async function loadSystemTelemetry() {
    const cpuPctEl = document.getElementById('host-cpu-pct');
    if (!cpuPctEl) return; // Not on dashboard

    try {
        const result = await apiRequest('/system/stats');
        if (!result || !result.success) return;

        // CPU Telemetry
        const cpu = result.cpu || {};
        const cpuPct = Math.round(cpu.pct || 0);
        cpuPctEl.textContent = `${cpuPct}%`;

        const cpuProg = document.getElementById('host-cpu-progress');
        if (cpuProg) {
            cpuProg.style.width = `${Math.min(100, Math.max(0, cpuPct))}%`;
            cpuProg.className = 'progress-bar ' + (cpuPct >= 90 ? 'bg-danger' : cpuPct >= 70 ? 'bg-warning' : 'bg-primary');
        }

        const cpuCoresEl = document.getElementById('host-cpu-cores');
        if (cpuCoresEl) cpuCoresEl.textContent = `${cpu.cores || 1} Cores`;

        const cpuStatusEl = document.getElementById('host-cpu-status');
        if (cpuStatusEl) {
            if (cpuPct >= 90) {
                cpuStatusEl.textContent = 'High Load';
                cpuStatusEl.className = 'badge bg-danger-subtle text-danger border border-danger-subtle ms-1';
            } else if (cpuPct >= 70) {
                cpuStatusEl.textContent = 'Elevated';
                cpuStatusEl.className = 'badge bg-warning-subtle text-warning border border-warning-subtle ms-1';
            } else {
                cpuStatusEl.textContent = 'Normal';
                cpuStatusEl.className = 'badge bg-success-subtle text-success border border-success-subtle ms-1';
            }
        }

        const c1 = document.getElementById('host-cpu-1m');
        const c5 = document.getElementById('host-cpu-5m');
        const c15 = document.getElementById('host-cpu-15m');
        if (c1) c1.textContent = cpu.load_1m !== undefined ? cpu.load_1m.toFixed(2) : '-';
        if (c5) c5.textContent = cpu.load_5m !== undefined ? cpu.load_5m.toFixed(2) : '-';
        if (c15) c15.textContent = cpu.load_15m !== undefined ? cpu.load_15m.toFixed(2) : '-';

        // Memory Telemetry
        const mem = result.memory || {};
        const memPct = Math.round(mem.pct || 0);
        const ramPctEl = document.getElementById('host-ram-pct');
        if (ramPctEl) ramPctEl.textContent = `${memPct}%`;

        const ramProg = document.getElementById('host-ram-progress');
        if (ramProg) {
            ramProg.style.width = `${Math.min(100, Math.max(0, memPct))}%`;
            ramProg.className = 'progress-bar ' + (memPct >= 90 ? 'bg-danger' : memPct >= 75 ? 'bg-warning' : 'bg-success');
        }

        const ramBreakdownEl = document.getElementById('host-ram-breakdown');
        if (ramBreakdownEl) {
            ramBreakdownEl.textContent = `${formatBytes(mem.used)} / ${formatBytes(mem.total)}`;
        }

        const ramFreeBadge = document.getElementById('host-ram-free');
        if (ramFreeBadge) {
            ramFreeBadge.textContent = `${formatBytes(mem.free)} Free`;
        }

        const ramUsedEl = document.getElementById('host-ram-used');
        const ramAvailEl = document.getElementById('host-ram-avail');
        const ramTotalEl = document.getElementById('host-ram-total');
        if (ramUsedEl) ramUsedEl.textContent = formatBytes(mem.used);
        if (ramAvailEl) ramAvailEl.textContent = formatBytes(mem.free);
        if (ramTotalEl) ramTotalEl.textContent = formatBytes(mem.total);
    } catch (e) {
        console.error('Failed to load system telemetry:', e);
    }
}

let healthCheckSections = [];
let healthCheckFilter = 'all';
let healthSectionsExpanded = false;

function getHealthSectionIcon(title) {
    const t = (title || '').toLowerCase();
    if (t.includes('container')) return 'bi-box-seam';
    if (t.includes('database') || t.includes('schema')) return 'bi-database';
    if (t.includes('shared') || t.includes('symlink') || t.includes('permission')) return 'bi-folder2-open';
    if (t.includes('web') || t.includes('endpoint')) return 'bi-globe';
    if (t.includes('download') || t.includes('isolation')) return 'bi-shield-lock';
    if (t.includes('network')) return 'bi-diagram-3';
    if (t.includes('rate limit')) return 'bi-speedometer2';
    if (t.includes('geoip')) return 'bi-geo-alt';
    if (t.includes('packet tracer') || t.includes('pt_opt')) return 'bi-hdd-network';
    return 'bi-check2-square';
}

function escapeHealthHtml(str) {
    return String(str ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function setHealthFilter(filter, btnEl) {
    healthCheckFilter = filter;
    document.querySelectorAll('[data-health-filter]').forEach(btn => {
        const f = btn.getAttribute('data-health-filter');
        btn.classList.remove('active', 'btn-primary', 'btn-danger', 'btn-success');
        if (f === 'all') btn.classList.add(f === filter ? 'btn-primary' : 'btn-outline-primary');
        if (f === 'fail') btn.classList.add(f === filter ? 'btn-danger' : 'btn-outline-danger');
        if (f === 'pass') btn.classList.add(f === filter ? 'btn-success' : 'btn-outline-success');
        if (f === filter) btn.classList.add('active');
    });
    renderHealthCheckSections();
}

function toggleAllHealthSections() {
    healthSectionsExpanded = !healthSectionsExpanded;
    const btn = document.getElementById('health-toggle-all-btn');
    if (btn) {
        btn.innerHTML = healthSectionsExpanded
            ? '<i class="bi bi-arrows-collapse"></i> Collapse All'
            : '<i class="bi bi-arrows-expand"></i> Expand All';
    }
    document.querySelectorAll('#health-check-sections .accordion-collapse').forEach(el => {
        const inst = bootstrap.Collapse.getOrCreateInstance(el, { toggle: false });
        if (healthSectionsExpanded) inst.show();
        else inst.hide();
    });
}

function toggleRawHealthLog() {
    const wrap = document.getElementById('health-check-raw-wrap');
    const btn = document.getElementById('health-raw-toggle-btn');
    if (!wrap) return;
    const visible = wrap.style.display !== 'none';
    wrap.style.display = visible ? 'none' : 'block';
    if (btn) {
        btn.classList.toggle('btn-secondary', !visible);
        btn.classList.toggle('btn-outline-secondary', visible);
    }
}

function renderHealthCheckSections() {
    const container = document.getElementById('health-check-sections');
    if (!container) return;

    const search = (document.getElementById('health-search-input')?.value || '').trim().toLowerCase();

    if (!healthCheckSections || healthCheckSections.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-3 small">No structured sections parsed. Open <strong>Raw Log</strong> to inspect output.</div>';
        return;
    }

    const htmlParts = [];
    healthCheckSections.forEach((sec, idx) => {
        const filteredTests = (sec.tests || []).filter(t => {
            if (healthCheckFilter !== 'all' && t.status !== healthCheckFilter) return false;
            if (search && !t.name.toLowerCase().includes(search) && !(sec.title || '').toLowerCase().includes(search)) {
                return false;
            }
            return true;
        });

        if (filteredTests.length === 0) return;

        const hasFail = sec.failed > 0;
        const shouldOpen = hasFail || healthSectionsExpanded || search.length > 0 || healthCheckFilter === 'fail';
        const collapseId = `health-sec-collapse-${sec.id}-${idx}`;
        const icon = getHealthSectionIcon(sec.title);
        const total = sec.passed + sec.failed;
        const badgeClass = hasFail ? 'bg-danger' : 'bg-success';
        const badgeText = hasFail ? `${sec.failed} Failed / ${total}` : `${sec.passed}/${total} Passed`;

        const rowsHtml = filteredTests.map(t => {
            const isPass = t.status === 'pass';
            const statusIcon = isPass
                ? '<i class="bi bi-check-circle-fill text-success me-2"></i>'
                : '<i class="bi bi-x-circle-fill text-danger me-2"></i>';
            const pill = isPass
                ? '<span class="badge bg-success-subtle text-success border border-success-subtle">PASS</span>'
                : '<span class="badge bg-danger-subtle text-danger border border-danger-subtle">FAIL</span>';
            return `
                <div class="d-flex justify-content-between align-items-center py-2 px-3 border-bottom small ${isPass ? '' : 'bg-danger-subtle bg-opacity-25'}">
                    <div class="d-flex align-items-center">
                        ${statusIcon}
                        <span>${escapeHealthHtml(t.name)}</span>
                    </div>
                    ${pill}
                </div>
            `;
        }).join('');

        htmlParts.push(`
            <div class="accordion-item border mb-2 rounded overflow-hidden">
                <h2 class="accordion-header">
                    <button class="accordion-button ${shouldOpen ? '' : 'collapsed'} py-2 px-3" type="button" data-bs-toggle="collapse" data-bs-target="#${collapseId}">
                        <div class="d-flex justify-content-between align-items-center w-100 me-3">
                            <span class="fw-semibold d-flex align-items-center gap-2">
                                <i class="bi ${icon} ${hasFail ? 'text-danger' : 'text-primary'}"></i>
                                <span>${escapeHealthHtml(sec.title)}</span>
                            </span>
                            <span class="badge ${badgeClass} rounded-pill">${badgeText}</span>
                        </div>
                    </button>
                </h2>
                <div id="${collapseId}" class="accordion-collapse collapse ${shouldOpen ? 'show' : ''}">
                    <div class="accordion-body p-0">
                        ${rowsHtml}
                    </div>
                </div>
            </div>
        `);
    });

    if (htmlParts.length === 0) {
        container.innerHTML = `
            <div class="text-center text-muted py-4 border rounded bg-body-tertiary">
                <i class="bi bi-funnel fs-4 d-block mb-1"></i>
                No checks match the current filter${search ? ` ("${escapeHealthHtml(search)}")` : ''}.
            </div>
        `;
        return;
    }

    container.innerHTML = htmlParts.join('');
}

/**
 * Run health check and display structured + raw results
 */
async function runHealthCheck(evt) {
    const resultsDiv = document.getElementById('health-check-results');
    const idleDiv = document.getElementById('health-check-idle');
    const sectionsDiv = document.getElementById('health-check-sections');
    const outputDiv = document.getElementById('health-check-output');
    const passedDiv = document.getElementById('health-tests-passed');
    const failedDiv = document.getElementById('health-tests-failed');
    const passRateDiv = document.getElementById('health-pass-rate');
    const progressBar = document.getElementById('health-progress-bar');
    const statusBadge = document.getElementById('health-status-badge');
    const runMeta = document.getElementById('health-run-meta');
    const runBtn = document.getElementById('health-run-btn') || evt?.target?.closest('button');

    resultsDiv.style.display = 'block';
    idleDiv.style.display = 'none';
    sectionsDiv.innerHTML = `
        <div class="text-center py-4 text-muted">
            <div class="spinner-border spinner-border-sm text-primary me-2" role="status"></div>
            Running comprehensive system checks (containers, DB, storage, endpoints, rate limits, GeoIP)...
        </div>
    `;
    outputDiv.innerHTML = '<div class="text-center text-muted">Running health check...</div>';
    if (runBtn) {
        runBtn.disabled = true;
        runBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Running...';
    }

    try {
        const result = await apiRequest('/health-check', 'POST');

        if (!result || !result.success) {
            sectionsDiv.innerHTML = `<div class="alert alert-danger mb-0">Error: ${escapeHealthHtml(result?.error || 'Unknown error')}</div>`;
            outputDiv.innerHTML = `<div class="text-danger">Error: ${escapeHealthHtml(result?.error || 'Unknown error')}</div>`;
            return;
        }

        const passed = result.tests_passed ?? 0;
        const failed = result.tests_failed ?? 0;
        const total = result.total_tests ?? (passed + failed);
        const passRate = result.pass_rate ?? (total > 0 ? Math.round((passed / total) * 1000) / 10 : 0);

        passedDiv.textContent = passed;
        failedDiv.textContent = failed;
        if (passRateDiv) passRateDiv.textContent = `${passRate}%`;

        document.getElementById('health-filter-all-count').textContent = total;
        document.getElementById('health-filter-fail-count').textContent = failed;
        document.getElementById('health-filter-pass-count').textContent = passed;

        if (progressBar) {
            progressBar.style.width = `${passRate}%`;
            progressBar.className = `progress-bar ${failed === 0 ? 'bg-success' : failed < 5 ? 'bg-warning' : 'bg-danger'}`;
        }

        if (runMeta) {
            const dur = result.duration_seconds !== undefined ? `${result.duration_seconds}s` : '';
            runMeta.textContent = dur ? `Completed in ${dur} · ${new Date().toLocaleTimeString()}` : `Completed at ${new Date().toLocaleTimeString()}`;
            runMeta.classList.remove('d-none');
        }

        statusBadge.textContent = (result.overall_status || 'unknown').toUpperCase();
        if (result.overall_status === 'healthy') {
            statusBadge.className = 'badge bg-success';
        } else if (result.overall_status === 'degraded') {
            statusBadge.className = 'badge bg-warning text-dark';
        } else {
            statusBadge.className = 'badge bg-danger';
        }

        healthCheckSections = Array.isArray(result.sections) ? result.sections : [];
        healthSectionsExpanded = false;
        const toggleBtn = document.getElementById('health-toggle-all-btn');
        if (toggleBtn) toggleBtn.innerHTML = '<i class="bi bi-arrows-expand"></i> Expand All';

        // Reset filter to 'fail' automatically if there are failures, otherwise 'all'
        const defaultFilter = failed > 0 ? 'fail' : 'all';
        setHealthFilter(defaultFilter);

        outputDiv.innerHTML = ansiToHtml(result.output || '');
    } catch (error) {
        console.error('Health check error:', error);
        sectionsDiv.innerHTML = `<div class="alert alert-danger mb-0">Error: ${escapeHealthHtml(error.message)}</div>`;
        outputDiv.innerHTML = `<div class="text-danger">Error: ${escapeHealthHtml(error.message)}</div>`;
    } finally {
        if (runBtn) {
            runBtn.disabled = false;
            runBtn.innerHTML = '<i class="bi bi-play-circle"></i> Run Verification Tests';
        }
    }
}

/**
 * Refresh all data for whichever sections exist on the current page
 */
async function refreshAll() {
    if (document.getElementById('stat-total-users') || document.getElementById('containers-tbody')) {
        await loadStats();
        await loadSystemTelemetry();
        await loadUsers();
        await loadContainers();
    }
    if (document.getElementById('logs-container')) {
        await refreshLogs();
    }
}

// Load data on page ready
document.addEventListener('DOMContentLoaded', () => {
    refreshAll();

    // Refresh dashboard data every 10 seconds when on dashboard
    if (document.getElementById('stat-total-users') || document.getElementById('containers-tbody')) {
        setInterval(refreshAll, 10000);
    }

    // Setup auto-refresh for logs when on Health & Logs page
    let logsRefreshInterval = null;
    const autoRefreshCheckbox = document.getElementById('autoRefresh');

    if (autoRefreshCheckbox && document.getElementById('logs-container')) {
        autoRefreshCheckbox.addEventListener('change', (e) => {
            if (e.target.checked) {
                logsRefreshInterval = setInterval(() => {
                    refreshLogs();
                }, 5000);
            } else {
                if (logsRefreshInterval) {
                    clearInterval(logsRefreshInterval);
                    logsRefreshInterval = null;
                }
            }
        });

        logsRefreshInterval = setInterval(() => {
            refreshLogs();
        }, 5000);
    }
});
