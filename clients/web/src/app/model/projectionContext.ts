/**
 * The Active Context a projection request carries (Architecture V2 Wave 5).
 *
 * Every read under `/api/projections/...` answers one question: what is true, on one time basis, as
 * of one instant, *for the context the caller declares*. `app/context` owns that declaration (the
 * gas day the desk selected, the delivery product and hub it focused); this module is the single
 * mapping from it onto the query names the projection routes declare, so the market, portfolio and
 * review lanes cannot drift into three dialects of the same request.
 *
 * Two rules the mapping keeps: a dimension the caller has not focused is omitted rather than sent
 * as a value the routes would match exactly (an exact `delivery_product=all` would narrow every
 * slice that applies the dimension to nothing), and no request invents an as-of instant - that is
 * the backend's own clock. A route that accepts a dimension but does not apply it to a slice says
 * so per slice in that slice's `context_filter`, so declaring a context never claims a filter the
 * backend did not run.
 */

import type { TraderContext } from "../context/traderContext.ts";

/**
 * The query a projection read is issued under, in the api client's own parameter names (the client
 * translates them to the routes' `gas_day` / `delivery_product` / `hub`).
 */
export interface ProjectionRequestContext {
  readonly gasDay: string;
  readonly product?: string;
  readonly hub?: string;
}

/** Map the canonical trading context onto a projection query. */
export function projectionRequestContext(context: TraderContext): ProjectionRequestContext {
  return {
    gasDay: context.gasDay,
    ...(context.deliveryProduct === "all" ? {} : { product: context.deliveryProduct }),
    ...(context.hubId ? { hub: context.hubId } : {}),
  };
}
