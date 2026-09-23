import type { ReactNode } from "react";
import controls from "@/components/ui/controls.module.css";
import { BOARD_COLUMNS, COLUMN_LABELS, HANDOFF_REASON_LABELS, decimal, minutesLabel, percent } from "@/lib/format";
import type { IdName, Indicators, IndicatorsQuery, IndicatorsResponse } from "@/lib/types";
import styles from "./indicators.module.css";

/** URL of this page with the same period and unit and the given normalization. */
export function indicatorsHref(q: IndicatorsQuery, normalize: boolean): string {
  const params = new URLSearchParams({
    from: q.fromDate,
    to: q.toDate,
    unit: q.unitId === null ? "" : String(q.unitId),
    norm: normalize ? "1" : "0",
  });
  return `/indicators?${params.toString()}`;
}

export function IndicatorsView({ response }: { response: IndicatorsResponse }) {
  const { query, units, data } = response;
  return (
    <div className={styles.page}>
      <Filters query={query} units={units} />
      <Volume data={data} />
      <Outcomes data={data} />
      <Heatmap data={data} query={query} />
      <Time data={data} />
      <FaqHealth data={data} />
      <AgentHealth data={data} />
    </div>
  );
}

export function Filters({ query, units }: { query: Pick<IndicatorsQuery, "fromDate" | "toDate" | "unitId" | "normalize">; units: IdName[] }) {
  return (
    <form role="search" aria-label="Filtros" method="get" action="/indicators" className={styles.filters}>
      <label className={controls.field}>
        <span className="label">De</span>
        <input className={controls.input} type="date" name="from" defaultValue={query.fromDate} required />
      </label>
      <label className={controls.field}>
        <span className="label">Até</span>
        <input className={controls.input} type="date" name="to" defaultValue={query.toDate} required />
      </label>
      <label className={`${controls.field} ${styles.unitField}`}>
        <span className="label">Unidade</span>
        <select className={controls.select} name="unit" defaultValue={query.unitId === null ? "" : String(query.unitId)}>
          <option value="">Todas</option>
          {units.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </select>
      </label>
      <input type="hidden" name="norm" value={query.normalize ? "1" : "0"} />
      <button type="submit" className={controls.primary}>
        Filtrar
      </button>
    </form>
  );
}

function Block({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section className={styles.block} aria-labelledby={id}>
      <h2 id={id} className={styles.heading}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function Stats({ children }: { children: ReactNode }) {
  return <dl className={styles.stats}>{children}</dl>;
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className={styles.stat}>
      <dt className="label">{label}</dt>
      <dd className={`figure ${styles.statValue}`}>{value}</dd>
      {note ? <dd className={styles.statNote}>{note}</dd> : null}
    </div>
  );
}

interface Row {
  key: string | number;
  label: string;
  count: number;
  extra?: string[];
}

/** A table whose count column carries a thin single-hue bar, scaled to the table's largest count. */
function CountTable({ caption, headers, rows, empty }: { caption: string; headers: string[]; rows: Row[]; empty: string }) {
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

function Volume({ data }: { data: Indicators }) {
  const v = data.volume;
  return (
    <Block id="block-volume" title="1. Volume">
      <Stats>
        <Stat label="Total de tickets no período" value={String(v.total)} />
      </Stats>
      <div className={styles.grid}>
        <CountTable
          caption="Por semana"
          headers={["Semana (início)", "Tickets"]}
          rows={v.byWeek.map((r) => ({ key: r.period, label: r.period, count: r.count }))}
          empty="Nenhum ticket no período."
        />
        <CountTable
          caption="Por mês"
          headers={["Mês", "Tickets"]}
          rows={v.byMonth.map((r) => ({ key: r.period, label: r.period, count: r.count }))}
          empty="Nenhum ticket no período."
        />
        <CountTable
          caption="Por unidade"
          headers={["Unidade", "Tickets"]}
          rows={v.byUnit.map((r) => ({ key: r.unitId ?? "none", label: r.unitName ?? "Sem unidade", count: r.count }))}
          empty="Nenhum ticket no período."
        />
        <CountTable
          caption="Por categoria"
          headers={["Categoria", "Tickets"]}
          rows={v.byCategory.map((r) => ({ key: r.categoryId ?? "none", label: r.label ?? "Sem categoria", count: r.count }))}
          empty="Nenhum ticket no período."
        />
      </div>
    </Block>
  );
}

function Outcomes({ data }: { data: Indicators }) {
  const o = data.outcomes;
  const reached = BOARD_COLUMNS.reduce((sum, c) => sum + o.byColumn[c], 0);
  return (
    <Block id="block-outcomes" title="2. Resultados">
      <Stats>
        <Stat
          label="Taxa de resolução pelo bot"
          value={percent(o.botResolutionRate)}
          note={`de ${o.identifiedReached} tickets identificados que saíram da triagem`}
        />
        <Stat label="Sem resposta" value={percent(o.noResponseShare)} note="não conta como resolvido pelo bot" />
      </Stats>
      <div className={styles.grid}>
        <CountTable
          caption="Onde os tickets estão"
          headers={["Coluna", "Tickets", "Parcela"]}
          rows={BOARD_COLUMNS.map((c) => ({
            key: c,
            label: COLUMN_LABELS[c],
            count: o.byColumn[c],
            extra: [percent(reached === 0 ? null : o.byColumn[c] / reached)],
          }))}
          empty="Nenhum ticket saiu da triagem."
        />
        <CountTable
          caption="Por que passaram para humano"
          headers={["Motivo da passagem para humano", "Tickets"]}
          rows={o.byHandoffReason.map((r) => ({ key: r.reason, label: HANDOFF_REASON_LABELS[r.reason], count: r.count }))}
          empty="Nenhuma passagem para humano no período."
        />
      </div>
    </Block>
  );
}

function Heatmap({ data, query }: { data: Indicators; query: IndicatorsQuery }) {
  const { units, categories, cells } = data.heatmap;
  const valueOf = (unitId: number, categoryId: number): number | null => {
    const n = cells.find((c) => c.unitId === unitId && c.categoryId === categoryId)?.count ?? 0;
    if (!query.normalize) return n;
    const attendants = units.find((u) => u.id === unitId)?.attendants ?? 0;
    return attendants === 0 ? null : n / attendants;
  };
  const max = Math.max(0, ...units.flatMap((u) => categories.map((c) => valueOf(u.id, c.id) ?? 0)));
  const inGrid = cells.reduce((sum, c) => sum + c.count, 0);
  const outside = Math.max(0, data.volume.total - inGrid);
  return (
    <Block id="block-heatmap" title="3. Unidade × categoria">
      <div className={styles.heatHead}>
        <p className={styles.explain}>
          {query.normalize
            ? "Tickets divididos pelo número de atendentes ativos de cada unidade."
            : "Quantidade de tickets por unidade e categoria."}{" "}
          Quanto mais forte o teal, maior o valor.
          {outside > 0 ? (
            <>
              {" "}
              {outside === 1
                ? "1 ticket sem unidade ou sem categoria fica fora desta tabela."
                : `${outside} tickets sem unidade ou sem categoria ficam fora desta tabela.`}
            </>
          ) : null}
        </p>
        <a className={styles.toggle} href={indicatorsHref(query, !query.normalize)}>
          {query.normalize ? "Mostrar números absolutos" : "Dividir pelo número de atendentes da unidade"}
        </a>
      </div>
      {categories.length === 0 || units.length === 0 || inGrid === 0 ? (
        <p className={styles.none}>Nenhum ticket com unidade e categoria no período.</p>
      ) : (
        <div className={styles.scroll}>
          <table className={`${styles.table} ${styles.heat}`}>
            <thead>
              <tr>
                <th scope="col">Unidade</th>
                {categories.map((c) => (
                  <th key={c.id} scope="col" className={styles.num}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {units.map((u) => (
                <tr key={u.id}>
                  <th scope="row">{u.name}</th>
                  {categories.map((c) => {
                    const v = valueOf(u.id, c.id);
                    const fill = heatFill(v === null || max === 0 ? 0 : v / max);
                    return (
                      <td
                        key={c.id}
                        className={`${styles.num} figure ${fill.dark ? styles.strong : ""}`}
                        style={{ background: `color-mix(in srgb, var(--teal) ${Math.round(fill.alpha * 100)}%, transparent)` }}
                      >
                        {v === null ? "—" : query.normalize ? decimal(v) : String(v)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Block>
  );
}

/**
 * Teal fill for a heatmap cell, 0..1 of the table's largest value. White ink keeps 4.5:1 up to 60%
 * teal over the ground and dark ink from 75%, so the scale jumps that band instead of failing it.
 */
export function heatFill(level: number): { alpha: number; dark: boolean } {
  if (level <= 0.7) return { alpha: (level / 0.7) * 0.6, dark: false };
  return { alpha: 0.75 + ((level - 0.7) / 0.3) * 0.1, dark: true };
}

function Time({ data }: { data: Indicators }) {
  const t = data.time;
  const rows = [
    ["Aguardando até alguém assumir", t.waitToTakeMedianMin, t.waitToTakeAvgMin],
    ["Da abertura ao fechamento", t.timeToCloseMedianMin, t.timeToCloseAvgMin],
  ] as const;
  return (
    <Block id="block-time" title="4. Tempo">
      <p className={styles.explain}>
        A espera conta só os tickets que alguém já assumiu no período; o fechamento, só os já fechados. Tickets
        ainda abertos não entram.
      </p>
      <div className={styles.scroll}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Medida</th>
            <th scope="col" className={styles.num}>
              Mediana
            </th>
            <th scope="col" className={styles.num}>
              Média
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, median, avg]) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              <td className={`${styles.num} figure`}>{minutesLabel(median)}</td>
              <td className={`${styles.num} figure`}>{minutesLabel(avg)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </Block>
  );
}

function FaqHealth({ data }: { data: Indicators }) {
  return (
    <Block id="block-faq" title="5. Saúde do FAQ">
      <CountTable
        caption="Cada item do FAQ: quantas vezes foi enviado e quantas resolveu"
        headers={["Item do FAQ", "Vezes usado", "Resolveu", "Parcela resolvida"]}
        rows={data.faqHealth.map((f) => ({
          key: f.faqItemId,
          label: f.title,
          count: f.used,
          extra: [String(f.resolved), percent(f.resolvedShare)],
        }))}
        empty="Nenhum item ativo no FAQ."
      />
    </Block>
  );
}

function AgentHealth({ data }: { data: Indicators }) {
  const a = data.agentHealth;
  return (
    <Block id="block-agent" title="6. Saúde do agente">
      <Stats>
        <Stat
          label="Categorias corrigidas por humanos"
          value={percent(a.correctedShare)}
          note={`de ${a.classified} tickets classificados pelo bot`}
        />
        <Stat label='Classificados como "Outros"' value={percent(a.otherShare)} note="quando nenhuma categoria serviu" />
      </Stats>
    </Block>
  );
}
