# First sign-in and first checks

[简体中文](QUICK_START-CN.md) · [Client guide](../guides/README.md)

**Outcome:** sign in, confirm the working context and inspect one data-backed view.

## Before you start

Obtain the workspace URL or approved desktop installer, your sign-in instructions and the
name of your firm's support contact. Ask the desk owner which book, hub and delivery period
to use for the first check. Administrators configure the sources your desk needs.

## Sign in

1. Open the workspace in your browser, or launch the installed desktop client.
2. Use the sign-in method provided by IT. A company SSO account and a dedicated test
   account are different sign-in arrangements; use the one assigned to this installation.
3. On a managed desktop, confirm the preconfigured service address. If IT asks you to
   enter it, use the supplied HTTPS API address ending in `/api`.
4. Open **Help & Settings → Settings**. Set your language, appearance and preferred market display.

**Check the result:** your name appears in the account menu and you can open the workspaces
assigned to you. If sign-in succeeds but a workspace is restricted, ask IT to check your
roles and data scopes.

Each installation uses the credentials issued for that environment.

## Inspect your first market view

1. Open **Market → Curves & Spreads**.
2. Select the gas day, delivery product and hub relevant to your task.
3. Find the quote's source, unit and timestamp. Inspect bid/offer and mid on the same basis.
4. Open **Capacity & Events** for physical context, or **Network** to inspect a location.
5. Compare a displayed record with the source or imported file used by your desk.

**Check the result:** the selected delivery period and units match your intended comparison.
A connected application with no market quotes needs source setup or an import; connection
health alone does not establish price availability.

## Continue with your work

- [Trader](../guides/TRADER.md): markets, resources, routes and positions.
- [Analyst](../guides/ANALYST_QUANT.md): spread analysis, saved strategies and datasets.
- [Risk and finance](../guides/RISK_AND_FINANCE.md): exposure, valuation and limits.
- [Administrator](../guides/ADMIN_AND_OPERATIONS.md): access and source setup.

## If the first check does not succeed

| What you see | Next step |
| --- | --- |
| Sign-in fails | Confirm the environment and sign-in method; send the time and visible error to IT |
| A workspace is restricted | Request the relevant role or data scope through your firm's access process |
| No records | Check the selected date and filters, then ask the data operator about the source's first successful run |
| An old timestamp | Check source freshness and the last ingestion result |
| A page is clipped or a control is unreachable | Record device, browser, orientation and a screenshot; follow [Support](../guides/SUPPORT_AND_UPDATES.md) |

[Understand data status and units](DATA_STATUS_AND_PROVENANCE.md)
