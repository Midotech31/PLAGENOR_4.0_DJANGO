(function () {
    'use strict';

    const WRAPPER_CLASS = 'password-input-wrapper';
    const BUTTON_CLASS = 'password-toggle-btn';
    const ENHANCED = 'passwordVisibilityEnhanced';

    const eyeIcon = [
        '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">',
        '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>',
        '<circle cx="12" cy="12" r="3"></circle>',
        '</svg>'
    ].join('');

    const eyeOffIcon = [
        '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">',
        '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"></path>',
        '<path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"></path>',
        '<path d="M14.12 14.12A3 3 0 0 1 9.88 9.88"></path>',
        '<line x1="1" y1="1" x2="23" y2="23"></line>',
        '</svg>'
    ].join('');

    function translatedLabel() {
        const htmlLabel = document.documentElement.dataset.passwordToggleLabel;
        if (htmlLabel) {
            return htmlLabel;
        }
        if (typeof window.gettext === 'function') {
            return window.gettext('Afficher/masquer le mot de passe');
        }
        return 'Afficher/masquer le mot de passe';
    }

    function syncButton(input, button) {
        const visible = input.type === 'text';
        button.setAttribute('aria-pressed', visible ? 'true' : 'false');
        button.setAttribute('aria-label', translatedLabel());
        button.setAttribute('title', translatedLabel());
        button.innerHTML = visible ? eyeOffIcon : eyeIcon;
    }

    function toggle(input, button) {
        const start = input.selectionStart;
        const end = input.selectionEnd;
        input.type = input.type === 'password' ? 'text' : 'password';
        syncButton(input, button);
        input.focus({ preventScroll: true });
        if (typeof start === 'number' && typeof end === 'number') {
            try {
                input.setSelectionRange(start, end);
            } catch (error) {
                // Some input implementations do not expose a selection range.
            }
        }
    }

    function enhance(input) {
        if (!(input instanceof HTMLInputElement) || input.dataset[ENHANCED] === 'true') {
            return;
        }
        if (input.type !== 'password') {
            return;
        }

        let wrapper = input.parentElement;
        if (!wrapper || !wrapper.classList.contains(WRAPPER_CLASS)) {
            wrapper = document.createElement('span');
            wrapper.className = WRAPPER_CLASS;
            input.parentNode.insertBefore(wrapper, input);
            wrapper.appendChild(input);
        }

        let button = wrapper.querySelector(':scope > .' + BUTTON_CLASS);
        if (!button) {
            button = document.createElement('button');
            button.type = 'button';
            button.className = BUTTON_CLASS;
            wrapper.appendChild(button);
        }

        button.removeAttribute('onclick');
        input.dataset[ENHANCED] = 'true';
        button.dataset.passwordToggle = 'true';
        button.addEventListener('click', function () {
            toggle(input, button);
        });
        syncButton(input, button);
    }

    function enhanceWithin(root) {
        if (!root || !root.querySelectorAll) {
            return;
        }
        if (root instanceof HTMLInputElement && root.type === 'password') {
            enhance(root);
        }
        root.querySelectorAll('input[type="password"]').forEach(enhance);
    }

    function init() {
        enhanceWithin(document);
        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        enhanceWithin(node);
                    }
                });
            });
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})();
