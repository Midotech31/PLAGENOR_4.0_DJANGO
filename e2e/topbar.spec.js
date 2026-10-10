const {test, expect} = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

for (const username of ['admin', 'admin_ops']) {
  for (const lang of ['fr', 'en', 'ar']) {
    test(`${username} menus open and close under production CSP in ${lang}`, async ({page}, testInfo) => {
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      expect((await page.request.post(`/__e2e__/session/${username}/`)).status()).toBe(204);
      const response = await page.goto('/dashboard/');
      expect(response.headers()['content-security-policy']).toContain("script-src 'self' 'unsafe-inline'");
      expect(response.headers()['content-security-policy']).not.toContain('unsafe-eval');
      expect(response.headers()['content-security-policy-report-only']).toBeUndefined();
      await page.locator(`.topbar button[name="language"][value="${lang}"]`).click();

      const bell = page.locator('.topbar-bell');
      const avatar = page.locator('.topbar-avatar-btn');
      const notifications = page.locator('.notif-dropdown');
      const profile = page.locator('.profile-dropdown');
      await expect(notifications).toBeHidden();
      await expect(profile).toBeHidden();

      for (const [button, panel] of [[bell, notifications], [avatar, profile]]) {
        await expect(button).toHaveAttribute('aria-expanded', 'false');
        await button.click();
        await expect(panel).toBeVisible();
        await expect(button).toHaveAttribute('aria-expanded', 'true');
        const bounds = await panel.boundingBox();
        expect(bounds.x).toBeGreaterThanOrEqual(0);
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(page.viewportSize().width);
        await button.click();
        await expect(panel).toBeHidden();
        await expect(button).toHaveAttribute('aria-expanded', 'false');
        await button.focus();
        await button.click();
        await expect(panel).toBeVisible();
        const tabStops = await panel.locator('a[href], button').count() + 1;
        for (let step = 0; step < tabStops && await panel.isVisible(); step++) {
          await page.keyboard.press('Tab');
        }
        await expect(panel).toBeHidden();
        await button.focus();
        await page.keyboard.press('Enter');
        await expect(panel).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(panel).toBeHidden();
        await expect(button).toBeFocused();
        await page.keyboard.press('Space');
        await expect(panel).toBeVisible();
        await page.locator('#main-content').click({position: {x: 10, y: 10}});
        await expect(panel).toBeHidden();
      }

      await bell.click();
      await avatar.click();
      await expect(notifications).toBeHidden();
      await expect(bell).toHaveAttribute('aria-expanded', 'false');
      await expect(profile).toBeVisible();
      const violations = await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
      expect(violations.violations.map(v => ({id: v.id, targets: v.nodes.map(n => n.target)}))).toEqual([]);
      await bell.click();
      await expect(profile).toBeHidden();
      await expect(notifications).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(notifications).toBeHidden();
      await expect(bell).toBeFocused();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({path: testInfo.outputPath(`menus-${username}-${lang}.png`), fullPage: false});
      expect(errors).toEqual([]);
    });
  }
}

test('menus stay hidden if the component bundle cannot load', async ({page}) => {
  expect((await page.request.post('/__e2e__/session/admin/')).status()).toBe(204);
  await page.route('**/static/vendor/alpine-*.min.js', route => route.abort());
  await page.goto('/dashboard/home/');
  await expect(page.locator('.topbar-bell')).toBeVisible();
  await expect(page.locator('.topbar-avatar-btn')).toBeVisible();
  await expect(page.locator('.notif-dropdown')).toBeHidden();
  await expect(page.locator('.profile-dropdown')).toBeHidden();
  await expect(page.locator('.topbar-bell')).toHaveAttribute('aria-expanded', 'false');
  await expect(page.locator('.topbar-avatar-btn')).toHaveAttribute('aria-expanded', 'false');
});

test('every role can select its dashboard tabs under enforced CSP', async ({page}) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const roles = [
    ['admin', '/dashboard/home/', 'content', 'overview'],
    ['admin_ops', '/dashboard/ops/', 'reports', 'pending'],
    ['analyst', '/dashboard/analyst/', 'profile', 'pending'],
    ['finance', '/dashboard/finance/', 'budget', 'validation'],
    ['amina', '/dashboard/requester/', 'archives', 'requests'],
    ['client', '/dashboard/client/', 'invoices', 'requests'],
  ];
  for (const [username, path, selected, fallback] of roles) {
    expect((await page.request.post(`/__e2e__/session/${username}/`)).status()).toBe(204);
    await page.goto(path + '?tab=' + selected);
    const root = page.locator('[x-data^="dashboardTabs("]');
    await expect(root.locator(`[x-show="tab === '${selected}'"]`).first()).toBeVisible();
    await expect(root.locator('.tab-item.active')).toHaveCount(1);
    const firstPanel = root.locator(':scope > [x-show]').first();
    // Settle the validation layout when leaving an autofocused empty field.
    const firstTab = root.locator('.tab-item').first();
    await firstTab.focus();
    await firstTab.click();
    await expect(firstPanel).toBeVisible();
    await page.goto(path + '?tab=absent_test');
    await expect(page.locator(`[x-show="tab === '${fallback}'"]`).first()).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test('CMS filtering accepts quotes, backticks and Arabic without executing content', async ({page}, testInfo) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  expect((await page.request.post('/__e2e__/session/admin/')).status()).toBe(204);
  await page.goto('/dashboard/home/?tab=content');
  await page.locator('.topbar button[name="language"][value="fr"]').click();
  await page.goto('/dashboard/home/?tab=content');
  const root = page.locator('[x-data*="editingKey"]');
  await root.locator('.card-header button').first().click();
  const form = root.locator('form').filter({has: page.locator('input[name="key"]:not([type="hidden"])')});
  const key = 'csp_search_' + testInfo.project.name.replace(/\W/g, '_') + '_' + Date.now();
  const value = 'Texte CSP ` " العربية <img src=x onerror="window.cmsInjected=true">';
  await form.locator('[name="key"]').fill(key);
  await form.locator('[name="value_fr"]').fill(value);
  await Promise.all([page.waitForNavigation(), form.locator('button[type="submit"]').click()]);
  const row = page.locator('tr[data-search-text]').filter({hasText: key});
  const filter = page.locator('input[x-model="filter"]');
  await filter.fill('العربية');
  await expect(row).toBeVisible();
  await filter.fill('` "');
  await expect(row).toBeVisible();
  await filter.fill('does_not_exist_' + key);
  await expect(row).toBeHidden();
  await filter.fill(key);
  await expect(row).toBeVisible();
  await expect(page.locator('#main-content img[src="x"]')).toHaveCount(0);
  expect(await page.evaluate(() => window.cmsInjected)).toBeUndefined();
  expect(errors).toEqual([]);
});
