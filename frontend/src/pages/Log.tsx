import { Search, Filter } from 'lucide-react'
import quinoaBowl from '../assets/images/73866.jpg'
import salmonAsparagus from '../assets/images/68708.jpg'
import cheeseburger from '../assets/images/125745.jpg'
import { useEffect, useState } from 'react'
import { getMealLog } from '../lib/mealLog'
import type { MealLogItem } from '../lib/mealLog'

const fallbackMeals: MealLogItem[] = [
  {
    id: '1',
    name: 'Quinoa Power Bowl',
    date: '3/14/2026',
    protein: '22g',
    carbs: '65g',
    fats: '18g',
    calories: 520,
    image: quinoaBowl,
  },
  {
    id: '2',
    name: 'Salmon Asparagus',
    date: '3/13/2026',
    protein: '38g',
    carbs: '26g',
    fats: '26g',
    calories: 420,
    image: salmonAsparagus,
  },
  {
    id: '3',
    name: 'Classic Cheeseburger',
    date: '3/12/2026',
    protein: '32g',
    carbs: '55g',
    fats: '48g',
    calories: 850,
    image: cheeseburger,
  },
]

export function Log() {
  const [meals, setMeals] = useState<MealLogItem[]>([])

  useEffect(() => {
    const savedMeals = getMealLog()
    setMeals(savedMeals.length > 0 ? savedMeals : fallbackMeals)
  }, [])

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

      <div className="log-list">
        {meals.map((meal) => (
          <article key={meal.id} className="log-card">
            <div className="log-card-left">
              <img src={meal.image} alt={meal.name} className="log-card-image" />
              <div className="log-card-text">
                <div className="log-card-name">{meal.name}</div>
                <div className="log-card-date">{meal.date}</div>
                <div className="log-card-macros">
                  <span>P: {meal.protein}</span>
                  <span>C: {meal.carbs}</span>
                  <span>F: {meal.fats}</span>
                </div>
              </div>
            </div>
            <div className="log-card-calories">
              <span className="log-card-calories-value">{meal.calories}</span>
              <span className="log-card-calories-label">kcal</span>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

