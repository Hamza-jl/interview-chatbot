import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Question } from "../lib/api";
import { Spinner } from "./AuthFlow";

type Props = {
  question: Question | null;
  busy: boolean;
  onSend: (message: string) => void;
};

function kindLabel(kind: string): string {
  if (kind === "grid") return "tableau";
  if (kind === "field") return "valeur courte";
  return "réponse rédigée";
}

export function Composer({ question, busy, onSend }: Props) {
  const [text, setText] = useState("");
  const [guided, setGuided] = useState(false);
  const [showExample, setShowExample] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);

  const isGrid = question?.kind === "grid";

  useEffect(() => {
    setGuided(false);
    setShowExample(false);
  }, [question?.id]);

  useEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);

  function send(value = text) {
    const message = value.trim();
    if (!message || busy) return;
    onSend(message);
    setText("");
  }

  const shortcuts = question
    ? [
        { label: "Que signifie ce terme ?", value: `Que signifie exactement « ${question.label} » ?` },
        { label: "Passer", value: "Je ne dispose pas de cette information, passons a la suite." },
      ]
    : [];

  return (
    <div className="border-t border-ink-600/70 bg-ink-900 px-4 py-4 backdrop-blur-xl sm:px-6">
      <AnimatePresence>
        {showExample && question && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="mb-3 rounded-2xl border border-ink-600 bg-ink-900 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="text-xs font-semibold uppercase tracking-[.12em] text-ink-400">
                  Format attendu · {kindLabel(question.kind)}
                </div>
                <button
                  type="button"
                  onClick={() => setShowExample(false)}
                  className="text-[11px] font-medium text-ink-400 transition hover:text-ink-100"
                >
                  Fermer
                </button>
              </div>

              {question.help && (
                <p className="mt-2 text-[12.5px] leading-relaxed text-ink-300">{question.help}</p>
              )}

              {isGrid && (
                <p className="mt-2 font-mono text-[11.5px] leading-relaxed text-ink-400">
                  {question.columns.map((c) => c.label).join("  |  ")}
                </p>
              )}

              <pre className="scroll-slim mt-3 overflow-x-auto rounded-xl border border-ink-600 bg-ink-950 px-3 py-2.5 font-mono text-[12px] leading-relaxed text-ink-100">
{question.example}
              </pre>

              <button
                type="button"
                onClick={() => {
                  setText((current) => (current.trim() ? current : question.example));
                  setShowExample(false);
                  area.current?.focus();
                }}
                className="btn-ghost mt-3 !py-2 text-[13px]"
              >
                Utiliser cet exemple comme point de depart
              </button>
              <p className="mt-2 text-[11px] text-ink-400">
                À adapter à votre entité : l'exemple sert de gabarit, il n'est jamais enregistré tel quel.
              </p>
            </div>
          </motion.div>
        )}

        {isGrid && guided && question && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <GuidedGrid question={question} onCompose={(line) => setText((t) => (t ? `${t}\n${line}` : line))} />
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        {shortcuts.map((shortcut) => (
          <button
            key={shortcut.label}
            type="button"
            className="chip"
            disabled={busy}
            onClick={() => send(shortcut.value)}
          >
            {shortcut.label}
          </button>
        ))}
        {question && question.example && (
          <button
            type="button"
            onClick={() => setShowExample((v) => !v)}
            className={`chip ${showExample ? "border-poppy-500/70 text-poppy-500" : ""}`}
          >
            Voir un exemple de réponse
          </button>
        )}
        {isGrid && (
          <button
            type="button"
            onClick={() => setGuided((v) => !v)}
            className={`chip ${guided ? "border-poppy-500/70 text-poppy-500" : ""}`}
          >
            {guided ? "Fermer la saisie guidee" : "Saisie guidee (tableau)"}
          </button>
        )}
      </div>

      <div className="group relative rounded-2xl border border-ink-600 bg-ink-950 shadow-card transition focus-within:border-poppy-500/60 focus-within:shadow-glow">
        <textarea
          ref={area}
          rows={1}
          value={text}
          disabled={busy}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder={
            isGrid
              ? "Une ligne par élément, colonnes séparées par «  |  » — ou repondez librement."
              : "Votre réponse… (Entrée pour envoyer, Maj+Entrée pour un retour à la ligne)"
          }
          aria-label="Votre message"
          className="scroll-slim w-full resize-none bg-transparent px-4 py-3.5 pr-32 text-[15px] leading-relaxed text-ink-100 placeholder:text-ink-400 focus:outline-none"
        />
        <div className="absolute bottom-2.5 right-2.5 flex items-center gap-2">
          <span className="hidden text-[11px] text-ink-400 sm:block">
            {text.length > 0 ? `${text.length}` : ""}
          </span>
          <button
            type="button"
            onClick={() => send()}
            disabled={busy || !text.trim()}
            className="btn-primary !px-4 !py-2 text-sm"
          >
            {busy ? <Spinner /> : (
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path
                  d="M4 12h15m0 0-6-6m6 6-6 6"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            )}
            <span>{busy ? "Analyse" : "Envoyer"}</span>
          </button>
        </div>
      </div>

      <p className="mt-2.5 text-center text-[11px] text-ink-400">
        Les informations saisies sont chiffrées avant enregistrement. Ne communiquez aucun mot de
        passe ni identifiant technique.
      </p>
    </div>
  );
}

/** Structured row builder for table questions. */
function GuidedGrid({
  question,
  onCompose,
}: {
  question: Question;
  onCompose: (line: string) => void;
}) {
  const [cells, setCells] = useState<Record<string, string>>({});

  function add() {
    const line = question.columns.map((c) => (cells[c.id] ?? "").trim()).join(" | ");
    if (!line.replace(/\|/g, "").trim()) return;
    onCompose(line);
    setCells({});
  }

  return (
    <div className="mb-3 rounded-2xl border border-ink-600 bg-ink-900 p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-[.12em] text-ink-400">
          Ajouter une ligne
        </span>
        <span className="text-[11px] text-ink-400">{question.columns.length} colonnes</span>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {question.columns.map((column) => (
          <div key={column.id}>
            <label
              className="mb-1 block truncate text-[11px] font-medium text-ink-300"
              title={column.hint || column.label}
              htmlFor={`col-${column.id}`}
            >
              {column.label}
              {!column.required && <span className="text-ink-400"> (facultatif)</span>}
            </label>
            {column.choices ? (
              <select
                id={`col-${column.id}`}
                className="field !py-2 text-sm"
                value={cells[column.id] ?? ""}
                onChange={(e) => setCells((c) => ({ ...c, [column.id]: e.target.value }))}
              >
                <option value="">—</option>
                {column.choices.map((choice) => (
                  <option key={choice} value={choice}>
                    {choice}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id={`col-${column.id}`}
                className="field !py-2 text-sm"
                value={cells[column.id] ?? ""}
                onChange={(e) => setCells((c) => ({ ...c, [column.id]: e.target.value }))}
                placeholder={column.hint ? column.hint.slice(0, 40) : ""}
              />
            )}
          </div>
        ))}
      </div>

      <button type="button" onClick={add} className="btn-ghost mt-3 !py-2 text-sm">
        + Ajouter au message
      </button>
    </div>
  );
}
