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

const SUMMARY = { overdue: 2, due_today: 1, due_this_week: 4, as_of: '2026-11-26T12:00:00+02:00' }

// Answers by URL, one response per call: `tasks` for GET /api/tasks (a list of responses, in order),
// `summary` for GET /api/tasks/summary. An Error in a list is a network failure.
function respond(r) {
  if (r instanceof Error) return Promise.reject(r)
  return Promise.resolve({ ok: r.status < 400, status: r.status, json: async () => r.body })
}

function mockFetch(...taskResponses) {
  return mockApi({ tasks: taskResponses, summary: [{ status: 200, body: SUMMARY }] })
}

function mockApi({ tasks, summary }) {
  const queues = { tasks: [...tasks], summary: [...summary] }
  const fn = vi.fn((url) => {
    const queue = url.endsWith('/api/tasks/summary') ? queues.summary : queues.tasks
    // Repeat the last answer when a test reloads more often than it listed responses.
    return respond(queue.length > 1 ? queue.shift() : queue[0])
  })
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
    expect(fetch).toHaveBeenCalledWith('http://api.test/api/tasks/summary', {
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
    expect(fetch).toHaveBeenCalledTimes(4) // tasks + summary, then both again after Retry
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

  // --- Summary widgets (User Story 4.1.3, AB#21) ---

  it('shows the counts from GET /api/tasks/summary above the list', async () => {
    mockFetch({ status: 200, body: TASKS })
    renderDashboard()
    const widgets = await screen.findByRole('region', { name: 'Summary' })
    expect(within(widgets).getByLabelText('Overdue: 2')).toBeInTheDocument()
    expect(within(widgets).getByLabelText('Due today: 1')).toBeInTheDocument()
    expect(within(widgets).getByLabelText('This week: 4')).toBeInTheDocument()
  })

  it('still shows the list, with dashes in the widgets, when the summary fails', async () => {
    mockApi({ tasks: [{ status: 200, body: TASKS }], summary: [{ status: 502, body: {} }] })
    renderDashboard()
    expect(await screen.findByText('Midterm exam')).toBeInTheDocument()
    const widgets = screen.getByRole('region', { name: 'Summary' })
    expect(within(widgets).getByLabelText('Overdue: unavailable')).toHaveTextContent('—')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('refreshes the widgets together with the list on Retry (the numbers follow the data)', async () => {
    mockApi({
      tasks: [{ status: 502, body: {} }, { status: 200, body: TASKS }],
      summary: [{ status: 200, body: SUMMARY }, { status: 200, body: { ...SUMMARY, overdue: 0, due_today: 3 } }],
    })
    renderDashboard()
    await userEvent.click(within(await screen.findByRole('alert')).getByRole('button', { name: 'Retry' }))
    const widgets = await screen.findByRole('region', { name: 'Summary' })
    expect(within(widgets).getByLabelText('Overdue: 0')).toBeInTheDocument()
    expect(within(widgets).getByLabelText('Due today: 3')).toBeInTheDocument()
  })

  it('shows no widgets while loading or when the list failed', async () => {
    mockFetch({ status: 502, body: {} })
    renderDashboard()
    expect(screen.queryByRole('region', { name: 'Summary' })).not.toBeInTheDocument()
    await screen.findByRole('alert')
    expect(screen.queryByRole('region', { name: 'Summary' })).not.toBeInTheDocument()
  })
})
