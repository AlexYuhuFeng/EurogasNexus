import assert from "node:assert/strict";
import test from "node:test";
import type { NormalizedMarketObsDTO } from "../src/api/client.ts";
import { strategyPriceCatalogue } from "../src/app/model/strategyPriceCatalogue.ts";

const row = (patch: Partial<NormalizedMarketObsDTO>) => ({
  is_gas_price: true, price_name: "EEX_DAY_AHEAD", source_system: "EEX_SIM",
  hub: "TTF", tenor: "day-ahead", currency: "EUR", unit: "MWh", ...patch,
}) as NormalizedMarketObsDTO;

test("catalogue uses canonical server names and exposes all source and unit variants", () => {
  const choices = strategyPriceCatalogue([row({}), row({}), row({ source_system: "EEX", currency: "GBP" })]);
  assert.equal(choices.length, 1);
  assert.equal(choices[0].name, "EEX_DAY_AHEAD");
  assert.match(choices[0].description, /EEX_SIM · TTF · day-ahead · EUR · MWh/);
  assert.match(choices[0].description, /EEX · TTF · day-ahead · GBP · MWh/);
  assert.equal(choices[0].description.split(";").length, 2);
});

test("catalogue never invents a price name or includes non-gas observations", () => {
  assert.deepEqual(strategyPriceCatalogue([row({ price_name: undefined }), row({ is_gas_price: false })]), []);
});

test("leg and hub matching prevents suggesting a day-ahead TTF price for NBP intraday", () => {
  const rows = [row({}), row({ price_name: "ICE_OCM", hub: "NBP", tenor: "within-day" })];
  assert.deepEqual(strategyPriceCatalogue(rows, "intraday", "NBP").map((choice) => choice.name), ["ICE_OCM"]);
  assert.deepEqual(strategyPriceCatalogue(rows, "day_ahead", "NBP"), []);
  assert.deepEqual(strategyPriceCatalogue(rows, "day_ahead", "TTF").map((choice) => choice.name), ["EEX_DAY_AHEAD"]);
});
