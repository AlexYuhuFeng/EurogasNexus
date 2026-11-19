/**
 * "See an example" (design basis H.1, the last first-use item): a page that is empty for a new
 * installation offers a look at what it is like when filled. The example is a small bundled
 * fixture (`app/experience/examples.ts`) drawn by the page's own components, under one banner,
 * "Example - not your data", with one control to leave it. The frame is inert: nothing in it can
 * be pressed, typed into or saved, so the example never reaches the store; it is the page's own
 * state, so moving to another page leaves it.
 */
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "./Button";

/** Whether the page shows its example, and the two ways in and out. */
export function useExampleView(): { example: boolean; show: () => void; leave: () => void } {
  const [example, setExample] = useState(false);
  return { example, show: () => setExample(true), leave: () => setExample(false) };
}

/** The empty state's offer: a quiet button that opens the page's example. */
export function SeeExample({ onShow }: { onShow: () => void }) {
  const { t } = useTranslation();
  return (
    <Button variant="quiet" size="sm" data-see-example="true" onClick={onShow}>
      {t("example.see")}
    </Button>
  );
}

/** The example itself: the banner and the page's components, inert, over the fixture. */
export function ExampleFrame({ page, onLeave, children }: { page: string; onLeave: () => void; children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <section className="ds-example" data-example={page} aria-label={t("example.banner")}>
      <div className="ds-example-banner" role="note">
        <p>
          <strong>{t("example.banner")}</strong> <span>{t("example.banner_detail")}</span>
        </p>
        <Button variant="secondary" size="sm" data-leave-example="true" onClick={onLeave}>
          {t("example.leave")}
        </Button>
      </div>
      <div className="ds-example-body" inert>
        {children}
      </div>
    </section>
  );
}

/** The page's own content, or (when on) the same content as the inert, labelled example. */
export function ExampleWhen({ on, page, onLeave, children }: { on: boolean; page: string; onLeave: () => void; children: ReactNode }) {
  return on ? <ExampleFrame page={page} onLeave={onLeave}>{children}</ExampleFrame> : <>{children}</>;
}
