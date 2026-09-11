import { describe, expect, it } from 'vitest'
import { patientFormSchema, resolveDateOfBirth, type PatientFormValues } from '@/components/patients/new-patient-dialog'

const BASE: PatientFormValues = {
  first_name: 'Asha',
  last_name: 'Rao',
  gender: undefined,
  date_of_birth: '',
  age: '',
  phone: '',
  email: '',
  address: '',
  abhaId: '',
  abhaAddress: '',
  checkInNow: false,
  branchId: '',
  doctorId: '',
}

describe('patientFormSchema', () => {
  it('accepts a minimal valid patient with just a phone', () => {
    expect(patientFormSchema.safeParse({ ...BASE, phone: '9876543210' }).success).toBe(true)
  })

  it('accepts a minimal valid patient with just an email', () => {
    expect(patientFormSchema.safeParse({ ...BASE, email: 'asha@example.com' }).success).toBe(true)
  })

  it('rejects a patient with neither phone nor email', () => {
    const result = patientFormSchema.safeParse(BASE)
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.some((issue) => issue.message === 'Provide a phone number or email address')).toBe(true)
    }
  })

  it('rejects a missing first name', () => {
    expect(patientFormSchema.safeParse({ ...BASE, first_name: '', phone: '9876543210' }).success).toBe(false)
  })

  it('rejects an invalid phone number shape', () => {
    expect(patientFormSchema.safeParse({ ...BASE, phone: 'not-a-phone' }).success).toBe(false)
  })

  it('rejects an implausible age', () => {
    expect(patientFormSchema.safeParse({ ...BASE, phone: '9876543210', age: '200' }).success).toBe(false)
    expect(patientFormSchema.safeParse({ ...BASE, phone: '9876543210', age: '0' }).success).toBe(false)
  })

  it('requires a branch when checking in now', () => {
    const result = patientFormSchema.safeParse({ ...BASE, phone: '9876543210', checkInNow: true, branchId: '' })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.some((issue) => issue.message === 'Select a branch to check in')).toBe(true)
    }
  })

  it('accepts checking in now once a branch is selected', () => {
    expect(
      patientFormSchema.safeParse({ ...BASE, phone: '9876543210', checkInNow: true, branchId: 'branch-1' }).success,
    ).toBe(true)
  })
})

describe('resolveDateOfBirth', () => {
  it('prefers an explicit date_of_birth over age', () => {
    expect(resolveDateOfBirth({ ...BASE, date_of_birth: '1990-05-12', age: '20' })).toBe('1990-05-12')
  })

  it('approximates a date of birth from age as Jan 1 of the birth year', () => {
    const expectedYear = new Date().getFullYear() - 30
    expect(resolveDateOfBirth({ ...BASE, date_of_birth: '', age: '30' })).toBe(`${expectedYear}-01-01`)
  })

  it('returns undefined when neither date_of_birth nor age is provided', () => {
    expect(resolveDateOfBirth({ ...BASE, date_of_birth: '', age: '' })).toBeUndefined()
  })
})
