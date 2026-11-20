/**
 * Environment Configuration Manager
 * Handles UI interactions for nginx configuration management
 */

let currentConfig = null;
let defaults = null;
let previewData = null;
let nginxAutoRefreshInterval = null;
let nginxLastLogLength = 0;

/**
 * Initialize the page
 */
document.addEventListener('DOMContentLoaded', async function() {
    console.log('🚀 Environment Configuration Manager loaded');
    
    // Load defaults
    await loadDefaults();
    
    // Load current configuration
    await loadConfiguration();
    
    // Set up event listeners
    setupEventListeners();
    
    // Load backups
    await loadBackups();
    
    // Load SSL info
    await loadSSLInfo();

    // Load Certbot status
    await loadCertbotStatus();
});

/**
 * Load default configuration
 */
async function loadDefaults() {
    try {
        const response = await fetch('/api/env/defaults');
        
        // Check for redirect
        if (!response.ok) {
            console.warn('⚠ Failed to load defaults');
            return;
        }
        
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            console.warn('⚠ Invalid response type for defaults');
            return;
        }
        
        const data = await response.json();
        
        if (data.success) {
            defaults = data.defaults;
            console.log('✓ Defaults loaded');
        }
    } catch (error) {
        console.error('✗ Error loading defaults:', error);
    }
}

/**
 * Load current configuration
 */
async function loadConfiguration() {
    try {
        showSpinner('Loading configuration...');
        
        const response = await fetch('/api/env/config');
        
        // Check if we got redirected to login (HTML response)
        if (!response.ok) {
            hideSpinner();
            showAlert('Session expired. Please log in again.', 'warning');
            setTimeout(() => window.location.href = '/login', 2000);
            return;
        }
        
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            hideSpinner();
            showAlert('Session expired. Please log in again.', 'warning');
            setTimeout(() => window.location.href = '/login', 2000);
            return;
        }
        
        const data = await response.json();
        
        if (data.success) {
            currentConfig = data.config;
            console.log('✓ Configuration loaded:', currentConfig);
            
            // Populate form fields
            populateForm(currentConfig);
            updateStatusBadge();

            const restartNotice = document.getElementById('https-cookie-restart-notice');
            if (restartNotice) {
                restartNotice.style.display = data.session_cookie_restart_needed ? 'block' : 'none';
            }
            hideSpinner();
        } else {
            hideSpinner();
            showAlert('Failed to load configuration: ' + data.message, 'danger');
        }
    } catch (error) {
        hideSpinner();
        console.error('✗ Error loading configuration:', error);
        showAlert('Error loading configuration: ' + error.message, 'danger');
    }
}

/**
 * Populate form with configuration values
 */
function populateForm(config) {
    // HTTPS
    document.getElementById('https-enabled').checked = config.https.enabled;
    document.getElementById('https-cert').value = config.https.cert_path;
    document.getElementById('https-key').value = config.https.key_path;
    const serverNameInput = document.getElementById('https-server-name');
    if (serverNameInput) {
        serverNameInput.value = config.https.server_name || 'localhost';
    }
    const tlsMode = config.https.tls_mode || 'self-signed';
    const modeBadge = document.getElementById('https-tls-mode-badge');
    if (modeBadge) {
        modeBadge.textContent = `Mode: ${tlsMode}`;
    }
    const sslModeLabel = document.getElementById('ssl-panel-mode-label');
    if (sslModeLabel) {
        sslModeLabel.textContent = tlsMode;
    }
    toggleHttpsOptions();
    
    // GeoIP
    document.getElementById('geoip-allow-enabled').checked = config.geoip.allow_enabled;
    document.getElementById('geoip-allow-countries').value = config.geoip.allow_countries.join(',');
    updateCountryTags('geoip-allow-countries', 'geoip-allow-tags');
    toggleGeoipAllowOptions();
    
    document.getElementById('geoip-block-enabled').checked = config.geoip.block_enabled;
    document.getElementById('geoip-block-countries').value = config.geoip.block_countries.join(',');
    updateCountryTags('geoip-block-countries', 'geoip-block-tags');
    toggleGeoipBlockOptions();
    
    // Rate Limiting
    document.getElementById('ratelimit-enabled').checked = config.rate_limit.enabled;
    document.getElementById('ratelimit-rate').value = config.rate_limit.rate;
    document.getElementById('ratelimit-burst').value = config.rate_limit.burst;
    document.getElementById('ratelimit-zone').value = config.rate_limit.zone_size;
    toggleRateLimitOptions();
    
    // Production
    document.getElementById('production-mode').checked = config.production.mode;
    document.getElementById('production-ip').value = config.production.public_ip;
    toggleProductionOptions();
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // HTTPS
    document.getElementById('https-enabled').addEventListener('change', toggleHttpsOptions);
    
    // GeoIP
    document.getElementById('geoip-allow-enabled').addEventListener('change', toggleGeoipAllowOptions);
    document.getElementById('geoip-allow-countries').addEventListener('input', function() {
        updateCountryTags('geoip-allow-countries', 'geoip-allow-tags');
    });
    
    document.getElementById('geoip-block-enabled').addEventListener('change', toggleGeoipBlockOptions);
    document.getElementById('geoip-block-countries').addEventListener('input', function() {
        updateCountryTags('geoip-block-countries', 'geoip-block-tags');
    });
    
    // Rate Limiting
    document.getElementById('ratelimit-enabled').addEventListener('change', toggleRateLimitOptions);
    document.getElementById('ratelimit-rate-example').addEventListener('change', function() {
        if (this.value) {
            document.getElementById('ratelimit-rate').value = this.value;
            this.value = '';
        }
    });
    
    document.getElementById('ratelimit-zone-example').addEventListener('change', function() {
        if (this.value) {
            document.getElementById('ratelimit-zone').value = this.value;
            this.value = '';
        }
    });
    
    // Production
    document.getElementById('production-mode').addEventListener('change', toggleProductionOptions);
}

/**
 * Toggle HTTPS options visibility
 */
function toggleHttpsOptions() {
    const enabled = document.getElementById('https-enabled').checked;
    document.getElementById('https-options').style.display = enabled ? 'block' : 'none';
}

/**
 * Toggle GeoIP ALLOW options visibility
 */
function toggleGeoipAllowOptions() {
    const enabled = document.getElementById('geoip-allow-enabled').checked;
    document.getElementById('geoip-allow-options').style.display = enabled ? 'block' : 'none';
}

/**
 * Toggle GeoIP BLOCK options visibility
 */
function toggleGeoipBlockOptions() {
    const enabled = document.getElementById('geoip-block-enabled').checked;
    document.getElementById('geoip-block-options').style.display = enabled ? 'block' : 'none';
}

/**
 * Toggle Rate Limit options visibility
 */
function toggleRateLimitOptions() {
    const enabled = document.getElementById('ratelimit-enabled').checked;
    document.getElementById('ratelimit-options').style.display = enabled ? 'block' : 'none';
}

/**
 * Toggle Production options visibility
 */
function toggleProductionOptions() {
    const enabled = document.getElementById('production-mode').checked;
    document.getElementById('production-options').style.display = enabled ? 'block' : 'none';
}

/**
 * Update country tags display
 */
function updateCountryTags(inputId, tagsContainerId) {
    const input = document.getElementById(inputId);
    const container = document.getElementById(tagsContainerId);
    
    const countries = input.value
        .split(',')
        .map(c => c.trim().toUpperCase())
        .filter(c => c.length === 2);
    
    container.innerHTML = '';
    for (const country of countries) {
        const chip = document.createElement('div');
        chip.className = 'country-chip';
        chip.textContent = `${country} `;

        const removeBtn = document.createElement('span');
        removeBtn.className = 'remove';
        removeBtn.textContent = '×';
        removeBtn.addEventListener('click', () => {
            removeCountry(inputId, country);
        });

        chip.appendChild(removeBtn);
        container.appendChild(chip);
    }
}

/**
 * Remove country from list
 */
function removeCountry(inputId, country) {
    const input = document.getElementById(inputId);
    const countries = input.value
        .split(',')
        .map(c => c.trim())
        .filter(c => c.toUpperCase() !== country);
    
    input.value = countries.join(',');
    updateCountryTags(inputId, inputId.replace('countries', 'tags'));
}

/**
 * Collect form data
 */
function getFormData() {
    const serverNameEl = document.getElementById('https-server-name');
    return {
        https: {
            enabled: document.getElementById('https-enabled').checked,
            cert_path: document.getElementById('https-cert').value,
            key_path: document.getElementById('https-key').value,
            server_name: serverNameEl ? serverNameEl.value.trim() : 'localhost',
        },
        geoip: {
            allow_enabled: document.getElementById('geoip-allow-enabled').checked,
            allow_countries: document.getElementById('geoip-allow-countries').value
                .split(',')
                .map(c => c.trim().toUpperCase())
                .filter(c => c),
            block_enabled: document.getElementById('geoip-block-enabled').checked,
            block_countries: document.getElementById('geoip-block-countries').value
                .split(',')
                .map(c => c.trim().toUpperCase())
                .filter(c => c),
        },
        rate_limit: {
            enabled: document.getElementById('ratelimit-enabled').checked,
            rate: document.getElementById('ratelimit-rate').value,
            burst: parseInt(document.getElementById('ratelimit-burst').value),
            zone_size: document.getElementById('ratelimit-zone').value,
        },
        production: {
            mode: document.getElementById('production-mode').checked,
            public_ip: document.getElementById('production-ip').value,
        },
    };
}

/**
 * Preview changes
 */
async function previewChanges() {
    try {
        showSpinner('Generating preview...');
        
        const config = getFormData();
        
        const response = await fetch('/api/env/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config),
        });
        
        const data = await response.json();
        hideSpinner();
        
        if (data.success) {
            previewData = config;
            showPreviewModal(data.preview);
        } else {
            showAlert('Failed to generate preview: ' + data.message, 'danger');
        }
    } catch (error) {
        hideSpinner();
        console.error('✗ Error previewing changes:', error);
        showAlert('Error previewing changes: ' + error.message, 'danger');
    }
}

/**
 * Show preview modal
 */
function showPreviewModal(preview) {
    const modal = document.getElementById('preview-modal');
    const content = document.getElementById('preview-content');
    
    let html = `<h5>Changes Summary</h5>`;
    
    if (preview.changes.https && Object.keys(preview.changes.https).length > 0) {
        html += `<div><strong>🔒 HTTPS</strong></div>`;
        for (const [key, change] of Object.entries(preview.changes.https)) {
            html += generateChangeItem(key, change);
        }
    }
    
    if (preview.changes.geoip && Object.keys(preview.changes.geoip).length > 0) {
        html += `<div style="margin-top: 10px;"><strong>🌍 GeoIP</strong></div>`;
        for (const [key, change] of Object.entries(preview.changes.geoip)) {
            html += generateChangeItem(key, change);
        }
    }
    
    if (preview.changes.rate_limit && Object.keys(preview.changes.rate_limit).length > 0) {
        html += `<div style="margin-top: 10px;"><strong>⚡ Rate Limiting</strong></div>`;
        for (const [key, change] of Object.entries(preview.changes.rate_limit)) {
            html += generateChangeItem(key, change);
        }
    }
    
    if (preview.changes.production && Object.keys(preview.changes.production).length > 0) {
        html += `<div style="margin-top: 10px;"><strong>☁️ Production</strong></div>`;
        for (const [key, change] of Object.entries(preview.changes.production)) {
            html += generateChangeItem(key, change);
        }
    }

    if (preview.changes.certbot && Object.keys(preview.changes.certbot).length > 0) {
        html += `<div style="margin-top: 10px;"><strong>🔐 Certbot</strong></div>`;
        for (const [key, change] of Object.entries(preview.changes.certbot)) {
            html += generateChangeItem(key, change);
        }
    }
    
    content.innerHTML = html;
    modal.classList.add('show');
}

/**
 * Generate change item HTML
 */
function generateChangeItem(key, change) {
    const from = escapeHtml(formatValue(change.from));
    const to = escapeHtml(formatValue(change.to));
    const label = escapeHtml(String(key).replace(/_/g, ' '));
    return `
        <div class="change-item">
            <div class="key">${label}</div>
            <div class="from">From: <code>${from}</code></div>
            <div class="to">To: <code>${to}</code></div>
        </div>
    `;
}

/**
 * Format value for display
 */
function formatValue(value) {
    if (value === null || value === undefined) return '(not set)';
    if (typeof value === 'boolean') return value ? 'enabled' : 'disabled';
    if (Array.isArray(value)) return value.join(', ') || '(none)';
    return String(value);
}

/**
 * Close preview modal
 */
function closePreviewModal() {
    document.getElementById('preview-modal').classList.remove('show');
    previewData = null;
}

/**
 * Confirm and apply changes
 */
async function confirmAndApply() {
    const confirmedPreview = previewData;
    closePreviewModal();
    await applyConfiguration(confirmedPreview);
}

/**
 * Apply configuration
 */
async function applyConfiguration(configOverride = null) {
    try {
        const configToApply = configOverride || previewData || getFormData();
        previewData = null;
        
        // Show log modal while applying
        showApplyLog();
        
        addApplyLog('📝 Updating .env configuration...', 'info');
        
        const response = await fetch('/api/env/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(configToApply),
        });
        
        const data = await response.json();
        
        if (data.success) {
            addApplyLog('✅ .env configuration updated', 'success');
            addApplyLog('🔄 Regenerating nginx configuration (generate-nginx-conf.sh)...', 'info');
            addApplyLog('🔍 Validating nginx -t and hot-reloading pt-nginx1...', 'info');
            addApplyLog(data.message || 'Nginx reloaded successfully', 'success');

            previewData = null;

            addApplyLog('🔄 Reloading configuration panel...', 'info');
            await loadConfiguration();
            await loadCertbotStatus();
            addApplyLog('✓ Configuration loaded and applied successfully', 'success');
            addApplyLog('✨ All changes are now active in nginx!', 'success');
            setTimeout(() => closeApplyLog(), 2000);
        } else {
            addApplyLog('❌ Error applying configuration: ' + data.message, 'danger');
        }
    } catch (error) {
        console.error('✗ Error applying configuration:', error);
        addApplyLog('❌ Error applying configuration: ' + error.message, 'danger');
    }
}

/**
 * Reset form to current configuration
 */
function resetForm() {
    if (confirm('Reset all changes to current configuration?')) {
        populateForm(currentConfig);
        showAlert('✓ Form reset to current configuration', 'info');
    }
}

/**
 * Create backup
 */
async function createBackup() {
    try {
        showSpinner('Creating backup...');
        
        const response = await fetch('/api/env/backup', {
            method: 'POST',
        });
        
        const data = await response.json();
        hideSpinner();
        
        if (data.success) {
            showAlert('✅ Backup created successfully!', 'success');
            await loadBackups();
        } else {
            showAlert('❌ Error creating backup: ' + data.message, 'danger');
        }
    } catch (error) {
        hideSpinner();
        console.error('✗ Error creating backup:', error);
        showAlert('❌ Error creating backup: ' + error.message, 'danger');
    }
}

/**
 * Load backups list
 */
async function loadBackups() {
    try {
        const response = await fetch('/api/env/backups');
        
        if (!response.ok) {
            console.warn('⚠ Failed to load backups');
            document.getElementById('backups-list').innerHTML = '<p class="text-muted">Unable to load backups</p>';
            return;
        }
        
        const data = await response.json();
        
        if (data.success && data.backups.length > 0) {
            const backupsList = document.getElementById('backups-list');
            backupsList.innerHTML = '';
            for (const backup of data.backups) {
                const row = document.createElement('div');
                row.style.cssText = 'background: var(--pt-bg); border: 1px solid var(--pt-border); padding: 12px; border-radius: 6px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;';
                row.innerHTML = `
                    <div>
                        <strong>${escapeHtml(backup.timestamp)}</strong>
                        <div style="font-size: 12px; color: var(--pt-text-muted);">${escapeHtml(backup.path)}</div>
                    </div>
                    <button type="button" class="btn btn-sm btn-secondary js-restore-env-backup">
                        Restore
                    </button>
                `;
                row.querySelector('.js-restore-env-backup').addEventListener('click', () => {
                    restoreBackup(backup.path);
                });
                backupsList.appendChild(row);
            }
        } else {
            document.getElementById('backups-list').innerHTML = '<p class="text-muted">No backups available</p>';
        }
    } catch (error) {
        console.error('✗ Error loading backups:', error);
    }
}

/**
 * Restore backup
 */
async function restoreBackup(backupPath) {
    if (!confirm('Restore configuration from this backup? This will overwrite current settings.')) {
        return;
    }
    
    try {
        showSpinner('Restoring backup...');
        
        const response = await fetch('/api/env/restore', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ backup_path: backupPath }),
        });
        
        const data = await response.json();
        hideSpinner();
        
        if (data.success) {
            showAlert('✅ Backup restored successfully!', 'success');
            await loadConfiguration();
        } else {
            showAlert('❌ Error restoring backup: ' + data.message, 'danger');
        }
    } catch (error) {
        hideSpinner();
        console.error('✗ Error restoring backup:', error);
        showAlert('❌ Error restoring backup: ' + error.message, 'danger');
    }
}

/**
 * Update status badge
 */
function updateStatusBadge() {
    let statuses = [];
    
    if (currentConfig.https.enabled) statuses.push('🔒 HTTPS');
    if (currentConfig.geoip.allow_enabled) statuses.push('🌍 GeoIP Allow');
    if (currentConfig.geoip.block_enabled) statuses.push('🚫 GeoIP Block');
    if (currentConfig.rate_limit.enabled) statuses.push('⚡ Rate Limit');
    if (currentConfig.production.mode) statuses.push('☁️ Production');
    
    const badge = document.getElementById('config-status');
    if (statuses.length > 0) {
        badge.className = 'status-badge enabled';
        badge.innerHTML = `<i class="bi bi-circle-fill"></i> ${statuses.join(' • ')}`;
    } else {
        badge.className = 'status-badge disabled';
        badge.innerHTML = '<i class="bi bi-circle"></i> No features enabled';
    }
}

/**
 * Show alert
 */
function showAlert(message, type = 'info') {
    const bsType = type === 'error' ? 'danger' : type;
    const container = document.getElementById('alerts-container');
    const alert = document.createElement('div');
    alert.className = `alert alert-${bsType}`;
    alert.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>${escapeHtml(message)}</div>
            <button type="button" class="btn-close" onclick="this.parentElement.parentElement.remove()"></button>
        </div>
    `;
    container.appendChild(alert);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (alert.parentElement) alert.remove();
    }, 5000);
}

/**
 * Show spinner
 */
function showSpinner(message = 'Loading...') {
    const container = document.getElementById('alerts-container');
    const spinner = document.createElement('div');
    spinner.id = 'loading-spinner';
    spinner.className = 'alert alert-info';
    spinner.innerHTML = `
        <div style="display: flex; gap: 10px; align-items: center;">
            <div class="spinner"></div>
            <div>${escapeHtml(message)}</div>
        </div>
    `;
    container.appendChild(spinner);
}

/**
 * Hide spinner
 */
function hideSpinner() {
    const spinner = document.getElementById('loading-spinner');
    if (spinner) spinner.remove();
}

/**
 * Load SSL certificate and key information
 */
async function loadSSLInfo() {
    try {
        // Load certificate info
        const certResponse = await fetch('/api/upload/info/crt');
        
        if (!certResponse.ok) {
            document.getElementById('cert-info').innerHTML = `
                <div class="alert alert-warning">
                    <strong>⚠ Unable to load certificate info</strong>
                </div>
            `;
        } else {
            const certData = await certResponse.json();
            
            if (certData.success && certData.file_info) {
                const info = certData.file_info;
                document.getElementById('cert-info').innerHTML = `
                    <div class="alert alert-success">
                        <strong>✓ Certificate found:</strong><br>
                        Size: ${(info.size / 1024).toFixed(2)} KB<br>
                        Modified: ${new Date(info.modified).toLocaleString()}
                    </div>
                `;
            } else {
                document.getElementById('cert-info').innerHTML = `
                    <div class="alert alert-warning">
                        <strong>⚠ No certificate found</strong>
                    </div>
                `;
            }
        }
        
        // Load key info
        const keyResponse = await fetch('/api/upload/info/key');
        
        if (!keyResponse.ok) {
            document.getElementById('key-info').innerHTML = `
                <div class="alert alert-warning">
                    <strong>⚠ Unable to load key info</strong>
                </div>
            `;
        } else {
            const keyData = await keyResponse.json();
            
            if (keyData.success && keyData.file_info) {
                const info = keyData.file_info;
                document.getElementById('key-info').innerHTML = `
                    <div class="alert alert-success">
                        <strong>✓ Private key found:</strong><br>
                        Size: ${(info.size / 1024).toFixed(2)} KB<br>
                        Modified: ${new Date(info.modified).toLocaleString()}
                    </div>
                `;
            } else {
                document.getElementById('key-info').innerHTML = `
                    <div class="alert alert-warning">
                        <strong>⚠ No private key found</strong>
                    </div>
                `;
            }
        }
        
        // Load backups
        await loadSSLBackups();
    } catch (error) {
        console.error('✗ Error loading SSL info:', error);
        showAlert('Error loading SSL information', 'danger');
    }
}

/**
 * Load SSL certificate and key backups
 */
async function loadSSLBackups() {
    try {
        const response = await fetch('/api/upload/backups');
        const data = await response.json();
        
        if (data.success && data.backups.length > 0) {
            const backupsList = document.getElementById('ssl-backups-list');
            backupsList.innerHTML = '';
            
            data.backups.forEach(backup => {
                const timestamp = escapeHtml(new Date(backup.modified).toLocaleString());
                const size = escapeHtml((backup.size / 1024).toFixed(2));
                
                const item = document.createElement('div');
                item.className = 'card mb-2';
                item.innerHTML = `
                    <div class="card-body p-3">
                        <div class="d-flex justify-content-between align-items-start">
                            <div>
                                <strong>${escapeHtml(backup.filename)}</strong><br>
                                <small class="text-muted">
                                    ${timestamp} • ${size} KB
                                </small>
                            </div>
                            <div class="btn-group" role="group">
                                <button type="button" class="btn btn-sm btn-primary js-restore-ssl-backup">
                                    <i class="bi bi-arrow-counterclockwise"></i> Restore
                                </button>
                                <button type="button" class="btn btn-sm btn-danger js-delete-ssl-backup">
                                    <i class="bi bi-trash"></i> Delete
                                </button>
                            </div>
                        </div>
                    </div>
                `;
                item.querySelector('.js-restore-ssl-backup').addEventListener('click', () => {
                    restoreSSLBackup(backup.path, backup.type);
                });
                item.querySelector('.js-delete-ssl-backup').addEventListener('click', () => {
                    deleteSSLBackup(backup.path);
                });
                backupsList.appendChild(item);
            });
        } else {
            document.getElementById('ssl-backups-list').innerHTML = `
                <p class="text-muted">No backups available yet</p>
            `;
        }
    } catch (error) {
        console.error('✗ Error loading SSL backups:', error);
    }
}

/**
 * Upload certificate file
 */
async function uploadCertificate() {
    const fileInput = document.getElementById('cert-file');
    const file = fileInput.files[0];
    
    if (!file) {
        showAlert('Please select a certificate file', 'warning');
        return;
    }
    
    await uploadSSLFile(file, 'certificate');
}

/**
 * Upload private key file
 */
async function uploadKey() {
    const fileInput = document.getElementById('key-file');
    const file = fileInput.files[0];
    
    if (!file) {
        showAlert('Please select a private key file', 'warning');
        return;
    }
    
    await uploadSSLFile(file, 'key');
}

/**
 * Generic SSL file upload function
 */
async function uploadSSLFile(file, type) {
    try {
        showSpinner(`Uploading ${type}...`);
        
        const formData = new FormData();
        formData.append('file', file);
        
        const endpoint = type === 'certificate' ? '/api/upload/certificate' : '/api/upload/key';
        
        const response = await fetch(endpoint, {
            method: 'POST',
            body: formData,
        });
        
        hideSpinner();
        const data = await response.json();
        
        if (data.success) {
            if (data.staged && data.pair_matched === false) {
                showAlert(data.warning || data.message || `${type} staged in .pending/ awaiting matching counterpart`, 'warning');
            } else {
                showAlert(data.message || `${type} uploaded and activated`, 'success');
                await loadConfiguration();
                await loadCertbotStatus();
            }
            
            // Clear file input
            document.getElementById(type === 'certificate' ? 'cert-file' : 'key-file').value = '';
            
            // Reload SSL info
            await loadSSLInfo();
        } else {
            showAlert(`Error: ${data.message}`, 'danger');
        }
    } catch (error) {
        hideSpinner();
        console.error(`✗ Error uploading ${type}:`, error);
        showAlert(`Error uploading ${type}`, 'danger');
    }
}

/**
 * Restore SSL backup
 */
async function restoreSSLBackup(backupPath, fileType) {
    try {
        if (!confirm(`Are you sure you want to restore from this ${fileType} backup?`)) {
            return;
        }
        
        showSpinner(`Restoring ${fileType}...`);
        
        const response = await fetch('/api/upload/restore', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                backup_path: backupPath,
                file_type: fileType,
            }),
        });
        
        hideSpinner();
        const data = await response.json();
        
        if (data.success) {
            if (data.staged && data.pair_matched === false) {
                showAlert(data.warning || data.message || `${fileType} staged in .pending/ awaiting matching counterpart`, 'warning');
            } else {
                showAlert(data.message || `${fileType} restored and activated`, 'success');
                await loadConfiguration();
                await loadCertbotStatus();
            }
            await loadSSLInfo();
        } else {
            showAlert(`Error: ${data.message}`, 'danger');
        }
    } catch (error) {
        hideSpinner();
        console.error('✗ Error restoring backup:', error);
        showAlert('Error restoring backup', 'danger');
    }
}

/**
 * Delete SSL backup
 */
async function deleteSSLBackup(backupPath) {
    try {
        if (!confirm('Are you sure you want to delete this backup?')) {
            return;
        }
        
        showSpinner('Deleting backup...');
        
        const response = await fetch('/api/upload/backup/delete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                backup_path: backupPath,
            }),
        });
        
        hideSpinner();
        const data = await response.json();
        
        if (data.success) {
            showAlert('Backup deleted successfully', 'success');
            await loadSSLInfo();
        } else {
            showAlert(`Error: ${data.message}`, 'danger');
        }
    } catch (error) {
        hideSpinner();
        console.error('✗ Error deleting backup:', error);
        showAlert('Error deleting backup', 'danger');
    }
}

/**
 * Log viewer functions for apply configuration
 */

function showApplyLog() {
    const modal = document.getElementById('apply-log-modal');
    const logContent = document.getElementById('apply-log-content');
    logContent.innerHTML = '<div class="log-line log-info">⏳ Applying configuration...</div>';
    modal.style.display = 'flex';
    modal.classList.add('show');
}

function addApplyLog(message, type = 'info') {
    const logContent = document.getElementById('apply-log-content');
    const logLine = document.createElement('div');
    logLine.className = `log-line log-${type}`;
    
    const timestamp = new Date().toLocaleTimeString();
    let icon = '';
    
    switch(type) {
        case 'success': icon = '✅'; break;
        case 'danger': icon = '❌'; break;
        case 'warning': icon = '⚠️'; break;
        case 'info': icon = 'ℹ️'; break;
        default: icon = '📝';
    }
    
    logLine.textContent = `[${timestamp}] ${icon} ${message}`;
    logContent.appendChild(logLine);
    
    // Auto-scroll to bottom
    logContent.scrollTop = logContent.scrollHeight;
}

function closeApplyLog() {
    const modal = document.getElementById('apply-log-modal');
    modal.classList.remove('show');
    setTimeout(() => {
        modal.style.display = 'none';
    }, 300);
}

/**
 * Nginx Console Functions
 */

async function loadNginxLogs() {
    try {
        const response = await fetch('/api/containers/pt-nginx1/logs?tail=200');
        
        if (!response.ok) {
            console.warn('⚠ Failed to fetch nginx logs');
            document.getElementById('nginx-console').textContent = 'Failed to load nginx logs. Please check container status.';
            return;
        }
        
        const data = await response.json();
        
        if (data.success && data.logs) {
            document.getElementById('nginx-console').textContent = data.logs;
            nginxLastLogLength = data.logs.length;
            // Auto-scroll to bottom
            const console = document.getElementById('nginx-console');
            console.scrollTop = console.scrollHeight;
        } else {
            document.getElementById('nginx-console').textContent = 'No logs available';
        }
    } catch (error) {
        console.error('✗ Error loading nginx logs:', error);
        document.getElementById('nginx-console').textContent = 'Error loading logs: ' + error.message;
    }
}

function clearNginxLogs() {
    document.getElementById('nginx-console').textContent = '';
    nginxLastLogLength = 0;
}

function toggleNginxAutoRefresh() {
    const autoRefreshCheckbox = document.getElementById('nginx-auto-refresh');
    
    if (autoRefreshCheckbox.checked) {
        // Start auto-refresh
        loadNginxLogs(); // Load immediately
        nginxAutoRefreshInterval = setInterval(loadNginxLogs, 5000);
        console.log('✓ Nginx auto-refresh enabled (5s interval)');
    } else {
        // Stop auto-refresh
        if (nginxAutoRefreshInterval) {
            clearInterval(nginxAutoRefreshInterval);
            nginxAutoRefreshInterval = null;
        }
        console.log('✗ Nginx auto-refresh disabled');
    }
}

// Load and display nginx configuration
async function loadNginxConfig() {
    try {
        const response = await fetch('/api/env/nginx-config');
        
        if (!response.ok) {
            console.warn('⚠ Failed to fetch nginx config');
            document.getElementById('nginx-config').textContent = 'Failed to load nginx configuration. Please check container status.';
            document.getElementById('main-config-path').textContent = 'N/A';
            return;
        }
        
        const data = await response.json();
        
        if (data.success && data.config) {
            document.getElementById('nginx-config').textContent = data.config;
            document.getElementById('main-config-path').textContent = data.config_path || '/etc/nginx/nginx.conf';
            // Auto-scroll to top
            const configDiv = document.getElementById('nginx-config');
            configDiv.scrollTop = 0;
        } else {
            document.getElementById('nginx-config').textContent = 'No configuration available';
            document.getElementById('main-config-path').textContent = 'N/A';
        }
    } catch (error) {
        console.error('✗ Error loading nginx config:', error);
        document.getElementById('nginx-config').textContent = 'Error loading config: ' + error.message;
        document.getElementById('main-config-path').textContent = 'Error';
    }
}

function copyNginxConfig() {
    const configText = document.getElementById('nginx-config').textContent;
    
    navigator.clipboard.writeText(configText).then(() => {
        const status = document.getElementById('copy-status');
        status.style.display = 'inline';
        setTimeout(() => {
            status.style.display = 'none';
        }, 2000);
        console.log('✓ Nginx config copied to clipboard');
    }).catch(error => {
        console.error('✗ Failed to copy config:', error);
        alert('Failed to copy configuration to clipboard');
    });
}

// Load nginx logs when tab is clicked
document.addEventListener('DOMContentLoaded', function() {
    // Add event listener for nginx console tab
    const nginxTab = document.getElementById('nginx-console-tab');
    if (nginxTab) {
        nginxTab.addEventListener('click', function() {
            setTimeout(() => loadNginxLogs(), 100);
        });
    }

    // Add event listener for nginx config tab
    const nginxConfigTab = document.getElementById('nginx-config-tab');
    if (nginxConfigTab) {
        nginxConfigTab.addEventListener('click', function() {
            setTimeout(() => loadNginxConfig(), 100);
        });
    }

    // Add event listener for lockout tab
    const lockoutTab = document.getElementById('lockout-tab');
    if (lockoutTab) {
        lockoutTab.addEventListener('click', function() {
            setTimeout(() => loadLockedUsers(), 100);
        });
    }

    // Add event listener for Certbot tab
    const certbotTab = document.getElementById('certbot-tab');
    if (certbotTab) {
        certbotTab.addEventListener('click', function() {
            setTimeout(() => loadCertbotStatus(), 100);
        });
    }
});

// ========================================================================
// User Lockout Management Functions
// ========================================================================

let lockoutAutoRefreshInterval = null;

/**
 * Load and display locked users from the API
 */
function loadLockedUsers() {
    console.log('📋 Loading locked users...');
    
    fetch('/api/env/users/locked', {
        headers: {
            'Accept': 'application/json'
        }
    })
    .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    })
    .then(data => {
        if (data.success) {
            displayLockedUsers(data.locked_users);
            console.log(`✓ Loaded ${data.count} locked users`);
        } else {
            showAlert('Failed to load locked users: ' + data.message, 'danger');
        }
    })
    .catch(error => {
        console.error('✗ Error loading locked users:', error);
        showAlert('Error loading locked users: ' + error.message, 'danger');
    });
}

/**
 * Display locked users in the table
 */
function displayLockedUsers(users) {
    const tbody = document.getElementById('locked-users-tbody');
    const emptyState = document.getElementById('empty-state');
    const unlockAllBtn = document.getElementById('unlock-all-btn');
    const resetAllBtn = document.getElementById('reset-all-btn');
    
    if (!users || users.length === 0) {
        tbody.innerHTML = '';
        emptyState.style.display = 'block';
        unlockAllBtn.style.display = 'none';
        resetAllBtn.style.display = 'none';
        return;
    }
    
    emptyState.style.display = 'none';
    unlockAllBtn.style.display = 'inline-block';
    resetAllBtn.style.display = 'inline-block';
    
    tbody.innerHTML = '';
    for (const user of users) {
        const lockedUntil = user.locked_until 
            ? new Date(user.locked_until).toLocaleString() 
            : '-';
        const lastFailed = user.last_failed_login
            ? new Date(user.last_failed_login).toLocaleString()
            : '-';
        
        const isCurrentlyLocked = user.locked === 1;
        const status = isCurrentlyLocked 
            ? '<span class="badge bg-danger">Locked</span>'
            : '<span class="badge bg-warning">Temporary</span>';
        
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>
                <input type="checkbox" class="user-checkbox" value="${escapeHtml(user.user_id)}">
            </td>
            <td><strong>${escapeHtml(user.username)}</strong></td>
            <td>${escapeHtml(user.failed_attempts || 0)}</td>
            <td><small>${escapeHtml(lastFailed)}</small></td>
            <td><small>${escapeHtml(lockedUntil)}</small></td>
            <td>${status}</td>
            <td>
                <button type="button" class="btn btn-sm btn-primary js-unlock-user">
                    <i class="bi bi-unlock"></i> Unlock
                </button>
            </td>
        `;
        tr.querySelector('.js-unlock-user').addEventListener('click', () => {
            unlockUser(user.user_id, user.username);
        });
        tbody.appendChild(tr);
    }
}

/**
 * Unlock a single user
 */
function unlockUser(userId, username) {
    if (!confirm(`Unlock user "${username}"?`)) return;
    
    console.log(`🔓 Unlocking user ${userId}...`);
    
    fetch('/api/env/users/unlock', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        },
        body: JSON.stringify({
            user_id: userId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert(`✓ User "${username}" has been unlocked`, 'success');
            loadLockedUsers();
        } else {
            showAlert(`✗ Failed to unlock user: ${data.message}`, 'danger');
        }
    })
    .catch(error => {
        console.error('✗ Error unlocking user:', error);
        showAlert(`Error: ${error.message}`, 'danger');
    });
}

/**
 * Unlock all selected users
 */
function unlockAllUsers() {
    const checkboxes = document.querySelectorAll('.user-checkbox:checked');
    if (checkboxes.length === 0) {
        alert('Please select at least one user');
        return;
    }
    
    const userIds = Array.from(checkboxes).map(cb => parseInt(cb.value));
    
    if (!confirm(`Unlock ${userIds.length} selected user(s)?`)) return;
    
    console.log(`🔓 Unlocking ${userIds.length} users...`);
    
    fetch('/api/env/users/unlock', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        },
        body: JSON.stringify({
            user_ids: userIds
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert(`✓ ${data.message}`, 'success');
            loadLockedUsers();
        } else {
            showAlert(`✗ ${data.message}`, 'warning');
            loadLockedUsers();
        }
    })
    .catch(error => {
        console.error('✗ Error unlocking users:', error);
        showAlert(`Error: ${error.message}`, 'danger');
    });
}

/**
 * Reset failed attempts for all selected users
 */
function resetAllAttempts() {
    const checkboxes = document.querySelectorAll('.user-checkbox:checked');
    if (checkboxes.length === 0) {
        alert('Please select at least one user');
        return;
    }
    
    const userIds = Array.from(checkboxes).map(cb => parseInt(cb.value));
    
    if (!confirm(`Reset failed attempts for ${userIds.length} selected user(s)?`)) return;
    
    console.log(`↻ Resetting attempts for ${userIds.length} users...`);
    
    fetch('/api/env/users/reset-attempts', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        },
        body: JSON.stringify({
            user_ids: userIds
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert(`✓ ${data.message}`, 'success');
            loadLockedUsers();
        } else {
            showAlert(`✗ ${data.message}`, 'warning');
            loadLockedUsers();
        }
    })
    .catch(error => {
        console.error('✗ Error resetting attempts:', error);
        showAlert(`Error: ${error.message}`, 'danger');
    });
}

/**
 * Toggle selection of all users
 */
function toggleSelectAllUsers() {
    const selectAll = document.getElementById('select-all-users');
    const checkboxes = document.querySelectorAll('.user-checkbox');
    checkboxes.forEach(cb => cb.checked = selectAll.checked);
}
window.toggleAllUserSelection = toggleSelectAllUsers;

/**
 * Toggle auto-refresh for locked users
 */
function toggleLockoutAutoRefresh() {
    const checkbox = document.getElementById('lockout-auto-refresh');
    
    if (checkbox.checked) {
        console.log('🔄 Enabling auto-refresh for locked users (5s)');
        lockoutAutoRefreshInterval = setInterval(() => {
            loadLockedUsers();
        }, 5000);
    } else {
        console.log('⏹ Disabling auto-refresh for locked users');
        if (lockoutAutoRefreshInterval) {
            clearInterval(lockoutAutoRefreshInterval);
            lockoutAutoRefreshInterval = null;
        }
    }
}

/**
 * Escape HTML special characters (null-safe)
 */
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}

// ========================================================================
// Certbot / Let's Encrypt TLS Management Functions
// ========================================================================

function setCertbotBusy(busy) {
    const buttons = document.querySelectorAll('.certbot-action-btn, #certbot-save-btn, #btn-mode-self-signed, #btn-mode-manual, #btn-mode-certbot');
    buttons.forEach(btn => {
        btn.disabled = Boolean(busy);
    });
}

function setCertbotTerminalOutput(text) {
    const out = document.getElementById('certbot-terminal-output');
    if (out) {
        out.textContent = text || '';
        out.scrollTop = out.scrollHeight;
    }
}

async function loadCertbotStatus() {
    try {
        const response = await fetch('/api/certbot/status', {
            headers: { 'Accept': 'application/json' },
        });
        if (!response.ok) {
            console.warn('⚠ Failed to load Certbot status:', response.status);
            return;
        }
        const data = await response.json();
        if (data.success) {
            renderCertbotStatus(data);
        }
    } catch (error) {
        console.error('✗ Error loading Certbot status:', error);
    }
}

function renderCertbotStatus(data) {
    const tlsMode = data.tls_mode || 'self-signed';

    // Update mode badges across panels
    const httpsModeBadge = document.getElementById('https-tls-mode-badge');
    if (httpsModeBadge) {
        httpsModeBadge.textContent = `Mode: ${tlsMode}`;
    }
    const certbotModeBadge = document.getElementById('certbot-mode-badge');
    if (certbotModeBadge) {
        certbotModeBadge.textContent = `TLS Mode: ${tlsMode}`;
    }
    const sslModeLabel = document.getElementById('ssl-panel-mode-label');
    if (sslModeLabel) {
        sslModeLabel.textContent = tlsMode;
    }

    // Container status badge
    const containerBadge = document.getElementById('certbot-container-badge');
    if (containerBadge && data.container) {
        const running = Boolean(data.container.running);
        containerBadge.className = running
            ? 'badge bg-success-subtle text-success border border-success-subtle'
            : 'badge bg-danger-subtle text-danger border border-danger-subtle';
        containerBadge.textContent = `${data.container.name || 'pt-certbot'}: ${data.container.status || (running ? 'running' : 'stopped')}`;
    }

    // Mode switcher active state
    const modeBtns = {
        'self-signed': document.getElementById('btn-mode-self-signed'),
        'manual': document.getElementById('btn-mode-manual'),
        'certbot': document.getElementById('btn-mode-certbot'),
    };
    Object.entries(modeBtns).forEach(([mode, btn]) => {
        if (!btn) return;
        if (mode === tlsMode) {
            btn.className = 'btn btn-sm btn-primary active';
        } else {
            btn.className = 'btn btn-sm btn-outline-secondary';
        }
    });

    // Active certificate metadata card
    const cert = data.certificate || {};
    const sourceEl = document.getElementById('cert-status-source');
    if (sourceEl) {
        const sourceLabels = {
            'self-signed': ['Self-Signed', 'badge bg-warning-subtle text-warning border border-warning-subtle'],
            'manual': ['Manual Upload', 'badge bg-info-subtle text-info border border-info-subtle'],
            'letsencrypt-staging': ["Let's Encrypt Staging", 'badge bg-warning-subtle text-warning border border-warning-subtle'],
            'letsencrypt': ["Let's Encrypt Production", 'badge bg-success-subtle text-success border border-success-subtle'],
        };
        const [label, cls] = sourceLabels[cert.source] || [cert.source || 'Unknown', 'badge bg-secondary-subtle text-secondary border'];
        sourceEl.className = cls;
        sourceEl.textContent = label;
    }

    const daysEl = document.getElementById('cert-status-days');
    if (daysEl) {
        if (cert.exists && typeof cert.days_remaining === 'number') {
            daysEl.textContent = `${cert.days_remaining} days left`;
            if (cert.days_remaining <= 7) {
                daysEl.className = 'badge bg-danger-subtle text-danger border border-danger-subtle';
            } else if (cert.days_remaining <= 30) {
                daysEl.className = 'badge bg-warning-subtle text-warning border border-warning-subtle';
            } else {
                daysEl.className = 'badge bg-success-subtle text-success border border-success-subtle';
            }
        } else {
            daysEl.className = 'badge bg-secondary-subtle text-secondary border';
            daysEl.textContent = cert.exists ? '-- days' : 'Missing';
        }
    }

    const pairEl = document.getElementById('cert-status-pair-match');
    if (pairEl) {
        if (cert.exists && cert.pair_matched) {
            pairEl.className = 'badge bg-success-subtle text-success border border-success-subtle';
            pairEl.textContent = 'Pair: Matched';
        } else {
            pairEl.className = 'badge bg-danger-subtle text-danger border border-danger-subtle';
            pairEl.textContent = cert.exists ? 'Pair: Mismatch' : 'Pair: Missing';
        }
    }

    const subjEl = document.getElementById('cert-status-subject');
    if (subjEl) subjEl.innerHTML = escapeHtml(cert.subject || '(none)');

    const issEl = document.getElementById('cert-status-issuer');
    if (issEl) issEl.innerHTML = escapeHtml(cert.issuer || '(none)');

    const sansEl = document.getElementById('cert-status-sans');
    if (sansEl) {
        const sansText = Array.isArray(cert.sans) && cert.sans.length > 0 ? cert.sans.join(', ') : '(none)';
        sansEl.innerHTML = escapeHtml(sansText);
    }

    const valEl = document.getElementById('cert-status-validity');
    if (valEl) {
        const valText = cert.exists ? `${cert.not_before || '?'} → ${cert.not_after || '?'}` : '--';
        valEl.innerHTML = escapeHtml(valText);
    }

    const pathEl = document.getElementById('cert-status-path');
    if (pathEl) pathEl.innerHTML = escapeHtml(data.ssl_cert_path || cert.path || '--');

    const renewalEl = document.getElementById('cert-status-renewal');
    if (renewalEl && data.renewal) {
        const r = data.renewal;
        const parts = [
            r.next_check_note || '',
            r.renewal_configs_present ? 'Renewal config present.' : 'No renewal config yet.',
            r.last_run_status ? `Last run: ${r.last_run_status}` : '',
        ].filter(Boolean);
        renewalEl.innerHTML = escapeHtml(parts.join(' '));
    }

    // Populate Certbot config form
    const cb = data.certbot || {};
    const cbEnabled = document.getElementById('certbot-enabled');
    if (cbEnabled) cbEnabled.checked = Boolean(cb.enabled);

    const cbDomain = document.getElementById('certbot-domain');
    if (cbDomain) cbDomain.value = cb.domain || '';

    const cbExtra = document.getElementById('certbot-extra-domains');
    if (cbExtra) cbExtra.value = cb.extra_domains || '';

    const cbEmail = document.getElementById('certbot-email');
    if (cbEmail) cbEmail.value = cb.email || '';

    const cbChallenge = document.getElementById('certbot-challenge-type');
    if (cbChallenge) cbChallenge.value = cb.challenge_type || 'http-01';

    const cbStaging = document.getElementById('certbot-staging');
    if (cbStaging) cbStaging.checked = Boolean(cb.staging);

    const cbAutoRenew = document.getElementById('certbot-auto-renew');
    if (cbAutoRenew) cbAutoRenew.checked = cb.auto_renew !== false;
}

async function saveCertbotConfig() {
    const payload = {
        enabled: document.getElementById('certbot-enabled').checked,
        domain: document.getElementById('certbot-domain').value.trim(),
        extra_domains: document.getElementById('certbot-extra-domains').value.trim(),
        email: document.getElementById('certbot-email').value.trim(),
        challenge_type: document.getElementById('certbot-challenge-type').value,
        staging: document.getElementById('certbot-staging').checked,
        auto_renew: document.getElementById('certbot-auto-renew').checked,
    };

    try {
        setCertbotBusy(true);
        showSpinner('Saving Certbot configuration...');
        const response = await fetch('/api/certbot/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            body: JSON.stringify(payload),
        });
        hideSpinner();
        const data = await response.json();
        if (response.ok && data.success) {
            showAlert(data.message || 'Certbot configuration saved', 'success');
            await loadCertbotStatus();
            await loadConfiguration();
        } else {
            showAlert(data.message || 'Failed to save Certbot configuration', 'danger');
        }
    } catch (error) {
        hideSpinner();
        console.error('✗ Error saving Certbot config:', error);
        showAlert('Error saving Certbot configuration: ' + error.message, 'danger');
    } finally {
        setCertbotBusy(false);
    }
}

async function issueCertbot(dryRun = false) {
    const staging = document.getElementById('certbot-staging').checked;
    if (!dryRun && !confirm(`Issue a ${staging ? 'STAGING' : 'PRODUCTION'} Let's Encrypt certificate for the configured domain?`)) {
        return;
    }

    try {
        setCertbotBusy(true);
        setCertbotTerminalOutput(`Running certbot certonly (${dryRun ? 'dry-run' : (staging ? 'staging' : 'production')})...`);
        const response = await fetch('/api/certbot/issue', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            body: JSON.stringify({
                dry_run: Boolean(dryRun),
                staging: Boolean(staging),
            }),
        });
        const data = await response.json();
        const output = data.output || [data.stdout, data.stderr, data.message].filter(Boolean).join('\n');
        setCertbotTerminalOutput(output || 'Completed.');

        if (response.status === 409) {
            showAlert(data.message || 'Another certificate operation is currently in progress', 'warning');
        } else if (response.ok && data.success) {
            showAlert(data.message || 'Certbot operation completed', 'success');
            if (!dryRun) {
                await loadCertbotStatus();
                await loadConfiguration();
                await loadSSLInfo();
            }
        } else {
            showAlert(data.message || 'Certbot issuance failed', 'danger');
        }
    } catch (error) {
        console.error('✗ Error running Certbot issue:', error);
        setCertbotTerminalOutput('Error: ' + error.message);
        showAlert('Error running Certbot issue: ' + error.message, 'danger');
    } finally {
        setCertbotBusy(false);
    }
}

async function renewCertbot(dryRun = false, forceRenewal = false) {
    if (!dryRun && forceRenewal && !confirm('Force-renew all Let\'s Encrypt certificates now?')) {
        return;
    }

    try {
        setCertbotBusy(true);
        setCertbotTerminalOutput(`Running certbot renew${dryRun ? ' --dry-run' : ''}${forceRenewal ? ' --force-renewal' : ''}...`);
        const response = await fetch('/api/certbot/renew', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            body: JSON.stringify({
                dry_run: Boolean(dryRun),
                force_renewal: Boolean(forceRenewal),
            }),
        });
        const data = await response.json();
        const output = data.output || [data.stdout, data.stderr, data.message].filter(Boolean).join('\n');
        setCertbotTerminalOutput(output || 'Completed.');

        if (response.status === 409) {
            showAlert(data.message || 'Another certificate operation is currently in progress', 'warning');
        } else if (response.ok && data.success) {
            showAlert(data.message || 'Certbot renewal completed', 'success');
            if (!dryRun) {
                await loadCertbotStatus();
                await loadConfiguration();
            }
        } else {
            showAlert(data.message || 'Certbot renewal failed', 'danger');
        }
    } catch (error) {
        console.error('✗ Error running Certbot renew:', error);
        setCertbotTerminalOutput('Error: ' + error.message);
        showAlert('Error running Certbot renew: ' + error.message, 'danger');
    } finally {
        setCertbotBusy(false);
    }
}

async function switchTlsMode(mode) {
    if (!confirm(`Switch active TLS mode to "${mode}" and reload Nginx?`)) {
        return;
    }

    try {
        setCertbotBusy(true);
        showSpinner(`Switching TLS mode to ${mode}...`);
        const response = await fetch('/api/certbot/switch-mode', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            body: JSON.stringify({ tls_mode: mode }),
        });
        hideSpinner();
        const data = await response.json();

        if (response.status === 409) {
            showAlert(data.message || 'Another certificate operation is currently in progress', 'warning');
        } else if (response.ok && data.success) {
            showAlert(data.message || `Switched TLS mode to ${mode}`, 'success');
            await loadCertbotStatus();
            await loadConfiguration();
            await loadSSLInfo();
        } else {
            showAlert(data.message || `Failed to switch TLS mode to ${mode}`, 'danger');
        }
    } catch (error) {
        hideSpinner();
        console.error('✗ Error switching TLS mode:', error);
        showAlert('Error switching TLS mode: ' + error.message, 'danger');
    } finally {
        setCertbotBusy(false);
    }
}