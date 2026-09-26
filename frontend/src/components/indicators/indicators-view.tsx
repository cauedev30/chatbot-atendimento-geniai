import type { ReactNode } from "react";
import controls from "@/components/ui/controls.module.css";
import { FocusedAlert } from "@/components/ui/focused-alert";
import { BOARD_COLUMNS, COLUMN_LABELS, HANDOFF_REASON_LABELS, decimal, minutesLabel, percent } from "@/lib/format";
import type { BoardColumn, IdName, Indicators, IndicatorsQuery, IndicatorsResponse } from "@/lib/types";
import { CountTable } from "./charts";
import styles from "./indicators.module.css";
import { VolumeView } from "./volume-view";

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

/**
 * Every indicator, always open, one subject per row: the four key numbers, then each subject under its own
 * heading, with a one-line explanation under it. Each subject gets the chart form its data asks for: parts
 * of a whole, ranked bars, columns over time, a heatmap, paired bars, progress bars and rings.
 */
export function IndicatorsView({ response }: { response: IndicatorsResponse }) {
  const { query, units, data } = response;
  return (
    <div className={styles.page}>
      <Filters query={query} units={units} />
      <Summary data={data} query={query} />
      <Outcomes data={data} />
      <Handoffs data={data} />
      <Volume data={data} query={query} />
      <Heatmap data={data} query={query} />
      <Time data={data} />
      <FaqHealth data={data} />
      <AgentHealth data={data} />
    </div>
  );
}

/** The unit id in the address, when it is one. */
export function unitIdOf(value: string | undefined): number | null {
  return value !== undefined && /^[1-9]\d*$/.test(value) ? Number(value) : null;
}

type FilterQuery = Pick<IndicatorsQuery, "fromDate" | "toDate" | "unitId" | "normalize">;

/** A period the backend refused: the filters keep what was chosen, and the error takes the focus. */
export function InvalidPeriod({ query, units, detail }: { query: FilterQuery; units: IdName[]; detail: string }) {
  return (
    <div className={styles.page}>
      <Filters query={query} units={units} />
      <FocusedAlert>{detail}</FocusedAlert>
    </div>
  );
}

export function Filters({ query, units }: { query: FilterQuery; units: IdName[] }) {
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

/** "26/08 a 24/09/2026" from two ISO dates. */
function periodLabel(from: string, to: string): string {
  const [fy, fm, fd] = from.split("-");
  const [ty, tm, td] = to.split("-");
  return fy === ty ? `${fd}/${fm} a ${td}/${tm}/${ty}` : `${fd}/${fm}/${fy} a ${td}/${tm}/${ty}`;
}

/** One subject of the page: its heading, a one-line explanation, then the content. */
function Block({ id, title, note, children }: { id: string; title: string; note?: string; children: ReactNode }) {
  return (
    <section className={styles.panel} aria-labelledby={id}>
      <header className={styles.panelHead}>
        <h2 id={id} className={styles.heading}>
          {title}
        </h2>
        {note ? <p className={styles.panelNote}>{note}</p> : null}
      </header>
      {children}
    </section>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className={styles.stat}>
      <dt className={styles.statLabel}>{label}</dt>
      <dd className={`figure ${styles.statValue}`}>{value}</dd>
      {note ? <dd className={styles.statNote}>{note}</dd> : null}
    </div>
  );
}

function Summary({ data, query }: { data: Indicators; query: IndicatorsQuery }) {
  const { volume, outcomes, time } = data;
  return (
    <section className={styles.summaryBlock} aria-labelledby="block-summary">
      <h2 id="block-summary" className={styles.summaryTitle}>
        Resumo de {periodLabel(query.fromDate, query.toDate)}
      </h2>
      <dl className={styles.stats}>
        <Stat label="Tickets no período" value={String(volume.total)} />
        <Stat
          label="Resolvidos pelo bot"
          value={percent(outcomes.botResolutionRate)}
          note={`de ${outcomes.identifiedReached} identificados que saíram da triagem; ${percent(outcomes.noResponseShare)} ficaram sem resposta`}
        />
        <Stat label="Espera até alguém assumir" value={minutesLabel(time.waitToTakeMedianMin)} note="mediana" />
        <Stat label="Da abertura ao fechamento" value={minutesLabel(time.timeToCloseMedianMin)} note="mediana" />
      </dl>
    </section>
  );
}

/** The board's five columns as one bar split into parts of the whole, a legend table under it. */
function Outcomes({ data }: { data: Indicators }) {
  const o = data.outcomes;
  const reached = BOARD_COLUMNS.reduce((sum, c) => sum + o.byColumn[c], 0);
  const shareOf = (c: BoardColumn) => (reached === 0 ? null : o.byColumn[c] / reached);
  return (
    <Block id="block-outcomes" title="Onde os tickets estão" note="Todos os tickets que saíram da triagem, inclusive de números não identificados.">
      {reached === 0 ? (
        <p className={styles.none}>Nenhum ticket saiu da triagem.</p>
      ) : (
        <div className={styles.split} aria-hidden="true">
          {BOARD_COLUMNS.filter((c) => o.byColumn[c] > 0).map((c) => (
            <span
              key={c}
              className={styles.part}
              data-column={c}
              style={{ flexGrow: o.byColumn[c] }}
              title={`${COLUMN_LABELS[c]}: ${o.byColumn[c]} (${percent(shareOf(c))})`}
            />
          ))}
        </div>
      )}
      <table className={`${styles.table} ${styles.legend}`}>
        <caption className="visually-hidden">Tickets por coluna do quadro</caption>
        <thead>
          <tr>
            <th scope="col">Coluna</th>
            <th scope="col" className={styles.num}>
              Tickets
            </th>
            <th scope="col" className={styles.num}>
              Parcela
            </th>
          </tr>
        </thead>
        <tbody>
          {BOARD_COLUMNS.map((c) => (
            <tr key={c}>
              <th scope="row">
                <span className={styles.swatch} data-column={c} aria-hidden="true" />
                {COLUMN_LABELS[c]}
              </th>
              <td className={`${styles.num} figure`}>{o.byColumn[c]}</td>
              <td className={`${styles.num} figure`}>{percent(shareOf(c))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Block>
  );
}

function Handoffs({ data }: { data: Indicators }) {
  const o = data.outcomes;
  return (
    <Block id="block-handoffs" title="Por que passaram para humano" note="O motivo de cada ticket que o bot passou para uma pessoa.">
      <CountTable
        caption="Motivos da passagem para humano"
        headers={["Motivo", "Tickets"]}
        rows={o.byHandoffReason.map((r) => ({ key: r.reason, label: HANDOFF_REASON_LABELS[r.reason], count: r.count }))}
        empty="Nenhuma passagem para humano no período."
      />
    </Block>
  );
}

function Volume({ data, query }: { data: Indicators; query: IndicatorsQuery }) {
  return (
    <Block id="block-volume" title="Volume" note={`${data.volume.total} tickets abertos no período. Escolha como ver.`}>
      <VolumeView volume={data.volume} fromDate={query.fromDate} toDate={query.toDate} />
    </Block>
  );
}

/** A heatmap row: a unit, or the tickets from unknown numbers (no unit, never divided by attendants). */
interface HeatRow {
  key: string;
  name: string;
  unitId: number | null;
  attendants: number | null;
}

function Heatmap({ data, query }: { data: Indicators; query: IndicatorsQuery }) {
  const { units, categories, cells, uncategorized } = data.heatmap;
  const unknownRow = cells.some((c) => c.unitId === null);
  const rows: HeatRow[] = [
    ...units.map((u) => ({ key: String(u.id), name: u.name, unitId: u.id, attendants: u.attendants })),
    ...(unknownRow ? [{ key: "none", name: "Sem unidade", unitId: null, attendants: null }] : []),
  ];
  const valueOf = (row: HeatRow, categoryId: number): number | null => {
    const n = cells.find((c) => c.unitId === row.unitId && c.categoryId === categoryId)?.count ?? 0;
    if (!query.normalize) return n;
    return row.attendants === null || row.attendants === 0 ? null : n / row.attendants;
  };
  const max = Math.max(0, ...rows.flatMap((r) => categories.map((c) => valueOf(r, c.id) ?? 0)));
  const inGrid = cells.reduce((sum, c) => sum + c.count, 0);
  return (
    <Block id="block-heatmap" title="Unidade × categoria" note="Quais unidades sofrem com cada problema.">
      <div className={styles.heatHead}>
        <p className={styles.explain}>
          {query.normalize
            ? "Tickets divididos pelo número de atendentes ativos de cada unidade."
            : "Quantidade de tickets por unidade e categoria."}{" "}
          Quanto mais forte a cor, maior o valor.
          {query.normalize && unknownRow ? " A linha Sem unidade não tem atendentes para dividir." : null}
          {uncategorized > 0 ? (
            <>
              {" "}
              {uncategorized === 1
                ? "1 ticket sem categoria fica fora desta tabela."
                : `${uncategorized} tickets sem categoria ficam fora desta tabela.`}
            </>
          ) : null}
        </p>
        <a className={styles.toggle} href={indicatorsHref(query, !query.normalize)}>
          {query.normalize ? "Mostrar números absolutos" : "Dividir pelo número de atendentes da unidade"}
        </a>
      </div>
      {categories.length === 0 || rows.length === 0 || inGrid === 0 ? (
        <p className={styles.none}>Nenhum ticket com categoria no período.</p>
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
              {rows.map((r) => (
                <tr key={r.key}>
                  <th scope="row">{r.name}</th>
                  {categories.map((c) => {
                    const v = valueOf(r, c.id);
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

/** Median and mean side by side for each measure, on one shared scale. */
function Time({ data }: { data: Indicators }) {
  const t = data.time;
  const rows = [
    ["Aguardando até alguém assumir", t.waitToTakeMedianMin, t.waitToTakeAvgMin],
    ["Da abertura ao fechamento", t.timeToCloseMedianMin, t.timeToCloseAvgMin],
  ] as const;
  const max = Math.max(0, ...rows.flatMap(([, median, avg]) => [median ?? 0, avg ?? 0]));
  const width = (n: number | null) => `${max === 0 || n === null ? 0 : (n / max) * 100}%`;
  return (
    <Block
      id="block-time"
      title="Tempo"
      note="A espera conta só os tickets que alguém já assumiu no período; o fechamento, só os já fechados. Tickets ainda abertos não entram."
    >
      <p className={styles.keys} aria-hidden="true">
        <span className={styles.key}>
          <span className={styles.keyMedian} />
          Mediana: o tempo típico
        </span>
        <span className={styles.key}>
          <span className={styles.keyMean} />
          Média: puxada pelos casos mais longos
        </span>
      </p>
      <table className={`${styles.table} ${styles.pairs}`}>
        <thead className="visually-hidden">
          <tr>
            <th scope="col">Medida</th>
            <th scope="col">Mediana</th>
            <th scope="col">Média</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, median, avg]) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              <td>
                <span className={styles.pairBar} aria-hidden="true">
                  <span className={styles.median} style={{ width: width(median) }} />
                </span>
                <span className="figure">{minutesLabel(median)}</span>
              </td>
              <td>
                <span className={styles.pairBar} aria-hidden="true">
                  <span className={styles.mean} style={{ width: width(avg) }} />
                </span>
                <span className="figure">{minutesLabel(avg)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Block>
  );
}

/** Each FAQ item: how often it was sent, and a progress bar of how many of those sends solved the case. */
function FaqHealth({ data }: { data: Indicators }) {
  const used = data.faqHealth.reduce((sum, f) => sum + f.used, 0);
  const items = data.faqHealth.length;
  return (
    <Block
      id="block-faq"
      title="Saúde do FAQ"
      note={`${items} ${items === 1 ? "item" : "itens"}, ${used} ${used === 1 ? "envio" : "envios"} no período. A barra mostra quantos envios resolveram.`}
    >
      {items === 0 ? (
        <p className={styles.none}>Nenhum item ativo no FAQ.</p>
      ) : (
        <table className={`${styles.table} ${styles.progressTable}`}>
          <caption className="visually-hidden">Cada item do FAQ: quantas vezes foi enviado e quantas resolveu</caption>
          <thead>
            <tr>
              <th scope="col">Item do FAQ</th>
              <th scope="col">Resolveu</th>
              <th scope="col" className={styles.num}>
                Parcela resolvida
              </th>
            </tr>
          </thead>
          <tbody>
            {data.faqHealth.map((f) => (
              <tr key={f.faqItemId}>
                <th scope="row">{f.title}</th>
                <td>
                  <span className={styles.progress} aria-hidden="true">
                    <span style={{ width: `${(f.resolvedShare ?? 0) * 100}%` }} />
                  </span>
                  <span className={`figure ${styles.progressText}`}>
                    {f.used === 0 ? "não foi enviado" : `${f.resolved} de ${f.used} ${f.used === 1 ? "envio" : "envios"}`}
                  </span>
                </td>
                <td className={`${styles.num} figure`}>{percent(f.resolvedShare)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Block>
  );
}

/** A percentage as a ring: the filled arc is the share, the value beside it. */
function Ring({ label, share, note }: { label: string; share: number | null; note: string }) {
  const r = 34;
  const length = 2 * Math.PI * r;
  return (
    <figure className={styles.ring}>
      <svg width="88" height="88" viewBox="0 0 88 88" aria-hidden="true" focusable="false">
        <circle cx="44" cy="44" r={r} className={styles.ringTrack} />
        {share ? (
          <circle
            cx="44"
            cy="44"
            r={r}
            className={styles.ringFill}
            strokeDasharray={`${share * length} ${length}`}
            transform="rotate(-90 44 44)"
          />
        ) : null}
      </svg>
      <figcaption className={styles.ringText}>
        <span className={styles.ringLabel}>{label}</span>
        <span className={`figure ${styles.ringValue}`}>{percent(share)}</span>
        <span className={styles.statNote}>{note}</span>
      </figcaption>
    </figure>
  );
}

function AgentHealth({ data }: { data: Indicators }) {
  const a = data.agentHealth;
  return (
    <Block id="block-agent" title="Saúde do agente" note="Quanto o bot erra ao classificar. Quanto menor, melhor.">
      <div className={styles.rings}>
        <Ring label="Categorias corrigidas por humanos" share={a.correctedShare} note={`de ${a.classified} tickets classificados pelo bot`} />
        <Ring label='Classificados como "Outros"' share={a.otherShare} note="quando nenhuma categoria serviu" />
      </div>
    </Block>
  );
}
