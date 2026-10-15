import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { get, post, setSessionExpiredHandler, tokens } from '../api/client'
import type { Role, User } from '../api/types'

interface AuthState {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  hasRole: (...roles: Role[]) => boolean
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const queryClient = useQueryClient()

  useEffect(() => {
    setSessionExpiredHandler(() => {
      setUser(null)
      queryClient.clear()
    })
    if (!tokens.access) {
      setLoading(false)
      return
    }
    get<User>('/auth/me/')
      .then(setUser)
      .catch(() => tokens.clear())
      .finally(() => setLoading(false))
  }, [queryClient])

  const login = useCallback(async (username: string, password: string) => {
    const data = await post<{ access: string; refresh: string; user: User }>('/auth/login/', { username, password })
    tokens.set(data.access, data.refresh)
    setUser(data.user)
  }, [])

  const logout = useCallback(async () => {
    const refresh = tokens.refresh
    try {
      if (refresh) await post('/auth/logout/', { refresh })
    } catch {
      /* the token is discarded locally either way */
    }
    tokens.clear()
    queryClient.clear()
    setUser(null)
  }, [queryClient])

  const hasRole = useCallback((...roles: Role[]) => !!user && roles.includes(user.role), [user])

  const value = useMemo(() => ({ user, loading, login, logout, hasRole }), [user, loading, login, logout, hasRole])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}

/** The signed-in user (pages behind the auth guard can rely on it). */
export function useUser(): User {
  const { user } = useAuth()
  if (!user) throw new Error('No signed-in user')
  return user
}
