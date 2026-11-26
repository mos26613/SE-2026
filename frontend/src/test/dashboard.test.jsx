// User Story 4.1.1 (AB#19): dashboard overview of all upcoming tasks.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../supabase', () => ({
  supabase: { auth: { signOut: vi.fn().mockResolvedValue({}) } },
}))

import DashboardPage from '../pages/DashboardPage'
import { supabase } from '../supabase'

const TASKS = [
  { moodle_id: '1', title: 'Midterm exam', course_name: 'Calculus', due_date: '2026-12-01T09:00:00+02:00', status: 'open' },
  { moodle_id: '2', title: 'Homework 3', course_name: 'Algorithms', due_date: '2026-12-05T23:59:00+02:00', status: 'open' },
  { moodle_id: '3', title: 'Lab report', course_name: 'Physics', due_date: null, status: 'done' },
]

function mockFetch(...responses) {
  const fn = vi.fn()
  for (const r of responses) {
    if (r instanceof Error) fn.mockRejectedValueOnce(r)
    else fn.mockResolvedValueOnce({ ok: r.status < 400, status: r.status, json: async () => r.body })
  }
  vi.stubGlobal('fetch', fn)
  return fn
}

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<DashboardPage token="student-token" />} />
        <Route path="/login" element={<p>Login page</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.unstubAllGlobals())

describe('Dashboard', () => {
  it('calls GET /api/tasks with the student token', async () => {
    const fetch = mockFetch({ status: 200, body: [] })
    renderDashboard()
    await screen.findByText('No tasks yet')
    expect(fetch).toHaveBeenCalledWith('http://api.test/api/tasks', {
      headers: { Authorization: 'Bearer student-token' },
    })
  })

  it('shows a loading state first', async () => {
    mockFetch({ status: 200, body: TASKS })
    renderDashboard()
    expect(screen.getByRole('status')).toHaveTextContent('Loading your tasks')
    await screen.findByText('Midterm exam')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('AC1: shows tasks from all synced courses, in the order the API returns', async () => {
    mockFetch({ status: 200, body: TASKS })
    renderDashboard()
    const list = await screen.findByRole('list', { name: 'Tasks' })
    const cards = within(list).getAllByRole('article')
    expect(cards.map((c) => within(c).getByRole('heading').textContent)).toEqual(['Midterm exam', 'Homework 3', 'Lab report'])
    for (const course of ['Calculus', 'Algorithms', 'Physics']) {
      expect(within(list).getByText(course)).toBeInTheDocument()
    }
    expect(screen.getByText('3 tasks from 3 courses')).toBeInTheDocument()
  })

  it('AC2: shows a clear empty state when there are no tasks', async () => {
    mockFetch({ status: 200, body: [] })
    renderDashboard()
    expect(await screen.findByRole('heading', { name: 'No tasks yet' })).toBeInTheDocument()
    expect(screen.getByText(/Open Moodle in Chrome with the extension/)).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Tasks' })).not.toBeInTheDocument()
  })

  it('shows an error with Retry when the server fails, and Retry reloads', async () => {
    const fetch = mockFetch({ status: 502, body: {} }, { status: 200, body: TASKS })
    renderDashboard()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Could not load your tasks')
    await userEvent.click(within(alert).getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('Midterm exam')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('shows an error when the server cannot be reached', async () => {
    mockFetch(new TypeError('Failed to fetch'))
    renderDashboard()
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the server')
  })

  it('signs out and goes to the login page when the session expired (401)', async () => {
    mockFetch({ status: 401, body: {} })
    renderDashboard()
    expect(await screen.findByText('Login page')).toBeInTheDocument()
    expect(supabase.auth.signOut).toHaveBeenCalled()
  })
})
