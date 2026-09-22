const { test, expect } = require('@playwright/test');

async function asAdmin(page) {
  const response = await page.request.post('/__e2e__/session/admin/');
  expect(response.status()).toBe(204);
}
async function clickAndSettle(button, page) {
  await button.click();
  await page.waitForLoadState('domcontentloaded');
}

test('techniques and payment methods persist through reloads', async ({ page }) => {
  await asAdmin(page);
  await page.goto('/dashboard/home/?tab=techniques');
  const create = page.locator('form[action="/dashboard/home/technique/create/"]');
  await create.locator('[name="name"]').fill('Technique CMS navigateur');
  await create.locator('[name="category"]').fill('Validation persistance');
  await clickAndSettle(create.locator('button[type="submit"]'), page);
  await page.goto('/dashboard/home/?tab=techniques');
  let row = page.locator('tr').filter({ hasText: 'Technique CMS navigateur' });
  await expect(row).toHaveCount(1);
  await row.getByRole('button', { name: 'Modifier' }).click();
  const edit = row.locator('form[action$="/edit/"]');
  await edit.locator('[name="name"]').fill('Technique CMS navigateur modifiée');
  await edit.locator('[name="category"]').fill('Catégorie persistée');
  await clickAndSettle(edit.locator('button[type="submit"]'), page);
  await page.goto('/dashboard/home/?tab=techniques');
  row = page.locator('tr').filter({ hasText: 'Technique CMS navigateur modifiée' });
  await expect(row).toContainText('Catégorie persistée');
  await clickAndSettle(row.locator('form[action$="/delete/"] button'), page);
  await page.goto('/dashboard/home/?tab=techniques');
  row = page.locator('tr').filter({ hasText: 'Technique CMS navigateur modifiée' });
  await expect(row).toContainText('Inactive');
  await clickAndSettle(row.locator('form[action$="/reactivate/"] button'), page);
  await page.goto('/dashboard/home/?tab=techniques');
  await expect(page.locator('tr').filter({ hasText: 'Technique CMS navigateur modifiée' })).toContainText('Active');

  await page.goto('/dashboard/home/?tab=payments');
  const payment = page.locator('form[action="/dashboard/home/payment-method/create/"]');
  await payment.locator('[name="name"]').fill('Virement CMS navigateur');
  await clickAndSettle(payment.locator('button[type="submit"]'), page);
  await page.goto('/dashboard/home/?tab=payments');
  await expect(page.locator('main')).toContainText('Virement CMS navigateur');
  await payment.locator('[name="name"]').fill('Virement CMS navigateur');
  await clickAndSettle(payment.locator('button[type="submit"]'), page);
  await expect(page.locator('main')).toContainText(/existe/i);
});

test('announcements create toggle and delete persist', async ({ page }) => {
  await asAdmin(page);
  await page.goto('/dashboard/home/?tab=system');
  const form = page.locator('form[action="/dashboard/home/announcement/create/"]');
  await form.locator('[name="title"]').fill('Annonce CMS navigateur');
  await form.locator('[name="message"]').fill('Message de persistance navigateur');
  await form.locator('[name="level"]').selectOption('info');
  await form.locator('[name="audience"]').selectOption('ALL');
  await clickAndSettle(form.locator('button[type="submit"]'), page);
  await page.goto('/dashboard/home/?tab=system');
  let row = page.locator('tr').filter({ hasText: 'Annonce CMS navigateur' });
  await expect(row).toContainText('Message de persistance navigateur');
  await clickAndSettle(row.locator('form[action$="/toggle/"] button'), page);
  await page.goto('/dashboard/home/?tab=system');
  row = page.locator('tr').filter({ hasText: 'Annonce CMS navigateur' });
  await expect(row).toContainText('Non');
  await clickAndSettle(row.locator('form[action$="/delete/"] button'), page);
  await page.goto('/dashboard/home/?tab=system');
  await expect(page.locator('tr').filter({ hasText: 'Annonce CMS navigateur' })).toHaveCount(0);
});

test('financial visibility persists after a new admin session', async ({ page, context }) => {
  await asAdmin(page);
  await page.goto('/dashboard/ops/financial-visibility/');
  let form = page.locator('main form');
  await form.locator('[name="show_estimates"]').check();
  await form.locator('[name="valid_until"]').fill('2030-12-31');
  await clickAndSettle(form.locator('button[type="submit"]'), page);
  await context.clearCookies();
  await asAdmin(page);
  await page.goto('/dashboard/ops/financial-visibility/');
  await expect(page.locator('[name="show_estimates"]')).toBeChecked();
  await expect(page.locator('[name="valid_until"]')).toHaveValue('2030-12-31');
  form = page.locator('main form');
  await form.locator('[name="show_estimates"]').uncheck();
  await form.locator('[name="valid_until"]').fill('');
  await clickAndSettle(form.locator('button[type="submit"]'), page);
  await page.goto('/dashboard/ops/financial-visibility/');
  await expect(page.locator('[name="show_estimates"]')).not.toBeChecked();
});

test('admin-created user survives edit and activation toggle', async ({ page }) => {
  await asAdmin(page);
  page.on('dialog', dialog => dialog.accept());
  await page.goto('/dashboard/home/?tab=users');
  const card = page.locator('.card').filter({ has: page.getByRole('heading', { name: 'Créer un utilisateur' }) });
  await card.getByRole('button', { name: 'Afficher' }).click();
  const create = card.locator('form[action="/dashboard/home/user/create/"]');
  await create.locator('[name="username"]').fill('cms-browser-user');
  await create.locator('[name="first_name"]').fill('CMS');
  await create.locator('[name="last_name"]').fill('Browser');
  await create.locator('[name="email"]').fill('cms-browser@example.test');
  await create.locator('[name="role"]').selectOption('CLIENT');
  await create.locator('[name="organization"]').fill('Institution initiale');
  await create.locator('[name="phone"]').fill('0555001122');
  await create.locator('[name="password"]').fill('CmsBrowserAudit!2026');
  await clickAndSettle(create.locator('button[type="submit"]'), page);
  await page.goto('/dashboard/home/?tab=users&user_q=cms-browser-user');
  let row = page.locator('tr').filter({ hasText: 'cms-browser@example.test' });
  await expect(row).toHaveCount(1);
  const editHref = await row.locator('a[href$="/edit/"]').getAttribute('href');
  await page.goto(editHref);
  await page.locator('[name="organization"]').fill('Institution persistée');
  await page.locator('[name="phone"]').fill('0555003344');
  await clickAndSettle(page.locator('main form button[type="submit"]'), page);
  await page.goto(editHref);
  await expect(page.locator('[name="organization"]')).toHaveValue('Institution persistée');
  await expect(page.locator('[name="phone"]')).toHaveValue('0555003344');
  await page.goto('/dashboard/home/?tab=users&user_q=cms-browser-user');
  row = page.locator('tr').filter({ hasText: 'cms-browser@example.test' });
  await clickAndSettle(row.locator('form[action$="/toggle/"] button'), page);
  await page.goto('/dashboard/home/?tab=users&user_q=cms-browser-user');
  row = page.locator('tr').filter({ hasText: 'cms-browser@example.test' });
  await expect(row).toContainText('Inactif');
  await clickAndSettle(row.locator('form[action$="/toggle/"] button'), page);
  await page.goto('/dashboard/home/?tab=users&user_q=cms-browser-user');
  await expect(page.locator('tr').filter({ hasText: 'cms-browser@example.test' })).toContainText('Actif');
});

test('document block CRUD persists relation and text', async ({ page }) => {
  await asAdmin(page);
  await page.goto('/documents/blocks/create/');
  let form = page.locator('main form');
  await form.locator('[name="template_type"]').selectOption('QUOTE');
  await form.locator('[name="language"]').selectOption('fr');
  await form.locator('[name="position"]').selectOption('TOP');
  await form.locator('[name="priority"]').fill('7');
  await form.locator('[name="title"]').fill('Bloc CMS navigateur');
  await form.locator('[name="body"]').fill('Contenu persistant du bloc');
  await form.locator('[name="is_active"]').check();
  await form.locator('[name="services"]').first().check();
  await clickAndSettle(form.locator('button[type="submit"]'), page);
  await page.goto('/documents/blocks/');
  let row = page.locator('tr').filter({ hasText: 'Bloc CMS navigateur' });
  await expect(row).toContainText('Contenu persistant du bloc');
  const editHref = await row.locator('a[href$="/edit/"]').getAttribute('href');
  await page.goto(editHref);
  await expect(page.locator('[name="priority"]')).toHaveValue('7');
  await expect(page.locator('[name="body"]')).toHaveValue('Contenu persistant du bloc');
  await expect(page.locator('[name="services"]:checked')).toHaveCount(1);
  form = page.locator('main form');
  await form.locator('[name="title"]').fill('Bloc CMS navigateur modifié');
  await form.locator('[name="body"]').fill('Contenu modifié et relu');
  await form.locator('[name="priority"]').fill('9');
  await clickAndSettle(form.locator('button[type="submit"]'), page);
  await page.goto(editHref);
  await expect(page.locator('[name="priority"]')).toHaveValue('9');
  await expect(page.locator('[name="body"]')).toHaveValue('Contenu modifié et relu');
  await page.goto('/documents/blocks/');
  row = page.locator('tr').filter({ hasText: 'Bloc CMS navigateur modifié' });
  const deleteHref = await row.locator('a[href$="/delete/"]').getAttribute('href');
  await page.goto(deleteHref);
  await clickAndSettle(page.locator('main form button[type="submit"]'), page);
  await page.goto('/documents/blocks/');
  await expect(page.locator('tr').filter({ hasText: 'Bloc CMS navigateur modifié' })).toHaveCount(0);
});
