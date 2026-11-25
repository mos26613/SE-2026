// The .env.example placeholders must count as "not configured" instead of crashing the app.
import { createClient } from '@supabase/supabase-js'
import { describe, expect, it } from 'vitest'
import { configured, supabaseUrl } from '../config'

describe('config', () => {
  it('accepts a real Supabase URL and key', () => {
    expect(supabaseUrl('https://abc.supabase.co')).toBe('https://abc.supabase.co')
    expect(configured('eyJhbGciOi.example')).toBe('eyJhbGciOi.example')
  })

  it('treats empty values and the .env.example placeholders as not set', () => {
    expect(supabaseUrl('')).toBe('')
    expect(supabaseUrl(undefined)).toBe('')
    expect(supabaseUrl('your-supabase-url-here')).toBe('')
    expect(configured('your-supabase-key-here')).toBe('')
  })

  it('treats a URL without http(s) as not set', () => {
    expect(supabaseUrl('abc.supabase.co')).toBe('')
  })

  it('never passes a value to createClient that makes it throw', () => {
    for (const value of ['', 'your-supabase-url-here', 'abc.supabase.co']) {
      expect(() => createClient(supabaseUrl(value) || 'http://localhost', 'key')).not.toThrow()
    }
  })
})
