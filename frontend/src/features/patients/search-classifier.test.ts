import { describe, expect, it } from 'vitest'
import { classifyPatientSearchTerm } from '@/features/patients/search-classifier'

describe('classifyPatientSearchTerm', () => {
  it('returns null for an empty or whitespace-only term', () => {
    expect(classifyPatientSearchTerm('')).toBeNull()
    expect(classifyPatientSearchTerm('   ')).toBeNull()
  })

  it('classifies a phone-shaped term as phone', () => {
    expect(classifyPatientSearchTerm('9876543210')).toEqual({ field: 'phone', value: '9876543210' })
    expect(classifyPatientSearchTerm('+91 98765 43210')).toEqual({ field: 'phone', value: '+91 98765 43210' })
  })

  it('classifies an MRN-shaped term (digit present, no space) as mrn', () => {
    expect(classifyPatientSearchTerm('MRN-2026-0004')).toEqual({ field: 'mrn', value: 'MRN-2026-0004' })
  })

  it('classifies a plain name as q, not mrn or phone', () => {
    expect(classifyPatientSearchTerm('Asha Rao')).toEqual({ field: 'q', value: 'Asha Rao' })
  })

  it('classifies an all-caps name with no digits as q, not mrn', () => {
    expect(classifyPatientSearchTerm('ASHA')).toEqual({ field: 'q', value: 'ASHA' })
  })

  it('classifies a name that happens to contain a digit but also a space as q, not mrn', () => {
    // MRN never has a space — this guards the exact misclassification
    // this function's own comment calls out.
    expect(classifyPatientSearchTerm('Suite 4B')).toEqual({ field: 'q', value: 'Suite 4B' })
  })

  it('trims surrounding whitespace before classifying', () => {
    expect(classifyPatientSearchTerm('  9876543210  ')).toEqual({ field: 'phone', value: '9876543210' })
  })
})
