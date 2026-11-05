# Trader guide

[简体中文](TRADER-CN.md) · [Client guide](README.md)

Use this guide to prepare the desk, inspect a position and compare a sale or routing
alternative. Have the relevant book, delivery period and price sources available.

## Prepare the desk

1. Open **Market → Curves & Spreads** and select the gas day, product and hub.
2. Choose **Hub board** for a hub comparison or **Ladder** for products across markets.
3. Check bid/offer, source and age before comparing levels. Keep NBP p/th and continental
   EUR/MWh quotes on a common basis when comparing them.
4. Open **Capacity & Events** for flows, capacity, storage, LNG and published outages.
5. Review relevant alerts and investigate the source behind an exception.

**Result:** a consistent market view for the period you are assessing.
[Data and conversion conventions](../user/DATA_STATUS_AND_PROVENANCE.md) explain the
timestamps, reference prices and FX basis.

## Review the physical book

1. In **Portfolio**, open the resource/contract library.
2. Inspect the recorded delivery points, contract quantity, price currency, payment terms
   and capacity rights for the selected contract.
3. Review the daily gas balance and delivery-against-nomination records where populated.
4. Open the exposure/position view for the relevant hub and month. Check the associated
   book, physical and financial legs, marks and hedge measures.

**Result:** a position assessment tied to recorded contracts and imported trades.
For contract entry, PDF intake, retirement and reinstatement, use the
[illustrated trader walkthrough](../user/manual/TRADER.md).

## Compare routes and sales

1. Open **Portfolio → Routes** and inspect the candidate's costs, capacity and access.
2. Use the available scenario handoff to carry the candidate into **Decision Center**.
3. Confirm which saved resources and sale options form the comparison. Panel edits and
   saved contract terms can have different roles in a calculation.
4. Run the comparison or optimisation. Inspect allocated and unallocated volume, binding
   constraints, price/FX basis and financing assumptions.
5. Retain the candidate and its evidence for review.

**Result:** alternatives whose quantities, costs and assumptions can be explained.
A blocked result names the input or constraint to resolve; a blank result needs data
or configuration, rather than a presumed zero economic value.

Each resource uses its own recorded contract financing rate. A resource without a rate
uses the scenario default; in the UI, that default comes from the first saved upstream
contract or the draft fallback. Inspect the rate, its source and day-count basis on each
allocation when comparing contracts with different funding terms.
[Portfolio workflow](../user/PORTFOLIO_WORKFLOW.md) describes this calculation path.

## Record the decision

Open **Decision Center → Review**, inspect the alternatives and record the permitted
review outcome with a rationale. Carry the agreed instructions into your firm's trading
or operating system through its usual approval process.

## Maintain a reliable price view

Licensed gas prices arrive through your firm's entitled source or approved import.
A provider's presence in Data Sources is a catalogue entry; the data operator can confirm
the connected/imported dataset and its last successful refresh.

See [Live price imports](../operations/LIVE_PRICE_SOURCES.md) and
[Support and updates](SUPPORT_AND_UPDATES.md).
