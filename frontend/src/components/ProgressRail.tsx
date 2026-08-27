import { useState } from "react";
import { motion } from "framer-motion";
import type { AnswerRow, SessionState } from "../lib/api";

/**
 * Progress rail, and the way back into any answer already given.
 *
 * A section expands to the questions it covers; picking one opens it for
 * correction. Answers recorded earlier are the ones most likely to need a
 * second look, and scrolling the transcript to find them is not a way to edit
 * an audit document.
 */
type Props = {
  state: SessionState;
  answers: AnswerRow[];
  onEdit: (questionId: string) => void;
};

export function ProgressRail({ state, answers, onEdit }: Props) {
  const [open, setOpen] = useState<string | null>(null);
  const bySection = new Map<string, AnswerRow[]>();
  for (const answer of answers) {
    const list = bySection.get(answer.section) ?? [];
    list.push(answer);
    bySection.set(answer.section, list);
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="px-5 pb-4 pt-5">
        <div className="text-[10px] font-semibold uppercase tracking-[.16em] text-ink-400">
          Entité documentee
        </div>
        <div className="mt-2 break-words font-display text-[15px] font-semibold leading-snug text-ink-100">
          {state.structure.name}
        </div>
        <div className="mt-1 flex items-center gap-2">
          <span className="rounded-md bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-ink-300">
            {state.structure.code}
          </span>
          <span className="text-[11px] text-ink-400">
            {state.template_kind === "dsi" ? "Modèle DSI" : "Modèle Entité"}
          </span>
        </div>
      </div>

      <div className="px-5 pb-4">
        <div className="mb-2 flex items-baseline justify-between">
          <span className="text-xs font-medium text-ink-300">Avancement</span>
          <span className="font-display text-lg font-bold text-ink-100">{state.percent}%</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-ink-800">
          <motion.div
            className="h-full rounded-full bg-poppy-500"
            animate={{ width: `${state.percent}%` }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          />
        </div>
        <div className="mt-2 text-[11px] text-ink-400">
          {state.answered} sur {state.total} points renseignes
        </div>
      </div>

      <nav
        aria-label="Sections du questionnaire"
        className="scroll-slim min-h-0 flex-1 overflow-y-auto px-3 pb-5"
      >
        <ul className="space-y-0.5">
          {state.sections.map((section) => {
            const done = section.answered >= section.total;
            const isOpen = open === section.title;
            const questions = bySection.get(section.title) ?? [];

            return (
              <li key={section.title}>
                <button
                  type="button"
                  aria-expanded={isOpen}
                  onClick={() => setOpen(isOpen ? null : section.title)}
                  className={`flex w-full items-start gap-3 rounded-xl px-2.5 py-2 text-left transition-colors ${
                    section.active ? "bg-poppy-500/10" : "hover:bg-ink-800"
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className={`mt-[3px] grid h-4 w-4 shrink-0 place-items-center rounded-full border text-[9px] ${
                      done
                        ? "border-accent-mint/70 bg-accent-mint/20 text-accent-mint"
                        : section.active
                          ? "border-poppy-500 bg-poppy-500/20 text-poppy-500"
                          : "border-ink-500 text-transparent"
                    }`}
                  >
                    {done ? "✓" : section.active ? "•" : ""}
                  </span>

                  <span className="min-w-0 flex-1">
                    <span
                      className={`block truncate text-[12.5px] leading-snug ${
                        section.active
                          ? "font-semibold text-ink-100"
                          : done
                            ? "text-ink-300"
                            : "text-ink-400"
                      }`}
                      title={section.title}
                    >
                      {section.title}
                    </span>
                    <span className="mt-1 block h-[3px] overflow-hidden rounded-full bg-ink-800">
                      <span
                        className={`block h-full rounded-full ${
                          done ? "bg-accent-mint/70" : "bg-poppy-500/70"
                        }`}
                        style={{ width: `${(section.answered / section.total) * 100}%` }}
                      />
                    </span>
                  </span>

                  <svg
                    width="11" height="11" viewBox="0 0 24 24" fill="none" aria-hidden="true"
                    className={`mt-1 shrink-0 text-ink-400 transition-transform ${isOpen ? "rotate-90" : ""}`}
                  >
                    <path d="m9 5 7 7-7 7" stroke="currentColor" strokeWidth="2.2"
                          strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>

                {isOpen && (
                  <ul className="mb-1 ml-7 mt-0.5 space-y-0.5 border-l border-ink-600 pl-2">
                    {questions.map((answer) => {
                      const filled = answer.completeness !== "vide";
                      return (
                        <li key={answer.question_id}>
                          <button
                            type="button"
                            onClick={() => onEdit(answer.question_id)}
                            className="group flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-ink-800"
                          >
                            <span
                              aria-hidden="true"
                              className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                                filled ? "bg-accent-mint" : "bg-ink-500"
                              }`}
                            />
                            <span className="min-w-0 flex-1 truncate text-[12px] text-ink-300 group-hover:text-ink-100">
                              {answer.label}
                            </span>
                            <span className="shrink-0 text-[10px] font-medium text-ink-400 opacity-0 transition-opacity group-hover:opacity-100">
                              {filled ? "Modifier" : "Répondre"}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                    {questions.length === 0 && (
                      <li className="px-2 py-1.5 text-[11px] text-ink-400">
                        Section pas encore atteinte.
                      </li>
                    )}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
