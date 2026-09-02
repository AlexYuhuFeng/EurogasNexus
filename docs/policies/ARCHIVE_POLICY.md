# Archive Policy

## Status

This policy is normative for documentation lifecycle in this repository.

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be
interpreted as described in RFC 2119 and RFC 8174.

## Purpose

Keep current documentation authoritative and small while retaining completed
plans, superseded blueprints, and obsolete notes as provenance. Archiving moves
a document out of the active search path; it does not rewrite history.

## Archive location

Archived documents live under `docs/archive/` in subdirectories that mirror
their original area:

- `docs/archive/architecture/`
- `docs/archive/clients/`
- `docs/archive/release/`
- additional area subdirectories as needed.

The archive index is [`docs/archive/README.md`](../archive/README.md).

## Archive criteria

A document MAY be archived only when it is unambiguously in one of these
states:

1. **Completed** — its plan or gate was delivered, the completion is recorded
   in a current queue or release document, and it is no longer used as an
   instruction.
2. **Superseded** — a current document explicitly replaces it and owns the same
   decisions.
3. **Obsolete** — its activation condition has passed or the named paths and
   surface no longer exist.

Current status markers, runbooks, contracts, active client specs, architecture
policies, and anything under active Strategy or other work in progress MUST NOT
be archived. Uncertain or mixed documents MUST NOT be moved.

## Archive procedure

1. Confirm the document meets exactly one criterion above.
2. Move it under `docs/archive/<area>/` without rewriting its content.
3. Update every affected Markdown link and code-span reference in current
   documents to either the archived path or its current replacement.
4. Add a row to the archive index with date, reason, and replacement.
5. Run `python scripts/ci/check_markdown_links.py` and the focused tests.
6. A multi-file archive set MUST be authorized by a dedicated accepted RFC,
   or by an equivalent dedicated archive-index section that lists every file,
   its archive date, reason, and replacement before the move. Single-file
   moves follow the ordinary archive procedure.

## Retention

Archived documents are retained indefinitely for provenance. They MAY be
deleted only by a separate maintenance change that records the deletion in the
archive index; ordinary refactors MUST NOT delete them.
