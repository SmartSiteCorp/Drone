export type MissionItem = {
  seq: number;
  frame: number;
  command: number;
  current: number;
  autocontinue: number;
  param1: number;
  param2: number;
  param3: number;
  param4: number;
  x: number;
  y: number;
  z: number;
};

function asNumber(value: unknown, field: string): number {
  const n = Number(value);

  if (!Number.isFinite(n)) {
    throw new Error(`Valeur invalide pour ${field}`);
  }

  return n;
}

export function parseMissionFile(
  filename: string,
  content: string,
): MissionItem[] {
  const lower = filename.toLowerCase();

  if (
    lower.endsWith(".waypoints") ||
    content.trimStart().startsWith("QGC WPL")
  ) {
    return parseWaypoints(content);
  }

  if (
    lower.endsWith(".json") ||
    lower.endsWith(".mission") ||
    content.trimStart().startsWith("{")
  ) {
    return parseMissionJson(content);
  }

  throw new Error(
    "Format de mission non supporté (.waypoints, .mission ou .json attendu)",
  );
}

function parseWaypoints(content: string): MissionItem[] {
  const lines = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (!lines.length || !lines[0].startsWith("QGC WPL")) {
    throw new Error("Fichier QGC WPL invalide");
  }

  const items: MissionItem[] = [];

  for (let i = 1; i < lines.length; i++) {
    const columns = lines[i].split(/\s+/);

    if (columns.length < 12) {
      throw new Error(
        `Ligne ${i + 1} invalide : 12 colonnes attendues`,
      );
    }

    items.push({
      seq: asNumber(columns[0], "seq"),
      current: asNumber(columns[1], "current"),
      frame: asNumber(columns[2], "frame"),
      command: asNumber(columns[3], "command"),

      param1: asNumber(columns[4], "param1"),
      param2: asNumber(columns[5], "param2"),
      param3: asNumber(columns[6], "param3"),
      param4: asNumber(columns[7], "param4"),

      x: asNumber(columns[8], "latitude"),
      y: asNumber(columns[9], "longitude"),
      z: asNumber(columns[10], "altitude"),

      autocontinue: asNumber(columns[11], "autocontinue"),
    });
  }

  if (!items.length) {
    throw new Error("Mission vide");
  }

  return items;
}

function parseMissionJson(content: string): MissionItem[] {
  let parsed: any;

  try {
    parsed = JSON.parse(content);
  } catch {
    throw new Error("JSON invalide");
  }

  const sourceItems =
    parsed?.mission?.items ??
    parsed?.items;

  if (!Array.isArray(sourceItems)) {
    throw new Error(
      "JSON invalide : mission.items doit être un tableau",
    );
  }

  const items: MissionItem[] = [];

  for (let index = 0; index < sourceItems.length; index++) {
    const item = sourceItems[index];

    if (!item || typeof item !== "object") {
      throw new Error(`Mission item ${index} invalide`);
    }

    if (!Array.isArray(item.params) || item.params.length < 7) {
      throw new Error(
        `Mission item ${index} : params[0..6] requis`,
      );
    }

    items.push({
      seq: index,

      frame: asNumber(item.frame, `items[${index}].frame`),
      command: asNumber(
        item.command,
        `items[${index}].command`,
      ),

      current: index === 0 ? 1 : 0,

      autocontinue:
        item.autoContinue === false ? 0 : 1,

      param1: asNumber(item.params[0] ?? 0, "param1"),
      param2: asNumber(item.params[1] ?? 0, "param2"),
      param3: asNumber(item.params[2] ?? 0, "param3"),
      param4: asNumber(item.params[3] ?? 0, "param4"),

      x: asNumber(item.params[4] ?? 0, "latitude"),
      y: asNumber(item.params[5] ?? 0, "longitude"),
      z: asNumber(item.params[6] ?? 0, "altitude"),
    });
  }

  if (!items.length) {
    throw new Error("Mission vide");
  }

  return items;
}