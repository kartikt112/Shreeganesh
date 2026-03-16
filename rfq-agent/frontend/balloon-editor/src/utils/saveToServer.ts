import Konva from "konva";
import type { Feature } from "../types/feature";
import type { ManufacturingMetadata } from "../types/metadata";

/**
 * Save features + rendered canvas PNG + editor draft to the backend API.
 * Called when the user clicks "Save to Server" in the balloon editor.
 */
export async function saveToServer(
  rfqId: number,
  apiBase: string,
  features: Feature[],
  metadata: ManufacturingMetadata | null,
  stage: Konva.Stage
): Promise<void> {
  // 1. Save features via bulk endpoint (for DB)
  const bulkResp = await fetch(`${apiBase}/api/rfq/${rfqId}/features/bulk`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ features }),
  });
  if (!bulkResp.ok) {
    const err = await bulkResp.text();
    throw new Error(`Failed to save features: ${err}`);
  }

  // 2. Export canvas as PNG blob and upload as the new ballooned image
  const dataUrl = stage.toDataURL({ pixelRatio: 2 });
  const blob = await (await fetch(dataUrl)).blob();

  const formData = new FormData();
  formData.append("file", blob, "ballooned.png");

  const imgResp = await fetch(
    `${apiBase}/api/rfq/${rfqId}/ballooned-image`,
    { method: "POST", body: formData }
  );
  if (!imgResp.ok) {
    const err = await imgResp.text();
    throw new Error(`Failed to upload ballooned image: ${err}`);
  }

  // 3. Save editor draft JSON (preserves balloon positions, radii, etc.)
  const draftResp = await fetch(
    `${apiBase}/api/rfq/${rfqId}/editor-draft`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        features,
        manufacturing_metadata: metadata || {},
      }),
    }
  );
  if (!draftResp.ok) {
    const err = await draftResp.text();
    throw new Error(`Failed to save editor draft: ${err}`);
  }

  // 4. Notify opener window (review page) to refresh, then close editor
  if (window.opener) {
    window.opener.postMessage(
      { type: "editor-saved", rfqId },
      "*"
    );
  }
  window.close();
}
