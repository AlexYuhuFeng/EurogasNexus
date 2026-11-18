import type { ReactNode } from "react";

/**
 * The page contract's first element (design basis H.1): one muted sentence under the title, in
 * the reader's terms, naming the decision the page helps with. At most 110 characters; always
 * visible; no "how to" prose (that is PanelHelp's "?" and the glossary).
 */
export const PURPOSE_MAX_CHARS = 110;

export function PageIntro({ purpose, id, children }: { purpose: string; id?: string; children?: ReactNode }) {
  if (!purpose) return null;
  return (
    <p className="page-intro" data-purpose={id ?? ""}>
      {purpose}
      {children}
    </p>
  );
}
