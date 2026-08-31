import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import type { PendingAnswer } from "../lib/api";
import { Spinner } from "./AuthFlow";

/**
 * The verification step, and the editor for any answer already given.
 *
 * Everything the engine extracts lands here first, laid out exactly as it will
 * appear in the client's document. Column names come from the .docx and are not
 * editable - the interviewee corrects the *content*, never the structure.
 *
 * Wide tables get an expanded view: six columns never fit legibly in a docked
 * side panel, and a clipped cell is worse than no table at all.
 */
type Props = {
  pending: PendingAnswer;
  busy: boolean;
  /** "verify" = a fresh extraction; "edit" = revisiting a recorded answer. */
  mode?: "verify" | "edit";
  onConfirm: (value: string | null, rows: Record<string, string>[] | null) => void;
  onDiscard: () => void;
};

function blankRow(pending: PendingAnswer): Record<string, string> {
  return Object.fromEntries(pending.columns.map((c) => [c.id, ""]));
}

export function VerificationPanel({
  pending,
  busy,
  mode = "verify",
  onConfirm,
  onDiscard,
}: Props) {
  const isGrid = pending.kind === "grid";
  const isEdit = mode === "edit";
  // Opened from the review, a point may never have been answered at all -
  // telling someone they are "relisant" an empty table reads as a bug.
  const isBlank = isEdit && !pending.value && !pending.rows?.length;
  const [value, setValue] = useState(pending.value ?? "");
  const [rows, setRows] = useState<Record<string, string>[]>(
    () => (pending.rows?.length ? pending.rows : [blankRow(pending)]),
  );
  // Every table opens expanded. The docked column is ~30rem: even three
  // columns clip their cells there, and a clipped cell is worse than no table
  // at all. "Reduire" docks it again for anyone who prefers that.
  const [expanded, setExpanded] = useState(isGrid);

  useEffect(() => {
    setValue(pending.value ?? "");
    setRows(pending.rows?.length ? pending.rows : [blankRow(pending)]);
    setExpanded(pending.kind === "grid");
  }, [pending]);

  const filledRows = useMemo(
    () => rows.filter((r) => Object.values(r).some((v) => (v ?? "").trim())),
    [rows],
  );
  const ready = isGrid ? filledRows.length > 0 : value.trim().length > 0;

  function setCell(index: number, columnId: string, next: string) {
    setRows((current) =>
      current.map((row, i) => (i === index ? { ...row, [columnId]: next } : row)),
    );
  }

  const shell = expanded
    ? "fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-8"
    : "absolute inset-y-0 right-0 z-30 flex w-full max-w-[32rem] flex-col border-l border-ink-600 bg-ink-950 shadow-panel xl:static xl:w-[30rem] xl:max-w-none xl:shadow-none";

  const body = (
    <div
      className={
        expanded
          ? "flex max-h-full w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-ink-600 bg-ink-950 shadow-panel"
          : "flex h-full flex-col"
      }
    >
      <header className="shrink-0 border-b border-ink-600 px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="truncate text-[10px] font-semibold uppercase tracking-[.16em] text-ink-400">
              {isEdit ? `${isBlank ? "Répondre" : "Modifier"} · ${pending.section}` : "Vérification"}
            </div>
            <h2 className="mt-1 font-display text-[15px] font-semibold text-ink-100">
              {pending.label}
            </h2>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {isGrid && (
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="rounded-lg border border-ink-600 px-2 py-1 text-[11px] font-medium text-ink-300 transition hover:border-ink-500 hover:text-ink-100"
              >
                {expanded ? "Réduire" : "Agrandir"}
              </button>
            )}
            <span
              className={`rounded-lg px-2 py-1 text-[10px] font-semibold ${
                isEdit
                  ? "border border-ink-600 bg-ink-800 text-ink-300"
                  : "border border-accent-fire/40 bg-accent-fire/10 text-ink-100"
              }`}
            >
              {isEdit ? (isBlank ? "Sans réponse" : "Enregistré") : "À confirmer"}
            </span>
          </div>
        </div>
        <p className="mt-2 text-[12.5px] leading-relaxed text-ink-300">
          {isBlank
            ? "Ce point n'a pas encore de réponse : la rubrique serait vide dans le document. Renseignez-la ici."
            : isEdit
            ? "Vous relisez une réponse déjà enregistrée. Toute modification remplace ce qui sera écrit dans le document."
            : "Voici ce que j'ai retenu. Corrigez ce qui doit l'être, puis confirmez : rien n'est écrit dans le document tant que vous n'avez pas validé."}
        </p>
      </header>

      <div className="scroll-slim min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {isGrid ? (
          <>
            <div className="scroll-slim overflow-x-auto rounded-xl border border-ink-600">
              <table className="w-full border-separate border-spacing-0 text-[12.5px]">
                <thead>
                  <tr>
                    {pending.columns.map((column) => (
                      <th
                        key={column.id}
                        scope="col"
                        title={column.hint || column.label}
                        style={{ minWidth: column.choices ? "7rem" : "12rem" }}
                        className="sticky top-0 z-10 whitespace-nowrap border-b border-ink-600 bg-ink-800 px-2.5 py-2 text-left font-semibold text-ink-100"
                      >
                        {column.label}
                      </th>
                    ))}
                    <th className="sticky top-0 z-10 w-10 border-b border-ink-600 bg-ink-800" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={index} className="align-top">
                      {pending.columns.map((column) => (
                        <td key={column.id} className="border-b border-ink-600 p-1">
                          {column.choices ? (
                            <select
                              aria-label={`${column.label}, ligne ${index + 1}`}
                              className="w-full rounded-lg border border-ink-600 bg-ink-950 px-2 py-1.5 text-ink-100 focus:border-poppy-500/70 focus:outline-none"
                              value={row[column.id] ?? ""}
                              onChange={(e) => setCell(index, column.id, e.target.value)}
                            >
                              <option value="">—</option>
                              {column.choices.map((choice) => (
                                <option key={choice} value={choice}>
                                  {choice}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <textarea
                              rows={expanded ? 2 : 3}
                              aria-label={`${column.label}, ligne ${index + 1}`}
                              className="scroll-slim w-full resize-y rounded-lg border border-ink-600 bg-ink-950 px-2 py-1.5 leading-snug text-ink-100 focus:border-poppy-500/70 focus:outline-none"
                              value={row[column.id] ?? ""}
                              onChange={(e) => setCell(index, column.id, e.target.value)}
                            />
                          )}
                        </td>
                      ))}
                      <td className="border-b border-ink-600 p-1 align-middle">
                        <button
                          type="button"
                          aria-label={`Supprimer la ligne ${index + 1}`}
                          disabled={rows.length === 1}
                          onClick={() => setRows((c) => c.filter((_, i) => i !== index))}
                          className="grid h-7 w-7 place-items-center rounded-lg text-ink-400 transition hover:bg-poppy-500/10 hover:text-poppy-500 disabled:opacity-30 disabled:hover:bg-transparent"
                        >
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                            <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setRows((c) => [...c, blankRow(pending)])}
                className="btn-ghost !py-2 text-[13px]"
              >
                + Ajouter une ligne
              </button>
              {!expanded && (
                <button
                  type="button"
                  onClick={() => setExpanded(true)}
                  className="text-[12px] font-medium text-poppy-500 hover:underline"
                >
                  Ouvrir en grand pour editer confortablement
                </button>
              )}
            </div>

            <p className="mt-3 text-[11px] leading-relaxed text-ink-400">
              Les intitules de colonnes proviennent du modèle officiel et ne sont pas
              modifiables. Vous pouvez corriger, compléter ou supprimer les lignes.
            </p>
          </>
        ) : (
          <>
            <label className="label" htmlFor="verify-value">
              Texte qui sera inscrit dans le document
            </label>
            <textarea
              id="verify-value"
              rows={pending.kind === "open" ? 10 : 3}
              className="field scroll-slim resize-y leading-relaxed"
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
            {pending.example && (
              <p className="mt-3 text-[11px] leading-relaxed text-ink-400">
                <span className="font-semibold text-ink-300">Attendu : </span>
                {pending.example}
              </p>
            )}
          </>
        )}
      </div>

      <footer className="shrink-0 border-t border-ink-600 bg-ink-900 px-5 py-4">
        <button
          type="button"
          disabled={busy || !ready}
          onClick={() => onConfirm(isGrid ? null : value, isGrid ? filledRows : null)}
          className="btn-primary w-full"
        >
          {busy ? <Spinner /> : null}
          {busy
            ? "Enregistrement…"
            : isEdit
              ? (isBlank ? "Enregistrer la réponse" : "Enregistrer la correction")
              : "Confirmer et continuer vers la question suivante"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onDiscard}
          className="mt-2 w-full rounded-xl px-4 py-2 text-[13px] text-ink-400 transition hover:text-ink-100"
        >
          {isEdit ? "Fermer sans modifier" : "Reprendre ma réponse"}
        </button>
        {!ready && (
          <p className="mt-2 text-center text-[11px] text-ink-400">
            {isGrid ? "Renseignez au moins une ligne." : "La réponse ne peut pas être vide."}
          </p>
        )}
      </footer>
    </div>
  );

  return (
    <motion.aside
      initial={{ opacity: 0, x: expanded ? 0 : 24, scale: expanded ? 0.98 : 1 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
      aria-label={isEdit ? "Modifier une réponse" : "Vérification de la réponse"}
      className={expanded ? `${shell} bg-ink-100/40 backdrop-blur-sm` : shell}
    >
      {body}
    </motion.aside>
  );
}
