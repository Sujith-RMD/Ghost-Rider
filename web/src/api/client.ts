export type Result<T> =
  | { ok: true; data: T }
  | {
      ok: false;
      error: {
        family: "validation" | "analysis" | "integration";
        code: string;
        message: string;
      };
    };
export async function request(
  path: string,
  options?: RequestInit,
): Promise<Result<unknown>> {
  const base = import.meta.env.VITE_API_BASE_URL;
  if (!base)
    return {
      ok: false,
      error: {
        family: "integration",
        code: "api_not_configured",
        message: "The API address is not configured.",
      },
    };
  try {
    const response = await fetch(new URL(path, base), {
      ...options,
      credentials: "include",
      signal: options?.signal ?? AbortSignal.timeout(15000),
    });
    if (!response.ok)
      return {
        ok: false,
        error: {
          family: response.status === 422 ? "validation" : "integration",
          code: `http_${response.status}`,
          message: `The service returned ${response.status}.`,
        },
      };
    return { ok: true, data: (await response.json()) as unknown };
  } catch {
    return {
      ok: false,
      error: {
        family: "integration",
        code: "network",
        message:
          "The service could not be reached. Check your connection and retry.",
      },
    };
  }
}
