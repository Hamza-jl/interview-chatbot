import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ApiError,
  api,
  setAccessToken,
  type LoginResponse,
  type TokenResponse,
  type TotpEnrollment,
} from "../lib/api";
import { AmbientGlow, CoBrand, SecurityBadge } from "./Brand";

type Stage = "credentials" | "totp" | "enroll";

const fade = {
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 },
  transition: { duration: 0.32, ease: [0.22, 1, 0.36, 1] as const },
};

export function AuthFlow({ onAuthenticated }: { onAuthenticated: (s: TokenResponse) => void }) {
  const [stage, setStage] = useState<Stage>("credentials");
  const [challenge, setChallenge] = useState("");
  const [enrollment, setEnrollment] = useState<TotpEnrollment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submitCredentials(email: string, password: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await api<LoginResponse>("/auth/login", {
        method: "POST",
        body: { email, password },
      });
      if (res.stage === "authenticated" && res.session) {
        setAccessToken(res.session.access_token);
        onAuthenticated(res.session);
        return;
      }
      setChallenge(res.challenge ?? "");
      if (res.stage === "totp_enrollment") {
        // The challenge travels in the body, never in the URL: query strings end
        // up in proxy logs, browser history and Referer headers.
        const data = await api<TotpEnrollment>("/auth/totp/enroll", {
          method: "POST",
          body: { challenge: res.challenge ?? "" },
        });
        setEnrollment(data);
        setStage("enroll");
      } else {
        setStage("totp");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Connexion impossible.");
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(code: string) {
    setBusy(true);
    setError(null);
    try {
      const path = stage === "enroll" ? "/auth/totp/activate" : "/auth/totp";
      const session = await api<TokenResponse>(path, {
        method: "POST",
        body: { challenge, code },
      });
      setAccessToken(session.access_token);
      onAuthenticated(session);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Code invalide.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center px-5 py-10">
      <AmbientGlow />
      <div className="w-full max-w-[26.5rem]">
        <motion.div {...fade} className="mb-8 flex flex-col items-center gap-5 text-center">
          <CoBrand />
          <div>
            <h1 className="font-display text-[26px] font-bold leading-tight text-ink-100">
              PROJETS <span className="text-poppy-500">SDSI/SMCA</span>
            </h1>
            <p className="mt-2 text-sm text-ink-300">
              Espace sécurisé · Collecte d'état des lieux
            </p>
          </div>
        </motion.div>

        <div className="panel p-7">
          {/* Enter-only, keyed by stage. Framer's exit animations are driven by
              requestAnimationFrame, which the browser suspends in a background
              tab - gating a login step behind one would strand the user on a
              frozen form until they came back. Mounting is unconditional. */}
          <motion.div key={stage} initial={fade.initial} animate={fade.animate} transition={fade.transition}>
            {stage === "credentials" && (
              <CredentialsForm busy={busy} onSubmit={submitCredentials} />
            )}
            {stage === "totp" && (
              <CodeForm
                busy={busy}
                title="Vérification en deux étapes"
                hint="Saisissez le code à 6 chiffres affiché par votre application d'authentification."
                onSubmit={submitCode}
                onBack={() => setStage("credentials")}
              />
            )}
            {stage === "enroll" && enrollment && (
              <EnrollForm busy={busy} enrollment={enrollment} onSubmit={submitCode} />
            )}
          </motion.div>

          <AnimatePresence>
            {error && (
              <motion.p
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                role="alert"
                className="mt-5 rounded-xl border border-poppy-500/40 bg-poppy-500/10 px-4 py-3 text-sm text-ink-100"
              >
                {error}
              </motion.p>
            )}
          </AnimatePresence>
        </div>

        <div className="mt-6 flex flex-col items-center gap-3">
          <SecurityBadge />
          <p className="text-center text-xs leading-relaxed text-ink-400">
            Vos réponses sont chiffrées et destinées exclusivement à l&apos;équipe Devoteam.
            <br />
            Toute tentative d&apos;accès est journalisée.
          </p>
        </div>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------- */
function CredentialsForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (email: string, password: string) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(email.trim(), password);
      }}
      noValidate
    >
      <h2 className="font-display text-lg font-semibold text-ink-100">Connexion</h2>
      <p className="mt-1 text-sm text-ink-300">
        Utilisez les identifiants qui vous ont été transmis par Devoteam.
      </p>

      <div className="mt-6">
        <label className="label" htmlFor="email">
          Adresse professionnelle
        </label>
        <input
          id="email"
          type="email"
          className="field"
          autoComplete="username"
          placeholder="prénom.nom@exemple.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoFocus
        />
      </div>

      <div className="mt-4">
        <label className="label" htmlFor="password">
          Mot de passe
        </label>
        <div className="relative">
          <input
            id="password"
            type={reveal ? "text" : "password"}
            className="field pr-24"
            autoComplete="current-password"
            placeholder="••••••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <button
            type="button"
            onClick={() => setReveal((v) => !v)}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg px-3 py-1.5 text-xs font-medium text-ink-400 hover:text-ink-100"
          >
            {reveal ? "Masquer" : "Afficher"}
          </button>
        </div>
      </div>

      <button type="submit" disabled={busy || !email || !password} className="btn-primary mt-7 w-full">
        {busy ? <Spinner /> : null}
        {busy ? "Vérification…" : "Se connecter"}
      </button>
    </form>
  );
}

/* --------------------------------------------------------------------- */
function CodeForm({
  busy,
  title,
  hint,
  onSubmit,
  onBack,
}: {
  busy: boolean;
  title: string;
  hint: string;
  onSubmit: (code: string) => void;
  onBack?: () => void;
}) {
  const [digits, setDigits] = useState<string[]>(Array(6).fill(""));
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const code = digits.join("");

  useEffect(() => {
    refs.current[0]?.focus();
  }, []);

  function place(index: number, value: string) {
    const clean = value.replace(/\D/g, "");
    if (!clean) {
      setDigits((d) => d.map((v, i) => (i === index ? "" : v)));
      return;
    }
    setDigits((d) => {
      const next = [...d];
      // Pasting the whole code into any box fills the row.
      clean.split("").forEach((ch, offset) => {
        if (index + offset < 6) next[index + offset] = ch;
      });
      return next;
    });
    refs.current[Math.min(index + clean.length, 5)]?.focus();
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(code);
      }}
    >
      <h2 className="font-display text-lg font-semibold text-ink-100">{title}</h2>
      <p className="mt-1 text-sm text-ink-300">{hint}</p>

      <div className="mt-6 flex justify-between gap-2">
        {digits.map((digit, i) => (
          <input
            key={i}
            ref={(el) => {
              refs.current[i] = el;
            }}
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            aria-label={`Chiffre ${i + 1}`}
            className="h-14 w-full rounded-xl border border-ink-600 bg-ink-900/80 text-center font-mono text-xl text-ink-100 transition focus:border-poppy-500/70 focus:ring-4 focus:ring-poppy-500/15"
            value={digit}
            onChange={(e) => place(i, e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Backspace" && !digits[i] && i > 0) refs.current[i - 1]?.focus();
              if (e.key === "ArrowLeft" && i > 0) refs.current[i - 1]?.focus();
              if (e.key === "ArrowRight" && i < 5) refs.current[i + 1]?.focus();
            }}
          />
        ))}
      </div>

      <button type="submit" disabled={busy || code.length < 6} className="btn-primary mt-7 w-full">
        {busy ? <Spinner /> : null}
        {busy ? "Vérification…" : "Valider"}
      </button>

      {onBack && (
        <button type="button" onClick={onBack} className="mt-3 w-full text-sm text-ink-400 hover:text-ink-200">
          Revenir a l&apos;identification
        </button>
      )}
    </form>
  );
}

/* --------------------------------------------------------------------- */
function EnrollForm({
  busy,
  enrollment,
  onSubmit,
}: {
  busy: boolean;
  enrollment: TotpEnrollment;
  onSubmit: (code: string) => void;
}) {
  const [saved, setSaved] = useState(false);
  const qr = useMemo(
    () => `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(enrollment.qr_svg)))}`,
    [enrollment.qr_svg],
  );

  if (!saved) {
    return (
      <div>
        <h2 className="font-display text-lg font-semibold text-ink-100">
          Activer la double authentification
        </h2>
        <p className="mt-1 text-sm text-ink-300">
          Obligatoire pour acceder aux données de continuité d&apos;activité.
        </p>

        <div className="mt-6 flex justify-center">
          <div className="rounded-2xl bg-white p-3">
            <img src={qr} alt="QR code d'enrolement" width={172} height={172} />
          </div>
        </div>

        <div className="mt-5">
          <span className="label">Ou saisissez cette clé manuellement</span>
          <code className="block break-all rounded-xl border border-ink-600 bg-ink-900/80 px-4 py-3 font-mono text-[13px] tracking-wider text-ink-200">
            {enrollment.secret}
          </code>
        </div>

        <div className="mt-5 rounded-xl border border-accent-fire/25 bg-accent-fire/10 p-4">
          <span className="mb-2 block text-xs font-semibold uppercase tracking-[.12em] text-accent-fire">
            Codes de secours — à conserver hors ligne
          </span>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[13px] text-ink-200">
            {enrollment.recovery_codes.map((code) => (
              <span key={code}>{code}</span>
            ))}
          </div>
          <p className="mt-3 text-xs text-ink-400">
            Chaque code ne fonctionne qu&apos;une seule fois et ne sera plus jamais affiche.
          </p>
        </div>

        <button onClick={() => setSaved(true)} className="btn-primary mt-6 w-full">
          J&apos;ai enregistré ces informations
        </button>
      </div>
    );
  }

  return (
    <CodeForm
      busy={busy}
      title="Confirmer l'enrolement"
      hint="Saisissez le code généré par votre application pour finaliser l'activation."
      onSubmit={onSubmit}
    />
  );
}

export function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity=".25" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
