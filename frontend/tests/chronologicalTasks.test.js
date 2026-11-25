import assert from "node:assert/strict";
import {
  sortTasksChronologically,
  getDateSectionLabel,
  groupTasksChronologically,
} from "../src/chronologicalTasks.js";

const referenceNow = new Date("2026-11-26T10:00:00");

const sampleTasks = [
  { id: "later", title: "Final Exam", due_date: "2026-12-10T09:00:00" },
  { id: "no-date", title: "Optional Reading", due_date: null },
  { id: "today", title: "Lab 3", due_date: "2026-11-26T20:00:00" },
  { id: "tomorrow", title: "Quiz 2", due_date: "2026-11-27T12:00:00" },
  { id: "overdue", title: "Past Assignment", due_date: "2026-11-24T18:00:00" },
  { id: "this-week", title: "Project Milestone", due_date: "2026-11-30T15:00:00" },
];

const sorted = sortTasksChronologically(sampleTasks);
assert.deepEqual(
  sorted.map((t) => t.id),
  ["overdue", "today", "tomorrow", "this-week", "later", "no-date"]
);

assert.equal(getDateSectionLabel(sampleTasks[2], referenceNow), "Today");
assert.equal(getDateSectionLabel(sampleTasks[3], referenceNow), "Tomorrow");
assert.equal(getDateSectionLabel(sampleTasks[4], referenceNow), "Overdue");
assert.equal(getDateSectionLabel(sampleTasks[5], referenceNow), "This Week");
assert.equal(getDateSectionLabel(sampleTasks[0], referenceNow), "Later");
assert.equal(getDateSectionLabel(sampleTasks[1], referenceNow), "No Deadline");

const grouped = groupTasksChronologically(sampleTasks, referenceNow);
assert.deepEqual(
  grouped.map((g) => g.section),
  ["Overdue", "Today", "Tomorrow", "This Week", "Later", "No Deadline"]
);

console.log("All chronological sorting and grouping tests passed!");
