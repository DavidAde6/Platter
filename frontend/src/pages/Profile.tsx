import { UserRound } from 'lucide-react'

export function Profile() {
  return (
    <div className="page">
      <section>
        <div className="profile-header">
          <div className="profile-avatar">
            <UserRound className="profile-avatar-icon" />
          </div>
          <h1 className="profile-name">Alex Johnson</h1>
          <div className="profile-meta">Member since Feb 2026</div>
        </div>

        <div className="profile-card">
          <div className="profile-card-header">Health Profile</div>
          <table className="profile-table">
            <tbody>
              <tr className="profile-table-row">
                <td className="profile-table-label">Height</td>
                <td className="profile-table-value">182 cm</td>
              </tr>
              <tr className="profile-table-row">
                <td className="profile-table-label">Weight</td>
                <td className="profile-table-value">78 kg</td>
              </tr>
              <tr className="profile-table-row">
                <td className="profile-table-label">Daily Calorie Target</td>
                <td className="profile-table-value">2,450 kcal</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="profile-actions">
          <button type="button" className="profile-primary-button">
            Edit Profile
          </button>
          <button type="button" className="profile-logout">
            Logout
          </button>
        </div>
      </section>
    </div>
  )
}

