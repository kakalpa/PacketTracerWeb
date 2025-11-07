/**
 * PT Management - Dashboard-specific functions
 */

let csvData = [];
let csvDeleteData = [];
let availableContainers = [];

// Load containers when page loads
document.addEventListener('DOMContentLoaded', function() {
    loadAvailableContainers();
    
    // Set up event listeners for new modals
    document.getElementById('createContainerBtn')?.addEventListener('click', createNewContainer);
    document.getElementById('createSingleUserBtn')?.addEventListener('click', createSingleUserWithContainer);
});

/**
 * Load available containers from API
 */
async function loadAvailableContainers() {
    try {
        const response = await apiRequest('/containers');
        if (response && response.success) {
            availableContainers = response.containers || [];
            updateContainerSelect();
            updateSingleUserContainerSelect();
        }
    } catch (err) {
        console.error('Failed to load containers:', err);
    }
}

/**
 * Update container select dropdown
 */
function updateContainerSelect() {
    const select = document.getElementById('containerSelect');
    if (!select) return;
    
    // Remove loading option
    const loadingOption = document.getElementById('container-loading');
    if (loadingOption) loadingOption.remove();
    
    // Add container options
    availableContainers.forEach(container => {
        const option = document.createElement('option');
        option.value = container.name;
        option.textContent = `${container.name} (${container.status})`;
        select.appendChild(option);
    });
}

/**
 * Update single user container select dropdown
 */
function updateSingleUserContainerSelect() {
    const select = document.getElementById('singleContainerSelect');
    if (!select) return;
    
    // Clear existing options (keep the first placeholder)
    while (select.options.length > 1) {
        select.remove(1);
    }
    
    // Add container options
    availableContainers.forEach(container => {
        const option = document.createElement('option');
        option.value = container.name;
        option.textContent = `${container.name} (${container.status})`;
        select.appendChild(option);
    });
}

/**
 * Parse CSV data for creation - supports username,password[,is_admin]
 */
function parseCSV(csv) {
    const lines = csv.trim().split('\n');
    const data = [];

    lines.forEach((line, index) => {
        line = line.trim();
        if (!line || index === 0) return; // Skip empty lines and header

        const parts = line.split(',').map(s => s.trim());
        const [username, password, is_admin] = parts;
        if (username && password) {
            data.push({ 
                username, 
                password,
                is_admin: is_admin ? (is_admin.toLowerCase() === 'true' || is_admin === '1' || is_admin === 'yes') : false
            });
        }
    });

    return data;
}
document.getElementById('csvFile')?.addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(event) {
        const csv = event.target.result;
        csvData = parseCSV(csv);
        
        if (csvData.length === 0) {
            showNotification('CSV file is empty or invalid', 'warning');
            return;
        }

        displayCSVPreview(csvData.slice(0, 5)); // Show first 5 rows
        showNotification(`Loaded ${csvData.length} users`, 'info');
    };
    reader.readAsText(file);
});

/**
 * Handle CSV file selection for delete operation
 */
document.getElementById('csvDeleteFile')?.addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(event) {
        const csv = event.target.result;
        csvDeleteData = parseDeleteCSV(csv);
        
        if (csvDeleteData.length === 0) {
            showNotification('CSV file is empty or invalid', 'warning');
            return;
        }

        displayDeleteCSVPreview(csvDeleteData.slice(0, 5)); // Show first 5 rows
        showNotification(`Loaded ${csvDeleteData.length} users for deletion`, 'info');
    };
    reader.readAsText(file);
});

/**
 * Parse CSV data for deletion
 * Can accept either just username or username,password (password ignored)
 */
function parseDeleteCSV(csv) {
    const lines = csv.trim().split('\n');
    const data = [];

    lines.forEach((line, index) => {
        line = line.trim();
        if (!line || index === 0) return; // Skip empty lines and header

        const [username] = line.split(',').map(s => s.trim());
        if (username) {
            data.push({ username });
        }
    });

    return data;
}

/**
 * Handle checkbox for creating new containers per user
 */
document.getElementById('createContainersCheckbox')?.addEventListener('change', function(e) {
    const containerSelectDiv = document.getElementById('containerSelectDiv');
    if (e.target.checked) {
        // When checkbox is checked, hide the container select
        containerSelectDiv.style.display = 'none';
        document.getElementById('containerSelect').value = '';
    } else {
        // When unchecked, show the container select
        containerSelectDiv.style.display = 'block';
    }
});

/**
 * Display CSV preview in modal
 */
function displayCSVPreview(data) {
    let html = '<div class="alert alert-info"><strong>Preview (first 5 rows):</strong></div>';
    html += '<table class="table table-sm">';
    html += '<thead><tr><th>Username</th><th>Password</th><th>Admin</th></tr></thead>';
    html += '<tbody>';

    data.forEach(row => {
        const isAdmin = row.is_admin ? '<span class="badge bg-danger">Admin</span>' : '<span class="badge bg-secondary">User</span>';
        html += `<tr><td>${row.username}</td><td>•••••••••</td><td>${isAdmin}</td></tr>`;
    });

    html += '</tbody></table>';
    document.getElementById('csvPreview').innerHTML = html;
}

/**
 * Display CSV delete preview in modal
 */
function displayDeleteCSVPreview(data) {
    let html = '<div class="alert alert-warning"><strong>Preview (first 5 rows to delete):</strong></div>';
    html += '<table class="table table-sm">';
    html += '<thead><tr><th>Username</th></tr></thead>';
    html += '<tbody>';

    data.forEach(row => {
        html += `<tr><td>${row.username}</td></tr>`;
    });

    html += '</tbody></table>';
    document.getElementById('csvDeletePreview').innerHTML = html;
}

/**
 * Handle bulk user creation
 */
document.getElementById('bulkCreateBtn')?.addEventListener('click', async function() {
    if (csvData.length === 0) {
        showNotification('Please select a CSV file first', 'warning');
        return;
    }

    const btn = this;
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Creating...';

    try {
        const createContainers = document.getElementById('createContainersCheckbox').checked;
        const makeAdmin = document.getElementById('makeAdminCheckbox').checked;
        
        let usersToCreate;
        
        if (createContainers) {
            // When creating new containers, mark users to spin up new containers
            usersToCreate = csvData.map(user => ({
                ...user,
                create_container: true,
                is_admin: makeAdmin || (user.is_admin === 'true' || user.is_admin === true || user.is_admin === 1)
            }));
            
            btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Creating containers & users...';
        } else {
            // Use default container from select if set
            const defaultContainer = document.getElementById('containerSelect')?.value || '';
            
            usersToCreate = csvData.map(user => ({
                ...user,
                container: defaultContainer,
                is_admin: makeAdmin || (user.is_admin === 'true' || user.is_admin === true || user.is_admin === 1)
            }));
        }

        const result = await apiRequest('/users', 'POST', { users: usersToCreate });

        if (result && result.success) {
            const message = createContainers 
                ? `Created ${result.count_created} users with new containers${result.count_failed > 0 ? `, ${result.count_failed} failed` : ''}`
                : `Created ${result.count_created} users${result.count_failed > 0 ? `, ${result.count_failed} failed` : ''}`;
            
            showNotification(
                message,
                result.count_failed > 0 ? 'warning' : 'success'
            );

            // Reset form
            document.getElementById('csvFile').value = '';
            document.getElementById('createContainersCheckbox').checked = false;
            document.getElementById('makeAdminCheckbox').checked = false;
            document.getElementById('containerSelectDiv').style.display = 'none';
            csvData = [];
            document.getElementById('csvPreview').innerHTML = '';
            document.getElementById('containerSelect').value = '';

            // Close modal
            bootstrap.Modal.getInstance(document.getElementById('bulkCreateModal')).hide();

            // Refresh users and containers
            await loadUsers();
            await loadContainers();
            await loadStats();
        }
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
});

/**
 * Handle bulk user deletion
 */
document.getElementById('bulkDeleteBtn')?.addEventListener('click', async function() {
    if (csvDeleteData.length === 0) {
        showNotification('Please select a CSV file first', 'warning');
        return;
    }

    // Confirm deletion
    if (!confirm(`Are you sure you want to delete ${csvDeleteData.length} users? This action cannot be undone.`)) {
        return;
    }

    const btn = this;
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Deleting...';

    try {
        const result = await apiRequest('/users/bulk/delete', 'POST', { users: csvDeleteData });

        if (result && result.success) {
            showNotification(
                `Deleted ${result.count_deleted} users${result.count_not_found > 0 ? `, ${result.count_not_found} not found` : ''}${result.count_failed > 0 ? `, ${result.count_failed} failed` : ''}`,
                (result.count_not_found > 0 || result.count_failed > 0) ? 'warning' : 'success'
            );

            // Reset form
            document.getElementById('csvDeleteFile').value = '';
            csvDeleteData = [];
            document.getElementById('csvDeletePreview').innerHTML = '';

            // Close modal
            bootstrap.Modal.getInstance(document.getElementById('bulkDeleteModal')).hide();

            // Refresh users list
            await loadUsers();
            await loadStats();
        }
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
});

/**
 * Create a new container instance
 */
async function createNewContainer() {
    const containerNameInput = document.getElementById('containerNameInput');
    const containerName = containerNameInput?.value?.trim() || '';
    
    // Allow empty names for auto-numbering, but validate if provided
    if (containerName) {
        // Validate container name format if provided
        if (!containerName.startsWith('ptvnc')) {
            showNotification('Container name must start with "ptvnc" (e.g., ptvnc1, ptvnc-lab)', 'warning');
            return;
        }
        const suffix = containerName.substring(5);
        const validSuffixPattern = /^[a-zA-Z0-9_-]*$/;
        if (suffix && !validSuffixPattern.test(suffix)) {
            showNotification('Container name suffix can only contain letters, numbers, hyphens, and underscores', 'warning');
            return;
        }
    }
    
    const btn = document.getElementById('createContainerBtn');
    const statusDiv = document.getElementById('createContainerStatus');
    const originalText = btn.innerHTML;
    
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Creating...';
    statusDiv.innerHTML = '';
    
    try {
        // Call API to create container
        const result = await apiRequest('/containers', 'POST', {
            name: containerName,
            image: 'ptvnc'
        });
        
        if (result && result.success) {
            statusDiv.innerHTML = `<div class="alert alert-success"><i class="bi bi-check-circle"></i> Container <strong>${result.container_name}</strong> created successfully!</div>`;
            
            // Reset form
            containerNameInput.value = '';
            
            // Refresh containers list
            await loadAvailableContainers();
            await loadContainers();
            
            // Close modal after 2 seconds
            setTimeout(() => {
                bootstrap.Modal.getInstance(document.getElementById('createContainerModal')).hide();
                statusDiv.innerHTML = '';
            }, 2000);
        } else {
            const errorMsg = result?.message || 'Failed to create container';
            statusDiv.innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-circle"></i> ${errorMsg}</div>`;
        }
    } catch (err) {
        statusDiv.innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-circle"></i> Error: ${err.message}</div>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

/**
 * Create a single user and assign a container
 */
async function createSingleUserWithContainer() {
    const username = document.getElementById('singleUsername')?.value?.trim() || '';
    const password = document.getElementById('singlePassword')?.value || '';
    const isAdmin = document.getElementById('singleUserIsAdmin')?.checked || false;
    const containerName = document.getElementById('singleContainerSelect')?.value || '';
    
    const statusDiv = document.getElementById('createUserStatus');
    statusDiv.innerHTML = '';
    
    // Validate inputs
    if (!username) {
        showNotification('Please enter a username', 'warning');
        return;
    }
    
    if (!password) {
        showNotification('Please enter a password', 'warning');
        return;
    }
    
    const btn = document.getElementById('createSingleUserBtn');
    const originalText = btn.innerHTML;
    
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Creating...';
    
    try {
        // Create user with container assignment and admin status
        const result = await apiRequest('/users', 'POST', {
            users: [{
                username: username,
                password: password,
                container: containerName,
                is_admin: isAdmin
            }]
        });
        
        if (result && result.success && result.count_created > 0) {
            const adminBadge = isAdmin ? ' <span class="badge bg-danger">Admin</span>' : '';
            const containerInfo = containerName 
                ? ` and assigned to <strong>${containerName}</strong>`
                : ' (no container assigned)';
            statusDiv.innerHTML = `<div class="alert alert-success"><i class="bi bi-check-circle"></i> User <strong>${username}</strong>${adminBadge} created${containerInfo}!</div>`;
            
            // Reset form
            document.getElementById('singleUsername').value = '';
            document.getElementById('singlePassword').value = '';
            document.getElementById('singleUserIsAdmin').checked = false;
            document.getElementById('singleContainerSelect').value = '';
            
            // Refresh users list
            await loadUsers();
            await loadStats();
            
            // Close modal after 2 seconds
            setTimeout(() => {
                bootstrap.Modal.getInstance(document.getElementById('createSingleUserModal')).hide();
                statusDiv.innerHTML = '';
            }, 2000);
        } else {
            const errorMsg = result?.message || (result?.count_failed > 0 ? 'Failed to create user' : 'Unknown error');
            statusDiv.innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-circle"></i> ${errorMsg}</div>`;
        }
    } catch (err) {
        statusDiv.innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-circle"></i> Error: ${err.message}</div>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

/**
 * Update user selection count
 */
function updateUserSelectionCount() {
    const checked = document.querySelectorAll('.user-checkbox:checked').length;
    const total = document.querySelectorAll('.user-checkbox').length;
    document.getElementById('users-selected-count').textContent = `${checked} of ${total} selected`;
    
    // Update "select all" checkbox
    const selectAllCheckbox = document.getElementById('users-select-all-checkbox');
    if (selectAllCheckbox) {
        selectAllCheckbox.checked = checked === total && total > 0;
        selectAllCheckbox.indeterminate = checked > 0 && checked < total;
    }
}

/**
 * Toggle all users
 */
function toggleAllUsers(checkbox) {
    document.querySelectorAll('.user-checkbox').forEach(cb => cb.checked = checkbox.checked);
    updateUserSelectionCount();
}

/**
 * Delete selected users
 */
async function deleteSelectedUsers() {
    const selected = Array.from(document.querySelectorAll('.user-checkbox:checked'))
        .map(cb => cb.closest('tr').getAttribute('data-username'));
    
    if (selected.length === 0) {
        showNotification('No users selected', 'warning');
        return;
    }
    
    if (!confirm(`Are you sure you want to delete ${selected.length} user(s)? This action cannot be undone.`)) {
        return;
    }
    
    const btn = document.getElementById('users-bulk-delete');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Deleting...';
    
    try {
        let successCount = 0;
        let failCount = 0;
        
        for (const username of selected) {
            const result = await apiRequest(`/users/${username}`, 'DELETE');
            if (result && result.success) {
                successCount++;
            } else {
                failCount++;
            }
        }
        
        showNotification(
            `Deleted ${successCount} user(s)${failCount > 0 ? `, ${failCount} failed` : ''}`,
            failCount > 0 ? 'warning' : 'success'
        );
        
        await loadUsers();
        await loadStats();
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

/**
 * Update container selection count
 */
function updateContainerSelectionCount() {
    const checked = document.querySelectorAll('.container-checkbox:checked').length;
    const total = document.querySelectorAll('.container-checkbox').length;
    document.getElementById('containers-selected-count').textContent = `${checked} of ${total} selected`;
    
    // Update "select all" checkbox
    const selectAllCheckbox = document.getElementById('containers-select-all-checkbox');
    if (selectAllCheckbox) {
        selectAllCheckbox.checked = checked === total && total > 0;
        selectAllCheckbox.indeterminate = checked > 0 && checked < total;
    }
}

/**
 * Toggle all containers
 */
function toggleAllContainers(checkbox) {
    document.querySelectorAll('.container-checkbox').forEach(cb => cb.checked = checkbox.checked);
    updateContainerSelectionCount();
}

/**
 * Delete selected containers
 */
async function deleteSelectedContainers() {
    const selected = Array.from(document.querySelectorAll('.container-checkbox:checked'))
        .map(cb => cb.closest('tr').getAttribute('data-container-name'));
    
    if (selected.length === 0) {
        showNotification('No containers selected', 'warning');
        return;
    }
    
    if (!confirm(`Are you sure you want to delete ${selected.length} container(s)? This action cannot be undone.`)) {
        return;
    }
    
    const btn = document.getElementById('containers-bulk-delete');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Deleting...';
    
    try {
        let successCount = 0;
        let failCount = 0;
        
        for (const containerName of selected) {
            const result = await apiRequest(`/containers/${containerName}`, 'DELETE');
            if (result && result.success) {
                successCount++;
            } else {
                failCount++;
            }
        }
        
        showNotification(
            `Deleted ${successCount} container(s)${failCount > 0 ? `, ${failCount} failed` : ''}`,
            failCount > 0 ? 'warning' : 'success'
        );
        
        await loadContainers();
        await loadStats();
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

/**
 * Open user menu modal for editing user details
 */
async function openUserMenu(user) {
    // Create modal content
    const modalHTML = `
    <div class="modal fade" id="userMenuModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">
                        <i class="bi bi-person"></i> Manage User: ${user.username}
                        ${user.is_admin ? '<span class="badge bg-danger ms-2"><i class="bi bi-shield-check"></i> Admin</span>' : ''}
                    </h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <!-- Reset Password Section -->
                    <div class="mb-4">
                        <h6><i class="bi bi-key"></i> Reset Password</h6>
                        <div class="input-group">
                            <input type="password" class="form-control" id="newPasswordInput" placeholder="Enter new password">
                            <button class="btn btn-primary" onclick="resetUserPassword('${user.username}')">
                                <i class="bi bi-arrow-repeat"></i> Reset
                            </button>
                        </div>
                    </div>
                    
                    <hr>
                    
                    <!-- Assign Containers Section -->
                    <div class="mb-4">
                        <h6><i class="bi bi-boxes"></i> Assign Containers</h6>
                        <div id="containerList" class="border rounded p-3" style="max-height: 300px; overflow-y: auto;">
                            <div class="text-center text-muted">Loading containers...</div>
                        </div>
                        <button class="btn btn-success mt-2" onclick="saveContainerAssignments('${user.username}')">
                            <i class="bi bi-check-circle"></i> Save Assignments
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>
    `;
    
    // Remove old modal if exists
    const oldModal = document.getElementById('userMenuModal');
    if (oldModal) oldModal.remove();
    
    // Add new modal
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    
    // Load containers for assignment
    await loadContainersForAssignment(user.username);
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('userMenuModal'));
    modal.show();
}

/**
 * Load containers for assignment to user
 */
async function loadContainersForAssignment(username) {
    const result = await apiRequest('/containers');
    const containerList = document.getElementById('containerList');
    
    if (!result || !result.success || !result.containers) {
        containerList.innerHTML = '<div class="text-danger">Failed to load containers</div>';
        return;
    }
    
    // Get user's current containers
    const userResult = await apiRequest(`/users/${username}`);
    const userConnections = userResult?.connections || [];
    
    // Create a mapping of possible connection names for each container
    const connectionNameMap = {};
    result.containers.forEach(container => {
        const names = [];
        if (container.name.startsWith('ptvnc')) {
            const suffix = container.name.replace('ptvnc', '');
            if (!isNaN(suffix)) {
                // For numeric suffixes, try both zero-padded and non-padded versions
                const num = parseInt(suffix);
                names.push('pt' + String(num).padStart(2, '0')); // pt01, pt05, etc.
                names.push('pt' + num);  // pt1, pt5, etc.
            } else {
                // For non-numeric suffixes
                names.push('pt' + suffix);
            }
        }
        connectionNameMap[container.name] = names;
    });
    
    let html = '';
    result.containers.forEach(container => {
        // Check if this container has any assigned connections
        const possibleNames = connectionNameMap[container.name] || [];
        const isAssigned = userConnections.some(conn => 
            possibleNames.includes(conn.connection_name)
        );
        
        html += `
        <div class="form-check">
            <input class="form-check-input container-assign-checkbox" type="checkbox" 
                   id="container_${container.name}" value="${container.name}" 
                   ${isAssigned ? 'checked' : ''}>
            <label class="form-check-label" for="container_${container.name}">
                <strong>${container.name}</strong> 
                <span class="badge ${container.status === 'running' ? 'bg-success' : 'bg-secondary'}">
                    ${container.status}
                </span>
            </label>
        </div>
        `;
    });
    
    containerList.innerHTML = html;
}

/**
 * Reset user password
 */
async function resetUserPassword(username) {
    const passwordInput = document.getElementById('newPasswordInput');
    const newPassword = passwordInput.value;
    
    if (!newPassword) {
        showNotification('Please enter a new password', 'warning');
        return;
    }
    
    if (!confirm(`Are you sure you want to reset password for ${username}?`)) {
        return;
    }
    
    const result = await apiRequest(`/users/${username}/reset-password`, 'POST', {
        password: newPassword
    });
    
    if (result && result.success) {
        showNotification(`Password reset successful for ${username}`, 'success');
        passwordInput.value = '';
    } else {
        showNotification(result?.error || 'Failed to reset password', 'error');
    }
}

/**
 * Save container assignments for user
 */
async function saveContainerAssignments(username) {
    const checkboxes = document.querySelectorAll('.container-assign-checkbox:checked');
    const containers = Array.from(checkboxes).map(cb => cb.value);
    
    const result = await apiRequest(`/users/${username}/containers`, 'POST', {
        containers: containers
    });
    
    if (result && result.success) {
        showNotification(
            `Assigned ${result.containers_assigned} container(s) to ${username}`,
            'success'
        );
        // Close modal
        bootstrap.Modal.getInstance(document.getElementById('userMenuModal')).hide();
        // Reload users
        loadUsers();
    } else {
        showNotification(result?.error || 'Failed to assign containers', 'error');
    }
}

/**
 * Handle resource tuning modal tab changes
 */
document.addEventListener('DOMContentLoaded', function() {
    const bulkTab = document.getElementById('bulk-tune-tab');
    const singleTab = document.getElementById('single-tune-tab');
    const bulkTuneBtn = document.getElementById('bulkTuneBtn');
    const singleTuneBtn = document.getElementById('singleTuneBtn');
    
    if (bulkTab) {
        bulkTab.addEventListener('shown.bs.tab', function() {
            bulkTuneBtn.style.display = 'block';
            singleTuneBtn.style.display = 'none';
        });
    }
    
    if (singleTab) {
        singleTab.addEventListener('shown.bs.tab', function() {
            bulkTuneBtn.style.display = 'none';
            singleTuneBtn.style.display = 'block';
            loadSingleTuneContainers();
        });
    }
    
    // Load single tune containers when modal is shown
    const resourceModal = document.getElementById('resourceTuningModal');
    if (resourceModal) {
        resourceModal.addEventListener('show.bs.modal', function() {
            loadSingleTuneContainers();
        });
    }
});

/**
 * Load containers for single tuning dropdown
 */
async function loadSingleTuneContainers() {
    const result = await apiRequest('/containers');
    const select = document.getElementById('singleTuneContainerSelect');
    
    if (!select) return;
    
    // Clear existing options except the first one
    while (select.children.length > 1) {
        select.removeChild(select.lastChild);
    }
    
    if (result && result.success && result.containers) {
        result.containers.forEach(container => {
            const option = document.createElement('option');
            option.value = container.name;
            option.textContent = `${container.name} (${container.status})`;
            select.appendChild(option);
        });
    }
}

/**
 * Apply bulk resource tuning to all containers
 */
async function applyBulkTuning() {
    const memory = document.getElementById('bulkMemoryInput').value.trim();
    const cpus = document.getElementById('bulkCpuInput').value.trim();
    const statusDiv = document.getElementById('bulkTuneStatus');
    
    if (!memory || !cpus) {
        showNotification('Please enter both memory and CPU values', 'warning');
        return;
    }
    
    if (!confirm(`Are you sure you want to update resources for ALL containers?\n\nMemory: ${memory}\nCPU: ${cpus}`)) {
        return;
    }
    
    statusDiv.innerHTML = '<div class="spinner-border spinner-border-sm me-2" role="status"></div>Updating all containers...';
    
    const result = await apiRequest('/containers/resources/bulk-update', 'PUT', {
        memory: memory,
        cpus: parseFloat(cpus)
    });
    
    if (result && result.success) {
        statusDiv.innerHTML = `
            <div class="alert alert-success">
                <i class="bi bi-check-circle"></i> Successfully updated ${result.updated_count} container(s)
                <ul class="mb-0 mt-2">
                    ${result.updated.map(c => `<li><strong>${c}</strong> - memory: ${result.memory}, cpus: ${result.cpus}</li>`).join('')}
                </ul>
                ${result.failed && result.failed.length > 0 ? `
                    <hr>
                    <strong class="text-danger">Failed:</strong>
                    <ul class="mb-0">
                        ${result.failed.map(c => `<li><strong>${c}</strong></li>`).join('')}
                    </ul>
                ` : ''}
            </div>
        `;
        showNotification(`Updated ${result.updated_count} container(s)`, 'success');
        setTimeout(() => loadContainers(), 2000);
    } else {
        statusDiv.innerHTML = `<div class="alert alert-danger">Failed to update containers: ${result?.error || 'Unknown error'}</div>`;
        showNotification(result?.error || 'Failed to update containers', 'error');
    }
}

/**
 * Apply resource tuning to single container
 */
async function applySingleTuning() {
    const containerName = document.getElementById('singleTuneContainerSelect').value;
    const memory = document.getElementById('singleMemoryInput').value.trim();
    const cpus = document.getElementById('singleCpuInput').value.trim();
    const statusDiv = document.getElementById('singleTuneStatus');
    
    if (!containerName) {
        showNotification('Please select a container', 'warning');
        return;
    }
    
    if (!memory || !cpus) {
        showNotification('Please enter both memory and CPU values', 'warning');
        return;
    }
    
    if (!confirm(`Are you sure you want to update ${containerName}?\n\nMemory: ${memory}\nCPU: ${cpus}`)) {
        return;
    }
    
    statusDiv.innerHTML = '<div class="spinner-border spinner-border-sm me-2" role="status"></div>Updating container...';
    
    const result = await apiRequest(`/containers/${containerName}/resources`, 'PUT', {
        memory: memory,
        cpus: parseFloat(cpus)
    });
    
    if (result && result.success) {
        statusDiv.innerHTML = `
            <div class="alert alert-success">
                <i class="bi bi-check-circle"></i> Successfully updated <strong>${containerName}</strong>
                <ul class="mb-0 mt-2">
                    <li>Memory: ${result.memory}</li>
                    <li>CPU: ${result.cpus}</li>
                </ul>
            </div>
        `;
        showNotification(`Updated ${containerName}`, 'success');
        setTimeout(() => loadContainers(), 2000);
    } else {
        statusDiv.innerHTML = `<div class="alert alert-danger">Failed to update container: ${result?.error || 'Unknown error'}</div>`;
        showNotification(result?.error || 'Failed to update container', 'error');
    }
}
