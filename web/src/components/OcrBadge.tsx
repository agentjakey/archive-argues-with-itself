import { OCR_BADGE_LABEL, OCR_BADGE_TITLE } from "../lib/sensitivity";

/** A small, plain badge marking a shown line whose OCR confidence is low. Honest about text
 *  quality rather than hiding it. Render only when sensitivity.ocrUncertain(row.ocr_quality). */
export function OcrBadge() {
  return (
    <span className="tag" title={OCR_BADGE_TITLE}>
      {OCR_BADGE_LABEL}
    </span>
  );
}
