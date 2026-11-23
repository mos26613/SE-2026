// Settings from the root .env (see .env.example). Vite only exposes VITE_* names.
export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')
export const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || ''
// The anon/public key: safe in the browser, Row Level Security protects the data.
// Never put the service_role key or GEMINI_API_KEY in a VITE_ variable.
export const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || ''
