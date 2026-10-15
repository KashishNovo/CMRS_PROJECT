import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'
import type { Branch, Paginated, User } from '../api/types'

export function useBranches() {
  return useQuery({
    queryKey: ['branches'],
    queryFn: () => get<Paginated<Branch>>('/branches/', { page_size: 200 }),
    staleTime: 5 * 60_000,
    select: (d) => d.results,
  })
}

export function useAgents(branch?: string | number | null, enabled = true) {
  return useQuery({
    queryKey: ['agents', branch ?? 'all'],
    queryFn: () => get<Paginated<User>>('/users/', { role: 'AGENT', branch: branch ?? '', page_size: 200 }),
    staleTime: 5 * 60_000,
    enabled,
    select: (d) => d.results,
  })
}

/** Small state holder for list filters + paging; resets to page 1 when a filter changes. */
export function useFilters<T extends Record<string, string>>(initial: T) {
  const [filters, setFilters] = useState<T>(initial)
  const [page, setPage] = useState(1)
  const set = (patch: Partial<T>) => {
    setFilters((f) => ({ ...f, ...patch }))
    setPage(1)
  }
  const params = useMemo(() => ({ ...filters, page }), [filters, page])
  return { filters, set, page, setPage, params, reset: () => { setFilters(initial); setPage(1) } }
}
