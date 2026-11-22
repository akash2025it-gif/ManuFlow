/**
 * ManuFlow — Manufacturing & Order Management System
 * Client-Side Utility & UX Interactivity Script
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Auto-dismiss standard alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) {
                bsAlert.close();
            }
        }, 5000);
    });

    // 2. Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));

    // 3. Double-submit guard for forms with [data-submit-once]
    document.querySelectorAll('form[data-submit-once]').forEach(form => {
        form.addEventListener('submit', function() {
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                const originalHtml = submitBtn.innerHTML;
                submitBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Processing...`;
                // Re-enable after 8 seconds in case validation fails client-side
                setTimeout(() => {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalHtml;
                }, 8000);
            }
        });
    });

    // 4. Desktop Sidebar Collapse Toggle & State Persistence
    const sidebarToggleBtn = document.getElementById('sidebarToggleBtn');
    if (sidebarToggleBtn) {
        if (localStorage.getItem('mf_sidebar_collapsed') === '1') {
            document.body.classList.add('mf-sidebar-collapsed');
        }
        sidebarToggleBtn.addEventListener('click', () => {
            document.body.classList.toggle('mf-sidebar-collapsed');
            const isCollapsed = document.body.classList.contains('mf-sidebar-collapsed');
            localStorage.setItem('mf_sidebar_collapsed', isCollapsed ? '1' : '0');
        });
    }

    // 5. Client-Side Data Table Search / Quick Filter
    document.querySelectorAll('[data-table-filter]').forEach(filterInput => {
        const targetSelector = filterInput.getAttribute('data-table-filter');
        const targetTable = document.querySelector(targetSelector);
        if (!targetTable) return;

        filterInput.addEventListener('input', function() {
            const query = this.value.toLowerCase().trim();
            const rows = targetTable.querySelectorAll('tbody tr');
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(query) ? '' : 'none';
            });
        });
    });

    // 6. Confirm Dialog Helper for Destructive Actions
    document.querySelectorAll('[data-confirm]').forEach(el => {
        el.addEventListener('click', function(e) {
            const message = this.getAttribute('data-confirm') || 'Are you sure you want to proceed?';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
});

/**
 * Helper to auto-fill demo credentials on the login screen
 */
function fillDemoCredentials(email, password) {
    const usernameInput = document.getElementById('id_username');
    const passwordInput = document.getElementById('id_password');
    if (usernameInput && passwordInput) {
        usernameInput.value = email;
        passwordInput.value = password;
        usernameInput.focus();
    }
}

/**
 * Toggle password field visibility between 'password' and 'text'
 */
function togglePasswordVisibility(inputId, btnEl) {
    const input = document.getElementById(inputId);
    if (!input) return;

    const icon = btnEl ? btnEl.querySelector('i') : null;
    if (input.type === 'password') {
        input.type = 'text';
        if (icon) {
            icon.classList.remove('bi-eye');
            icon.classList.add('bi-eye-slash');
        }
        if (btnEl) btnEl.setAttribute('aria-label', 'Hide password');
    } else {
        input.type = 'password';
        if (icon) {
            icon.classList.remove('bi-eye-slash');
            icon.classList.add('bi-eye');
        }
        if (btnEl) btnEl.setAttribute('aria-label', 'Show password');
    }
}

// 5. Back-Forward Cache (bfcache) Guard
// Ensures authenticated pages cannot be restored from browser back cache after logout
window.addEventListener('pageshow', (event) => {
    if (event.persisted) {
        window.location.reload();
    }
});

/**
 * 1-Click One-Touch Demo Sign In
 * Fills demo credentials and submits the authentication form immediately
 */
function oneClickDemoLogin(email = 'demo@manuflow.app', password = 'ManuFlow@Demo2026!') {
    fillDemoCredentials(email, password);
    const form = document.querySelector('form[action*="login"]');
    if (form) {
        form.submit();
    }
}
