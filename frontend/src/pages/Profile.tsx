import { UserRound } from "lucide-react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function formatMemberSince(createdAt: string) {
  return new Date(createdAt).toLocaleDateString(undefined, {
    month: "short",
    year: "numeric",
  });
}

function formatCalories(value: number | null) {
  if (value === null) return "Not set";
  return `${value.toLocaleString()} kcal`;
}

export function Profile() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="page">
      <section>
        <div className="profile-header">
          <div className="profile-avatar">
            <UserRound className="profile-avatar-icon" />
          </div>
          <h1 className="profile-name">{user.user_name}</h1>
          <div className="profile-meta">
            {user.user_email} · Member since {formatMemberSince(user.created_at)}
          </div>
        </div>

        <div className="profile-card">
          <div className="profile-card-header">Account</div>
          <table className="profile-table">
            <tbody>
              <tr className="profile-table-row">
                <td className="profile-table-label">Daily Calorie Target</td>
                <td className="profile-table-value">
                  {formatCalories(user.daily_caloric_target)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="profile-actions">
          <Link to="/profile/edit" className="profile-primary-button">
            Edit Profile
          </Link>
          <button type="button" className="profile-logout" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </section>
    </div>
  );
}
