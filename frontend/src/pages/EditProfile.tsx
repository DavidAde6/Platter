import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export function EditProfile() {
  const { user, updateProfile } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState(user?.user_name ?? "");
  const [dailyCaloricTarget, setDailyCaloricTarget] = useState(
    user?.daily_caloric_target?.toString() ?? "",
  );
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    const parsedTarget = dailyCaloricTarget.trim()
      ? Number(dailyCaloricTarget)
      : null;

    if (parsedTarget !== null && (Number.isNaN(parsedTarget) || parsedTarget < 500)) {
      setError("Daily calorie target must be at least 500 kcal");
      setSubmitting(false);
      return;
    }

    try {
      await updateProfile({
        user_name: name.trim(),
        daily_caloric_target: parsedTarget,
        ...(password ? { password } : {}),
      });
      navigate("/profile");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page">
      <section className="page-card auth-card">
        <div className="page-card-header">
          <h1 className="page-card-title">Edit profile</h1>
          <p className="page-card-subtitle">Update your account details</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="auth-field">
            <span>Name</span>
            <input
              type="text"
              autoComplete="name"
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>

          <label className="auth-field">
            <span>Email</span>
            <input type="email" value={user?.user_email ?? ""} disabled />
          </label>

          <label className="auth-field">
            <span>Daily calorie target</span>
            <input
              type="number"
              min={500}
              max={10000}
              placeholder="Leave blank if unset"
              value={dailyCaloricTarget}
              onChange={(event) => setDailyCaloricTarget(event.target.value)}
            />
          </label>

          <label className="auth-field">
            <span>New password (optional)</span>
            <input
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          {error && <p className="auth-error">{error}</p>}

          <button type="submit" className="auth-submit" disabled={submitting}>
            {submitting ? "Saving…" : "Save changes"}
          </button>
        </form>

        <p className="auth-switch">
          <Link to="/profile">Cancel</Link>
        </p>
      </section>
    </div>
  );
}
