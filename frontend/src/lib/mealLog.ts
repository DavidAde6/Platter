export interface ScanApiResponse {
  query: string;
  food: string;
  serving: number;
  macros: Record<string, { value: number; unit: string }>;
}

export interface MealLogItem {
  id: string;
  name: string;
  date: string;
  protein: string;
  carbs: string;
  fats: string;
  calories: number;
  image: string;
}

const MEAL_LOG_KEY = "platter.mealLog";

export function getMealLog(): MealLogItem[] {
  const raw = localStorage.getItem(MEAL_LOG_KEY);
  if (!raw) return [];

  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveMealLog(meals: MealLogItem[]) {
  localStorage.setItem(MEAL_LOG_KEY, JSON.stringify(meals));
}

export function addMealLogItem(item: MealLogItem) {
  const current = getMealLog();
  saveMealLog([item, ...current]);
}
