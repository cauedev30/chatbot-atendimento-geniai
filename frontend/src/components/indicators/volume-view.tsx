"use client";

import { useState } from "react";
import type { Indicators } from "@/lib/types";
import { ColumnChart, CountTable, monthColumns, weekColumns } from "./charts";
import styles from "./indicators.module.css";

const VIEWS = [
  { key: "week", label: "Por semana" },
  { key: "month", label: "Por mês" },
  { key: "unit", label: "Por unidade" },
  { key: "category", label: "Por categoria" },
] as const;

type View = (typeof VIEWS)[number]["key"];

/** Volume one view at a time: columns over time for weeks and months, ranked bars for units and categories. */
export function VolumeView({ volume, fromDate, toDate }: { volume: Indicators["volume"]; fromDate: string; toDate: string }) {
  const [view, setView] = useState<View>("week");
  const empty = "Nenhum ticket no período.";
  return (
    <>
      <div className={styles.segmented} role="group" aria-label="Ver o volume">
        {VIEWS.map((v) => (
          <button
            key={v.key}
            type="button"
            className={styles.segment}
            aria-pressed={view === v.key}
            onClick={() => setView(v.key)}
          >
            {v.label}
          </button>
        ))}
      </div>
      {view === "week" ? <ColumnChart columns={weekColumns(fromDate, toDate, volume.byWeek)} empty={empty} /> : null}
      {view === "month" ? <ColumnChart columns={monthColumns(fromDate, toDate, volume.byMonth)} empty={empty} /> : null}
      {view === "unit" ? (
        <CountTable
          caption="Tickets por unidade"
          headers={["Unidade", "Tickets"]}
          rows={[...volume.byUnit]
            .sort((a, b) => b.count - a.count)
            .map((r) => ({ key: r.unitId ?? "none", label: r.unitName ?? "Sem unidade", count: r.count }))}
          empty={empty}
        />
      ) : null}
      {view === "category" ? (
        <CountTable
          caption="Tickets por categoria"
          headers={["Categoria", "Tickets"]}
          rows={[...volume.byCategory]
            .sort((a, b) => b.count - a.count)
            .map((r) => ({ key: r.categoryId ?? "none", label: r.label ?? "Sem categoria", count: r.count }))}
          empty={empty}
        />
      ) : null}
    </>
  );
}
