/** Formats supplied timestamps; never creates a capture timestamp. */
export function formatTimestamp(value: string | null): string {
  if (!value || !Number.isFinite(Date.parse(value))) return "Not supplied";
  return (
    new Intl.DateTimeFormat("en-IN", {
      dateStyle: "medium",
      timeStyle: "medium",
      timeZone: "Asia/Kolkata",
    }).format(new Date(value)) + " IST"
  );
}
