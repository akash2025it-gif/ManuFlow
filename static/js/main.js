/**
 * NIT Trichy Order-to-Audit Management System - Foundation Script
 */

document.addEventListener('DOMContentLoaded', () => {
    // Auto-dismiss standard alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) {
                bsAlert.close();
            }
        }, 5000);
    });

    // Initialize tooltips if any
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
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
