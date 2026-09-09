import { Plus, Search, ShoppingCart, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useCheckoutOtcSale, useMedicineSearch } from '@/features/pharmacy/hooks'
import { PHARMACY_PAYMENT_METHODS } from '@/features/pharmacy/types'
import { getErrorMessage } from '@/lib/errors'

const METHOD_LABELS: Record<string, string> = {
  CASH: 'Cash',
  CARD: 'Card',
  UPI: 'UPI',
  NET_BANKING: 'Net banking',
  INSURANCE: 'Insurance',
  OTHER: 'Other',
}

interface CartLine {
  medicineId: string
  name: string
  unitPrice: number
  quantity: number
}

function formatMoney(value: number): string {
  return `₹${value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function OtcCheckoutCard() {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const { data: results, isFetching } = useMedicineSearch(query)
  const [cart, setCart] = useState<CartLine[]>([])
  const [customerName, setCustomerName] = useState('')
  const [customerPhone, setCustomerPhone] = useState('')
  const [discount, setDiscount] = useState('0')
  const [paymentMode, setPaymentMode] = useState<(typeof PHARMACY_PAYMENT_METHODS)[number]>('CASH')
  const checkout = useCheckoutOtcSale()

  const subtotal = cart.reduce((sum, line) => sum + line.unitPrice * line.quantity, 0)
  const net = Math.max(0, subtotal - Number(discount || 0))

  function addToCart(medicineId: string, name: string, unitPrice: number) {
    setCart((current) => {
      const existing = current.find((line) => line.medicineId === medicineId)
      if (existing) {
        return current.map((line) => (line.medicineId === medicineId ? { ...line, quantity: line.quantity + 1 } : line))
      }
      return [...current, { medicineId, name, unitPrice, quantity: 1 }]
    })
    setQuery('')
    setOpen(false)
  }

  function updateQuantity(medicineId: string, quantity: number) {
    if (quantity < 1) return
    setCart((current) => current.map((line) => (line.medicineId === medicineId ? { ...line, quantity } : line)))
  }

  function removeLine(medicineId: string) {
    setCart((current) => current.filter((line) => line.medicineId !== medicineId))
  }

  async function handleCheckout() {
    if (cart.length === 0) {
      toast.error('Add at least one item to the cart')
      return
    }
    try {
      const sale = await checkout.mutateAsync({
        customer_name: customerName || undefined,
        customer_phone: customerPhone || undefined,
        items: cart.map((line) => ({ medicine_id: line.medicineId, quantity: line.quantity })),
        discount_amount: discount || '0',
        payment_mode: paymentMode,
      })
      toast.success(`Sale complete — ${formatMoney(Number(sale.net_amount))}`)
      setCart([])
      setCustomerName('')
      setCustomerPhone('')
      setDiscount('0')
    } catch (error) {
      toast.error('Could not complete sale', { description: getErrorMessage(error) })
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5 text-base">
          <ShoppingCart className="size-4" />
          New sale
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-slate-400" />
          <Input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setOpen(true)
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
            placeholder="Search a medicine to add…"
            className="pl-8"
          />
          {open && query.trim().length >= 2 && (isFetching || (results?.items.length ?? 0) > 0) && (
            <div className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-md border border-slate-200 bg-popover shadow-md dark:border-slate-800">
              {isFetching && <p className="px-2 py-1.5 text-xs text-slate-500">Searching…</p>}
              {!isFetching &&
                results?.items.map((medicine) => (
                  <button
                    key={medicine.id}
                    type="button"
                    className="flex w-full items-center justify-between px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
                    onMouseDown={(e) => {
                      e.preventDefault()
                      addToCart(medicine.id, medicine.name, Number(medicine.unit_price))
                    }}
                  >
                    <span>
                      {medicine.name}
                      {medicine.strength ? ` (${medicine.strength})` : ''}
                    </span>
                    <span className="text-xs text-slate-500">{formatMoney(Number(medicine.unit_price))}</span>
                  </button>
                ))}
            </div>
          )}
        </div>

        {cart.length === 0 ? (
          <p className="py-4 text-center text-sm text-slate-500 dark:text-slate-400">Cart is empty.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-slate-100 dark:divide-slate-800">
            {cart.map((line) => (
              <li key={line.medicineId} className="flex items-center justify-between gap-2 py-2 first:pt-0 last:pb-0">
                <div className="flex min-w-0 flex-col">
                  <span className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">{line.name}</span>
                  <span className="text-xs text-slate-500 dark:text-slate-400">{formatMoney(line.unitPrice)} each</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Input
                    type="number"
                    min={1}
                    value={line.quantity}
                    onChange={(e) => updateQuantity(line.medicineId, Number(e.target.value))}
                    className="w-16"
                  />
                  <Button variant="ghost" size="icon-sm" onClick={() => removeLine(line.medicineId)}>
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="customerName">Customer name (optional)</Label>
            <Input id="customerName" value={customerName} onChange={(e) => setCustomerName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="customerPhone">Customer phone (optional)</Label>
            <Input id="customerPhone" value={customerPhone} onChange={(e) => setCustomerPhone(e.target.value)} />
          </div>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="discount">Discount</Label>
            <Input id="discount" type="number" min={0} step="0.01" value={discount} onChange={(e) => setDiscount(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Payment mode</Label>
            <Select value={paymentMode} onValueChange={(v) => setPaymentMode((v ?? 'CASH') as typeof paymentMode)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PHARMACY_PAYMENT_METHODS.map((method) => (
                  <SelectItem key={method} value={method}>
                    {METHOD_LABELS[method]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-slate-200 pt-2 dark:border-slate-800">
          <span className="text-sm text-slate-500 dark:text-slate-400">Net amount</span>
          <span className="text-lg font-semibold text-slate-900 dark:text-slate-100">{formatMoney(net)}</span>
        </div>

        <Button className="gap-1.5" disabled={checkout.isPending} onClick={() => void handleCheckout()}>
          <Plus className="size-4" />
          {checkout.isPending ? 'Completing…' : 'Complete sale'}
        </Button>
      </CardContent>
    </Card>
  )
}
