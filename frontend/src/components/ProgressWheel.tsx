type Props = {
  percent: number;
  label?: string;
};

export default function ProgressWheel({ percent, label }: Props) {
  const p = Math.min(100, Math.max(0, Math.round(percent)));
  const r = 28;
  const c = 2 * Math.PI * r;
  const offset = c - (p / 100) * c;

  return (
    <div className="progress-wheel" role="progressbar" aria-valuenow={p} aria-valuemin={0} aria-valuemax={100}>
      <svg width="72" height="72" viewBox="0 0 72 72" aria-hidden>
        <circle className="progress-wheel-track" cx="36" cy="36" r={r} />
        <circle
          className="progress-wheel-fill"
          cx="36"
          cy="36"
          r={r}
          strokeDasharray={c}
          strokeDashoffset={offset}
          transform="rotate(-90 36 36)"
        />
      </svg>
      <span className="progress-wheel-pct">{p}%</span>
      {label && <p className="progress-wheel-label">{label}</p>}
    </div>
  );
}
