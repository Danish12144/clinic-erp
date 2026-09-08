import { apiClient } from '@/lib/api-client'

// Backend's Prescription/etc. summaries return pdf_download_url as
// "/api/v1/files/{id}/content" — a path that already includes /api/v1,
// which apiClient's baseURL also includes. Don't pass that string to
// apiClient directly (it would double up); build the request from the
// document id instead.
export async function downloadDocumentBlob(documentId: string): Promise<Blob> {
  const { data } = await apiClient.get<Blob>(`/files/${documentId}/content`, { responseType: 'blob' })
  return data
}
