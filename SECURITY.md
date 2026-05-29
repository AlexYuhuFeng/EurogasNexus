# Security Policy

## Public Repository Warning

This is a public repository. Do not commit secrets, real vendor data, internal
commercial data, raw market data, contracts, or real business strategy
parameters.

## Reporting

Do not open a public issue for suspected secrets, credentials, entitlement
failures, or vulnerabilities. Report them through the private project security
channel for the repository owner.

## V1 Guardrails

- Runtime DB URLs must never be printed in full.
- Unknown commercial-data entitlement must fail closed.
- Tests and import-time code must not call external APIs, LLM providers, live
  connectors, live databases, or live infrastructure.
- Trial and release modes must not silently fall back to local files.

## Supported Scope

The V1 bootstrap supports backend foundation work only. Trade execution, order
entry, order routing, trade capture, nomination submission, official approval,
legal advice, official trading recommendations, auto-trading, ETRM replacement
behavior, frontend, desktop clients, live connectors, and company SSO/OIDC are
out of scope.
