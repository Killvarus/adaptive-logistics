import type { ApiErrorBody, DatasetResponse, EvaluationResponse, OptimizationResponse, ScenarioInput } from "./types";

export class ApiClientError extends Error {
  status: number;
  body: ApiErrorBody | null;

  constructor(status: number, message: string, body: ApiErrorBody | null) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiClientError(0, "Не удалось связаться с расчётным сервисом.", null);
  }
  if (!response.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      body = null;
    }
    throw new ApiClientError(response.status, body?.error.message ?? "Запрос отклонён.", body);
  }
  return (await response.json()) as T;
}

export function fetchDemoDataset(signal?: AbortSignal): Promise<DatasetResponse> {
  return request<DatasetResponse>("/api/v1/datasets/demo", { signal });
}

export function evaluateScenario(input: ScenarioInput, signal?: AbortSignal): Promise<EvaluationResponse> {
  return request<EvaluationResponse>("/api/v1/evaluate", {
    method: "POST",
    body: JSON.stringify(input),
    signal,
  });
}

export function optimizeScenario(input: ScenarioInput, signal?: AbortSignal): Promise<OptimizationResponse> {
  return request<OptimizationResponse>("/api/v1/optimize", {
    method: "POST",
    body: JSON.stringify(input),
    signal,
  });
}
