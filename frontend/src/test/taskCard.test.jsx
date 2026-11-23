// Task AB#109: task card with title, course, deadline and status.
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import TaskCard from '../components/TaskCard'

describe('TaskCard', () => {
  it('shows title, course, deadline in Israel time and status', () => {
    render(
      <TaskCard
        task={{
          moodle_id: '1',
          title: 'Homework 3',
          course_name: 'Algorithms',
          due_date: '2026-12-05T21:59:00Z', // 23:59 in Israel
          status: 'open',
          moodle_url: 'https://moodle.example.ac.il/mod/assign/view.php?id=1',
          ai_summary: 'Solve exercises 1-4',
        }}
      />,
    )
    expect(screen.getByRole('link', { name: 'Homework 3' })).toHaveAttribute('href', 'https://moodle.example.ac.il/mod/assign/view.php?id=1')
    expect(screen.getByText('Algorithms')).toBeInTheDocument()
    expect(screen.getByText(/5 Dec 2026.*23:59/)).toBeInTheDocument()
    expect(screen.getByText('Open')).toBeInTheDocument()
    expect(screen.getByText('Solve exercises 1-4')).toBeInTheDocument()
  })

  it('handles a task without course, deadline or link, and a done task', () => {
    render(<TaskCard task={{ moodle_id: '2', title: 'תרגיל בית 4', course_name: null, due_date: null, status: 'done' }} />)
    expect(screen.getByRole('heading', { name: 'תרגיל בית 4' })).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('No course')).toBeInTheDocument()
    expect(screen.getByText('No deadline')).toBeInTheDocument()
    expect(screen.getByText('Done')).toBeInTheDocument()
  })
})
