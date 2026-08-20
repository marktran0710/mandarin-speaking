/** Small, auditable IRT layer for question selection and pilot calibration.
 * It starts with Rasch-compatible estimates and accepts discrimination so the
 * question bank can graduate to 2PL without changing its stored schema. */

export interface IrtItem {
  itemId: string;
  prompt: string;
  targetTonePattern: string;
  difficulty: number;
  discrimination: number;
  exposureCount?: number;
  active?: boolean;
}

export interface IrtResponse {
  studentId: string;
  itemId: string;
  correct: boolean;
  condition?: "control" | "experimental";
}

export interface IrtCalibration {
  itemId: string;
  n: number;
  proportionCorrect: number;
  difficulty: number;
  discrimination: number;
  usable: boolean;
  flags: string[];
}

const EPSILON = 0.01;

export function irtProbability(theta: number, item: Pick<IrtItem, "difficulty" | "discrimination">): number {
  const exponent = item.discrimination * (theta - item.difficulty);
  return 1 / (1 + Math.exp(-exponent));
}

export function estimateAbility(
  responses: Array<{ item: Pick<IrtItem, "difficulty" | "discrimination">; correct: boolean }>,
  initialTheta = 0,
): number {
  if (responses.length === 0) return initialTheta;
  let theta = initialTheta;
  for (let iteration = 0; iteration < 12; iteration += 1) {
    let score = 0;
    let information = 0;
    for (const response of responses) {
      const probability = irtProbability(theta, response.item);
      score += response.item.discrimination * ((response.correct ? 1 : 0) - probability);
      information += response.item.discrimination ** 2 * probability * (1 - probability);
    }
    if (information < EPSILON) break;
    theta = Math.max(-4, Math.min(4, theta + score / information));
  }
  return Math.round(theta * 100) / 100;
}

export function calibrateItems(items: IrtItem[], responses: IrtResponse[]): IrtCalibration[] {
  return items.map((item) => {
    const itemResponses = responses.filter((response) => response.itemId === item.itemId);
    const n = itemResponses.length;
    const proportionCorrect = n ? itemResponses.filter((response) => response.correct).length / n : 0;
    const clipped = Math.min(1 - EPSILON, Math.max(EPSILON, proportionCorrect));
    const difficulty = Math.round(-Math.log(clipped / (1 - clipped)) * 100) / 100;
    const flags: string[] = [];
    if (n < 30) flags.push("small_sample");
    if (proportionCorrect >= 0.95) flags.push("too_easy");
    if (proportionCorrect <= 0.05) flags.push("too_hard");
    return {
      itemId: item.itemId,
      n,
      proportionCorrect: Math.round(proportionCorrect * 1000) / 1000,
      difficulty,
      discrimination: item.discrimination,
      usable: n >= 30 && flags.every((flag) => flag !== "too_easy" && flag !== "too_hard"),
      flags,
    };
  });
}

export function selectNextItem(items: IrtItem[], theta: number, excludedIds: string[] = []): IrtItem | null {
  const excluded = new Set(excludedIds);
  return items
    .filter((item) => item.active !== false && !excluded.has(item.itemId))
    .sort((a, b) => {
      const aDistance = Math.abs(a.difficulty - theta) + (a.exposureCount ?? 0) * 0.01;
      const bDistance = Math.abs(b.difficulty - theta) + (b.exposureCount ?? 0) * 0.01;
      return aDistance - bDistance;
    })[0] ?? null;
}
