const { test, expect } = require('@playwright/test');

test('login password can always be shown and hidden without changing its value', async ({ page }) => {
  await page.goto('/accounts/login/');
  const password = page.locator('#id_password');
  await password.fill('VisibilityCheck!2026');
  const toggle = password.locator('xpath=..').locator('.password-toggle-btn');
  await expect(toggle).toBeVisible();
  await expect(password).toHaveAttribute('type', 'password');
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await toggle.click();
  await expect(password).toHaveAttribute('type', 'text');
  await expect(password).toHaveValue('VisibilityCheck!2026');
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await toggle.click();
  await expect(password).toHaveAttribute('type', 'password');
  await expect(password).toHaveValue('VisibilityCheck!2026');
});

test('registration exposes independent show/hide controls for both password fields', async ({ page }) => {
  await page.goto('/accounts/register/');
  const first = page.locator('#id_password1');
  const second = page.locator('#id_password2');
  await first.fill('VisibilityCheck!2026');
  await second.fill('VisibilityCheck!2026');
  const firstToggle = first.locator('xpath=..').locator('.password-toggle-btn');
  const secondToggle = second.locator('xpath=..').locator('.password-toggle-btn');
  await expect(firstToggle).toBeVisible();
  await expect(secondToggle).toBeVisible();
  await firstToggle.click();
  await expect(first).toHaveAttribute('type', 'text');
  await expect(second).toHaveAttribute('type', 'password');
  await secondToggle.click();
  await expect(second).toHaveAttribute('type', 'text');
  await firstToggle.click();
  await secondToggle.click();
  await expect(first).toHaveAttribute('type', 'password');
  await expect(second).toHaveAttribute('type', 'password');
  await expect(first).toHaveValue('VisibilityCheck!2026');
  await expect(second).toHaveValue('VisibilityCheck!2026');
});

test('IBTIKAR signup requires complete details and preserves supervisor email', async ({ page }, testInfo) => {
  await page.goto('/accounts/register/');
  const academic = ['student_level', 'laboratory', 'supervisor', 'supervisor_email', 'ibtikar_id'];
  const extra = ['phone', 'wilaya', 'gender'];
  for (const field of [...academic, ...extra]) {
    await expect(page.locator('#id_' + field)).toHaveAttribute('required', '');
  }
  await page.locator('.role-option').filter({ has: page.locator('input[value="CLIENT"]') }).click();
  for (const field of academic) await expect(page.locator('#id_' + field)).toBeDisabled();
  for (const field of extra) await expect(page.locator('#id_' + field)).not.toHaveAttribute('required', '');
  await page.locator('.role-option').filter({ has: page.locator('input[value="REQUESTER"]') }).click();
  const suffix = `${testInfo.project.name}-${Date.now()}`;
  const fields = {
    first_name: 'Amine', last_name: 'Test', username: `signup-${suffix}`,
    email: `signup-${suffix}@example.test`, organization: 'Université de test',
    laboratory: 'Laboratoire de test', supervisor: 'Encadrant Test',
    supervisor_email: 'supervisor@example.test', ibtikar_id: 'IDGRSTD12345',
    phone: '0554050460', password1: 'DifferentPass!2026', password2: 'DifferentPass!2026',
  };
  for (const [field, value] of Object.entries(fields)) await page.locator('#id_' + field).fill(value);
  await page.locator('#id_organization_type').selectOption('academique');
  await page.locator('#id_country').selectOption('DZ');
  await page.locator('#id_student_level').selectOption('doctorat');
  await page.locator('#id_wilaya').selectOption('31');
  await page.locator('#id_gender').selectOption('M');
  await page.locator('#id_supervisor_email').fill('invalid');
  expect(await page.locator('#id_supervisor_email').evaluate(el => el.checkValidity())).toBe(false);
  await page.locator('#id_supervisor_email').fill(fields.supervisor_email);
  await page.locator('form[method="post"] button[type="submit"]').last().click();
  await expect(page).toHaveURL(/\/dashboard\//);
  await page.goto('/accounts/profile/');
  await expect(page.locator('main')).toContainText(fields.supervisor_email);
});
