/** Format a unix-epoch timestamp to a short human-readable string. */
export function fmtSyncTime(ts: number | null): string {
  if (!ts) return "Never";
  return new Date(ts * 1000).toLocaleString("en", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}
