// Mirrors backend/app/modules/patients/schemas.py's _PHONE_PATTERN /
// _MRN_PATTERN exactly (also reused by staff/doctors, which validate phone
// the same way) — keep these in sync with the backend if either changes.
export const PHONE_PATTERN = /^\+?[0-9][0-9 -]{6,17}$/
export const MRN_PATTERN = /^[A-Za-z0-9][A-Za-z0-9-]{2,49}$/
