import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useCreateBranch, useUpdateBranch } from '@/features/branches/hooks'
import type { BranchSummary } from '@/features/branches/types'
import { getErrorMessage } from '@/lib/errors'

const branchFormSchema = z.object({
  name: z.string().min(1, 'Name is required').max(200),
  address: z.string().max(500).optional().or(z.literal('')),
  phone: z.string().max(30).optional().or(z.literal('')),
})

type BranchFormValues = z.infer<typeof branchFormSchema>

const DEFAULT_VALUES: BranchFormValues = { name: '', address: '', phone: '' }

export function BranchFormDialog({
  branch,
  open,
  onOpenChange,
}: {
  branch: BranchSummary | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const createBranch = useCreateBranch()
  const updateBranch = useUpdateBranch()

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<BranchFormValues>({ resolver: zodResolver(branchFormSchema), defaultValues: DEFAULT_VALUES })

  useEffect(() => {
    if (open) {
      reset(branch ? { name: branch.name, address: branch.address ?? '', phone: branch.phone ?? '' } : DEFAULT_VALUES)
    }
  }, [open, branch, reset])

  async function onSubmit(values: BranchFormValues) {
    try {
      if (branch) {
        await updateBranch.mutateAsync({
          branchId: branch.id,
          payload: { name: values.name, address: values.address || null, phone: values.phone || null },
        })
        toast.success('Branch updated')
      } else {
        await createBranch.mutateAsync({ name: values.name, address: values.address || undefined, phone: values.phone || undefined })
        toast.success('Branch created')
      }
      onOpenChange(false)
    } catch (error) {
      toast.error('Could not save branch', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{branch ? 'Edit branch' : 'Add branch'}</DialogTitle>
          <DialogDescription>Branches are shared reference data — every role that schedules or checks in patients needs to see them.</DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="branchName">Name *</Label>
            <Input id="branchName" {...register('name')} />
            {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="branchAddress">Address</Label>
            <Input id="branchAddress" {...register('address')} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="branchPhone">Phone</Label>
            <Input id="branchPhone" type="tel" {...register('phone')} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Saving…' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
