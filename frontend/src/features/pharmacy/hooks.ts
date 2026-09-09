import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  checkoutOtcSale,
  createMedicine,
  dispensePrescriptionItem,
  getMedicine,
  receiveStock,
  searchMedicineBatches,
  searchMedicines,
  searchMedicinesFull,
  searchOtcSales,
  updateMedicine,
} from '@/features/pharmacy/api'
import { useAuth } from '@/features/auth/auth-context'
import type {
  DispenseRequest,
  MedicineCreateRequest,
  MedicineSearchParams,
  MedicineUpdateRequest,
  OTCSaleCreateRequest,
  ReceiveStockRequest,
  SaleSearchParams,
} from '@/features/pharmacy/types'
import { useDebouncedValue } from '@/lib/use-debounced-value'

// Never throws into the UI — a clinic with pharmacy.view_catalog withheld,
// or any other transient failure, just means the Rx pad's drug field falls
// back to plain free text instead of catalog suggestions (see RxTable).
export function useMedicineSearch(rawQuery: string) {
  const { hasPermission } = useAuth()
  const debounced = useDebouncedValue(rawQuery, 300)

  return useQuery({
    queryKey: ['pharmacy', 'medicines', 'search', debounced],
    queryFn: () => searchMedicines(debounced),
    enabled: hasPermission('pharmacy.view_catalog') && debounced.trim().length >= 2,
    retry: false,
  })
}

export function useMedicineCatalog(params: MedicineSearchParams) {
  return useQuery({
    queryKey: ['pharmacy', 'medicines', 'catalog', params],
    queryFn: () => searchMedicinesFull(params),
    placeholderData: keepPreviousData,
  })
}

export function useMedicineBatches(medicineId: string | undefined) {
  return useQuery({
    queryKey: ['pharmacy', 'medicines', 'batches', medicineId],
    queryFn: () => searchMedicineBatches(medicineId!),
    enabled: Boolean(medicineId),
  })
}

function useInvalidateCatalog() {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: ['pharmacy', 'medicines'] })
}

export function useCreateMedicine() {
  const invalidate = useInvalidateCatalog()
  return useMutation({
    mutationFn: (payload: MedicineCreateRequest) => createMedicine(payload),
    onSuccess: invalidate,
  })
}

export function useUpdateMedicine() {
  const invalidate = useInvalidateCatalog()
  return useMutation({
    mutationFn: ({ medicineId, payload }: { medicineId: string; payload: MedicineUpdateRequest }) =>
      updateMedicine(medicineId, payload),
    onSuccess: invalidate,
  })
}

export function useReceiveStock() {
  const invalidate = useInvalidateCatalog()
  return useMutation({
    mutationFn: ({ medicineId, payload }: { medicineId: string; payload: ReceiveStockRequest }) =>
      receiveStock(medicineId, payload),
    onSuccess: invalidate,
  })
}

export function useMedicine(medicineId: string | undefined) {
  return useQuery({
    queryKey: ['pharmacy', 'medicines', 'get', medicineId],
    queryFn: () => getMedicine(medicineId!),
    enabled: Boolean(medicineId),
  })
}

export function useDispensePrescriptionItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: DispenseRequest) => dispensePrescriptionItem(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['prescriptions'] })
      void queryClient.invalidateQueries({ queryKey: ['pharmacy', 'medicines'] })
    },
  })
}

export function useOtcSales(params: SaleSearchParams) {
  const { hasPermission } = useAuth()
  return useQuery({
    queryKey: ['pharmacy', 'sales', 'search', params],
    queryFn: () => searchOtcSales(params),
    enabled: hasPermission('pharmacy.dispense') || hasPermission('pharmacy.sell_otc'),
    retry: false,
    placeholderData: keepPreviousData,
  })
}

export function useCheckoutOtcSale() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: OTCSaleCreateRequest) => checkoutOtcSale(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['pharmacy', 'sales'] })
      void queryClient.invalidateQueries({ queryKey: ['pharmacy', 'medicines'] })
    },
  })
}
