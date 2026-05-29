# infra/deployment

Reserved for deployment topology templates and environment notes.

Deployment work must keep backend, web, and Windows client responsibilities
separate:

- backend service owns API and runtime data access;
- web client is an API consumer;
- Windows client packages the web workspace.
