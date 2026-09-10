import { describe, expect, it } from 'vitest'
import { leadFormSchema } from '@/components/leads/new-lead-dialog'

describe('leadFormSchema', () => {
  it('accepts a minimal valid lead (first name only)', () => {
    const result = leadFormSchema.safeParse({ firstName: 'Asha' })
    expect(result.success).toBe(true)
  })

  it('accepts a fully populated lead', () => {
    const result = leadFormSchema.safeParse({
      firstName: 'Asha',
      lastName: 'Rao',
      phone: '9876543210',
      email: 'asha@example.com',
      source: 'WEBSITE',
      notes: 'Interested in a dermatology consult.',
    })
    expect(result.success).toBe(true)
  })

  it('rejects a missing first name', () => {
    const result = leadFormSchema.safeParse({ firstName: '' })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0].message).toBe('First name is required')
    }
  })

  it('rejects an invalid email but allows an empty one', () => {
    expect(leadFormSchema.safeParse({ firstName: 'Asha', email: 'not-an-email' }).success).toBe(false)
    expect(leadFormSchema.safeParse({ firstName: 'Asha', email: '' }).success).toBe(true)
  })

  it('rejects a source outside the known LEAD_SOURCES list', () => {
    const result = leadFormSchema.safeParse({ firstName: 'Asha', source: 'CARRIER_PIGEON' })
    expect(result.success).toBe(false)
  })
})
