import { useState, type FormEvent } from "react";
import { login } from "../api/client";
import type { LoginResponse } from "../types/api";

interface LoginFormProps {
  onLoginSuccess: (session: LoginResponse) => void;
}

export function LoginForm({ onLoginSuccess }: LoginFormProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const session = await login(email, password);
      onLoginSuccess(session);
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al iniciar sesión");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="card" aria-labelledby="login-heading">
      <div className="card-header">
        <div>
          <h2 id="login-heading" className="card-title">
            Iniciar sesión
          </h2>
          <p className="card-subtitle">
            Accede a tus cursos, sílabos y cronograma de estudio.
          </p>
        </div>
      </div>

      <form className="form-stack" onSubmit={(e) => void handleSubmit(e)}>
        <div className="form-field">
          <label className="form-label" htmlFor="login-email">
            Correo electrónico
          </label>
          <input
            id="login-email"
            className="form-input"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="usuario@universidad.edu"
          />
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor="login-password">
            Contraseña
          </label>
          <input
            id="login-password"
            className="form-input"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Ingresa tu contraseña"
          />
        </div>

        {error && (
          <div className="alert alert--error" role="alert">
            {error}
          </div>
        )}

        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? "Ingresando..." : "Ingresar"}
        </button>
      </form>
    </section>
  );
}
