/**
 * Admin -> Users, the pure part: the state shown for a person and the words for a refusal.
 * The backend decides every rule; these only present what it answered.
 */

import type { AccessUserDTO } from "@/api/client";

/** The state Admin -> Users shows (older servers answer without `account_state`). */
export function userState(user: Pick<AccessUserDTO, "account_state" | "status">): string {
  return user.account_state ?? user.status;
}

/** Localise a refused administration request by the machine code the backend sends. */
export function accessErrorKey(error: unknown): string {
  const message = String(error);
  const codes = [
    "last_administrator",
    "entitlement_self_grant_forbidden",
    "data_scope_not_licensed",
    "username_taken",
    "username_invalid",
    "username_required",
    "email_taken",
    "email_invalid",
    "subject_taken",
    "invite_identifier_missing",
    "local_accounts_disabled",
    "sso_not_configured",
    "user_has_history",
    "cannot_delete_self",
    "not_a_local_account",
    "unknown_job_function",
  ];
  const code = codes.find((item) => message.includes(item));
  return code ? `access.error.${code}` : "access.mutation_failed";
}

