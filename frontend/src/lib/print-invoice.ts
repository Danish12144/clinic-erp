// Client-side-only printable receipt — there is no backend PDF generation
// for invoices (unlike prescriptions, which get a real server-rendered
// PDF via app/modules/consultation/pdf.py); building one here would need
// a new backend endpoint, so this opens a plain HTML document in a new
// tab and calls window.print() on it, the same "print what the browser
// can already render" approach used for the prescription PDF preview's
// own Print button (iframe.contentWindow.print()), just without a PDF
// source to point an iframe at.

interface PrintableInvoiceLineItem {
  description: string
  quantity: string | number
  unit_price: string
  total: string
  source_type: string
}

interface PrintableInvoicePayment {
  amount: string
  method: string
  recorded_at: string
}

export interface PrintableInvoice {
  clinicName: string
  clinicGstNumber: string | null
  branchName: string | null
  branchAddress: string | null
  branchPhone: string | null
  patientName: string
  patientMrn: string
  invoiceId: string
  status: string
  paymentStatus: string
  createdAt: string
  lineItems: PrintableInvoiceLineItem[]
  subtotal: string
  tax: string
  discount: string
  total: string
  totalPaid: string
  balanceDue: string
  payments: PrintableInvoicePayment[]
}

function money(value: string | number): string {
  return `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
}

function renderReceiptHtml(invoice: PrintableInvoice): string {
  const rows = invoice.lineItems
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.description)}</td>
          <td class="right">${item.quantity}</td>
          <td class="right">${money(item.unit_price)}</td>
          <td class="right">${money(item.total)}</td>
        </tr>`,
    )
    .join('')

  const paymentRows = invoice.payments.length
    ? invoice.payments
        .map(
          (p) => `
        <tr>
          <td>${new Date(p.recorded_at).toLocaleString()}</td>
          <td>${escapeHtml(p.method)}</td>
          <td class="right">${money(p.amount)}</td>
        </tr>`,
        )
        .join('')
    : '<tr><td colspan="3">No payments recorded</td></tr>'

  return `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>Invoice ${escapeHtml(invoice.invoiceId.slice(0, 8))}</title>
<style>
  body { font-family: -apple-system, Segoe UI, Arial, sans-serif; color: #0f172a; margin: 2rem; }
  h1 { font-size: 1.25rem; margin: 0 0 0.25rem; }
  .muted { color: #64748b; font-size: 0.85rem; }
  .header { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #0f172a; padding-bottom: 1rem; margin-bottom: 1rem; }
  .status { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 0.8rem; font-weight: 600; background: #dcfce7; color: #166534; }
  .status.not-paid { background: #fef3c7; color: #92400e; }
  .status.void { background: #fee2e2; color: #991b1b; }
  table { width: 100%; border-collapse: collapse; margin-top: 0.75rem; }
  th, td { padding: 0.4rem 0.3rem; text-align: left; border-bottom: 1px solid #e2e8f0; font-size: 0.9rem; }
  th { color: #64748b; font-weight: 600; font-size: 0.8rem; text-transform: uppercase; }
  .right { text-align: right; }
  .totals { margin-top: 0.75rem; width: 260px; margin-left: auto; }
  .totals div { display: flex; justify-content: space-between; padding: 0.2rem 0; font-size: 0.9rem; }
  .totals .grand { font-weight: 700; border-top: 1px solid #0f172a; margin-top: 0.3rem; padding-top: 0.4rem; }
  @media print { body { margin: 0.5in; } }
</style>
</head>
<body>
  <div class="header">
    <div>
      <h1>${escapeHtml(invoice.clinicName)}</h1>
      ${invoice.branchName ? `<div class="muted">${escapeHtml(invoice.branchName)}</div>` : ''}
      ${invoice.branchAddress ? `<div class="muted">${escapeHtml(invoice.branchAddress)}</div>` : ''}
      ${invoice.branchPhone ? `<div class="muted">Ph: ${escapeHtml(invoice.branchPhone)}</div>` : ''}
      ${invoice.clinicGstNumber ? `<div class="muted">GSTIN: ${escapeHtml(invoice.clinicGstNumber)}</div>` : ''}
    </div>
    <div style="text-align: right">
      <div class="muted">Invoice #${escapeHtml(invoice.invoiceId.slice(0, 8).toUpperCase())}</div>
      <div class="muted">${new Date(invoice.createdAt).toLocaleString()}</div>
      <div style="margin-top: 0.4rem">
        <span class="status ${invoice.paymentStatus === 'PAID' ? '' : invoice.status === 'VOID' ? 'void' : 'not-paid'}">${escapeHtml(invoice.paymentStatus)}</span>
      </div>
    </div>
  </div>

  <div class="muted">Billed to</div>
  <div><strong>${escapeHtml(invoice.patientName)}</strong> · MRN ${escapeHtml(invoice.patientMrn)}</div>

  <table>
    <thead><tr><th>Description</th><th class="right">Qty</th><th class="right">Unit price</th><th class="right">Total</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="4">No line items</td></tr>'}</tbody>
  </table>

  <div class="totals">
    <div><span>Subtotal</span><span>${money(invoice.subtotal)}</span></div>
    <div><span>Tax</span><span>${money(invoice.tax)}</span></div>
    <div><span>Discount</span><span>-${money(invoice.discount)}</span></div>
    <div class="grand"><span>Total</span><span>${money(invoice.total)}</span></div>
    <div><span>Paid</span><span>${money(invoice.totalPaid)}</span></div>
    <div><span>Balance due</span><span>${money(invoice.balanceDue)}</span></div>
  </div>

  <div class="muted" style="margin-top: 1.5rem">Payments</div>
  <table>
    <thead><tr><th>Date</th><th>Method</th><th class="right">Amount</th></tr></thead>
    <tbody>${paymentRows}</tbody>
  </table>
</body>
</html>`
}

export function openInvoicePrintView(invoice: PrintableInvoice): void {
  const printWindow = window.open('', '_blank', 'noopener,noreferrer,width=800,height=1000')
  if (!printWindow) return
  printWindow.document.write(renderReceiptHtml(invoice))
  printWindow.document.close()
  printWindow.onload = () => {
    printWindow.focus()
    printWindow.print()
  }
}
