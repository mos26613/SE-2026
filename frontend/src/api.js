import { API_URL } from './config'

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

/** GET /api/tasks: the student's relevant tasks from all courses, soonest deadline first. */
export async function fetchTasks(accessToken) {
  let response
  try {
    response = await fetch(`${API_URL}/api/tasks`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  } catch {
    throw new ApiError(0, 'Could not reach the server. Check your connection and try again.')
  }
  if (response.status === 401) throw new ApiError(401, 'Your session has expired. Please sign in again.')
  if (!response.ok) throw new ApiError(response.status, 'Could not load your tasks. Please try again.')
  return response.json()
}

/**
 * GET /api/tasks/summary: how many open tasks are overdue, due within 24 hours, due within 7 days
 * ({ overdue, due_today, due_this_week, as_of }). Counted by the backend from the same tasks as the list.
 */
export async function fetchSummary(accessToken) {
  let response
  try {
    response = await fetch(`${API_URL}/api/tasks/summary`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  } catch {
    throw new ApiError(0, 'Could not reach the server. Check your connection and try again.')
  }
  if (response.status === 401) throw new ApiError(401, 'Your session has expired. Please sign in again.')
  if (!response.ok) throw new ApiError(response.status, 'Could not load the summary. Please try again.')
  return response.json()
}
