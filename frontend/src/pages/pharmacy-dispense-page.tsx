import { CheckCircle2, ClipboardList, Loader2, Search, UserRoundSearch, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { PharmacyTabs } from '@/components/pharmacy/pharmacy-tabs'
import { EmptyState } from '@/components/shared/empty-state'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { usePatientPrescriptions } from '@/features/consultations/hooks'
import type { PrescriptionItemSummary, PrescriptionSummary } from '@/features/consultations/types'
import { useDispensePrescriptionItem } from '@/features/pharmacy/hooks'
import { usePatientSearch } from '@/features/patients/hooks'
import type { PatientSummary } from '@/features/patients/types'
import { getErrorMessage } from '@/lib/errors'

function medicineLabel(item: PrescriptionItemSummary): string {
  return item.medicine_name_freetext ?? '(catalog medicine)'
}

function DispenseItemRow({ item }: { item: PrescriptionItemSummary }) {
  const remaining = item.prescribed_quantity - item.dispensed_quantity
  const [quantity, setQuantity] = useState(String(remaining))
  const dispense = useDispensePrescriptionItem()

  const fullyDispensed = remaining <= 0
  // A prescription item is only ever dispensable against inventory when it
  // was linked to a catalog medicine (medicine_id) at the point it was
  // prescribed — a free-text-only item (the Rx pad's own fallback when a
  // doctor types a name without picking a catalog suggestion) 422s every
  // time with "no linked catalog medicine," which used to surface as a
  // generic "Could not dispense" with no indication why. Disable it here
  // instead of letting the click fail.
  const notCatalogLinked = item.medicine_id == null

  async function handleDispense() {
    const qty = Number(quantity)
    if (!Number.isInteger(qty) || qty < 1 || qty > remaining) {
      toast.error(`Enter a quantity between 1 and ${remaining}`)
      return
    }
    try {
      const result = await dispense.mutateAsync({ prescription_item_id: item.id, quantity: qty })
      toast.success(`Dispensed ${result.quantity_dispensed} — ${medicineLabel(item)}`)
    } catch (error) {
      toast.error('Could not dispense', { description: getErrorMessage(error) })
    }
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
      <div className="flex flex-col">
        <span className="text-sm font-medium text-slate-900 dark:text-slate-100">{medicineLabel(item)}</span>
        <span className="text-xs text-slate-500 dark:text-slate-400">
          {[item.dosage, item.frequency, item.duration].filter(Boolean).join(' · ') || 'No dosage details'} · Dispensed{' '}
          {item.dispensed_quantity}/{item.prescribed_quantity}
        </span>
      </div>
      {fullyDispensed ? (
        <Badge variant="outline" className="gap-1 border-transparent bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400">
          <CheckCircle2 className="size-3.5" />
          Fully dispensed
        </Badge>
      ) : notCatalogLinked ? (
        <Badge variant="outline" className="gap-1 border-transparent bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400">
          Not catalog-linked — cannot dispense
        </Badge>
      ) : (
        <div className="flex items-center gap-2">
          <Input
            type="number"
            min={1}
            max={remaining}
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            className="w-20"
          />
          <Button size="sm" disabled={dispense.isPending} onClick={() => void handleDispense()}>
            {dispense.isPending ? 'Dispensing…' : 'Dispense'}
          </Button>
        </div>
      )}
    </li>
  )
}

function PrescriptionCard({ prescription }: { prescription: PrescriptionSummary }) {
  const allDispensed = prescription.items.every((item) => item.dispensed_quantity >= item.prescribed_quantity)
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400">
          Issued {new Date(prescription.issued_at).toLocaleString()}
        </CardTitle>
        {allDispensed && <Badge variant="secondary">All dispensed</Badge>}
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col divide-y divide-slate-100 dark:divide-slate-800">
          {prescription.items.map((item) => (
            <DispenseItemRow key={item.id} item={item} />
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

export function PharmacyDispensePage() {
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedPatient, setSelectedPatient] = useState<PatientSummary | null>(null)
  const { data: searchResults, isFetching } = usePatientSearch(searchTerm)
  const { data: prescriptions, isLoading: prescriptionsLoading } = usePatientPrescriptions(selectedPatient?.id)

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Pharmacy</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Dispense prescribed medicines against a patient's Rx.</p>
      </div>

      <PharmacyTabs />

      {!selectedPatient ? (
        <div className="flex flex-col gap-2">
          <div className="relative max-w-sm">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-slate-400" />
            <Input
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Phone, MRN, or name…"
              className="pl-8"
            />
            {isFetching && (
              <Loader2 className="absolute top-1/2 right-2.5 size-4 -translate-y-1/2 animate-spin text-slate-400" />
            )}
          </div>

          {searchTerm.trim().length === 0 ? (
            <EmptyState icon={UserRoundSearch} title="Search for a patient" description="Type a phone number, MRN, or name to find their prescriptions." />
          ) : (
            <div className="max-w-sm rounded-md border border-slate-200 dark:border-slate-800">
              {!isFetching && searchResults?.items.length === 0 ? (
                <EmptyState icon={UserRoundSearch} title="No patients found" description="Try a different search term." />
              ) : (
                searchResults?.items.map((patient) => (
                  <button
                    key={patient.id}
                    type="button"
                    className="flex w-full flex-col gap-0.5 border-b border-slate-100 px-3 py-2 text-left last:border-0 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50"
                    onClick={() => setSelectedPatient(patient)}
                  >
                    <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                      {[patient.first_name, patient.last_name].filter(Boolean).join(' ')}
                    </span>
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      MRN {patient.mrn} {patient.phone ? `· ${patient.phone}` : ''}
                    </span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between rounded-md border border-slate-200 p-3 dark:border-slate-800">
            <div>
              <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                {[selectedPatient.first_name, selectedPatient.last_name].filter(Boolean).join(' ')}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">MRN {selectedPatient.mrn}</p>
            </div>
            <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => setSelectedPatient(null)}>
              <X className="size-3.5" />
              Change patient
            </Button>
          </div>

          {prescriptionsLoading ? (
            <Skeleton className="h-40 w-full" />
          ) : !prescriptions || prescriptions.items.length === 0 ? (
            <EmptyState icon={ClipboardList} title="No prescriptions found" description="This patient has no prescriptions on record yet." />
          ) : (
            <div className="flex flex-col gap-3">
              {prescriptions.items.map((prescription) => (
                <PrescriptionCard key={prescription.id} prescription={prescription} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
