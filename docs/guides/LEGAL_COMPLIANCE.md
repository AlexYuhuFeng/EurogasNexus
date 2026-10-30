# Legal and compliance guide

**You land on Decision Center → Review.**

- **Decision record:** every decision case keeps its evidence, the person who opened it and
  the person who decided (never the same person).
- **Audit trail:** access changes, organisation settings, decisions, exports and LLM calls
  are audited with actor and time.
- **Licences:** licensed data is visible only to users whose data scopes include that
  source family; exports are refused when the licence does not allow them. Terms per
  source: [DATA_SOURCE_TERMS.md](../legal/DATA_SOURCE_TERMS.md); dependencies:
  [DEPENDENCY_LICENSE_REVIEW.md](../legal/DEPENDENCY_LICENSE_REVIEW.md).
- **Personal data and regions:** staff identities and audit stay in the installation of
  their legal entity; China runs its own installation
  ([GLOBAL_DEPLOYMENT.md](../architecture/GLOBAL_DEPLOYMENT.md)).
- **LLM use:** external models are off unless approved per installation; prompts exclude
  licensed raw prices; answers are advisory and labelled.
- **Scope:** the product does not execute trades, nominate or settle; outputs are
  research candidates requiring human review.
