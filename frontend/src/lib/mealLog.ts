import { getApiBaseUrl, getStoredToken } from "./auth";

export interface MealUploadMetadata {
  filename?: string;
  content_type?: string;
  file_size_bytes?: number;
  image_format?: string;
  image_type?: string;
  width?: number;
  height?: number;
  is_animated?: boolean;
  n_frames?: number;
  make?: string;
  model?: string;
  focal_length?: number;
  iso?: number;
  gps_latitude?: number;
  gps_longitude?: number;
  [key: string]: unknown;
}

export interface MealUploadResponse {
  meal_id: number;
  status: string;
  image_url?: string | null;
  thumbnail_url?: string | null;
  metadata: MealUploadMetadata;
}

export interface MealLogItem {
  id: string;
  name: string;
  date: string;
  protein: string | null;
  carbs: string | null;
  fats: string | null;
  calories: number | null;
  image: string | null;
  status: string;
}

export interface MealApiItem {
  meal_id: number;
  image_url: string | null;
  thumbnail_url: string | null;
  source: string;
  status: string;
  created_at: string;
  processed_at: string | null;
  rejection_reason: string | null;
  image_format: string | null;
  image_type: string | null;
}

function authHeaders(): HeadersInit {
  const token = getStoredToken();
  if (!token) {
    throw new Error("Not authenticated");
  }
  return { Authorization: `Bearer ${token}` };
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
  } catch {
    // ignore
  }
  return `Request failed (${res.status})`;
}

export function mealApiItemToLogItem(meal: MealApiItem): MealLogItem {
  const formatLabel = meal.image_format ?? "Image";
  const name = `${formatLabel} scan #${meal.meal_id}`;

  return {
    id: String(meal.meal_id),
    name,
    date: new Date(meal.created_at).toLocaleDateString(),
    protein: null,
    carbs: null,
    fats: null,
    calories: null,
    image: meal.thumbnail_url ?? meal.image_url,
    status: meal.status,
  };
}

export async function uploadMealImage(file: File): Promise<MealUploadResponse> {
  const formData = new FormData();
  formData.append("image", file);

  const res = await fetch(`${getApiBaseUrl()}/api/upload`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });

  if (!res.ok) {
    throw new Error(await parseError(res));
  }

  return res.json();
}

/**
 * Fetch a protected meal image (a relative `/api/meals/:id/image` path) with
 * the bearer token and return an object URL usable as an <img> src.
 *
 * An <img> tag can't send the Authorization header itself, so we fetch the
 * bytes here and wrap them in a blob URL. Callers MUST revoke the returned URL
 * (URL.revokeObjectURL) when done to avoid leaking memory.
 */
export async function fetchMealImageObjectUrl(path: string): Promise<string> {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    headers: authHeaders(),
  });

  if (!res.ok) {
    throw new Error(await parseError(res));
  }

  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export async function fetchMealLog(): Promise<MealLogItem[]> {
  const res = await fetch(`${getApiBaseUrl()}/api/meals`, {
    headers: authHeaders(),
  });

  if (!res.ok) {
    throw new Error(await parseError(res));
  }

  const meals: MealApiItem[] = await res.json();
  return meals.map(mealApiItemToLogItem);
}
