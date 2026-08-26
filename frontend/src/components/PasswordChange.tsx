import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ApiError, api, type User } from "../lib/api";
import { AmbientGlow, Wordmark } from "./Brand";
import { Spinner } from "./AuthFlow";

const RULES: { label: string; test: (v: string) => boolean }[] = [
  { label: "12 caracteres minimum", test: (v) => v.length >= 12 },
  { label: "Une minuscule", test: (v) => /[a-z]/.test(v) },
  { label: "Une majuscule", test: (v) => /[A-Z]/.test(v) },
  { label: "Un chiffre", test: (v) => /\d/.test(v) },
  { label: "Un caractere special", test: (v) => /[^\w\s]/.test(v) },
];

export function PasswordChange({ onDone }: { onDone: (user: User) => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const passed = useMemo(() => RULES.map((r) => r.test(next)), [next]);
  const strength = passed.filter(Boolean).length;
  const matches = next.length > 0 && next === confirm;
  const ready = strength === RULES.length && matches && current.length > 0;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await api<User>("/auth/password", {
        method: "POST",
        body: { current_password: current, new_password: next },
      });
      onDone(user);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Modification impossible.");
    } finally {
      setBusy(false);
    }
  }

  const bar = ["bg-poppy-600", "bg-poppy-500", "bg-accent-fire", "bg-accent-fire", "bg-accent-mint"][
    Math.max(0, strength - 1)
  ];

  return (
    <div className="relative flex min-h-screen items-center justify-center px-5 py-10">
      <AmbientGlow />
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-[27rem]"
      >
        <div className="mb-8 flex justify-center">
          <Wordmark />
        </div>

        <form onSubmit={submit} className="panel p-7">
          <h2 className="font-display text-lg font-semibold text-ink-100">
            Definir votre mot de passe
          </h2>
          <p className="mt-1 text-sm text-ink-300">
            Le mot de passe fourni par Devoteam est provisoire. Choisissez-en un nouveau pour
            continuer.
          </p>

          <div className="mt-6">
            <label className="label" htmlFor="current">
              Mot de passe provisoire
            </label>
            <input
              id="current"
              type="password"
              className="field"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div className="mt-4">
            <label className="label" htmlFor="next">
              Nouveau mot de passe
            </label>
            <input
              id="next"
              type="password"
              className="field"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
            />
            <div className="mt-3 h-1 overflow-hidden rounded-full bg-ink-700">
              <motion.div
                className={`h-full ${bar}`}
                animate={{ width: `${(strength / RULES.length) * 100}%` }}
                transition={{ duration: 0.3 }}
              />
            </div>
            <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5">
              {RULES.map((rule, i) => (
                <li
                  key={rule.label}
                  className={`flex items-center gap-1.5 text-[12px] transition-colors ${
                    passed[i] ? "text-accent-mint" : "text-ink-400"
                  }`}
                >
                  <span aria-hidden="true">{passed[i] ? "✓" : "○"}</span>
                  {rule.label}
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-4">
            <label className="label" htmlFor="confirm">
              Confirmation
            </label>
            <input
              id="confirm"
              type="password"
              className="field"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
            />
            {confirm.length > 0 && !matches && (
              <p className="mt-2 text-xs font-medium text-ink-100">Les deux saisies different.</p>
            )}
          </div>

          {error && (
            <p
              role="alert"
              className="mt-5 rounded-xl border border-poppy-500/40 bg-poppy-500/10 px-4 py-3 text-sm text-ink-100"
            >
              {error}
            </p>
          )}

          <button type="submit" disabled={busy || !ready} className="btn-primary mt-6 w-full">
            {busy ? <Spinner /> : null}
            {busy ? "Enregistrement…" : "Enregistrer et continuer"}
          </button>
        </form>
      </motion.div>
    </div>
  );
}
