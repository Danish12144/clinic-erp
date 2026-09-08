import { z } from 'zod'

const rxItemSchema = z
  .object({
    medicineId: z.string().optional(),
    medicineLabel: z.string().min(1, 'Medicine name is required').max(300),
    dosage: z.string().max(200).optional().or(z.literal('')),
    frequency: z.string().max(200).optional().or(z.literal('')),
    duration: z.string().max(200).optional().or(z.literal('')),
    route: z.string().max(100).optional().or(z.literal('')),
    instructions: z.string().max(1000).optional().or(z.literal('')),
    prescribedQuantity: z
      .string()
      .min(1, 'Required')
      .refine((v) => Number.isInteger(Number(v)) && Number(v) >= 1 && Number(v) <= 10000, 'Must be 1-10000'),
  })
  .strict()

export const consultationFormSchema = z.object({
  chiefComplaint: z.string().max(2000).optional().or(z.literal('')),
  clinicalNotes: z.string().max(10000).optional().or(z.literal('')),
  diagnosisText: z.string().max(2000).optional().or(z.literal('')),
  icd10Code: z.string().max(20).optional().or(z.literal('')),
  items: z.array(rxItemSchema).min(1, 'Add at least one medicine before finishing'),
})

export type ConsultationFormValues = z.infer<typeof consultationFormSchema>

export const EMPTY_RX_ITEM: ConsultationFormValues['items'][number] = {
  medicineId: undefined,
  medicineLabel: '',
  dosage: '',
  frequency: '',
  duration: '',
  route: '',
  instructions: '',
  prescribedQuantity: '1',
}
