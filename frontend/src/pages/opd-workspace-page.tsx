import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowLeft, FileCheck, Loader2, Save } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { consultationFormSchema, EMPTY_RX_ITEM, type ConsultationFormValues } from '@/components/opd/consultation-form-schema'
import { FollowUpPanel } from '@/components/opd/follow-up-panel'
import { LabOrderPanel } from '@/components/opd/lab-order-panel'
import { PrescriptionPreviewDialog } from '@/components/opd/prescription-preview-dialog'
import { RxTable } from '@/components/opd/rx-table'
import { VitalsPanel } from '@/components/opd/vitals-panel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { useEncounter } from '@/features/checkin/hooks'
import {
  useCompleteConsultation,
  useConsultationByEncounter,
  useIssuePrescription,
  useStartConsultation,
  useUpdateConsultation,
} from '@/features/consultations/hooks'
import type { ConsultationSummary, PrescriptionItemCreateRequest } from '@/features/consultations/types'
import { usePatient } from '@/features/patients/hooks'
import type { PatientSummary } from '@/features/patients/types'
import { getErrorMessage } from '@/lib/errors'

function formatAge(dateOfBirth: string | null): string {
  if (!dateOfBirth) return ''
  const years = Math.floor((Date.now() - new Date(dateOfBirth).getTime()) / (365.25 * 24 * 60 * 60 * 1000))
  return `${years}y`
}

function buildItemPayload(item: ConsultationFormValues['items'][number]): PrescriptionItemCreateRequest {
  return {
    medicine_id: item.medicineId || undefined,
    medicine_name_freetext: item.medicineId ? undefined : item.medicineLabel,
    dosage: item.dosage || undefined,
    frequency: item.frequency || undefined,
    duration: item.duration || undefined,
    route: item.route || undefined,
    instructions: item.instructions || undefined,
    prescribed_quantity: Number(item.prescribedQuantity),
  }
}

function ConsultationPad({
  consultation,
  encounterId,
  patient,
}: {
  consultation: ConsultationSummary
  encounterId: string
  patient: PatientSummary
}) {
  const navigate = useNavigate()
  const updateConsultation = useUpdateConsultation()
  const completeConsultation = useCompleteConsultation()
  const issuePrescription = useIssuePrescription()
  const [previewDocumentId, setPreviewDocumentId] = useState<string | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)

  const {
    register,
    handleSubmit,
    control,
    setValue,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm<ConsultationFormValues>({
    resolver: zodResolver(consultationFormSchema),
    defaultValues: {
      chiefComplaint: consultation.chief_complaint ?? '',
      clinicalNotes: consultation.clinical_notes ?? '',
      diagnosisText: consultation.diagnosis_text ?? '',
      icd10Code: consultation.icd10_code ?? '',
      items: [{ ...EMPTY_RX_ITEM }],
    },
  })

  async function saveNotes() {
    const values = getValues()
    const hasAnyNote = [values.chiefComplaint, values.clinicalNotes, values.diagnosisText, values.icd10Code].some(
      (v) => v && v.trim(),
    )
    if (!hasAnyNote) {
      toast.error('Enter at least one note field before saving')
      return
    }
    try {
      await updateConsultation.mutateAsync({
        consultationId: consultation.id,
        payload: {
          chief_complaint: values.chiefComplaint || undefined,
          clinical_notes: values.clinicalNotes || undefined,
          diagnosis_text: values.diagnosisText || undefined,
          icd10_code: values.icd10Code || undefined,
        },
      })
      toast.success('Notes saved')
    } catch (error) {
      toast.error('Could not save notes', { description: getErrorMessage(error) })
    }
  }

  async function onFinalize(values: ConsultationFormValues) {
    try {
      const hasAnyNote = [values.chiefComplaint, values.clinicalNotes, values.diagnosisText, values.icd10Code].some(
        (v) => v && v.trim(),
      )
      if (hasAnyNote) {
        await updateConsultation.mutateAsync({
          consultationId: consultation.id,
          payload: {
            chief_complaint: values.chiefComplaint || undefined,
            clinical_notes: values.clinicalNotes || undefined,
            diagnosis_text: values.diagnosisText || undefined,
            icd10_code: values.icd10Code || undefined,
          },
        })
      }

      const prescription = await issuePrescription.mutateAsync({
        encounter_id: encounterId,
        items: values.items.map(buildItemPayload),
      })

      await completeConsultation.mutateAsync(consultation.id)

      toast.success('Encounter completed — prescription generated')

      if (prescription.pdf_document_id) {
        setPreviewDocumentId(prescription.pdf_document_id)
        setPreviewOpen(true)
      } else {
        navigate('/opd')
      }
    } catch (error) {
      toast.error('Could not finish encounter', { description: getErrorMessage(error) })
    }
  }

  const isFinalizing = isSubmitting || issuePrescription.isPending || completeConsultation.isPending

  return (
    <div className="flex flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <div>
          <Link to="/opd" className="mb-1 flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="size-3.5" />
            Back to queue
          </Link>
          <h1 className="text-xl font-semibold">
            {[patient.first_name, patient.last_name].filter(Boolean).join(' ')}
          </h1>
          <p className="text-sm text-muted-foreground">
            MRN {patient.mrn} · {formatAge(patient.date_of_birth)} {patient.gender ?? ''} · {patient.phone ?? 'no phone'}
          </p>
        </div>
        <Badge variant="secondary">Consultation in progress</Badge>
      </div>

      <VitalsPanel encounterId={encounterId} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Chief complaint & clinical notes</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="chiefComplaint">Chief complaint</Label>
            <Textarea id="chiefComplaint" rows={2} {...register('chiefComplaint')} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="diagnosisText">Diagnosis</Label>
              <Textarea id="diagnosisText" rows={2} {...register('diagnosisText')} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="icd10Code">ICD-10 code</Label>
              <input
                id="icd10Code"
                className="h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                {...register('icd10Code')}
              />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="clinicalNotes">Clinical notes</Label>
            <Textarea id="clinicalNotes" rows={4} {...register('clinicalNotes')} />
          </div>
          <Button type="button" variant="outline" size="sm" className="w-fit gap-1.5" onClick={() => void saveNotes()}>
            <Save className="size-3.5" />
            Save notes
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Prescription</CardTitle>
        </CardHeader>
        <CardContent>
          <RxTable control={control} setValue={setValue} errorMessage={errors.items?.message ?? errors.items?.root?.message} />
        </CardContent>
      </Card>

      <LabOrderPanel encounterId={encounterId} />
      <FollowUpPanel patientId={patient.id} encounterId={encounterId} />

      <div className="flex justify-end border-t border-border pt-4">
        <Button size="lg" className="gap-1.5" disabled={isFinalizing} onClick={handleSubmit(onFinalize)}>
          {isFinalizing ? <Loader2 className="size-4 animate-spin" /> : <FileCheck className="size-4" />}
          {isFinalizing ? 'Finishing…' : 'Finish encounter & generate Rx'}
        </Button>
      </div>

      <PrescriptionPreviewDialog
        documentId={previewDocumentId}
        open={previewOpen}
        onOpenChange={(open) => {
          setPreviewOpen(open)
          if (!open) navigate('/opd')
        }}
      />
    </div>
  )
}

export function OpdWorkspacePage() {
  const { encounterId } = useParams<{ encounterId: string }>()
  const encounterQuery = useEncounter(encounterId)
  const patientQuery = usePatient(encounterQuery.data?.patient_id)
  const consultationQuery = useConsultationByEncounter(encounterId)
  const startConsultation = useStartConsultation()

  if (!encounterId) return <Navigate to="/opd" replace />

  if (encounterQuery.isLoading || consultationQuery.isLoading || (consultationQuery.data && patientQuery.isLoading)) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (encounterQuery.isError || !encounterQuery.data) {
    return (
      <div className="p-6 text-sm text-destructive">
        Could not load this encounter. {getErrorMessage(encounterQuery.error)}
      </div>
    )
  }

  const encounter = encounterQuery.data

  if (encounter.status === 'COMPLETED' || encounter.status === 'CANCELLED') {
    return (
      <div className="flex flex-col items-center gap-3 p-12 text-center">
        <p className="text-lg font-semibold">This encounter is {encounter.status.toLowerCase()}.</p>
        <Link to="/opd" className="text-sm text-primary underline underline-offset-4">
          Back to queue
        </Link>
      </div>
    )
  }

  // consultationQuery.data is undefined while loading, null once loaded
  // with no match — the encounter is OPEN but nobody's clicked "Start
  // consultation" yet for it (or this page was reached by direct
  // navigation) — offer to start it right here instead of dead-ending.
  if (!consultationQuery.data) {
    return (
      <div className="flex flex-col items-center gap-3 p-12 text-center">
        <p className="text-lg font-semibold">Consultation not started yet.</p>
        <Button
          className="gap-1.5"
          disabled={startConsultation.isPending}
          onClick={() => {
            startConsultation.mutate(
              { encounter_id: encounterId },
              { onError: (error) => toast.error('Could not start consultation', { description: getErrorMessage(error) }) },
            )
          }}
        >
          {startConsultation.isPending ? 'Starting…' : 'Start consultation'}
        </Button>
      </div>
    )
  }

  if (!patientQuery.data) {
    return (
      <div className="p-6 text-sm text-destructive">
        Could not load this patient. {getErrorMessage(patientQuery.error)}
      </div>
    )
  }

  return <ConsultationPad consultation={consultationQuery.data} encounterId={encounterId} patient={patientQuery.data} />
}
