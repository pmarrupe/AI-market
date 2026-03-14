export default function TableSkeleton({ columns = 10, rows = 6 }) {
  return (
    <div className="table-skeleton">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="table-skeleton__row">
          {Array.from({ length: columns }).map((_, c) => (
            <div
              key={c}
              className="table-skeleton__cell"
              style={{ width: c === 0 ? 28 : c === columns - 1 ? "40%" : undefined }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
