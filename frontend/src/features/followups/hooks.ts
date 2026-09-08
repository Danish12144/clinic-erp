import { useMutation } from '@tanstack/react-query'
import { createFollowUp } from '@/features/followups/api'
import type { FollowUpCreateRequest } from '@/features/followups/types'

export function useCreateFollowUp() {
  return useMutation({
    mutationFn: (payload: FollowUpCreateRequest) => createFollowUp(payload),
  })
}
