const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const wcagTags = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

async function expectAccessible(page, context) {
  const results = await new AxeBuilder({ page }).withTags(wcagTags).analyze();
  const summary = results.violations.map(({ id, impact, nodes }) => ({
    id,
    impact,
    targets: nodes.map((node) => node.target.join(' ')),
  }));
  expect(summary, `${context}: ${JSON.stringify(summary, null, 2)}`).toEqual([]);
}

async function login(page, username) {
  const response = await page.request.post(`/__e2e__/session/${username}/`);
  expect(response.status()).toBe(204);
  await page.goto('/dashboard/');
  await expect(page).toHaveURL(/\/dashboard\//);
}

const publicPages = [
  ['home', '/'],
  ['services', '/services/'],
  ['about', '/about/'],
  ['contact', '/contact/'],
  ['help', '/help/'],
  ['tracking', '/track/'],
  ['login', '/accounts/login/'],
  ['registration', '/accounts/register/'],
  ['password reset', '/accounts/password-reset/'],
  ['privacy', '/confidentialite/'],
];

for (const [name, path] of publicPages) {
  test(`public ${name} has no automated WCAG 2.2 AA violations`, async ({ page }) => {
    await page.goto(path);
    await expect(page.locator('main')).toBeVisible();
    await expectAccessible(page, `public ${name}`);
  });
}

const roleAccounts = [
  ['superadmin', 'admin', /\/dashboard\/home\//],
  ['platform admin', 'admin_ops', /\/dashboard\/ops\//],
  ['analyst', 'analyst', /\/dashboard\/analyst\//],
  ['finance', 'finance', /\/dashboard\/finance\//],
  ['requester', 'amina', /\/dashboard\/requester\//],
  ['client', 'client', /\/dashboard\/client\//],
];

for (const [role, username, target] of roleAccounts) {
  test(`${role} dashboard is routed correctly and accessible`, async ({ page }) => {
    await login(page, username);
    await expect(page).toHaveURL(target);
    await expect(page.locator('main')).toBeVisible();
    await expectAccessible(page, `${role} dashboard`);
  });
}

test('Arabic locale activates RTL and remains accessible', async ({ page }) => {
  await page.goto('/accounts/login/');
  await page.locator('button[name="language"][value="ar"]').click();
  await expect(page.locator('html')).toHaveAttribute('lang', /^ar/);
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expectAccessible(page, 'Arabic login');
});

test('English locale remains LTR and accessible', async ({ page }) => {
  await page.goto('/accounts/login/');
  await page.locator('button[name="language"][value="en"]').click();
  await expect(page.locator('html')).toHaveAttribute('lang', /^en/);
  await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
  await expectAccessible(page, 'English login');
});

test('skip link provides keyboard access to main content', async ({ page }) => {
  await page.goto('/');
  await page.keyboard.press('Tab');
  const skipLink = page.locator('.skip-link');
  await expect(skipLink).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#main-content$/);
});

test('non-superadmin cannot open the superadmin dashboard', async ({ page }) => {
  await login(page, 'admin_ops');
  // Firefox treats an intentionally empty 403 document as a network error.
  // The context-bound request client carries the authenticated cookies and
  // lets us assert the authorization contract directly across all engines.
  const response = await page.request.get('/dashboard/home/');
  expect(response.status()).toBe(403);
});
