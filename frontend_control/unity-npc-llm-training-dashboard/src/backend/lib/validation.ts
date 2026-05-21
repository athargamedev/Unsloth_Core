import type { StartCommandPayload } from "../types";

/**
 * Validates required fields in a command payload.
 * Supports nested "options.xxx" notation.
 */
export function validateRequiredFields(
  payload: StartCommandPayload,
  requiredFields: string[],
): void {
  for (const requiredField of requiredFields) {
    const [root, key] = requiredField.split(".");
    if (root === "options" && key) {
      const value = payload.options?.[key];
      if (
        value === undefined ||
        value === null ||
        String(value).trim() === ""
      ) {
        throw new Error(`${requiredField} is required.`);
      }
      continue;
    }

    const directValue = (
      payload as unknown as Record<string, unknown>
    )[requiredField];
    if (
      directValue === undefined ||
      directValue === null ||
      String(directValue).trim() === ""
    ) {
      throw new Error(`${requiredField} is required.`);
    }
  }
}
