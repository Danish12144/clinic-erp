// Local-timezone "today" as YYYY-MM-DD — the clinic's own calendar day,
// used for ranges over real timestamptz columns (see todayLocalRange
// below). Do NOT use this to compare against `QueueToken.token_date`
// specifically — see todayUTCDate's own docstring for why.
export function todayLocalDate(): string {
  const now = new Date()
  const yyyy = now.getFullYear()
  const mm = String(now.getMonth() + 1).padStart(2, '0')
  const dd = String(now.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

// UTC calendar date as YYYY-MM-DD — matches the backend's own
// `token_date` computation exactly (`datetime.now(timezone.utc).date()`,
// see backend/app/modules/checkin/repository.py::QueueTokenRepository
// .issue's own comment: "token_date is computed in the app as
// datetime.now(timezone.utc).date() ... so the lock/read/insert all
// agree on the same date value"). Deliberately NOT the same as
// todayLocalDate(): for any clinic operating ahead of UTC (India is
// UTC+5:30 — this app's whole target market, per its ₹/GSTIN/MRN
// conventions elsewhere), the two disagree for a real ~5.5-hour window
// every single day (00:00-05:30 IST). A token issued during that window
// is stamped "yesterday" by the backend; filtering the OPD queue by
// `t.token_date === todayLocalDate()` silently drops it from the active
// queue for everyone (Doctor's own queue and Receptionist's clinic-wide
// view alike) until well past midnight local time — caught by
// e2e/collect-fee.spec.ts failing at 00:56 IST, not a hypothetical. Use
// this, never todayLocalDate(), for any `token_date` comparison.
export function todayUTCDate(): string {
  return new Date().toISOString().slice(0, 10)
}

// [start, end) ISO instants spanning the local calendar day — for datetime
// query params like GET /encounters?date_from=&date_to=.
export function todayLocalRange(): { start: string; end: string } {
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const end = new Date(start)
  end.setDate(end.getDate() + 1)
  return { start: start.toISOString(), end: end.toISOString() }
}
