import { isAxiosError } from 'axios'

interface PydanticValidationDetailItem {
  msg?: string
}

// FastAPI's HTTPException(status, "message") puts a plain string in
// response.data.detail; an unhandled Pydantic RequestValidationError (a
// field that slipped past our own Zod validation but fails a backend
// validator) puts a list of {msg, loc, ...} objects there instead — this
// normalizes both into one readable string.
export function getErrorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (isAxiosError(error)) {
    const detail = error.response?.data?.detail as string | PydanticValidationDetailItem[] | undefined
    if (typeof detail === 'string' && detail.length > 0) return detail
    if (Array.isArray(detail) && detail.length > 0 && typeof detail[0]?.msg === 'string') {
      return detail[0].msg
    }
    if (error.message) return error.message
  }
  if (error instanceof Error) return error.message
  return fallback
}
