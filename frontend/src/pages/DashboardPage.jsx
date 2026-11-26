import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchSummary, fetchTasks } from '../api'
import { supabase } from '../supabase'
import SummaryWidgets from '../components/SummaryWidgets'
import TaskCard from '../components/TaskCard'

/**
 * User Story 4.1.1 (AB#19): all upcoming tasks from all synced courses on one screen.
 *
 * Layout (docs/ui/dashboard.md):
 *   header (title, sign out)
 *   summary widgets: overdue / due today / this week (US 4.1.3, AB#21)
 *   task list, soonest deadline first (the backend's order; date sections: US 4.2.1, AB#23)
 */
export default function DashboardPage({ token }) {
  const navigate = useNavigate()
  const [state, setState] = useState({ status: 'loading', tasks: [], summary: null, error: '' })

  const load = useCallback(async () => {
    setState((s) => ({ ...s, status: 'loading', error: '' }))
    try {
      // The list is required. The summary is extra: if it fails the widgets show a dash and
      // the list still works (a 401 on the summary also fails the list, which signs out below).
      const [tasks, summary] = await Promise.all([fetchTasks(token), fetchSummary(token).catch(() => null)])
      setState({ status: 'ready', tasks, summary, error: '' })
    } catch (err) {
      if (err.status === 401) {
        await supabase.auth.signOut()
        navigate('/login', { replace: true })
        return
      }
      setState({ status: 'error', tasks: [], summary: null, error: err.message })
    }
  }, [token, navigate])

  useEffect(() => {
    load()
  }, [load])

  async function signOut() {
    await supabase.auth.signOut()
    navigate('/login', { replace: true })
  }

  const courseCount = new Set(state.tasks.map((t) => t.course_name ?? '')).size

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>My tasks</h1>
        <button type="button" className="link-button" onClick={signOut}>Sign out</button>
      </header>

      {state.status === 'ready' && <SummaryWidgets summary={state.summary} />}

      <main>
        {state.status === 'loading' && (
          <p className="status" role="status" aria-live="polite">Loading your tasks…</p>
        )}

        {state.status === 'error' && (
          <div className="status error" role="alert">
            <p>{state.error}</p>
            <button type="button" onClick={load}>Retry</button>
          </div>
        )}

        {state.status === 'ready' && state.tasks.length === 0 && (
          <div className="status empty">
            <h2>No tasks yet</h2>
            <p>Open Moodle in Chrome with the extension installed, and your assignments will appear here after the next sync.</p>
          </div>
        )}

        {state.status === 'ready' && state.tasks.length > 0 && (
          <>
            <p className="summary">
              {state.tasks.length} {state.tasks.length === 1 ? 'task' : 'tasks'} from {courseCount}{' '}
              {courseCount === 1 ? 'course' : 'courses'}
            </p>
            <ul className="task-list" aria-label="Tasks">
              {state.tasks.map((task) => (
                <li key={task.moodle_id}>
                  <TaskCard task={task} />
                </li>
              ))}
            </ul>
          </>
        )}
      </main>
    </div>
  )
}
