import styles from "./indicators.module.css";

/*
 * The chart forms of the indicators page, one per job: ranked horizontal bars (CountTable), columns over
 * time (ColumnChart). Every value is also text, so no number depends on reading a bar.
 */

export interface Row {
  key: string | number;
  label: string;
  count: number;
  extra?: string[];
}

/** A ranked table whose count column carries a thin single-hue bar, scaled to the table's largest count. */
export function CountTable({ caption, headers, rows, empty }: { caption: string; headers: string[]; rows: Row[]; empty: string }) {
  const max = Math.max(0, ...rows.map((r) => r.count));
  const stacked = headers.length > 2;
  return (
    <div className={styles.scroll}>
      <table className={`${styles.table} ${stacked ? styles.stack : ""}`}>
        <caption className={styles.caption}>{caption}</caption>
        <thead>
          <tr>
            {headers.map((h, i) => (
              <th key={h} scope="col" className={i > 0 ? styles.num : undefined}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={headers.length} className={styles.none}>
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((r) => (
              <tr key={r.key}>
                <th scope="row">{r.label}</th>
                <td className={`${styles.num} ${styles.countCell}`} data-label={headers[1]}>
                  <span className={styles.bar} aria-hidden="true">
                    <span style={{ width: `${max === 0 ? 0 : (r.count / max) * 100}%` }} />
                  </span>
                  <span className="figure">{r.count}</span>
                </td>
                {(r.extra ?? []).map((cell, i) => (
                  <td key={i} className={`${styles.num} figure`} data-label={headers[i + 2]}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export interface Column {
  key: string;
  label: string;
  /** What a screen reader and the hover say, e.g. "Semana de 07/09". */
  spoken: string;
  count: number;
}

/** Columns over time: one per period, the count on its cap, the period under it. */
export function ColumnChart({ columns, empty }: { columns: Column[]; empty: string }) {
  const max = Math.max(0, ...columns.map((c) => c.count));
  if (max === 0) return <p className={styles.none}>{empty}</p>;
  return (
    <ol className={styles.chart}>
      {columns.map((c) => {
        const text = `${c.spoken}: ${c.count} ${c.count === 1 ? "ticket" : "tickets"}`;
        return (
          <li key={c.key} className={styles.column} title={text}>
            <span className="visually-hidden">{text}</span>
            <span className={styles.columnTrack} aria-hidden="true">
              <span className={styles.columnFill} style={{ height: `${(c.count / max) * 100}%` }}>
                <span className={`figure ${styles.columnCount}`}>{c.count}</span>
              </span>
            </span>
            <span className={`figure ${styles.columnLabel}`} aria-hidden="true">
              {c.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

const DAY_MS = 86_400_000;
const MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

interface Period {
  period: string;
  count: number;
}

/** Every week of the period, from its Monday, zero where nothing was opened. */
export function weekColumns(from: string, to: string, byWeek: Period[]): Column[] {
  const start = Date.parse(`${from}T00:00:00Z`);
  const end = Date.parse(`${to}T00:00:00Z`);
  const monday = start - ((new Date(start).getUTCDay() + 6) % 7) * DAY_MS;
  const counts = new Map(byWeek.map((w) => [w.period, w.count]));
  const columns: Column[] = [];
  for (let d = monday; d <= end; d += 7 * DAY_MS) {
    const w = new Date(d).toISOString().slice(0, 10);
    const label = `${w.slice(8, 10)}/${w.slice(5, 7)}`;
    columns.push({ key: w, label, spoken: `Semana de ${label}`, count: counts.get(w) ?? 0 });
  }
  return columns;
}

/** Every month of the period, zero where nothing was opened. */
export function monthColumns(from: string, to: string, byMonth: Period[]): Column[] {
  const counts = new Map(byMonth.map((m) => [m.period, m.count]));
  const columns: Column[] = [];
  let [y, m] = [Number(from.slice(0, 4)), Number(from.slice(5, 7))];
  for (let key = ""; (key = `${y}-${String(m).padStart(2, "0")}`) <= to.slice(0, 7); ) {
    const name = MONTHS[m - 1];
    columns.push({ key, label: `${name}/${key.slice(2, 4)}`, spoken: `${name} de ${y}`, count: counts.get(key) ?? 0 });
    if (++m > 12) [y, m] = [y + 1, 1];
  }
  return columns;
}
