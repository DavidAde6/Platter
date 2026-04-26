import { Target, CalendarCheck2, Utensils, Activity } from 'lucide-react'

export function Trends() {
  return (
    <div className="page">
      <section className="trends-summary-row">
        <article className="trends-summary-card trends-summary-card--green">
          <header className="trends-summary-header">
            <div>
              <div className="trends-summary-label">Daily Avg Calories</div>
              <div className="trends-summary-value">2,142</div>
            </div>
            <div className="trends-summary-pill trends-summary-pill-green">
              <Target className="trends-summary-icon" />
            </div>
          </header>
          <div className="trends-summary-footer">4% below goal</div>
        </article>

        <article className="trends-summary-card trends-summary-card--purple">
          <header className="trends-summary-header">
            <div>
              <div className="trends-summary-label">Weekly Consistency</div>
              <div className="trends-summary-value">92%</div>
            </div>
            <div className="trends-summary-pill trends-summary-pill-purple">
              <CalendarCheck2 className="trends-summary-icon" />
            </div>
          </header>
          <div className="trends-summary-footer">Perfect streak: 5 days</div>
        </article>

        <article className="trends-summary-card trends-summary-card--pink">
          <header className="trends-summary-header">
            <div>
              <div className="trends-summary-label">Meals Tracked</div>
              <div className="trends-summary-value">24</div>
            </div>
            <div className="trends-summary-pill trends-summary-pill-pink">
              <Utensils className="trends-summary-icon" />
            </div>
          </header>
          <div className="trends-summary-footer">New level unlocked!</div>
        </article>

        <article className="trends-summary-card trends-summary-card--orange">
          <header className="trends-summary-header">
            <div>
              <div className="trends-summary-label">Health Score</div>
              <div className="trends-summary-value">A-</div>
            </div>
            <div className="trends-summary-pill trends-summary-pill-orange">
              <Activity className="trends-summary-icon" />
            </div>
          </header>
          <div className="trends-summary-footer">Top 10% of users</div>
        </article>
      </section>

      <section className="trends-main-grid">
        <article className="trends-main-card">
          <header className="trends-main-header">
            <span className="trends-main-title">Calorie Trend</span>
            <span className="trends-main-meta">Last 7 Days</span>
          </header>
          <div className="trends-line-chart" aria-hidden="true">
            <svg viewBox="0 0 320 140" preserveAspectRatio="none">
              <defs>
                <linearGradient id="calorieFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#22c55e" stopOpacity="0.32" />
                  <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
                </linearGradient>
              </defs>
              <path
                d="M10 90 Q 60 75 110 60 T 210 70 T 310 55"
                fill="none"
                stroke="#22c55e"
                strokeWidth="3"
                strokeLinecap="round"
              />
              <path
                d="M10 90 Q 60 75 110 60 T 210 70 T 310 55 L 310 140 L 10 140 Z"
                fill="url(#calorieFill)"
              />
            </svg>
            <div className="trends-line-chart-labels">
              {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((day) => (
                <span key={day}>{day}</span>
              ))}
            </div>
          </div>
        </article>

        <article className="trends-main-card trends-macros-card">
          <header className="trends-main-header">
            <span className="trends-main-title">Average Macros</span>
          </header>
          <div className="trends-macros-content">
            <div className="trends-macros-bars" aria-hidden="true">
              <div className="trends-macro-bar">
                <div className="trends-macro-bar-fill trends-macro-bar-protein" />
                <span className="trends-bar-label">Protein</span>
              </div>
              <div className="trends-macro-bar">
                <div className="trends-macro-bar-fill trends-macro-bar-carbs" />
                <span className="trends-bar-label">Carbs</span>
              </div>
              <div className="trends-macro-bar">
                <div className="trends-macro-bar-fill trends-macro-bar-fat" />
                <span className="trends-bar-label">Fat</span>
              </div>
            </div>
            <table className="trends-macros-table">
              <tbody>
                <tr>
                  <td>
                    <span className="trends-macros-dot trends-macros-dot-protein" />
                    Protein
                  </td>
                  <td className="trends-macros-value">120 g</td>
                </tr>
                <tr>
                  <td>
                    <span className="trends-macros-dot trends-macros-dot-carbs" />
                    Carbs
                  </td>
                  <td className="trends-macros-value">240 g</td>
                </tr>
                <tr>
                  <td>
                    <span className="trends-macros-dot trends-macros-dot-fat" />
                    Fat
                  </td>
                  <td className="trends-macros-value">70 g</td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </div>
  )
}

