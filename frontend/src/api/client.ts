import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'

const BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '') + '/api'

const ACCESS = 'cmrs.access'
const REFRESH = 'cmrs.refresh'

export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS)
  },
  get refresh() {
    return localStorage.getItem(REFRESH)
  },
  set(access: string, refresh?: string) {
    localStorage.setItem(ACCESS, access)
    if (refresh) localStorage.setItem(REFRESH, refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS)
    localStorage.removeItem(REFRESH)
  },
}

/** The backend always answers errors as {error: {code, message, details}}. */
export class ApiError extends Error {
  code: string
  status: number
  details: Record<string, unknown>
  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
  /** Field-level validation messages, if any: {field: "message"} */
  get fieldErrors(): Record<string, string> {
    if (this.code !== 'VALIDATION_ERROR') return {}
    const out: Record<string, string> = {}
    for (const [k, v] of Object.entries(this.details)) out[k] = Array.isArray(v) ? String(v[0]) : String(v)
    return out
  }
}

export const http = axios.create({ baseURL: BASE, timeout: 20000 })

http.interceptors.request.use((config) => {
  const access = tokens.access
  if (access) config.headers.Authorization = `Bearer ${access}`
  return config
})

let refreshing: Promise<string | null> | null = null
let onSessionExpired: () => void = () => {}
export const setSessionExpiredHandler = (fn: () => void) => {
  onSessionExpired = fn
}

async function refreshAccess(): Promise<string | null> {
  const refresh = tokens.refresh
  if (!refresh) return null
  try {
    const { data } = await axios.post(`${BASE}/auth/refresh/`, { refresh })
    tokens.set(data.access, data.refresh)
    return data.access
  } catch {
    return null
  }
}

http.interceptors.response.use(
  (res) => res,
  async (error: AxiosError<{ error?: { code: string; message: string; details?: Record<string, unknown> } }>) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined
    const isAuthCall = original?.url?.includes('/auth/login') || original?.url?.includes('/auth/refresh')
    if (error.response?.status === 401 && original && !original._retried && !isAuthCall) {
      original._retried = true
      refreshing ??= refreshAccess().finally(() => (refreshing = null))
      const access = await refreshing
      if (access) {
        original.headers.Authorization = `Bearer ${access}`
        return http(original)
      }
      tokens.clear()
      onSessionExpired()
    }
    if (!error.response) {
      throw new ApiError(0, 'NETWORK_ERROR', 'Cannot reach the server. Check your connection and try again.')
    }
    const body = error.response.data?.error
    throw new ApiError(
      error.response.status,
      body?.code ?? 'ERROR',
      body?.message ?? `Request failed (${error.response.status})`,
      body?.details ?? {},
    )
  },
)

/** Drop empty filter values so they don't reach the query string. */
export function clean(params: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined))
}

export async function get<T>(url: string, params: Record<string, unknown> = {}) {
  return (await http.get<T>(url, { params: clean(params) })).data
}

export async function post<T>(url: string, body: unknown = {}) {
  return (await http.post<T>(url, body)).data
}

export async function patch<T>(url: string, body: unknown = {}) {
  return (await http.patch<T>(url, body)).data
}
