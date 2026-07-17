import { supabase } from "@/lib/supabase";
import type {
  Advice,
  Alert,
  Field,
  Observation,
  PolygonGeometry,
  RefreshResult,
  Weather,
} from "@/lib/types";

const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** An error carrying a message intended to be shown to the user as-is. */
export class ApiError extends Error {}

async function authorizedFetch(path: string, init?: RequestInit): Promise<Response> {
  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session) {
    throw new ApiError("Please sign in again.");
  }

  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${data.session.access_token}`,
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError("Could not reach the server. Check your connection.");
  }

  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response));
  }
  return response;
}

/**
 * FastAPI reports our deliberate rejections as a `detail` string, but its own
 * validation failures as a list of error objects. Flatten both into something
 * a person can read.
 */
async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && typeof detail[0]?.msg === "string") {
      return detail[0].msg.replace(/^Value error, /, "");
    }
  } catch {
    // Fall through to the generic message below.
  }
  return "Something went wrong. Please try again.";
}

export async function listFields(): Promise<Field[]> {
  const response = await authorizedFetch("/fields");
  return (await response.json()) as Field[];
}

export async function createField(
  name: string,
  geometry: PolygonGeometry,
): Promise<Field> {
  const response = await authorizedFetch("/fields", {
    method: "POST",
    body: JSON.stringify({ name, geometry }),
  });
  return (await response.json()) as Field;
}

export async function refreshField(id: string): Promise<RefreshResult> {
  const response = await authorizedFetch(`/fields/${id}/refresh`);
  return (await response.json()) as RefreshResult;
}

export async function listObservations(id: string): Promise<Observation[]> {
  const response = await authorizedFetch(`/fields/${id}/observations`);
  return (await response.json()) as Observation[];
}

export async function listAlerts(id: string): Promise<Alert[]> {
  const response = await authorizedFetch(`/fields/${id}/alerts`);
  return (await response.json()) as Alert[];
}

export async function getWeather(id: string): Promise<Weather> {
  const response = await authorizedFetch(`/fields/${id}/weather`);
  return (await response.json()) as Weather;
}

export async function getAdvice(id: string, crop?: string): Promise<Advice> {
  const response = await authorizedFetch(`/fields/${id}/advice`, {
    method: "POST",
    body: JSON.stringify({ crop: crop || null }),
  });
  return (await response.json()) as Advice;
}
