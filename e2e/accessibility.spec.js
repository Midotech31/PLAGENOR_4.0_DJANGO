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

for (const [lang, phrase] of [['fr', 'étudiants algériens'], ['en', 'Algerian students'], ['ar', 'الطلبة الجزائريين']]) {
  test(`IBTIKAR national scope is published in ${lang}`, async ({page}, testInfo) => {
    await page.goto('/');
    await page.locator(`button[name="language"][value="${lang}"]`).first().click();
    await expect(page.locator('main')).toContainText(phrase);
    await expect(page.locator('main')).not.toContainText("Canal dédié aux étudiants et chercheurs de l'ESSBO");
    await expectAccessible(page, `IBTIKAR ${lang}`);
    await page.screenshot({path: testInfo.outputPath(`home-${lang}.png`), fullPage:true});
  });
}

test('Ops can open the catalogue and financial visibility controls', async ({page}, testInfo) => {
  await login(page, 'admin_ops');
  await page.goto('/dashboard/ops/services/');
  await expect(page.locator('main')).toContainText(/Prestations et tarifs|Services and pricing/);
  await expectAccessible(page, 'Ops catalogue');
  await page.goto('/dashboard/ops/financial-visibility/');
  await expect(page.locator('[name="show_estimates"]')).toBeVisible();
  await expectAccessible(page, 'Estimate visibility');
  await page.screenshot({path:testInfo.outputPath('visibility.png'), fullPage:true});
});

for (const [lang, name, option, heading] of [
  ['fr', 'Contrôle qualité des acides nucléiques', 'Simple', 'Vérification de la demande'],
  ['ar', 'مراقبة جودة الأحماض النووية', 'مفرد', 'مراجعة الطلب'],
  ['en', 'Nucleic Acid Quality Control', 'Single', 'Review your request'],
]) {
  test(`catalogue, service form and request preview are translated in ${lang}`, async ({page}, testInfo) => {
    await page.goto('/services/');
    await page.locator(`button[name="language"][value="${lang}"]`).first().click();
    await expect(page.locator('main')).toContainText(name);
    await expectAccessible(page, `service catalogue ${lang}`);
    await page.screenshot({path:testInfo.outputPath(`services-${lang}.png`), fullPage:true});
    const fragment = await page.request.get('/dashboard/api/service-form/EGTP-IMT/');
    expect(await fragment.text()).toMatch(new RegExp(`value="Simple"[^>]*>${option}</option>`));
    await login(page, 'client');
    // Account preferences may override an anonymous visitor's locale.
    await page.locator(`button[name="language"][value="${lang}"]`).first().click();
    await page.goto('/dashboard/client/?tab=new');
    await page.locator('[name="title"]').fill('<img src=x onerror="window.previewInjected=true">');
    await page.locator('[onclick*="showFormPreview"]').click();
    await expect(page.locator('#form-preview-overlay h2')).toHaveText(heading);
    await expect(page.locator('#form-preview-overlay')).toContainText('<img src=x');
    await expect(page.locator('#form-preview-overlay img')).toHaveCount(0);
    expect(await page.evaluate(() => window.previewInjected)).toBeUndefined();
  });
}

test('new service form exposes six required language fields from the start', async ({page}) => {
  await login(page, 'admin');
  for (const lang of ['fr', 'ar', 'en']) {
    for (const field of ['name', 'description']) {
      await expect(page.locator(`[name="${field}_${lang}"]`).first()).toHaveAttribute('required', '');
    }
  }
});
