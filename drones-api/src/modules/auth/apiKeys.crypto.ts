import crypto from "crypto";

function base64url(buf: Buffer) {
  return buf
    .toString("base64")
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");
}

/**
 * Génère une clé API lisible, longue, difficile à deviner.
 * Exemple: dc_xxxxx.yyyyy
 */
export function generateApiKey(): string {
  const a = base64url(crypto.randomBytes(24));
  const b = base64url(crypto.randomBytes(24));
  return `dc_${a}.${b}`;
}

/**
 * Prefix pour retrouver rapidement une clé en DB (index).
 * Ici: "dc_" + 12 chars après.
 */
export function getKeyPrefix(apiKey: string): string {
  // "dc_" + 12 chars = 15 chars environ, assez pour éviter collisions
  return apiKey.slice(0, Math.min(apiKey.length, 15));
}

/**
 * Hash sécurisé (scrypt) + sel.
 * Stockage: scrypt$<salt>$<hash>
 */
export function hashApiKey(apiKey: string): string {
  const salt = crypto.randomBytes(16);
  const derived = crypto.scryptSync(apiKey, salt, 32);
  return `scrypt$${salt.toString("hex")}$${derived.toString("hex")}`;
}

/**
 * Comparaison (utile plus tard pour l’auth).
 */
export function verifyApiKey(apiKey: string, stored: string): boolean {
  const [algo, saltHex, hashHex] = stored.split("$");
  if (algo !== "scrypt" || !saltHex || !hashHex) return false;

  const salt = Buffer.from(saltHex, "hex");
  const derived = crypto.scryptSync(apiKey, salt, 32);
  const expected = Buffer.from(hashHex, "hex");
  return crypto.timingSafeEqual(derived, expected);
}
