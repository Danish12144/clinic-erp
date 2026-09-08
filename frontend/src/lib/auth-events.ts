// Lets the Axios layer (outside the React tree) tell AuthContext a session
// died — refresh failed, or there was never a session to begin with — without
// either module importing the other. AuthContext subscribes once and clears
// its state / redirects to /login in response.

const SESSION_EXPIRED_EVENT = 'clinic_erp:session-expired'

export function emitSessionExpired(): void {
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
}

export function onSessionExpired(handler: () => void): () => void {
  window.addEventListener(SESSION_EXPIRED_EVENT, handler)
  return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handler)
}
