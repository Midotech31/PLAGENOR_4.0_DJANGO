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
  await page.locator('button[name="language"][value="fr"]').click();
  await expect(page.locator('html')).toHaveAttribute('lang', /^fr/);
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

for (const [name, path] of [
  ['financial settings', '/dashboard/ops/financial-settings/'],
  ['email templates', '/dashboard/ops/email-templates/'],
]) {
  test(`Admin Ops can manage ${name} with accessible controls`, async ({ page }) => {
    await login(page, 'admin_ops');
    await page.goto(path);
    await expect(page.locator('main h1')).toBeVisible();
    await expectAccessible(page, name);
  });
}

test('OHB is assigned internally and goes from quote to invoice without VAT', async ({ page }) => {
  await login(page, 'admin_ops');
  const fixture = await page.request.post('/__e2e__/financial-request/');
  expect(fixture.status()).toBe(200);
  const { id } = await fixture.json();
  await page.goto(`/dashboard/ops/request/${id}/`);
  await page.locator('[name="billing_channel"]').selectOption('OHB');
  await page.locator('form').filter({ has: page.locator('[name="billing_channel"]') }).getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await page.goto(`/dashboard/ops/quote/${id}/`);
  await expect(page.locator('#vat_rate_input')).toHaveValue('0');
  await expect(page.locator('#vat_rate_input')).toHaveAttribute('readonly', '');
  await page.getByRole('button', { name: /Ajouter une ligne/ }).click();
  await page.locator('.line-item-row').first().getByRole('button', { name: 'Supprimer', exact: true }).click();
  await expect(page.locator('#item_label_0')).toHaveCount(1);
  await expect(page.locator('#item_label_1')).toHaveCount(0);
  await page.locator('[name="item_label_0"]').fill('Prestation de recette');
  await page.locator('[name="item_unit_price_0"]').fill('123.45');
  await page.locator('[name="item_quantity_0"]').fill('2');
  await expect(page.locator('#total_ttc')).toContainText('246.90');
  await page.locator('button[name="action"][value="send"]').click();
  await expect(page).toHaveURL(new RegExp(`/dashboard/ops/request/${id}/`));
  await expect(page.locator('[name="billing_channel"]')).toHaveCount(0);
  await login(page, 'client');
  await page.goto(`/dashboard/client/request/${id}/`);
  await expect(page.locator('[name="billing_channel"]')).toHaveCount(0);
  await expect(page.locator('main')).not.toContainText('Opérations Hors Budget');
  await page.locator('form[action$="/accept/"] button').click();
  await page.locator('[name="order_file"]').setInputFiles({ name: 'order.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\n% Synthetic purchase order for CI\n%%EOF') });
  await page.locator('form').filter({ has: page.locator('[name="order_file"]') }).locator('button[type="submit"]').click();
  await login(page, 'admin_ops');
  await page.goto(`/dashboard/ops/request/${id}/`);
  await page.locator(`form[action="/dashboard/ops/invoice/${id}/"] button`).click();
  await expect(page.locator('main')).toContainText('ESSBO-INV');
  await login(page, 'client');
  await page.goto(`/dashboard/client/request/${id}/`);
  await expect(page.locator('[name="payment_order_reference"]')).toBeVisible();
  await expect(page.locator('[name="billing_channel"]')).toHaveCount(0);
});
