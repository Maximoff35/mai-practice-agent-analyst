import type { AnalysisResult } from "./types";
import { buildMockAnalysisResult } from "./mock";

const MOCK_DELAY_MS = 700;

export async function analyzeRequirements(
  requirements: string,
): Promise<AnalysisResult> {
  // TODO: заменить на POST /api/analyze после готовности backend.
  await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY_MS));
  return buildMockAnalysisResult(requirements);
}