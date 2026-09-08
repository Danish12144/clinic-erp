// Local-timezone "today" as YYYY-MM-DD, matching the backend's date-typed
// fields (e.g. QueueToken.token_date) when serialized to JSON — used to
// filter "today's" rows client-side where the backend has no date filter
// of its own (see features/opd/use-doctor-queue.ts, features/dashboard).
export function todayLocalDate(): string {
  const now = new Date()
  const yyyy = now.getFullYear()
  const mm = String(now.getMonth() + 1).padStart(2, '0')
  const dd = String(now.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
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
