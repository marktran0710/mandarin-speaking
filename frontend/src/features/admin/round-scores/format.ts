const completedAtFormatter = new Intl.DateTimeFormat("en", {
  dateStyle: "medium",
  timeStyle: "short",
});

const completedDateFormatter = new Intl.DateTimeFormat("en", { dateStyle: "medium" });

export function formatCompletedAt(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : completedAtFormatter.format(date);
}

export function formatCompletedDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : completedDateFormatter.format(date);
}
