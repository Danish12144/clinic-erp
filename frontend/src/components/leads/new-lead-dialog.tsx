import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useCreateLead } from '@/features/leads/hooks'
import { LEAD_SOURCES, LEAD_SOURCE_LABELS, type LeadSource } from '@/features/leads/types'
import { getErrorMessage } from '@/lib/errors'

export const leadFormSchema = z.object({
  firstName: z.string().min(1, 'First name is required').max(100),
  lastName: z.string().max(100).optional().or(z.literal('')),
  phone: z.string().max(20).optional().or(z.literal('')),
  email: z.string().email('Invalid email').max(255).optional().or(z.literal('')),
  source: z.enum(LEAD_SOURCES).optional(),
  notes: z.string().max(2000).optional().or(z.literal('')),
})

type LeadFormValues = z.infer<typeof leadFormSchema>

const DEFAULT_VALUES: LeadFormValues = { firstName: '', lastName: '', phone: '', email: '', source: undefined, notes: '' }

export function NewLeadDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const createLead = useCreateLead()

  const {
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<LeadFormValues>({ resolver: zodResolver(leadFormSchema), defaultValues: DEFAULT_VALUES })

  useEffect(() => {
    if (open) reset(DEFAULT_VALUES)
  }, [open, reset])

  async function onSubmit(values: LeadFormValues) {
    try {
      await createLead.mutateAsync({
        first_name: values.firstName,
        last_name: values.lastName || undefined,
        phone: values.phone || undefined,
        email: values.email || undefined,
        source: values.source,
        notes: values.notes || undefined,
      })
      toast.success('Lead added')
      onOpenChange(false)
    } catch (error) {
      toast.error('Could not add lead', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New lead</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="leadFirstName">First name</Label>
              <Input id="leadFirstName" {...register('firstName')} autoFocus />
              {errors.firstName && <p className="text-sm text-destructive">{errors.firstName.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="leadLastName">Last name</Label>
              <Input id="leadLastName" {...register('lastName')} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="leadPhone">Phone</Label>
              <Input id="leadPhone" {...register('phone')} />
              {errors.phone && <p className="text-sm text-destructive">{errors.phone.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="leadEmail">Email</Label>
              <Input id="leadEmail" type="email" {...register('email')} />
              {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Source</Label>
            <Select value={watch('source') ?? ''} onValueChange={(value) => setValue('source', (value || undefined) as LeadSource | undefined)}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Where did this lead come from?" />
              </SelectTrigger>
              <SelectContent>
                {LEAD_SOURCES.map((source) => (
                  <SelectItem key={source} value={source}>
                    {LEAD_SOURCE_LABELS[source]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="leadNotes">Notes</Label>
            <Textarea id="leadNotes" rows={3} placeholder="Anything useful for the first follow-up…" {...register('notes')} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Adding…' : 'Add lead'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
