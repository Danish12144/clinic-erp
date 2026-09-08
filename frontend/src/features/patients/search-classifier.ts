// The backend ANDs whatever filters are supplied, and phone/mrn are exact
// matches, not partial (see backend/app/modules/patients/repository.py) —
// so a single search box can't just forward the same text to q+phone+mrn
// at once (it would almost always AND itself into zero results). Instead
// we guess which single filter the text is meant for, mirroring the
// backend's own validation patterns (backend/app/modules/patients/schemas.py).

import { MRN_PATTERN, PHONE_PATTERN } from '@/lib/validation'

export type PatientSearchField = 'phone' | 'mrn' | 'q'

export interface ClassifiedSearch {
  field: PatientSearchField
  value: string
}

export function classifyPatientSearchTerm(raw: string): ClassifiedSearch | null {
  const term = raw.trim()
  if (!term) return null
  if (PHONE_PATTERN.test(term)) return { field: 'phone', value: term }
  // An MRN always has a digit somewhere and never a space — otherwise a
  // plain all-letters name (or a name typed in caps) would misclassify as
  // an MRN attempt.
  if (!term.includes(' ') && /\d/.test(term) && MRN_PATTERN.test(term)) return { field: 'mrn', value: term }
  return { field: 'q', value: term }
}
