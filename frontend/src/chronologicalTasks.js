function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function parseDeadline(task) {
  const raw = task?.due_date ?? task?.deadline ?? null;
  if (!raw) return null;
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function sortTasksChronologically(tasks = []) {
  return [...tasks].sort((a, b) => {
    const dateA = parseDeadline(a);
    const dateB = parseDeadline(b);

    if (dateA && dateB) {
      const diff = dateA.getTime() - dateB.getTime();
      if (diff !== 0) return diff;
    } else if (dateA && !dateB) {
      return -1;
    } else if (!dateA && dateB) {
      return 1;
    }

    return String(a?.title ?? "").localeCompare(String(b?.title ?? ""));
  });
}

export function getDateSectionLabel(task, now = new Date()) {
  const deadline = parseDeadline(task);
  if (!deadline) return "No Deadline";

  const todayStart = startOfDay(now);
  const taskDayStart = startOfDay(deadline);
  const diffDays = Math.round((taskDayStart.getTime() - todayStart.getTime()) / (1000 * 60 * 60 * 24));

  if (diffDays < 0) return "Overdue";
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Tomorrow";
  if (diffDays <= 7) return "This Week";
  return "Later";
}

export function groupTasksChronologically(tasks = [], now = new Date()) {
  const sorted = sortTasksChronologically(tasks);
  const sectionOrder = ["Overdue", "Today", "Tomorrow", "This Week", "Later", "No Deadline"];
  const groups = new Map(sectionOrder.map((label) => [label, []]));

  for (const task of sorted) {
    const label = getDateSectionLabel(task, now);
    groups.get(label).push(task);
  }

  return sectionOrder
    .filter((label) => groups.get(label).length > 0)
    .map((label) => ({
      section: label,
      tasks: groups.get(label),
    }));
}
