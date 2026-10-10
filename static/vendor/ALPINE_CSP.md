# Alpine CSP bundle

`alpine-csp-3.17.4.min.js` is the unmodified `dist/cdn.min.js` from the published
`@alpinejs/csp@3.17.4` npm package, licensed under MIT (see `ALPINE_LICENSE.md`).
It replaces the standard Alpine evaluator, which requires `unsafe-eval` and
cannot execute under PLAGENOR's enforced production content security policy.
The bundle is served locally; no frontend request to an external CDN is added.

- Upstream: https://github.com/alpinejs/alpine/tree/v3.17.4/packages/csp
- Documentation: https://alpinejs.dev/advanced/csp
- npm integrity: `sha512-SlRXmqO6kYhnxlg+99etmuzJtE9Lk4QbKjBHqerXzaMflJqoJXdz/SI3IvHJGZ/vRVyC3bR0SSBz40oY7goBeg==`
- Bundle SHA-256: `0d18d7f8d7910e2e0212f0f056b12f50bebc3abb7d88d2f7c7cb4c336fe4519a`

Complex application expressions live in `static/js/alpine-components.js`.
Dashboard tab selection validates the query against panels rendered for the
current role. CMS search reads escaped DOM data rather than template literals.
`plagenor/settings_e2e.py` enforces the production CSP in every browser test.
