const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

async function controlFor(page, input) {
  const id = await input.getAttribute('id');
  expect(id).toBeTruthy();
  const button = page.locator('button[aria-controls="' + id + '"]');
  await expect(button).toHaveCount(1);
  await expect(button).toBeVisible();
  await expect(button).toHaveAttribute('type', 'button');
  await expect(button).toHaveAttribute('aria-label', /\S/);
  await expect(button).toHaveAttribute('aria-pressed', 'false');
  return button;
}

test('login password visibility preserves its value and works repeatedly from the keyboard', async ({ page }) => {
  await page.goto('/accounts/login/');
  await expect(page.locator('#id_username')).toHaveAttribute('autocomplete', 'username');
  const input = page.locator('#id_password');
  await expect(input).toHaveAttribute('autocomplete', 'current-password');
  await input.fill('VisibilityCheck!2026');
  const button = await controlFor(page, input);
  await button.focus();
  await page.keyboard.press('Space');
  await expect(input).toHaveAttribute('type', 'text');
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  await expect(button).toBeFocused();
  await page.keyboard.press('Space');
  await expect(input).toHaveAttribute('type', 'password');
  await expect(input).toHaveValue('VisibilityCheck!2026');
  await expect(button).toHaveAttribute('aria-pressed', 'false');
  await expect(page).toHaveURL(/\/accounts\/login\/$/);
});

test('registration password controls are independent and accessible', async ({ page }) => {
  await page.goto('/accounts/register/');
  const first = page.locator('#id_password1');
  const second = page.locator('#id_password2');
  for (const input of [first, second]) {
    await expect(input).toHaveAttribute('autocomplete', 'new-password');
    await input.fill('VisibilityCheck!2026');
  }
  const firstButton = await controlFor(page, first);
  const secondButton = await controlFor(page, second);
  await firstButton.click();
  await expect(first).toHaveAttribute('type', 'text');
  await expect(second).toHaveAttribute('type', 'password');
  await secondButton.click();
  await expect(second).toHaveAttribute('type', 'text');
  await firstButton.click();
  await secondButton.click();
  for (const input of [first, second]) {
    await expect(input).toHaveAttribute('type', 'password');
    await expect(input).toHaveValue('VisibilityCheck!2026');
  }
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
  expect(result.violations.map(v => v.id)).toEqual([]);
});

test('admin account creation and editing share the password controls', async ({ page }) => {
  expect((await page.request.post('/__e2e__/session/admin/')).status()).toBe(204);
  await page.goto('/dashboard/home/?tab=users&user_q=admin');
  const create = page.locator('form[action="/dashboard/home/user/create/"]');
  await create.evaluate(form => form.closest('.card').querySelector('.card-header button').click());
  const input = create.locator('[name="password"]');
  await expect(input).toHaveAttribute('autocomplete', 'new-password');
  await input.fill('NewAccountPassword!2026');
  const button = await controlFor(page, input);
  await button.click();
  await expect(input).toHaveAttribute('type', 'text');
  await button.click();
  await expect(input).toHaveValue('NewAccountPassword!2026');
  const editUrl = await page.locator('tr:visible a[href$="/edit/"]').first().getAttribute('href');
  await page.goto(editUrl);
  const replacement = page.locator('[name="new_password"]');
  await expect(replacement).toHaveAttribute('autocomplete', 'new-password');
  await replacement.fill('ReplacementPassword!2026');
  await (await controlFor(page, replacement)).click();
  await expect(replacement).toHaveAttribute('type', 'text');
  await expect(replacement).toHaveValue('ReplacementPassword!2026');
});

test('Arabic dynamic password fields gain one localized control with unique IDs', async ({ page, context }) => {
  await context.addCookies([{ name: 'django_language', value: 'ar', url: 'http://127.0.0.1:8001' }]);
  await page.goto('/accounts/register/');
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  const label = await page.locator('html').getAttribute('data-password-toggle-label');
  expect(label).toMatch(/[\u0600-\u06ff]/);
  await page.evaluate(() => {
    const collision = document.createElement('span');
    collision.id = 'password-visibility-1';
    const input = document.createElement('input');
    input.type = 'password';
    input.name = 'dynamic-password';
    input.className = 'form-control';
    input.autocomplete = 'new-password';
    document.querySelector('main').append(input, collision);
  });
  const input = page.locator('[name="dynamic-password"]');
  await expect(input).toHaveAttribute('id', /password-visibility-/);
  expect(await input.getAttribute('id')).not.toBe('password-visibility-1');
  const button = await controlFor(page, input);
  await expect(button).toHaveAttribute('aria-label', label);
  await input.fill('DynamicPassword!2026');
  await button.click();
  await expect(input).toHaveAttribute('type', 'text');
  await page.evaluate(() => document.querySelector('main').appendChild(document.createElement('div')));
  await button.click();
  await expect(input).toHaveAttribute('type', 'password');
  await expect(input).toHaveValue('DynamicPassword!2026');
  await expect(input.locator('xpath=..').locator('.password-toggle-btn')).toHaveCount(1);
  const inputBox = await input.boundingBox();
  const buttonBox = await button.boundingBox();
  expect(buttonBox.x).toBeLessThan(inputBox.x + inputBox.width / 2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
