import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api, download, type Contact, type ExportResult, type SessionState, type User } from "../lib/api";
import { Logo } from "./Brand";
import { Spinner } from "./AuthFlow";

export function ThankYou({
  result,
  state,
  user,
  onClose,
  onExit,
}: {
  result: ExportResult;
  state: SessionState;
  user: User;
  onClose: () => void;
  onExit: () => void;
}) {
  const [contact, setContact] = useState<Contact | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    api<Contact>("/contact")
      .then(setContact)
      .catch(() => setContact(null));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function save() {
    setDownloading(true);
    try {
      await download(result.download_token, result.filename);
    } finally {
      setDownloading(false);
    }
  }

  const firstName = user.full_name.split(/\s+/)[0];
  const blank = state.sections.filter((section) => section.answered < section.total);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-ink-100/40 p-4 backdrop-blur-md"
      role="dialog"
      aria-modal="true"
      aria-labelledby="thankyou-title"
    >
      <motion.div
        initial={{ opacity: 0, y: 26, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 14, scale: 0.98 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        className="panel relative my-auto w-full max-w-lg overflow-hidden"
      >
        <div className="pointer-events-none absolute -top-24 left-1/2 h-56 w-56 -translate-x-1/2 rounded-full bg-poppy-300/70 blur-[80px]" />

        <div className="relative px-7 pb-7 pt-9 text-center">
          <motion.div
            initial={{ scale: 0.6, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.12, type: "spring", stiffness: 220, damping: 18 }}
            className="mx-auto grid h-16 w-16 place-items-center rounded-2xl bg-poppy-500 shadow-glow-lg"
          >
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="m4.5 12.5 5 5 10-11"
                stroke="#fff"
                strokeWidth="2.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </motion.div>

          <h2 id="thankyou-title" className="mt-6 font-display text-2xl font-bold text-ink-100">
            Merci {firstName} !
          </h2>
          <p className="mx-auto mt-3 max-w-md text-[15px] leading-relaxed text-ink-300">
            L&apos;etat des lieux de <strong className="text-ink-100">{state.structure.name}</strong>{" "}
            {blank.length === 0 ? "est complet" : "est enregistre"}. Votre contribution alimente
            directement le Plan de Continuite d&apos;Activite — nous mesurons le temps
            et l&apos;attention que vous y avez consacres.
          </p>

          <div className="mt-6 grid grid-cols-3 gap-2">
            <Stat value={`${state.answered}`} label="points renseignes" />
            <Stat value={`${state.sections.length}`} label="sections couvertes" />
            <Stat value={`${state.percent}%`} label="de couverture" />
          </div>

          {/* An audit deliverable must never imply completeness it does not have. */}
          {blank.length > 0 && (
            <div className="mt-4 rounded-xl border border-accent-fire/30 bg-accent-fire/10 p-3.5 text-left">
              <div className="text-[11px] font-semibold uppercase tracking-[.12em] text-accent-fire">
                {blank.length} point{blank.length > 1 ? "s" : ""} rest
                {blank.length > 1 ? "ent" : "e"} a completer
              </div>
              <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-300">
                Ces rubriques apparaissent vides dans le document :{" "}
                <span className="text-ink-200">{blank.map((s) => s.title).join(", ")}</span>. Vous
                pouvez les completer avec votre consultant Devoteam.
              </p>
            </div>
          )}

          <div className="mt-6 rounded-2xl border border-ink-600/80 bg-ink-900/70 p-4 text-left">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-ink-100">{result.filename}</div>
                <div className="mt-0.5 font-mono text-[11px] text-ink-400">
                  {(result.size_bytes / 1024).toFixed(0)} Ko · SHA-256 {result.sha256.slice(0, 12)}…
                </div>
              </div>
              <button onClick={save} disabled={downloading} className="btn-primary shrink-0 !px-4 !py-2.5 text-sm">
                {downloading ? <Spinner /> : (
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path
                      d="M12 3v12m0 0 4.5-4.5M12 15l-4.5-4.5M4 20h16"
                      stroke="currentColor"
                      strokeWidth="2.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
                Telecharger
              </button>
            </div>
          </div>

          {contact && (
            <div className="mt-5 rounded-2xl border border-ink-600/80 bg-ink-800/40 p-4 text-left">
              <div className="mb-3 flex items-center gap-2.5">
                <Logo size={22} />
                <span className="text-xs font-semibold uppercase tracking-[.14em] text-ink-400">
                  Une question ? Nous restons a votre disposition
                </span>
              </div>
              <div className="space-y-1.5 text-sm">
                <div className="font-semibold text-ink-100">{contact.name}</div>
                <a
                  href={`mailto:${contact.email}`}
                  className="flex items-center gap-2 text-ink-300 transition hover:text-poppy-500"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <rect x="3" y="5" width="18" height="14" rx="2.5" stroke="currentColor" strokeWidth="1.8" />
                    <path d="m3.5 7 8.5 6 8.5-6" stroke="currentColor" strokeWidth="1.8" />
                  </svg>
                  {contact.email}
                </a>
                <a
                  href={`tel:${contact.phone.replace(/\s/g, "")}`}
                  className="flex items-center gap-2 text-ink-300 transition hover:text-poppy-500"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path
                      d="M6.5 3.5h3l1.5 4-2 1.5a12 12 0 0 0 6 6l1.5-2 4 1.5v3a2 2 0 0 1-2.2 2A16.5 16.5 0 0 1 4.5 5.7 2 2 0 0 1 6.5 3.5Z"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinejoin="round"
                    />
                  </svg>
                  {contact.phone}
                </a>
              </div>
            </div>
          )}

          <div className="mt-6 flex flex-col gap-2 sm:flex-row">
            <button onClick={onExit} className="btn-ghost flex-1">
              Documenter une autre structure
            </button>
            <button onClick={onClose} className="btn-ghost flex-1">
              Fermer
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-xl border border-ink-600/70 bg-ink-900/60 px-2 py-3">
      <div className="font-display text-xl font-bold text-poppy-500">{value}</div>
      <div className="mt-0.5 text-[10.5px] leading-tight text-ink-400">{label}</div>
    </div>
  );
}
