// Triggers a browser "Save As" for an in-memory Blob — used by the CSV
// export buttons (Billing, Reports). The object URL is revoked right after
// the click since the browser has already captured what it needs from it
// by then; keeping it around would just leak memory.
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
