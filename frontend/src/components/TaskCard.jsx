import { formatDeadline } from '../format'

/** One task: title, course, deadline and status (task AB#109). */
export default function TaskCard({ task }) {
  const done = task.status === 'done'
  const title = task.moodle_url ? (
    <a href={task.moodle_url} target="_blank" rel="noreferrer">{task.title}</a>
  ) : (
    task.title
  )

  return (
    <article className={`task-card${done ? ' done' : ''}`} aria-label={task.title}>
      <h3 className="task-title" dir="auto">{title}</h3>
      <p className="task-course" dir="auto">{task.course_name || 'No course'}</p>
      <p className="task-deadline">
        <span className="visually-hidden">Deadline: </span>
        <time dateTime={task.due_date ?? undefined}>{formatDeadline(task.due_date)}</time>
      </p>
      <span className={`task-status ${done ? 'status-done' : 'status-open'}`}>{done ? 'Done' : 'Open'}</span>
      {task.ai_summary && <p className="task-summary" dir="auto">{task.ai_summary}</p>}
    </article>
  )
}
