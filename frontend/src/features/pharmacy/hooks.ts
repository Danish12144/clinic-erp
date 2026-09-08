import { useQuery } from '@tanstack/react-query'
import { searchMedicines } from '@/features/pharmacy/api'
import { useAuth } from '@/features/auth/auth-context'
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
