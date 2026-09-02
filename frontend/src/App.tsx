import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  api,
  onLogout as registerLogoutHandler,
  restoreSession,
  setAccessToken,
  type SessionDetail,
  type TokenResponse,
  type User,
} from "./lib/api";
import { AmbientGlow } from "./components/Brand";
import { AdminConsole } from "./components/AdminConsole";
import { AuthFlow } from "./components/AuthFlow";
import { Chat } from "./components/Chat";
import { PasswordChange } from "./components/PasswordChange";
import { StructurePicker } from "./components/StructurePicker";
import { TopNav } from "./components/TopNav";

/** Mirrors the server-side idle timeout so the UI warns before the API refuses. */
const IDLE_LIMIT_SECONDS = 15 * 60;

type View = "booting" | "auth" | "password" | "picker" | "chat" | "admin";

export default function App() {
  const [view, setView] = useState<View>("booting");
  const [user, setUser] = useState<User | null>(null);
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [idleLeft, setIdleLeft] = useState(IDLE_LIMIT_SECONDS);

  const refreshTimer = useRef<number | null>(null);
  const idleDeadline = useRef(0);

  const notify = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(null), 6000);
  }, []);

  const clearSession = useCallback(() => {
    if (refreshTimer.current) window.clearTimeout(refreshTimer.current);
    setAccessToken(null);
    setUser(null);
    setDetail(null);
    setView("auth");
  }, []);

  /* -- silent refresh loop: renew shortly before the access token expires -- */
  const scheduleRefresh = useCallback(
    (expiresIn: number) => {
      if (refreshTimer.current) window.clearTimeout(refreshTimer.current);
      const delay = Math.max(20, expiresIn - 45) * 1000;
      refreshTimer.current = window.setTimeout(async () => {
        const renewed = await restoreSession();
        if (renewed) {
          setUser(renewed.user);
          scheduleRefresh(renewed.expires_in);
        } else {
          clearSession();
        }
      }, delay);
    },
    [clearSession],
  );

  const adopt = useCallback(
    (session: TokenResponse) => {
      setUser(session.user);
      scheduleRefresh(session.expires_in);
      setView(session.user.must_change_password ? "password" : "picker");
    },
    [scheduleRefresh],
  );

  /* -- boot: try to resume an existing browser session -------------------- */
  useEffect(() => {
    registerLogoutHandler(() => {
      clearSession();
      notify("Votre session a expire. Merci de vous reconnecter.");
    });

    (async () => {
      const session = await restoreSession();
      if (session) adopt(session);
      else setView("auth");
    })();
  }, [adopt, clearSession, notify]);

  /* -- idle countdown ------------------------------------------------------ */
  // Keyed on the user's id, not the user object: the silent refresh loop hands
  // back a fresh object every few minutes, and re-running this effect on that
  // would re-arm the timer forever - an idle session would never time out.
  const userId = user?.id ?? null;

  useEffect(() => {
    if (!userId) return;

    // A wall-clock deadline rather than a decrementing counter. Counting ticks
    // gets both ends wrong: a leftover count from a previous session logs the
    // next one straight back out, and a backgrounded tab has its timers
    // throttled, so the count would over-report and outlive the server's own
    // idle window.
    const arm = () => {
      idleDeadline.current = Date.now() + IDLE_LIMIT_SECONDS * 1000;
    };
    arm();
    setIdleLeft(IDLE_LIMIT_SECONDS);

    const events = ["mousedown", "keydown", "touchstart", "scroll"] as const;
    events.forEach((e) => window.addEventListener(e, arm, { passive: true }));

    const tick = window.setInterval(() => {
      const left = Math.max(0, Math.round((idleDeadline.current - Date.now()) / 1000));
      setIdleLeft(left);
      if (left === 0) {
        window.clearInterval(tick);
        void logout("idle");
      }
    }, 1000);

    return () => {
      events.forEach((e) => window.removeEventListener(e, arm));
      window.clearInterval(tick);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  async function logout(reason: "user" | "idle" = "user") {
    try {
      await api<void>("/auth/logout", { method: "POST" });
    } catch {
      /* the session is being discarded either way */
    }
    clearSession();
    if (reason === "idle") notify("Déconnexion automatique après 15 minutes d'inactivité.");
  }

  return (
    <div className="min-h-screen">
      <AmbientGlow />

      {view === "booting" && (
        <div className="grid min-h-screen place-items-center">
          <div className="flex flex-col items-center gap-4">
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-ink-600 border-t-poppy-500" />
            <p className="text-sm text-ink-400">Ouverture de l&apos;espace sécurisé…</p>
          </div>
        </div>
      )}

      {view === "auth" && <AuthFlow onAuthenticated={adopt} />}

      {view === "password" && user && (
        <PasswordChange
          onDone={(updated) => {
            setUser(updated);
            setView("picker");
          }}
        />
      )}

      {(view === "picker" || view === "chat" || view === "admin") && user && (
        <>
          <TopNav
            user={user}
            idleSeconds={idleLeft}
            onLogout={() => logout("user")}
            onOpenAdmin={user.role === "admin" ? () => setView("admin") : undefined}
          />
          <main className="pt-4">
            {/* Enter-only for the same reason as the auth steps: a suspended
                rAF clock must never be able to hide the main view. */}
            {view === "admin" ? (
              <motion.div
                key="admin"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
              >
                <AdminConsole
                  onError={notify}
                  onClose={() => setView(detail ? "chat" : "picker")}
                />
              </motion.div>
            ) : view === "picker" ? (
              <motion.div
                key="picker"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
              >
                <StructurePicker
                  onError={notify}
                  onOpen={(session) => {
                    setDetail(session);
                    setView("chat");
                  }}
                />
              </motion.div>
            ) : (
              detail && (
                <motion.div
                  key="chat"
                  initial={{ opacity: 0, scale: 0.985 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
                >
                  <Chat
                    detail={detail}
                    user={user}
                    onError={notify}
                    onExit={() => {
                      setDetail(null);
                      setView("picker");
                    }}
                  />
                </motion.div>
              )
            )}
          </main>
        </>
      )}

      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            role="status"
            className="fixed bottom-5 left-1/2 z-[60] -translate-x-1/2 rounded-xl border border-poppy-500/40 bg-ink-950 px-5 py-3 text-sm text-ink-100 shadow-panel backdrop-blur-xl"
          >
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
