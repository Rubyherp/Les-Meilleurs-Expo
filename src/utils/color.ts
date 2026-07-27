/**
 * Safely append an alpha hex suffix (e.g. "8C") to a 6-digit hex colour.
 *
 * Returns the original string unchanged when `hex` is not a valid 6-digit hex
 * colour (e.g. named colours, 3‑digit hex, rgba(), etc.) so that the caller
 * can still pass it to React Native which accepts most CSS colour formats.
 */
export function toHexWithAlpha(hex: string, alphaHex: string): string {
  if (/^#[0-9a-fA-F]{6}$/.test(hex)) {
    return hex + alphaHex;
  }
  return hex;
}
