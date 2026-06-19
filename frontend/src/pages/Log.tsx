import { Search, Filter, ImageIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchMealImageObjectUrl, fetchMealLog } from "../lib/mealLog";
import type { MealLogItem } from "../lib/mealLog";

function MealImage({ meal }: { meal: MealLogItem }) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!meal.image) {
      setSrc(null);
      return;
    }

    let active = true;
    let objectUrl: string | null = null;

    fetchMealImageObjectUrl(meal.image)
      .then((url) => {
        if (active) {
          objectUrl = url;
          setSrc(url);
        } else {
          URL.revokeObjectURL(url);
        }
      })
      .catch(() => {
        // Leave the placeholder if the image can't be loaded.
      });

    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [meal.image]);

  if (src) {
    return <img src={src} alt={meal.name} className="log-card-image" />;
  }

  return (
    <div className="log-card-image log-card-image-placeholder" aria-hidden="true">
      <ImageIcon className="log-card-image-icon" />
    </div>
  );
}

export function Log() {
  const [meals, setMeals] = useState<MealLogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMealLog()
      .then(setMeals)
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Could not load meals");
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="page">
      <header className="log-header">
        <h1 className="log-title">Your Meal Log</h1>
        <div className="log-actions">
          <button type="button" className="log-icon-button" aria-label="Search meals">
            <Search className="log-icon" />
          </button>
          <button type="button" className="log-icon-button" aria-label="Filter meals">
            <Filter className="log-icon" />
          </button>
        </div>
      </header>

      {loading && <p className="auth-loading">Loading meals…</p>}
      {error && <p className="scan-error">{error}</p>}

      {!loading && !error && meals.length === 0 && (
        <p className="auth-loading">No meals yet. Scan your first meal to get started.</p>
      )}

      <div className="log-list">
        {meals.map((meal) => (
          <article key={meal.id} className="log-card">
            <div className="log-card-left">
              <MealImage meal={meal} />
              <div className="log-card-text">
                <div className="log-card-name">{meal.name}</div>
                <div className="log-card-date">{meal.date}</div>
                {meal.calories !== null ? (
                  <div className="log-card-macros">
                    <span>P: {meal.protein}</span>
                    <span>C: {meal.carbs}</span>
                    <span>F: {meal.fats}</span>
                  </div>
                ) : (
                  <div className="log-card-macros">Status: {meal.status}</div>
                )}
              </div>
            </div>
            <div className="log-card-calories">
              {meal.calories !== null ? (
                <>
                  <span className="log-card-calories-value">{meal.calories}</span>
                  <span className="log-card-calories-label">kcal</span>
                </>
              ) : (
                <span className="log-card-calories-label">Pending analysis</span>
              )}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
