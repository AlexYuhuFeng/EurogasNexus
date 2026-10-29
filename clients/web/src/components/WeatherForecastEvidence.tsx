import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from "react";
import { fetchWeatherForecasts, type ForecastPointReadingDTO, type ForecastReadEnvelopeDTO } from "@/api/client";
import { PanelHeader } from "@/components/ui";

interface WeatherForecastEvidenceProps {
  t: (key: string) => string;
}

const UTC_EXAMPLE = "2026-10-27T00:00:00Z";
const hashStyle = { overflowWrap: "anywhere", wordBreak: "break-word" } as const;
const fieldStyle = { display: "grid", gap: "0.25rem", textAlign: "left", minWidth: 0 } as const;

function parseIdentifiers(value: string): string[] {
  return [...new Set(value.split(/[\n,]+/).map((entry) => entry.trim()).filter(Boolean))];
}

function readingTime(value: string) {
  return <time dateTime={value}>{value}</time>;
}

function ReadingDetails({ row, t }: { row: ForecastPointReadingDTO; t: (key: string) => string }) {
  return (
    <details style={hashStyle}>
      <summary>{t("sources.weather.details")}</summary>
      <p>{t("sources.weather.observation")}: <code style={hashStyle}>{row.observation_id}</code></p>
      <p>{t("sources.weather.series")}: {row.series_id} · {t("sources.weather.entity")}: {row.entity_id}</p>
      <p>{t("sources.weather.model")}: {row.model} · {t("sources.weather.run")}: {row.run_id} · {t("sources.weather.point")}: {row.point_id}</p>
      <p>{t("sources.weather.requested")}: {row.requested_latitude.toFixed(4)}, {row.requested_longitude.toFixed(4)}</p>
      <p><strong>{t("sources.weather.raw_hash")}</strong> <code style={hashStyle}>{row.raw_grib_sha256}</code></p>
      <p><strong>{t("sources.weather.record_hash")}</strong> <code style={hashStyle}>{row.record_content_sha256}</code></p>
    </details>
  );
}

export function WeatherForecastEvidence({ t }: WeatherForecastEvidenceProps) {
  const [seriesInput, setSeriesInput] = useState("");
  const [entityInput, setEntityInput] = useState("");
  const [predictionOrigin, setPredictionOrigin] = useState("");
  const [validFrom, setValidFrom] = useState("");
  const [validTo, setValidTo] = useState("");
  const [limitInput, setLimitInput] = useState("100");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [envelope, setEnvelope] = useState<ForecastReadEnvelopeDTO | null>(null);
  const requestGeneration = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const invalidate = () => {
    requestGeneration.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setError(null);
    setEnvelope(null);
  };

  useEffect(() => () => {
    requestGeneration.current += 1;
    abortRef.current?.abort();
  }, []);

  const edit = (setter: (value: string) => void) => (
    event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) => {
    invalidate();
    setter(event.currentTarget.value);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    const seriesIds = parseIdentifiers(seriesInput);
    const entityIds = parseIdentifiers(entityInput);
    const limit = Number(limitInput);
    const validationKey =
      seriesIds.length === 0 || entityIds.length === 0
        ? "sources.weather.error_identifiers"
        : !predictionOrigin.trim() || !validFrom.trim() || !validTo.trim()
          ? "sources.weather.error_time"
          : !Number.isInteger(limit) || limit < 1 || limit > 256
            ? "sources.weather.error_limit"
            : null;
    if (validationKey) {
      setError(t(validationKey));
      setEnvelope(null);
      return;
    }

    const generation = requestGeneration.current + 1;
    requestGeneration.current = generation;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setError(null);
    setEnvelope(null);
    try {
      const result = await fetchWeatherForecasts({
        seriesIds,
        entityIds,
        predictionOrigin: predictionOrigin.trim(),
        validFrom: validFrom.trim(),
        validTo: validTo.trim(),
        limit,
        signal: controller.signal,
      });
      if (generation !== requestGeneration.current || controller.signal.aborted) return;
      setEnvelope(result);
    } catch (caught) {
      if (generation !== requestGeneration.current || controller.signal.aborted) return;
      setError(caught instanceof Error ? caught.message : t("sources.weather.error_unknown"));
    } finally {
      if (generation === requestGeneration.current) {
        setBusy(false);
        abortRef.current = null;
      }
    }
  };

  const state = busy ? "busy" : error ? "error" : envelope ? (envelope.data.length > 0 ? "ready" : "empty") : "not-ready";

  return (
    <section className="source-weather-evidence" aria-labelledby="weather-evidence-title" data-state={state}>
      <PanelHeader
        title={<span id="weather-evidence-title">{t("sources.weather.title")}</span>}
        meta={t("sources.weather.meta")}
      />
      <p className="muted">{t("sources.weather.intro")}</p>
      <form className="credential-form" onSubmit={submit} aria-busy={busy}>
        <label style={fieldStyle}><span>{t("sources.weather.series")}</span>
          <textarea rows={2} value={seriesInput} onChange={edit(setSeriesInput)} placeholder={t("sources.weather.identifier_placeholder")} />
          <small className="muted">{t("sources.weather.identifier_hint")}</small>
        </label>
        <label style={fieldStyle}><span>{t("sources.weather.entity")}</span>
          <textarea rows={2} value={entityInput} onChange={edit(setEntityInput)} placeholder={t("sources.weather.identifier_placeholder")} />
          <small className="muted">{t("sources.weather.identifier_hint")}</small>
        </label>
        <label style={fieldStyle}><span>{t("sources.weather.prediction_origin")}</span>
          <input type="text" spellCheck={false} value={predictionOrigin} onChange={edit(setPredictionOrigin)} placeholder={UTC_EXAMPLE} />
        </label>
        <label style={fieldStyle}><span>{t("sources.weather.valid_from")}</span>
          <input type="text" spellCheck={false} value={validFrom} onChange={edit(setValidFrom)} placeholder={UTC_EXAMPLE} />
        </label>
        <label style={fieldStyle}><span>{t("sources.weather.valid_to")}</span>
          <input type="text" spellCheck={false} value={validTo} onChange={edit(setValidTo)} placeholder={UTC_EXAMPLE} />
        </label>
        <label style={fieldStyle}><span>{t("sources.weather.limit")}</span>
          <input type="number" min={1} max={256} step={1} value={limitInput} onChange={edit(setLimitInput)} />
        </label>
        <p className="muted" style={{ gridColumn: "1 / -1" }}>{t("sources.weather.utc_hint")}</p>
        <button type="submit" className="source-open-access" disabled={busy}>
          {busy ? t("sources.weather.busy") : t("sources.weather.submit")}
        </button>
      </form>

      {busy && <p role="status" aria-live="polite">{t("sources.weather.busy")}</p>}
      {error && (
        <div className="source-registry-state is-failed" role="alert">
          <strong>{t("sources.weather.error")}</strong>
          <p style={hashStyle}>{error}</p>
        </div>
      )}
      {!busy && !error && !envelope && (
        <p className="muted" data-empty-state="weather-not-ready">{t("sources.weather.not_ready")}</p>
      )}

      {envelope && (
        <>
          <div className="source-next-action" data-weather-meta="true">
            <span>{t("sources.weather.attribution")}</span>
            <p style={hashStyle}>{envelope.meta.attribution}</p>
            <span>{t("sources.weather.warnings")}</span>
            {envelope.meta.warnings.length > 0 ? (
              <ul>{envelope.meta.warnings.map((warning) => <li key={warning} style={hashStyle}>{warning}</li>)}</ul>
            ) : (
              <small>{t("sources.weather.no_warnings")}</small>
            )}
            <details>
              <summary>{t("sources.weather.source_references")}</summary>
              <ul>{envelope.meta.source_references.map((reference) => (
                <li key={reference}><code style={hashStyle}>{reference}</code></li>
              ))}</ul>
            </details>
            <small>{t("sources.weather.research_only")}</small>
          </div>
          {envelope.data.length === 0 ? (
            <p role="status" data-empty-state="weather-readings">{t("sources.weather.empty")}</p>
          ) : (
            <div className="source-operations-table-wrap" tabIndex={0} role="region" aria-label={t("sources.weather.readings")}>
              <table className="source-operations-table" data-record="weather-readings">
                <thead>
                  <tr>
                    <th scope="col">{t("sources.weather.valid")}</th>
                    <th scope="col">{t("sources.weather.issued")}</th>
                    <th scope="col">{t("sources.weather.received")}</th>
                    <th scope="col">{t("sources.weather.temperature")}</th>
                    <th scope="col">{t("sources.weather.grid_point")}</th>
                  </tr>
                </thead>
                <tbody>{envelope.data.map((row) => (
                  <tr key={row.observation_id} data-record="weather-reading" data-record-id={row.observation_id}>
                    <td>{readingTime(row.valid_at_utc)}</td>
                    <td>{readingTime(row.issued_at_utc)}</td>
                    <td>{readingTime(row.available_at_utc)}</td>
                    <td>{row.temperature_c.toFixed(2)} °C</td>
                    <td><span>{row.grid_latitude.toFixed(4)}, {row.grid_longitude.toFixed(4)}</span><ReadingDetails row={row} t={t} /></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
