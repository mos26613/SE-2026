// Placeholder sign-in page: clear messages for wrong credentials vs. other failures.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../supabase', () => ({ supabase: { auth: { signInWithPassword: vi.fn() } } }))

import LoginPage from '../pages/LoginPage'
import { supabase } from '../supabase'

async function signIn() {
  render(<LoginPage />)
  await userEvent.type(screen.getByLabelText('Email'), 'test1@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'secret')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
}

beforeEach(() => vi.clearAllMocks())

describe('LoginPage', () => {
  it('says "wrong email or password" only for invalid credentials', async () => {
    supabase.auth.signInWithPassword.mockResolvedValue({ error: { code: 'invalid_credentials', message: 'Invalid login credentials' } })
    await signIn()
    expect(await screen.findByRole('alert')).toHaveTextContent('Wrong email or password.')
  })

  it('shows the real reason for other failures', async () => {
    supabase.auth.signInWithPassword.mockResolvedValue({ error: { message: 'Failed to fetch' } })
    await signIn()
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not sign in: Failed to fetch')
  })
})
