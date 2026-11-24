/**
 * Who set a figure and who approved it (P-17 maker-checker): "Set by A · approved by B, 12 Nov
 * 14:02". A figure set by one person (four eyes off for that write, or set before P-17) says
 * so, so a reader never takes a single person's figure for an approved one.
 */
import type { FigureProvenanceDTO } from "@/api/client";
import { provenanceParts } from "@/app/model/makerCheckerModel";
import { Instant } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export function FigureProvenance({ provenance, t }: { provenance?: FigureProvenanceDTO | null; t: Translate }) {
  const parts = provenanceParts(provenance);
  if (!parts) return null;
  const words =
    parts.kind === "approved"
      ? t("changes.provenance.approved", { setBy: parts.value.setBy, approvedBy: parts.value.approvedBy })
      : t("changes.provenance.single", { setBy: parts.value.setBy });
  return (
    <small
      className="figure-provenance"
      data-provenance={parts.kind}
      title={parts.kind === "approved" && provenance?.reason ? `${t("changes.why")}: ${provenance.reason}` : undefined}
    >
      {words}
      {parts.value.at && (
        <>
          {", "}
          <Instant value={parts.value.at} />
        </>
      )}
    </small>
  );
}
