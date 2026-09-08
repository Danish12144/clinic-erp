import { QueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (failureCount, error) => {
        // A 401 here has already been through apiClient's refresh-and-retry
        // interceptor and still failed — retrying it again at the query
        // layer would just repeat the same doomed request.
        if (isAxiosError(error) && error.response?.status === 401) return false
        return failureCount < 2
      },
    },
  },
})
