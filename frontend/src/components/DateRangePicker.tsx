interface DateRangePickerProps {
  start: string;
  end: string;
  onChange: (start: string, end: string) => void;
}

const PRESETS = [
  { label: "30d",  days: 30  },
  { label: "90d",  days: 90  },
  { label: "6m",   days: 180 },
  { label: "1y",   days: 365 },
  { label: "YtD",  days: -1  },
  { label: "All",  days: 0   },
];

function toISO(d: Date) {
  return d.toISOString().slice(0, 10);
}

export function ytdStart() {
  return `${new Date().getFullYear()}-01-01`;
}

export function DateRangePicker({ start, end, onChange }: DateRangePickerProps) {
  const today = toISO(new Date());

  const applyPreset = (days: number) => {
    if (days === 0) {
      onChange("2018-01-01", today);
    } else if (days === -1) {
      onChange(ytdStart(), today);
    } else {
      const s = new Date();
      s.setDate(s.getDate() - days);
      onChange(toISO(s), today);
    }
  };

  const isYtD = start === ytdStart() && end === today;
  const isAll = start <= "2018-01-02" && end === today;
  const isDays = (days: number) => {
    const s = new Date(); s.setDate(s.getDate() - days);
    return start === toISO(s) && end === today;
  };

  const isActive = (label: string, days: number) => {
    if (days === -1) return isYtD;
    if (days === 0)  return isAll;
    return isDays(days);
  };

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {PRESETS.map((p) => (
        <button
          key={p.label}
          onClick={() => applyPreset(p.days)}
          className="px-3 py-1 rounded-md text-xs font-medium transition-colors"
          style={{
            backgroundColor: isActive(p.label, p.days) ? "#6366f1" : "#2a2d3a",
            color:           isActive(p.label, p.days) ? "#fff"     : "#94a3b8",
            border: `1px solid ${isActive(p.label, p.days) ? "#6366f1" : "#3a3d4a"}`,
            cursor: "pointer",
          }}
        >
          {p.label}
        </button>
      ))}
      <input
        type="date"
        value={start}
        onChange={(e) => onChange(e.target.value, end)}
        className="px-2 py-1 rounded-md text-xs"
        style={{ backgroundColor: "#2a2d3a", color: "#94a3b8", border: "1px solid #3a3d4a" }}
      />
      <span style={{ color: "#64748b" }}>→</span>
      <input
        type="date"
        value={end}
        onChange={(e) => onChange(start, e.target.value)}
        className="px-2 py-1 rounded-md text-xs"
        style={{ backgroundColor: "#2a2d3a", color: "#94a3b8", border: "1px solid #3a3d4a" }}
      />
    </div>
  );
}
