/**
 * Story page for the InstrumentPicker (development only; not part of the product build): open
 * `/instrument-picker-story.html` on the dev server. `?lang=zh` for Chinese, `?theme=dark` for
 * the dark theme, `?open=1` to open the first picker. It mounts the picker over a fixture
 * catalogue (instruments only, no prices) and in hub-only mode, for screenshots, the keyboard
 * path and axe in the browser sweep.
 */
import "../styles/design-system.css";
import "./story.css";
import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { useTranslation } from "react-i18next";

import i18n from "../i18n";
import { InstrumentPicker } from "../components/ui/InstrumentPicker";
import { catalogueFromDTO, catalogueFromHubs, type PickerSelection } from "../app/model/instrumentPicker";
import { fixtureCatalogue } from "./instrumentPickerFixture";

const params = new URLSearchParams(window.location.search);
if (params.get("theme") === "dark") document.documentElement.classList.add("dark");
if (params.get("lang") === "zh") void i18n.changeLanguage("zh");
const TODAY = new Date(params.get("today") ?? "2026-11-17T12:00:00Z");

function Story() {
  const { t } = useTranslation();
  const catalogue = useMemo(() => catalogueFromDTO(fixtureCatalogue(TODAY)), []);
  const hubs = useMemo(
    () => catalogueFromHubs(catalogue.hubs.map((hub) => ({ hub: hub.hub, name: hub.name, nativeUnit: hub.nativeUnit, simulated: hub.simulated }))),
    [catalogue],
  );
  const [picked, setPicked] = useState<PickerSelection | null>(null);
  const [hub, setHub] = useState<string | null>("TTF");

  useEffect(() => {
    if (params.get("open") === "1") {
      document.querySelector<HTMLButtonElement>("[data-instrument-picker='story-instrument'] .ds-ipicker-trigger")?.click();
    }
  }, []);

  return (
    <main className="ipicker-story" data-story="instrument-picker">
      <h1>{t("instrument_picker.story.title")}</h1>
      <p>{t("instrument_picker.story.intro")}</p>
      <div className="ipicker-story-row">
        <InstrumentPicker
          id="story-instrument"
          label={t("instrument_picker.choose")}
          catalogue={catalogue}
          value={picked?.instrument?.id ?? null}
          onChange={setPicked}
          today={TODAY}
        />
        <InstrumentPicker
          id="story-hub"
          scope="hub"
          label={t("instrument_picker.story.hub_scope")}
          catalogue={hubs}
          value={hub}
          onChange={(selection) => setHub(selection.hub)}
          today={TODAY}
        />
      </div>
      <p data-story-picked={picked?.instrument?.id ?? ""}>
        {t("instrument_picker.story.picked")}: {picked?.instrument ? `${picked.instrument.label} (${picked.instrument.tenor})` : t("instrument_picker.story.none")}
      </p>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Story />
  </StrictMode>,
);
