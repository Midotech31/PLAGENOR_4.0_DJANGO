/**
 * PLAGENOR 4.0 - Comprehensive Form Validation Module
 * Handles mandatory fields, format checks, email uniqueness, and success feedback
 */

(function() {
    'use strict';

    // Configuration
    const CONFIG = {
        emailRegex: /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/,
        dateRegex: /^\d{2}\/\d{2}\/\d{4}$/,
        phoneRegex: /^[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}$/,
        toastDuration: 4000,
        debounceDelay: 500
    };

    // Translations
    const TRANSLATIONS = {
        fr: {
            requiredField: 'Ce champ est obligatoire',
            invalidEmail: 'Format d\'email invalide',
            invalidDate: 'Format de date invalide (JJ/MM/AAAA attendu)',
            invalidPhone: 'Format de téléphone invalide',
            emailExists: 'Cet email est déjà enregistré',
            fillRequired: 'Veuillez remplir tous les champs obligatoires',
            formSuccess: 'Formulaire soumis avec succès',
            checking: 'Vérification en cours...',
            copied: 'Copié !'
        },
        en: {
            requiredField: 'This field is required',
            invalidEmail: 'Invalid email format',
            invalidDate: 'Invalid date format (DD/MM/YYYY expected)',
            invalidPhone: 'Invalid phone format',
            emailExists: 'This email is already registered',
            fillRequired: 'Please fill all required fields',
            formSuccess: 'Form submitted successfully',
            checking: 'Checking...',
            copied: 'Copied!'
        }
    };

    // Get current language
    function getCurrentLanguage() {
        const htmlLang = document.documentElement.lang;
        return htmlLang && htmlLang.startsWith('en') ? 'en' : 'fr';
    }

    // Get translation
    function t(key) {
        const lang = getCurrentLanguage();
        return TRANSLATIONS[lang][key] || TRANSLATIONS['fr'][key];
    }

    // Toast notification system
    function showToast(message, type = 'success') {
        const existingToasts = document.querySelectorAll('.plagenor-toast');
        existingToasts.forEach(toast => toast.remove());

        const toast = document.createElement('div');
        toast.className = `plagenor-toast plagenor-toast-${type}`;
        toast.innerHTML = `
            <div class="toast-content">
                <span class="toast-icon">${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span>
                <span class="toast-message">${message}</span>
            </div>
        `;
        document.body.appendChild(toast);

        setTimeout(() => toast.classList.add('show'), 10);
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, CONFIG.toastDuration);
    }

    // Create error message element
    function createErrorElement(message) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'form-error';
        errorDiv.textContent = message;
        return errorDiv;
    }

    // Clear error for a field
    function clearError(field) {
        const existingError = field.parentElement.querySelector('.form-error');
        if (existingError) {
            existingError.remove();
        }
        field.classList.remove('is-invalid');
    }

    // Show error for a field
    function showError(field, message) {
        clearError(field);
        field.classList.add('is-invalid');
        const errorDiv = createErrorElement(message);
        field.parentElement.appendChild(errorDiv);
    }

    // Validate required field
    function validateRequired(field) {
        if (!field.hasAttribute('required')) return true;
        
        const value = field.value.trim();
        if (!value) {
            showError(field, t('requiredField'));
            return false;
        }
        clearError(field);
        return true;
    }

    // Validate email format
    function validateEmailFormat(field) {
        if (field.type !== 'email' && !field.name.includes('email')) return true;
        
        const value = field.value.trim();
        if (value && !CONFIG.emailRegex.test(value)) {
            showError(field, t('invalidEmail'));
            return false;
        }
        return true;
    }

    // Validate date format (DD/MM/YYYY)
    // type="date" inputs are handled natively by the browser (value is YYYY-MM-DD) — skip them
    function validateDateFormat(field) {
        if (field.type === 'date') return true;  // browser validates natively
        if (!field.name.toLowerCase().includes('date')) return true;
        
        const value = field.value.trim();
        if (value && !CONFIG.dateRegex.test(value)) {
            showError(field, t('invalidDate'));
            return false;
        }
        return true;
    }

    // Validate phone format
    function validatePhoneFormat(field) {
        if (field.type !== 'tel' && !field.name.includes('phone')) return true;
        
        const value = field.value.trim();
        if (value && !CONFIG.phoneRegex.test(value)) {
            showError(field, t('invalidPhone'));
            return false;
        }
        return true;
    }

    // Check email uniqueness via AJAX
    let emailCheckTimeout = null;
    function checkEmailUniqueness(field) {
        if (!field.name.includes('email')) return Promise.resolve(true);
        
        const value = field.value.trim();
        if (!value || !CONFIG.emailRegex.test(value)) return Promise.resolve(true);

        return new Promise((resolve) => {
            if (emailCheckTimeout) clearTimeout(emailCheckTimeout);
            
            emailCheckTimeout = setTimeout(() => {
                const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
                
                fetch('/accounts/check-email/', {  // This will be resolved by Django URL routing
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ email: value })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.exists) {
                        showError(field, t('emailExists'));
                        resolve(false);
                    } else {
                        clearError(field);
                        resolve(true);
                    }
                })
                .catch(() => {
                    resolve(true);
                });
            }, CONFIG.debounceDelay);
        });
    }

    // Validate entire form
    async function validateForm(form) {
        let isValid = true;
        const fields = form.querySelectorAll('input, select, textarea');

        for (const field of fields) {
            if (field.type === 'hidden' || field.disabled) continue;

            const requiredValid = validateRequired(field);
            const emailValid = validateEmailFormat(field);
            const dateValid = validateDateFormat(field);
            const phoneValid = validatePhoneFormat(field);
            
            if (!requiredValid || !emailValid || !dateValid || !phoneValid) {
                isValid = false;
            }
        }

        // Check email uniqueness
        const emailFields = form.querySelectorAll('input[name*="email"], input[type="email"]');
        for (const emailField of emailFields) {
            const unique = await checkEmailUniqueness(emailField);
            if (!unique) {
                isValid = false;
            }
        }

        return isValid;
    }

    // Wrap submit button for tooltip support
    function ensureSubmitWrapper(submitBtn) {
        if (submitBtn.parentElement.classList.contains('submit-btn-wrapper')) return;
        const wrapper = document.createElement('span');
        wrapper.className = 'submit-btn-wrapper';
        submitBtn.parentElement.insertBefore(wrapper, submitBtn);
        wrapper.appendChild(submitBtn);
    }

    // Update submit button state
    function updateSubmitButton(form) {
        const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
        if (!submitBtn) return;

        ensureSubmitWrapper(submitBtn);
        const wrapper = submitBtn.parentElement;

        const fields = form.querySelectorAll('input[required], select[required], textarea[required]');
        let allFilled = true;

        fields.forEach(field => {
            if (field.type === 'hidden' || field.disabled) return;
            const val = field.type === 'checkbox' ? field.checked : field.value.trim();
            if (!val) {
                allFilled = false;
            }
        });

        if (!allFilled) {
            submitBtn.disabled = true;
            submitBtn.style.opacity = '0.5';
            submitBtn.style.cursor = 'not-allowed';
            submitBtn.title = '';
            wrapper.setAttribute('data-tooltip', t('fillRequired'));
        } else {
            submitBtn.disabled = false;
            submitBtn.style.opacity = '1';
            submitBtn.style.cursor = 'pointer';
            submitBtn.title = '';
            wrapper.removeAttribute('data-tooltip');
        }
    }

    // Initialize form validation
    function initFormValidation(form) {
        if (!form || form.dataset.validationInitialized) return;
        form.dataset.validationInitialized = 'true';

        const fields = form.querySelectorAll('input, select, textarea');

        // Add red asterisk to required field labels
        fields.forEach(field => {
            if (field.hasAttribute('required') && field.type !== 'hidden') {
                const label = form.querySelector(`label[for="${field.id}"]`);
                if (label && !label.querySelector('.required-asterisk')) {
                    const asterisk = document.createElement('span');
                    asterisk.className = 'required-asterisk';
                    asterisk.textContent = ' *';
                    asterisk.style.color = '#dc2626';
                    asterisk.style.fontWeight = 'bold';
                    label.appendChild(asterisk);
                }
            }
        });

        // Real-time validation on blur
        fields.forEach(field => {
            field.addEventListener('blur', function() {
                validateRequired(this);
                validateEmailFormat(this);
                validateDateFormat(this);
                validatePhoneFormat(this);
                
                if (this.name.includes('email') || this.type === 'email') {
                    checkEmailUniqueness(this);
                }
            });

            field.addEventListener('input', function() {
                updateSubmitButton(form);
                if (this.classList.contains('is-invalid')) {
                    clearError(this);
                }
            });
        });

        // Form submit validation
        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const isValid = await validateForm(form);
            
            if (!isValid) {
                showToast(t('fillRequired'), 'error');
                const firstError = form.querySelector('.is-invalid');
                if (firstError) {
                    firstError.focus();
                    firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
                return false;
            }

            // Show success toast only if form has show-success class
            if (form.classList.contains('show-success')) {
                showToast(t('formSuccess'), 'success');
            }

            // Submit the form after a brief delay
            setTimeout(() => {
                form.submit();
            }, 500);
        });

        // Initial button state
        updateSubmitButton(form);
    }

    // Initialize on DOM ready
    document.addEventListener('DOMContentLoaded', function() {
        const forms = document.querySelectorAll('form');
        forms.forEach(form => {
            if (!form.classList.contains('no-validation')) {
                initFormValidation(form);
            }
        });
    });

    // Expose globally
    window.PlagenorValidation = {
        validateForm,
        showToast,
        showError,
        clearError,
        t
    };

})();
