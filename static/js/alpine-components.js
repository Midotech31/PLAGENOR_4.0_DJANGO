/* Components use ordinary functions, compatible with the no-eval CSP build. */
document.addEventListener('alpine:init', function () {
    Alpine.data('dashboardTabs', function (defaultTab) {
        return {
            tab: defaultTab,
            init() {
                const requested = new URLSearchParams(window.location.search).get('tab');
                // Only a tab actually rendered for this role may be selected.
                const matches = Array.from(this.$root.children).some(function (panel) {
                    return panel.getAttribute('x-show') === "tab === '" + requested + "'";
                });
                this.tab = matches ? requested : defaultTab;
            },
        };
    });

    Alpine.data('topbarMenus', function () {
        return {
            openMenu: null,
            toggleMenu(menu) {
                this.openMenu = this.openMenu === menu ? null : menu;
            },
            closeMenu(menu) {
                if (this.openMenu === menu) this.openMenu = null;
            },
            closeOnFocusLeave(event, menu) {
                if (!event.currentTarget.contains(event.relatedTarget)) this.closeMenu(menu);
            },
            dismissMenu(event) {
                if (!this.openMenu) return;
                const button = this.$root.querySelector('[data-topbar-menu="' + this.openMenu + '"]');
                this.openMenu = null;
                event.preventDefault();
                event.stopPropagation();
                if (button) button.focus();
            },
        };
    });
});
