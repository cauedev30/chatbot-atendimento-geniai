// Named API types, from the backend's OpenAPI schema (npm run api:types). Never hand-copied.
import type { components } from "./api-schema";

type Schemas = components["schemas"];

export type BoardColumn = Schemas["MoveIn"]["to"];
export type HandoffReason = Schemas["ReasonCount"]["reason"];
export type BoardCard = Schemas["BoardCard"];
export type IdName = Schemas["IdName"];
export type IdLabel = Schemas["IdLabel"];
/** The schema types dict keys as strings; the backend always sends all five board columns. */
export type Board = Omit<Schemas["Board"], "columns"> & { columns: Record<BoardColumn, BoardCard[]> };
export type Outcomes = Omit<Schemas["Outcomes"], "byColumn"> & { byColumn: Record<BoardColumn, number> };
export type Indicators = Omit<Schemas["Indicators"], "outcomes"> & { outcomes: Outcomes };
export type IndicatorsQuery = Schemas["IndicatorsQueryOut"];
export type IndicatorsResponse = Omit<Schemas["IndicatorsResponse"], "data"> & { data: Indicators };
export type ErrorBody = Schemas["ErrorOut"];
