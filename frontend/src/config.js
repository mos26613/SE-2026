// Settings from the root .env (see .env.example). Vite only exposes VITE_* names.

// A value counts as "not set" when it is empty or still the placeholder from .env.example
// ("your-supabase-url-here" ...). Without this, the placeholder URL reaches createClient,
// which throws "Invalid supabaseUrl" and the app never starts.
export function configured(value) {
  return value && !/^your-/i.test(value) ? value : ''
}

export function supabaseUrl(value) {
  const url = configured(value)
  return /^https?:\/\//i.test(url) ? url : ''
}

export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')
export const SUPABASE_URL = supabaseUrl(import.meta.env.VITE_SUPABASE_URL)
// The anon/public key: safe in the browser, Row Level Security protects the data.
// Never put the service_role key or GEMINI_API_KEY in a VITE_ variable.
export const SUPABASE_ANON_KEY = configured(import.meta.env.VITE_SUPABASE_ANON_KEY)
