import { describe, expect, it } from "vitest";
import {
  getDateSectionLabel,
  groupTasksChronologically,
  sortTasksChronologically,
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

describe("chronologicalTasks (AB#23)", () => {
  it("sorts tasks chronologically by deadline and puts tasks without deadline last", () => {
    const sorted = sortTasksChronologically(sampleTasks);
    expect(sorted.map((t) => t.id)).toEqual([
      "overdue",
      "today",
      "tomorrow",
      "this-week",
      "later",
      "no-date",
    ]);
  });

  it("assigns accurate date section labels", () => {
    expect(getDateSectionLabel(sampleTasks[2], referenceNow)).toBe("Today");
    expect(getDateSectionLabel(sampleTasks[3], referenceNow)).toBe("Tomorrow");
    expect(getDateSectionLabel(sampleTasks[4], referenceNow)).toBe("Overdue");
    expect(getDateSectionLabel(sampleTasks[5], referenceNow)).toBe("This Week");
    expect(getDateSectionLabel(sampleTasks[0], referenceNow)).toBe("Later");
    expect(getDateSectionLabel(sampleTasks[1], referenceNow)).toBe("No Deadline");
  });

  it("groups tasks into non-empty sections in chronological order", () => {
    const grouped = groupTasksChronologically(sampleTasks, referenceNow);
    expect(grouped.map((g) => g.section)).toEqual([
      "Overdue",
      "Today",
      "Tomorrow",
      "This Week",
      "Later",
      "No Deadline",
    ]);
  });
});