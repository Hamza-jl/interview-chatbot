import { useState } from "react";
import { motion } from "framer-motion";
import type { SessionState } from "../lib/api";
import { Spinner } from "./AuthFlow";

/**
 * The last step before the interview closes.
 *
 * Every question has been passed, but some may never have been answered - a
 * skip, a "je ne sais pas", a question the engine could not extract anything
 * from. Closing straight into the completion screen would be the first the
 * interviewee ever hears of those gaps, with the document already produced.
 * So the interview stops here and shows them, each one a way back in.
 */
type Props = {
  state: SessionState;
  busy: boolean;
  onOpen: (questionId: string) => void;
  onFinish: (acknowledge: boolean) => void;
};

export function ReviewGate({ state, busy, onOpen, onFinish }: Props) {
  const [confirming, setConfirming] = useState(false);
  const missing = state.missing;
  const count = missing.length;

  if (count === 0) {
    return (
      <div className="border-t border-ink-600 bg-ink-900 px-6 py-5">
        <div className="mx-auto flex max-w-3xl flex-col items-center gap-3 text-center">
          <p className="text-sm text-ink-300">
            Les {state.total} points du questionnaire sont renseignés. Vous pouvez clôturer
            l&apos;entretien : le document sera généré immédiatement.
          </p>
          <button onClick={() => onFinish(false)} disabled={busy} className="btn-primary">
            {busy ? <Spinner /> : null}
            Clôturer l&apos;entretien et générer le document
          </button>
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="max-h-[52%] overflow-y-auto scroll-slim border-t border-accent-fire/30 bg-accent-fire/[0.07] px-6 py-5"
    >
      <div className="mx-auto max-w-3xl">
        <div className="flex items-start gap-2.5">
          <svg
            width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true"
            className="mt-[3px] shrink-0 text-accent-fire"
          >
            <path
              d="M12 8.5v5m0 3.2v.1M10.3 3.9 2.6 17.4A2 2 0 0 0 4.3 20.4h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"
              stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"
            />
          </svg>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-ink-100">
              {count} point{count > 1 ? "s" : ""} sans réponse
            </h3>
            <p className="mt-0.5 text-[12.5px] leading-relaxed text-ink-300">
              Sélectionnez-en un pour le compléter maintenant. Sans réponse, la rubrique
              restera vide dans le document.
            </p>
          </div>
        </div>

        <ul className="mt-3.5 space-y-1.5">
          {missing.map((point) => (
            <li key={point.question_id}>
              <button
                type="button"
                onClick={() => onOpen(point.question_id)}
                disabled={busy}
                className="group flex w-full items-center gap-3 rounded-xl border border-ink-600/80 bg-ink-900 px-3.5 py-2.5 text-left transition hover:border-poppy-500/60 hover:bg-ink-800 disabled:opacity-50"
              >
                <span className="shrink-0 rounded-md bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-ink-400 group-hover:text-ink-200">
                  {point.index + 1}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium text-ink-100">
                    {point.label}
                  </span>
                  <span className="block truncate text-[11px] text-ink-400">{point.section}</span>
                </span>
                <span className="shrink-0 text-[11px] font-semibold text-poppy-500 opacity-0 transition-opacity group-hover:opacity-100">
                  Répondre →
                </span>
              </button>
            </li>
          ))}
        </ul>

        {/* Closing with gaps is legitimate - some points genuinely have no
            answer - but it is never the accidental path. */}
        <div className="mt-4 border-t border-ink-600/70 pt-4">
          {confirming ? (
            <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-[12.5px] text-ink-300">
                Clôturer sans renseigner {count === 1 ? "ce point" : `ces ${count} points`} ?
                Ils apparaîtront vides dans le document.
              </p>
              <div className="flex shrink-0 gap-2">
                <button onClick={() => setConfirming(false)} disabled={busy} className="btn-ghost !py-2 text-sm">
                  Revenir
                </button>
                <button onClick={() => onFinish(true)} disabled={busy} className="btn-primary !py-2 text-sm">
                  {busy ? <Spinner /> : null}
                  Confirmer la clôture
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setConfirming(true)}
              disabled={busy}
              className="btn-ghost w-full !py-2 text-sm"
            >
              Clôturer l&apos;entretien en l&apos;état
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}
