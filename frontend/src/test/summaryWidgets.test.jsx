// User Story 4.1.3 (AB#21), task AB#53: the summary widgets and their API call.
import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, fetchSummary } from '../api'
import SummaryWidgets from '../components/SummaryWidgets'

afterEach(() => vi.unstubAllGlobals())

describe('SummaryWidgets', () => {
  it('shows the three counts with their labels and windows', () => {
    render(<SummaryWidgets summary={{ overdue: 3, due_today: 1, due_this_week: 7 }} />)
    const widgets = screen.getByRole('region', { name: 'Summary' })
    expect(within(widgets).getByLabelText('Overdue: 3')).toHaveTextContent('3')
    expect(within(widgets).getByLabelText('Due today: 1')).toHaveTextContent('1')
    expect(within(widgets).getByLabelText('This week: 7')).toHaveTextContent('7')
    expect(within(widgets).getByText('next 24 hours')).toBeInTheDocument()
    expect(within(widgets).getByText('next 7 days')).toBeInTheDocument()
  })

  it('shows 0, not a dash, when nothing is due', () => {
    render(<SummaryWidgets summary={{ overdue: 0, due_today: 0, due_this_week: 0 }} />)
    expect(screen.getByLabelText('Overdue: 0')).toHaveTextContent('0')
  })

  it('highlights Overdue only when something is overdue', () => {
    const { container, rerender } = render(<SummaryWidgets summary={{ overdue: 2, due_today: 0, due_this_week: 0 }} />)
    expect(container.querySelector('.widget-overdue')).toHaveClass('widget-alert')
    rerender(<SummaryWidgets summary={{ overdue: 0, due_today: 5, due_this_week: 5 }} />)
    expect(container.querySelector('.widget-overdue')).not.toHaveClass('widget-alert')
    expect(container.querySelector('.widget-due_today')).not.toHaveClass('widget-alert')
  })

  it('shows dashes when there is no summary', () => {
    render(<SummaryWidgets summary={null} />)
    for (const label of ['Overdue', 'Due today', 'This week']) {
      expect(screen.getByLabelText(`${label}: unavailable`)).toHaveTextContent('—')
    }
  })
})

describe('fetchSummary', () => {
  function stub(response) {
    const fn = vi.fn().mockImplementation(() => (response instanceof Error ? Promise.reject(response) : Promise.resolve(response)))
    vi.stubGlobal('fetch', fn)
    return fn
  }

  it('calls GET /api/tasks/summary with the token and returns the counts', async () => {
    const body = { overdue: 1, due_today: 2, due_this_week: 3, as_of: '2026-11-26T12:00:00+02:00' }
    const fetch = stub({ ok: true, status: 200, json: async () => body })
    expect(await fetchSummary('tok')).toEqual(body)
    expect(fetch).toHaveBeenCalledWith('http://api.test/api/tasks/summary', { headers: { Authorization: 'Bearer tok' } })
  })

  it('maps 401, server errors and an unreachable server to ApiError', async () => {
    stub({ ok: false, status: 401 })
    await expect(fetchSummary('t')).rejects.toMatchObject({ status: 401 })
    stub({ ok: false, status: 502 })
    await expect(fetchSummary('t')).rejects.toBeInstanceOf(ApiError)
    stub(new TypeError('Failed to fetch'))
    await expect(fetchSummary('t')).rejects.toMatchObject({ status: 0 })
  })
})
