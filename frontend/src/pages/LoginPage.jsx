import { useState } from 'react'
import { supabase } from '../supabase'

// PLACEHOLDER until User Story 1.1.2 (AB#188, student sign-in). Just enough to get a
// Supabase session so the dashboard can call the API. No sign-up or password reset.
export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    const { error: signInError } = await supabase.auth.signInWithPassword({ email, password })
    if (signInError) setError('Wrong email or password.')
    setBusy(false)
    // On success, App sees the new session and opens the dashboard.
  }

  return (
    <main className="login">
      <h1>Smart Student Task Hub</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
        </label>
        {error && <p role="alert" className="error-text">{error}</p>}
        <button type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </main>
  )
}
