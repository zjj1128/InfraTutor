import type { RoadmapData, SeedName } from "../types/roadmap";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

export async function fetchRoadmap(signal?: AbortSignal): Promise<RoadmapData> {
  const response = await fetch(`${API_BASE_URL}/roadmap`, { signal });
  if (!response.ok) {
    throw new Error(`路线加载失败 (${response.status})`);
  }
  return response.json() as Promise<RoadmapData>;
}

export async function resetLearner(seed: SeedName): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/demo/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ seed }),
  });
  if (!response.ok) {
    throw new Error(`学习状态重置失败 (${response.status})`);
  }
}
