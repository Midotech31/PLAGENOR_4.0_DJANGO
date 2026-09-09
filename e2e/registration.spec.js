const { test, expect } = require('@playwright/test');

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
