import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  ApiError,
  api,
  download,
  type ExportResult,
  type SessionState,
  type Structure,
} from "../lib/api";
import { Spinner } from "./AuthFlow";

/**
 * What you get instead of a second interview.
 *
 * An état des lieux is closed once per entity: the document it produced is the
 * deliverable, and starting over would quietly create a competing one for the
 * same structure. So the entry point becomes read-and-download rather than a
 * blank questionnaire.
 */
type Props = {
  structure: Structure;
  session: SessionState;
  onConsult: () => void;
  onClose: () => void;
  onError: (message: string) => void;
};

export function CompletedInterview({ structure, session, onConsult, onClose, onError }: Props) {
  const [downloading, setDownloading] = useState(false);
  const [opening, setOpening] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function save() {
    setDownloading(true);
    try {
      // Rebuilt from the stored answers rather than served from a cache, so a
      // correction made since the clôture is in the file you get.
      const result = await api<ExportResult>(`/sessions/${session.id}/export`, { method: "POST" });
      await download(result.download_token, result.filename);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Le téléchargement a échoué.");
    } finally {
      setDownloading(false);
    }
  }

  const closedOn = session.completed_at
    ? new Date(session.completed_at).toLocaleDateString("fr-FR", {
        day: "numeric",
        month: "long",
        year: "numeric",
      })
    : null;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-ink-100/40 p-4 backdrop-blur-md"
      role="dialog"
      aria-modal="true"
      aria-labelledby="done-title"
    >
      <motion.div
        initial={{ opacity: 0, y: 22, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 12, scale: 0.98 }}
        transition={{ duration: 0.34, ease: [0.22, 1, 0.36, 1] }}
        className="panel relative my-auto w-full max-w-md overflow-hidden"
      >
        <div className="relative px-7 pb-7 pt-8 text-center">
          <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-accent-mint/40 bg-accent-mint/15">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="m4.5 12.5 5 5 10-11"
                stroke="currentColor"
                strokeWidth="2.6"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="text-accent-mint"
              />
            </svg>
          </div>

          <h2 id="done-title" className="mt-5 font-display text-xl font-bold text-ink-100">
            Entretien déjà réalisé
          </h2>
          <p className="mx-auto mt-2.5 max-w-sm text-[14px] leading-relaxed text-ink-300">
            L&apos;état des lieux de l&apos;entité{" "}
            <strong className="text-ink-100">{structure.name}</strong> a été clôturé
            {closedOn ? ` le ${closedOn}` : ""}. Il ne peut pas être recommencé : le document
            produit fait référence.
          </p>

          <div className="mt-5 flex items-center justify-center gap-2 text-[12px] text-ink-400">
            <span className="rounded-lg border border-ink-600 bg-ink-800/70 px-2.5 py-1 font-medium text-ink-300">
              {session.answered} / {session.total} points renseignés
            </span>
            {session.missing.length > 0 && (
              <span className="rounded-lg border border-accent-fire/30 bg-accent-fire/10 px-2.5 py-1 font-medium text-accent-fire">
                {session.missing.length} laissé{session.missing.length > 1 ? "s" : ""} vide
                {session.missing.length > 1 ? "s" : ""}
              </span>
            )}
          </div>

          <p className="mt-4 text-[12.5px] leading-relaxed text-ink-400">
            Vous pouvez relire vos réponses — et les corriger si besoin, le document est alors
            régénéré — ou récupérer le fichier Word tel quel.
          </p>

          <div className="mt-6 flex flex-col gap-2">
            <button onClick={save} disabled={downloading} className="btn-primary w-full">
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
              {downloading ? "Préparation du document…" : "Retélécharger le document Word"}
            </button>
            <button
              onClick={() => {
                setOpening(true);
                onConsult();
              }}
              disabled={opening}
              className="btn-ghost w-full"
            >
              {opening ? <Spinner /> : null}
              Consulter mes réponses
            </button>
            <button onClick={onClose} className="w-full py-2 text-sm text-ink-400 hover:text-ink-200">
              Choisir une autre structure
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
