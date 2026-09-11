import { FileText, Pill, Stethoscope } from 'lucide-react'
import { useState } from 'react'
import { PrescriptionPreviewDialog } from '@/components/opd/prescription-preview-dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { StatusBadge } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { usePatientEmrTimeline } from '@/features/emr/hooks'
import { useMyPatient } from '@/features/patients/hooks'

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function PortalMedicalRecordsPage() {
  const { data: patient } = useMyPatient()
  const { data: timeline, isLoading } = usePatientEmrTimeline(patient?.id)
  const [previewDocumentId, setPreviewDocumentId] = useState<string | null>(null)

  if (isLoading || !timeline) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4 p-4 sm:p-6">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 p-4 sm:p-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Medical records</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Your visit history, prescriptions, and vitals.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Stethoscope className="size-4" />
            Visits
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {timeline.visits.length === 0 ? (
            <EmptyState icon={Stethoscope} title="No visits yet" description="Your consultation history will appear here." />
          ) : (
            timeline.visits.map((visit) => (
              <div key={visit.encounter_id} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{formatDateTime(visit.checked_in_at)}</p>
                  <StatusBadge status={visit.encounter_status} />
                </div>
                {visit.chief_complaint && <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{visit.chief_complaint}</p>}
                {visit.diagnosis_text && (
                  <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">
                    <span className="font-medium">Diagnosis: </span>
                    {visit.diagnosis_text}
                    {visit.icd10_code && <span className="text-slate-400 dark:text-slate-600"> ({visit.icd10_code})</span>}
                  </p>
                )}
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Pill className="size-4" />
            Prescriptions
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {timeline.prescriptions.length === 0 ? (
            <EmptyState icon={Pill} title="No prescriptions yet" description="Prescriptions from your visits will appear here." />
          ) : (
            timeline.prescriptions.map((prescription) => (
              <div key={prescription.id} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{formatDateTime(prescription.issued_at)}</p>
                  {prescription.pdf_document_id && (
                    <Button variant="outline" size="sm" onClick={() => setPreviewDocumentId(prescription.pdf_document_id)}>
                      View PDF
                    </Button>
                  )}
                </div>
                <ul className="mt-1 flex flex-col gap-0.5 text-sm text-slate-600 dark:text-slate-400">
                  {prescription.items.map((item) => (
                    <li key={item.id}>
                      {item.medicine_name_freetext || 'Catalog medicine'}
                      {item.dosage ? ` — ${item.dosage}` : ''}
                      {item.frequency ? `, ${item.frequency}` : ''}
                      {item.duration ? `, ${item.duration}` : ''}
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Vitals</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {timeline.vitals.length === 0 ? (
            <EmptyState icon={Stethoscope} title="No vitals recorded" description="Readings taken during your visits will appear here." />
          ) : (
            timeline.vitals.map((vitals) => (
              <div key={vitals.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-800">
                <span className="font-medium text-slate-900 dark:text-slate-100">{formatDateTime(vitals.recorded_at)}</span>
                {vitals.systolic_bp && vitals.diastolic_bp && (
                  <span className="text-slate-600 dark:text-slate-400">
                    BP {vitals.systolic_bp}/{vitals.diastolic_bp}
                  </span>
                )}
                {vitals.heart_rate && <span className="text-slate-600 dark:text-slate-400">Pulse {vitals.heart_rate}</span>}
                {vitals.temperature_celsius && <span className="text-slate-600 dark:text-slate-400">{vitals.temperature_celsius}°C</span>}
                {vitals.weight_kg && <span className="text-slate-600 dark:text-slate-400">{vitals.weight_kg} kg</span>}
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {timeline.documents.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileText className="size-4" />
              Documents
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {/* No download link — medical_documents.storage_key is a raw
                pointer (an S3-style key or an external URL), not a
                documents.id the generic /files/{id}/content route can
                resolve, so there's no reliable way to fetch these bytes
                from here yet. Listed for visibility only. */}
            {timeline.documents.map((document) => (
              <div key={document.id} className="flex items-center justify-between rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-800">
                <div>
                  <p className="font-medium text-slate-900 dark:text-slate-100">{document.title}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">{document.document_type}</p>
                </div>
                <span className="text-xs text-slate-400 dark:text-slate-600">{new Date(document.created_at).toLocaleDateString()}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <PrescriptionPreviewDialog
        documentId={previewDocumentId}
        open={Boolean(previewDocumentId)}
        onOpenChange={(open) => !open && setPreviewDocumentId(null)}
      />
    </div>
  )
}
