/* PLAGENOR 4.0 — Main JS */

// HTMX: include CSRF token in all requests
document.body.addEventListener('htmx:configRequest', (e) => {
    e.detail.headers['X-CSRFToken'] =
        document.querySelector('[name=csrfmiddlewaretoken]')?.value
        || document.cookie.match(/csrftoken=([^;]+)/)?.[1]
        || '';
});

// Notification badge refresh
function refreshNotificationCount() {
    fetch('/dashboard/api/notification-count/')
        .then(r => r.json())
        .then(data => {
            const badge = document.getElementById('notification-count');
            if (badge) {
                badge.textContent = data.count;
                badge.style.display = data.count > 0 ? 'flex' : 'none';
            }
        })
        .catch(() => {});
}

setInterval(refreshNotificationCount, 30000);

// Language toggle
function toggleLanguage() {
    const form = document.getElementById('language-form');
    if (!form) return;
    const input = form.querySelector('[name=language]');
    input.value = input.value === 'fr' ? 'en' : 'fr';
    form.submit();
}

// Mobile sidebar toggle
function toggleSidebar() {
    document.querySelector('.sidebar')?.classList.toggle('open');
}

// Close sidebar on overlay click (mobile)
document.addEventListener('click', (e) => {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar?.classList.contains('open') && !sidebar.contains(e.target) && !e.target.closest('.topbar-hamburger')) {
        sidebar.classList.remove('open');
    }
});

// Dynamic service form loading
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('select[name="service_id"]').forEach(function(select) {
        select.addEventListener('change', function() {
            var serviceId = this.value;
            var container = document.getElementById('dynamic-service-form');
            if (!container) return;
            if (!serviceId) { container.innerHTML = ''; return; }
            var option = this.options[this.selectedIndex];
            var code = option.getAttribute('data-code') || '';
            if (code) {
                fetch('/dashboard/api/service-form/' + code + '/')
                    .then(function(r) { return r.text(); })
                    .then(function(html) { container.innerHTML = html; })
                    .catch(function() { container.innerHTML = ''; });
            }
        });
    });
});

// Role selector (registration page)
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.role-option').forEach(option => {
        option.addEventListener('click', () => {
            document.querySelectorAll('.role-option').forEach(o => o.classList.remove('selected'));
            option.classList.add('selected');
            option.querySelector('input[type=radio]').checked = true;
        });
    });
});
