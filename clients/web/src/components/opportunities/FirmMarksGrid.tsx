/**
 * Enter marks (B.7): a small grid of hub × month in each hub's native unit, stored as the firm's
 * own marks (`PUT /api/market/firm-marks`). Every row says "firm's mark": a mark is the desk's
 * figure, never a price from the market, and an opportunity priced from marks is at most
 * indicative unless the firm's setting accepts marks.
 */
import { useEffect, useState } from "react";

import { api, type FirmMarkDTO } from "@/api/client";
import { MARK_HUBS, markRowsToCells, nextMonths, type MarkRow } from "@/app/model/firmMarksModel";
import { saveOutcome } from "@/app/model/makerCheckerModel";
import { Button, Select } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export function FirmMarksGrid({ t, onClose, onSaved }: { t: Translate; onClose: () => void; onSaved: () => void }) {
  const months = nextMonths(new Date(), 6);
  const [held, setHeld] = useState<FirmMarkDTO[]>([]);
  const [rows, setRows] = useState<MarkRow[]>([{ hub: "TTF", values: {} }]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // P-17: marks wait for an independent price check by the risk function before they count.
  const [proposed, setProposed] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .firmMarks({ signal: controller.signal })
      .then((response) => setHeld(response.data.marks))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const save = () => {
    const result = markRowsToCells(rows, months);
    if ("error" in result) {
      setError(t(`opportunities.marks.error.${result.error}`, { cell: result.cell }));
      return;
    }
    setSaving(true);
    setError(null);
    api
      .putFirmMarks(result.cells)
      .then((response) => {
        const outcome = saveOutcome(response.data);
        if (outcome === "saved") {
          onSaved();
          return;
        }
        setRows([{ hub: "TTF", values: {} }]);
        setProposed(t(outcome === "proposed" ? "opportunities.marks.proposed" : "changes.unchanged"));
      })
      .catch(() => setError(t("opportunities.marks.error.rejected")))
      .finally(() => setSaving(false));
  };

  const heldFor = (hub: string, month: string) => held.find((mark) => mark.hub === hub && mark.period === month);

  return (
    <section className="firm-marks" aria-labelledby="firm-marks-title" data-firm-marks="true">
      <h3 id="firm-marks-title">{t("opportunities.marks.title")}</h3>
      <p className="opportunities-muted">{t("opportunities.marks.statement")}</p>
      <table className="firm-marks-grid">
        <thead>
          <tr>
            <th scope="col">{t("opportunities.marks.hub")}</th>
            {months.map((month) => (
              <th key={month} scope="col">
                {month}
              </th>
            ))}
            <th scope="col">{t("opportunities.marks.unit")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              <th scope="row">
                <Select
                  aria-label={t("opportunities.marks.hub")}
                  value={row.hub}
                  options={MARK_HUBS.map((hub) => ({ value: hub.code, label: hub.code }))}
                  onChange={(hub) => setRows(rows.map((item, at) => (at === index ? { ...item, hub } : item)))}
                />
              </th>
              {months.map((month) => {
                const current = heldFor(row.hub, month);
                return (
                  <td key={month}>
                    <input
                      className="ds-input firm-marks-cell"
                      inputMode="decimal"
                      aria-label={`${row.hub} ${month}`}
                      placeholder={current ? String(current.value) : ""}
                      value={row.values[month] ?? ""}
                      onChange={(event) =>
                        setRows(
                          rows.map((item, at) =>
                            at === index ? { ...item, values: { ...item.values, [month]: event.target.value } } : item,
                          ),
                        )
                      }
                    />
                  </td>
                );
              })}
              <td className="opportunities-muted">{MARK_HUBS.find((hub) => hub.code === row.hub)?.unit}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {proposed && (
        <p className="opportunity-message" role="status" data-marks-proposed="true">
          {proposed}
        </p>
      )}
      {error && (
        <p className="opportunity-message" role="alert">
          {error}
        </p>
      )}
      <div className="opportunity-actions">
        <Button variant="secondary" onClick={() => setRows([...rows, { hub: "THE", values: {} }])}>
          {t("opportunities.marks.add_hub")}
        </Button>
        <Button variant="primary" onClick={save} disabled={saving}>
          {t("opportunities.marks.save")}
        </Button>
        <Button variant="quiet" onClick={onClose}>
          {t("opportunities.marks.cancel")}
        </Button>
      </div>
    </section>
  );
}
