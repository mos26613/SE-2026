/**
 * The three counters above the task list (User Story 4.1.3, AB#21, task AB#53).
 *
 * The numbers come from GET /api/tasks/summary, which counts the same tasks as the list.
 * Windows run from now: overdue = the deadline passed, due today = the next 24 hours,
 * this week = the next 7 days. When the summary could not be loaded (`summary` is null)
 * the widgets show a dash instead of a number, and the list below still works.
 */
const WIDGETS = [
  { key: 'overdue', label: 'Overdue', hint: 'deadline passed' },
  { key: 'due_today', label: 'Due today', hint: 'next 24 hours' },
  { key: 'due_this_week', label: 'This week', hint: 'next 7 days' },
]

export default function SummaryWidgets({ summary }) {
  return (
    <section className="widgets" aria-label="Summary">
      {WIDGETS.map(({ key, label, hint }) => {
        const count = summary ? summary[key] : null
        const alert = key === 'overdue' && count > 0
        return (
          <div key={key} className={`widget widget-${key}${alert ? ' widget-alert' : ''}`}>
            <span className="widget-count" aria-label={`${label}: ${count ?? 'unavailable'}`}>{count ?? '—'}</span>
            <span className="widget-label">{label}</span>
            <span className="widget-hint">{hint}</span>
          </div>
        )
      })}
    </section>
  )
}
