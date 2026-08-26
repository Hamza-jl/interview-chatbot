import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import type { User } from "../lib/api";
import { Wordmark } from "./Brand";

export function TopNav({
  user,
  idleSeconds,
  onLogout,
}: {
  user: User;
  idleSeconds: number;
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (menu.current && !menu.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const initials = user.full_name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toUpperCase();

  const warning = idleSeconds <= 120;

  return (
    <header className="sticky top-0 z-40 px-3 pt-3 sm:px-5">
      <motion.nav
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        className="mx-auto flex h-14 w-full max-w-[80rem] items-center justify-between rounded-2xl border border-ink-600 bg-ink-950/85 px-4 shadow-card backdrop-blur-xl"
      >
        <Wordmark compact />

        <div className="hidden items-center gap-1 md:flex">
          {["Etat des lieux", "Referentiel PCA", "Support"].map((item, i) => (
            <span
              key={item}
              className={`rounded-lg px-3 py-1.5 text-[13px] transition ${
                i === 0 ? "bg-ink-800 font-medium text-ink-100" : "text-ink-400"
              }`}
            >
              {item}
            </span>
          ))}
        </div>

        <div className="flex items-center gap-2.5">
          <span
            title="Deconnexion automatique apres inactivite"
            className={`hidden rounded-lg border px-2.5 py-1 font-mono text-[11px] transition-colors sm:block ${
              warning
                ? "border-poppy-500/50 bg-poppy-500/10 text-ink-100"
                : "border-ink-600 bg-ink-800/60 text-ink-400"
            }`}
          >
            {formatClock(idleSeconds)}
          </span>

          <div className="relative" ref={menu}>
            <button
              onClick={() => setOpen((v) => !v)}
              aria-haspopup="menu"
              aria-expanded={open}
              className="flex items-center gap-2.5 rounded-xl border border-ink-600 bg-ink-950 py-1.5 pl-1.5 pr-3 transition hover:border-ink-500 hover:bg-ink-800"
            >
              <span className="grid h-7 w-7 place-items-center rounded-lg bg-poppy-500 text-[11px] font-bold text-white">
                {initials}
              </span>
              <span className="hidden text-left leading-tight sm:block">
                <span className="block max-w-[10rem] truncate text-[12.5px] font-medium text-ink-100">
                  {user.full_name}
                </span>
                <span className="block text-[10.5px] text-ink-400">{user.organisation}</span>
              </span>
            </button>

            {open && (
              <motion.div
                initial={{ opacity: 0, y: -6, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                role="menu"
                className="absolute right-0 mt-2 w-60 overflow-hidden rounded-xl border border-ink-600 bg-ink-950 shadow-panel"
              >
                <div className="border-b border-ink-600/70 px-4 py-3">
                  <div className="truncate text-sm font-medium text-ink-100">{user.email}</div>
                  <div className="mt-1 flex items-center gap-2">
                    <span className="rounded-md bg-ink-700 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-300">
                      {user.role}
                    </span>
                    {user.totp_enabled && (
                      <span className="rounded-md bg-accent-mint/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent-mint">
                        2FA active
                      </span>
                    )}
                  </div>
                </div>
                <button
                  onClick={onLogout}
                  role="menuitem"
                  className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm text-ink-200 transition hover:bg-poppy-500/10 hover:text-poppy-500"
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path
                      d="M15 17v2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v2M19 12H9m10 0-3-3m3 3-3 3"
                      stroke="currentColor"
                      strokeWidth="1.9"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  Se deconnecter
                </button>
              </motion.div>
            )}
          </div>
        </div>
      </motion.nav>
    </header>
  );
}

function formatClock(seconds: number): string {
  const safe = Math.max(0, seconds);
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
}
