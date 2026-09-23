import type { Metadata } from "next";
import { IndicatorsView, InvalidPeriod, unitIdOf } from "@/components/indicators/indicators-view";
import { AppShell } from "@/components/ui/app-shell";
import { BackendError, backendGet } from "@/lib/backend";
import type { IndicatorsResponse } from "@/lib/types";

export const metadata: Metadata = { title: "Indicadores" };

type SearchParams = Promise<Record<string, string | string[] | undefined>>;
type Loaded = { ok: true; response: IndicatorsResponse } | { ok: false; detail: string; fallback: IndicatorsResponse };

const PASSED = ["from", "to", "unit", "norm"] as const;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

async function load(query: string): Promise<Loaded> {
  try {
    return { ok: true, response: await backendGet<IndicatorsResponse>(`/api/indicators${query ? `?${query}` : ""}`) };
  } catch (err) {
    if (!(err instanceof BackendError) || err.status !== 400) throw err;
    return { ok: false, detail: err.detail, fallback: await backendGet<IndicatorsResponse>("/api/indicators") };
  }
}

export default async function IndicatorsPage({ searchParams }: { searchParams: SearchParams }) {
  const raw = await searchParams;
  const params = new URLSearchParams();
  for (const key of PASSED) {
    const value = first(raw[key]);
    if (value !== undefined) params.set(key, value);
  }
  const loaded = await load(params.toString());

  return (
    <AppShell current="indicators">
      <h1 className="visually-hidden">Indicadores do suporte</h1>
      {loaded.ok ? (
        <IndicatorsView response={loaded.response} />
      ) : (
        // Invalid period: keep what was chosen in the form and show the backend's message.
        <InvalidPeriod
          units={loaded.fallback.units}
          query={{
            fromDate: first(raw.from) ?? loaded.fallback.query.fromDate,
            toDate: first(raw.to) ?? loaded.fallback.query.toDate,
            unitId: unitIdOf(first(raw.unit)),
            normalize: first(raw.norm) === "1",
          }}
          detail={loaded.detail}
        />
      )}
    </AppShell>
  );
}
