import { expect, test, type Page } from '@playwright/test'

// Verifies the Receptionist "pay first, see the doctor after" flow added
// in this session: OPD Queue -> "Collect fee" -> CollectConsultationFeeDialog
// (pre-filled from the doctor directory's consultation_fee) -> create +
// issue + record-payment in one action -> lands on the new invoice's
// detail page already PAID. Same prerequisites as golden-path.spec.ts —
// see playwright.config.ts's own top comment.

const CLINIC_SLUG = 'my-clinic'
const RECEPTIONIST = { identifier: 'reception.myclinic@gmail.com', password: 'Demo@12345' }

async function login(page: Page, credentials: { identifier: string; password: string }) {
  await page.goto('/login')
  await page.locator('#clinicSlug').fill(CLINIC_SLUG)
  await page.locator('#identifier').fill(credentials.identifier)
  await page.locator('#password').fill(credentials.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL('/')
}

async function selectComboboxNearLabel(page: Page, labelText: string, optionName: string | RegExp) {
  await page.getByText(labelText, { exact: true }).locator('..').getByRole('combobox').click()
  await page.getByRole('option', { name: optionName }).click()
}

test('receptionist collects the consultation fee straight from the OPD queue', async ({ page }) => {
  const uniqueId = Date.now().toString().slice(-9)
  const lastName = `CollectFee${uniqueId}`
  const phone = `8${uniqueId}`

  // ---- 1. Receptionist registers + checks in a new patient, assigned to the demo doctor ----
  await login(page, RECEPTIONIST)
  await page.goto('/patients')
  await page.getByRole('button', { name: 'New patient' }).click()

  await page.locator('#first_name').fill('FeeTest')
  await page.locator('#last_name').fill(lastName)
  await page.locator('#phone').fill(phone)
  await selectComboboxNearLabel(page, 'Doctor (optional)', /Demo Doctor/i)

  await page.getByRole('button', { name: 'Register patient' }).click()
  await expect(page.getByText(/registered/i).first()).toBeVisible()
  await expect(page.getByText(/checked in/i).first()).toBeVisible()

  // ---- 2. OPD Queue: Receptionist sees the patient (queue.view, clinic-wide) and has a "Collect fee" action ----
  await page.goto('/opd')
  await expect(page.getByText(lastName)).toBeVisible({ timeout: 15_000 })

  const queueRow = page.getByRole('row').filter({ hasText: lastName })
  // Receptionist doesn't hold vitals.record by default (see the earlier
  // session reverting that blanket grant) — confirms the view-only fix
  // alongside the billing action, not just the billing action alone.
  await expect(queueRow.getByRole('button', { name: 'Record vitals' })).toHaveCount(0)
  await queueRow.getByRole('button', { name: 'Collect fee' }).click()

  // ---- 3. CollectConsultationFeeDialog: amount pre-filled from the doctor's consultation_fee (seeded 500.00) ----
  const dialog = page.getByRole('dialog').filter({ hasText: 'Collect consultation fee' })
  await expect(dialog).toBeVisible()
  await expect(dialog.locator('#feeAmount')).toHaveValue('500.00')
  // base-ui's Checkbox renders both a hidden native <input> and a visual
  // <span role="checkbox">, both aria-labelledby the same <Label> — same
  // "the library exposes two accessible nodes for one control" quirk
  // golden-path.spec.ts's own selectComboboxNearLabel comment documents
  // for Select, just for Checkbox instead — getByLabel resolves to both
  // (a strict-mode violation) where getByRole('checkbox', ...) resolves
  // to the one real interactive element.
  await expect(dialog.getByRole('checkbox', { name: 'Collected now — mark as paid' })).toBeChecked()

  await dialog.getByRole('button', { name: 'Create invoice' }).click()

  // ---- 4. Lands on the new invoice, already PAID (create -> issue -> record payment, one action) ----
  // Both invoice.status AND invoice.payment_status read "PAID" once fully
  // settled, so InvoiceDetailPage renders two separate "Paid" badges —
  // .first() is enough to confirm the state, not a specific one of them.
  await expect(page).toHaveURL(/\/billing\/[0-9a-f-]+$/)
  await expect(page.getByText('Paid', { exact: true }).first()).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('Consultation Fee')).toBeVisible()
})
