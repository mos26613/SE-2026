// Routing: signed-out students see the sign-in page, signed-in students the dashboard.
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

const session = { current: null }
vi.mock('../supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn(async () => ({ data: { session: session.current } })),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
      signOut: vi.fn(),
      signInWithPassword: vi.fn(),
    },
  },
}))

import App from '../App'

afterEach(() => vi.unstubAllGlobals())

describe('App routing', () => {
  it('sends a signed-out student to the sign-in page', async () => {
    session.current = null
    render(<MemoryRouter initialEntries={['/']}><App /></MemoryRouter>)
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('shows the dashboard to a signed-in student', async () => {
    session.current = { access_token: 'tok' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }))
    render(<MemoryRouter initialEntries={['/login']}><App /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'My tasks' })).toBeInTheDocument()
  })
})
