import { expect, test, type Page } from '@playwright/test'

// Golden path: Patient Check-in -> OPD Queue -> Doctor Consultation ->
// Prescription -> Billing Checkout -- the same end-to-end story verified
// manually via API scripts against production earlier in this project's
// life (see CLAUDE.md's "first live, end-to-end golden-path smoke test"
// note), now driven through the real UI so a frontend regression (a
// broken button, a selector that stopped matching, a form that silently
// stopped submitting) fails a test instead of only being caught by a
// human clicking through it by hand.
//
// Requires a fully prepared local dev environment — see playwright.config.ts's
// own top comment for the exact prerequisites (migrated + seeded local
// Postgres, backend running on :8000). Logs in as the fixed
// reception.myclinic@gmail.com / doctor.myclinic@gmail.com accounts
// scripts/seed_demo_accounts.py provisions — local-only credentials, not
// a secret worth protecting (see that script's own docstring).

const CLINIC_SLUG = 'my-clinic'
const RECEPTIONIST = { identifier: 'reception.myclinic@gmail.com', password: 'Demo@12345' }
const DOCTOR = { identifier: 'doctor.myclinic@gmail.com', password: 'Demo@12345' }

async function login(page: Page, credentials: { identifier: string; password: string }) {
  await page.goto('/login')
  await page.locator('#clinicSlug').fill(CLINIC_SLUG)
  await page.locator('#identifier').fill(credentials.identifier)
  await page.locator('#password').fill(credentials.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL('/')
}

async function logout(page: Page) {
  await page.getByRole('button', { name: 'Log out' }).click()
  await expect(page).toHaveURL('/login')
}

// base-ui's Select renders an accessible combobox trigger + a listbox of
// options — role-based locators, so this survives styling changes the way
// the rest of this suite's selectors are meant to. Anchored to the
// visible <Label> text rather than combobox index/position: this app's
// pages routinely have more than one combobox in play at once (e.g.
// BillingPage's own status filter sits behind the New Invoice dialog),
// so "the Nth combobox" is not a reliable way to pick one — these forms'
// <Label>/<Select> pairs aren't id-linked (no htmlFor), just DOM
// siblings, hence the parent-then-descendant walk instead of getByLabel.
async function selectComboboxNearLabel(page: Page, labelText: string, optionName: string | RegExp) {
  await page.getByText(labelText, { exact: true }).locator('..').getByRole('combobox').click()
  await page.getByRole('option', { name: optionName }).click()
}

test('golden path: register + check-in -> OPD consultation -> prescription -> billing -> paid', async ({ page }) => {
  const uniqueId = Date.now().toString().slice(-9)
  const lastName = `E2E${uniqueId}`
  const phone = `9${uniqueId}`

  // ---- 1. Receptionist registers and checks in a new patient, assigned to the demo doctor ----
  await login(page, RECEPTIONIST)
  await page.goto('/patients')
  await page.getByRole('button', { name: 'New patient' }).click()

  await page.locator('#first_name').fill('GoldenPath')
  await page.locator('#last_name').fill(lastName)
  await page.locator('#phone').fill(phone)

  // "Check in now" defaults to checked (canCheckIn === true for Receptionist) —
  // the branch select auto-fills for a single-branch clinic (see
  // NewPatientDialog's own effect); only the doctor picker needs a
  // deliberate choice, since the OPD queue below is scoped to one doctor.
  await selectComboboxNearLabel(page, 'Doctor (optional)', /Demo Doctor/i)

  await page.getByRole('button', { name: 'Register patient' }).click()
  await expect(page.getByText(/registered/i).first()).toBeVisible()
  await expect(page.getByText(/checked in/i).first()).toBeVisible()

  await logout(page)

  // ---- 2. Doctor starts the consultation from the OPD queue ----
  await login(page, DOCTOR)
  await page.goto('/opd')
  await expect(page.getByText(lastName)).toBeVisible({ timeout: 15_000 })

  const queueRow = page.getByRole('row').filter({ hasText: lastName })
  await queueRow.getByRole('button', { name: 'Start consultation' }).click()
  await expect(page).toHaveURL(/\/opd\/[0-9a-f-]+$/)

  // ---- 3. Record notes and issue a prescription ----
  await page.locator('#chiefComplaint').fill('E2E golden-path test complaint')
  await page.locator('#diagnosisText').fill('E2E golden-path test diagnosis')
  await page.getByPlaceholder('Medicine name').fill('Paracetamol 500mg (E2E test)')

  await page.getByRole('button', { name: 'Finish encounter & generate Rx' }).click()
  await expect(page.getByText(/encounter completed/i)).toBeVisible({ timeout: 15_000 })

  // A prescription PDF preview dialog may open automatically (see
  // OpdWorkspacePage's onFinalize) — but the completed-encounter refetch
  // it triggers can swap the workspace into its read-only "this encounter
  // is completed" view before the dialog is interacted with, unmounting
  // it from under a real user too, not just this test. Verifying that
  // transient dialog isn't the golden path's job; going straight to the
  // queue is what actually matters here.
  await page.goto('/opd')

  await logout(page)

  // ---- 4. Receptionist finds the auto-generated invoice and collects payment ----
  // ConsultationService.complete_consultation's own best-effort auto-
  // generate-on-completion call already created a DRAFT CONSULTATION
  // invoice for this patient back in step 3 — go straight to it rather
  // than opening "New invoice" and picking "auto-generate from
  // consultation" again, which would 409 on the duplicate-invoice guard
  // (no second non-VOID invoice of the same source_type per encounter).
  await login(page, RECEPTIONIST)
  await page.goto('/billing')
  await page.getByRole('row').filter({ hasText: `GoldenPath ${lastName}` }).click()
  await expect(page).toHaveURL(/\/billing\/[0-9a-f-]+$/)

  await page.getByRole('button', { name: 'Issue invoice' }).click()
  // exact:true disambiguates the StatusBadge ("Issued") from the toast
  // ("Invoice issued"), which both otherwise match getByText('Issued').
  await expect(page.getByText('Issued', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Record payment' }).click()
  const paymentDialog = page.getByRole('dialog')
  await paymentDialog.getByRole('button', { name: 'Record payment' }).click()

  // ---- 5. Confirm the invoice is fully paid ----
  await expect(page.getByText('Paid', { exact: true })).toBeVisible({ timeout: 10_000 })
})
