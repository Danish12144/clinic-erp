// Mirrors backend/app/modules/pharmacy/schemas.py's MedicineSummary — only
// the fields the Rx pad's autocomplete needs.

export interface MedicineSummary {
  id: string
  name: string
  generic_name: string | null
  dosage_form: string | null
  strength: string | null
  is_active: boolean
}

export interface MedicineListResponse {
  items: MedicineSummary[]
  total: number
  limit: number
  offset: number
}
