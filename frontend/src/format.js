// Moodle deadlines are Israel time; show them that way wherever the browser is.
const dateFormat = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Jerusalem',
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

export function formatDeadline(isoDate) {
  if (!isoDate) return 'No deadline'
  const date = new Date(isoDate)
  return Number.isNaN(date.getTime()) ? 'No deadline' : dateFormat.format(date)
}
