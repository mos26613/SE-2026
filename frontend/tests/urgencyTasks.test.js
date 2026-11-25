import { describe, expect, it } from "vitest";
import {
  annotateTasksWithUrgency,
  getTaskUrgency,
} from "../src/chronologicalTasks.js";

const referenceNow = new Date("2026-11-26T10:00:00");

const overdueTask = { id: "1", title: "Late Homework", due_date: "2026-11-25T23:59:00" };
const urgentTask = { id: "2", title: "Quiz Tomorrow", due_date: "2026-11-27T08:00:00" };
const normalTask = { id: "3", title: "Final Project", due_date: "2026-12-05T18:00:00" };
const noDeadlineTask = { id: "4", title: "Reading", due_date: null };

describe("urgencyTasks (AB#26)", () => {
  it("classifies overdue, urgent, and normal deadlines consistently", () => {
    expect(getTaskUrgency(overdueTask, referenceNow)).toBe("overdue");
    expect(getTaskUrgency(urgentTask, referenceNow)).toBe("urgent");
    expect(getTaskUrgency(normalTask, referenceNow)).toBe("normal");
    expect(getTaskUrgency(noDeadlineTask, referenceNow)).toBe("normal");
  });

  it("annotates sorted tasks with urgency metadata and badges", () => {
    const annotated = annotateTasksWithUrgency(
      [normalTask, overdueTask, noDeadlineTask, urgentTask],
      referenceNow
    );

    expect(annotated.map((t) => [t.id, t.urgency, t.highlightBadge])).toEqual([
      ["1", "overdue", "Overdue"],
      ["2", "urgent", "Urgent"],
      ["3", "normal", null],
      ["4", "normal", null],
    ]);
  });
});