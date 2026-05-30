# apps/worker

Reserved for a future backend worker process.

Do not implement worker runtime until a milestone explicitly activates it.
Future worker code must call application/runtime-store boundaries and must not
become a second source of truth.
