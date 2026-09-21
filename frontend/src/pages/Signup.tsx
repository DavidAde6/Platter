import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export function Signup() {
  const { signup } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [dailyCaloricTarget, setDailyCaloricTarget] = useState("");
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
      await signup(name.trim(), email.trim(), password, parsedTarget);
      navigate("/profile", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page">
      <section className="page-card auth-card">
        <div className="page-card-header">
          <h1 className="page-card-title">Create your account</h1>
          <p className="page-card-subtitle">Start tracking meals with Platter</p>
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
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>

          <label className="auth-field">
            <span>Password</span>
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          <label className="auth-field">
            <span>Daily calorie target (optional)</span>
            <input
              type="number"
              min={500}
              max={10000}
              placeholder="e.g. 2450"
              value={dailyCaloricTarget}
              onChange={(event) => setDailyCaloricTarget(event.target.value)}
            />
          </label>

          {error && <p className="auth-error">{error}</p>}

          <button type="submit" className="auth-submit" disabled={submitting}>
            {submitting ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="auth-switch">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </section>
    </div>
  );
}
