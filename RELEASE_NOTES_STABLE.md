# Eurogas Nexus 0.5.0 (reviewed stable notes template)

This file is a template, not a published stable release. Before any stable
tag, a release reviewer must replace each placeholder with reviewed text.

## Version

0.5.0

## Channel

stable

## Commit

<full commit SHA of the tagged mainline commit>

## What changed

<human-reviewed summary; do not paste raw commit messages>

## Data/model changes

<none or explicit data/model changes>

## Schema revision

0030_reliability_indexes

## Compatibility

- API contract: api-contract/v1
- Minimum supported client: 0.5.0
- Minimum supported server: 0.5.0

## Installer/update guidance

<which signed installers to use, WebView2 policy, checksum verification>

## Known limitations

<explicit limitations, including any remaining external acceptance items>

## Security notes where relevant

<security fixes or external security acceptance state>

## Migration requirements

`alembic upgrade head` and migration preflight as documented.

## Rollback guidance

docs/operations/RELEASE_ROLLBACK.md; container rollback by immutable digest.

## Signing status

<verified Authenticode/GPG evidence or explicit external-pending statement>
