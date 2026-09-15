import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ApiError,
  api,
  uploadDocument,
  type DocumentDetail,
  type SessionDetail,
  type UploadResult,
  type UploadedDocument,
} from "../lib/api";
import { Spinner } from "./AuthFlow";

/**
 * Bring your own questionnaire.
 *
 * Three steps, shown as three steps, because the middle one is slow and a
 * spinner with no explanation reads as a hang: the file is read in a second,
 * but writing a question for every blank runs a model on this machine and
 * takes as long as it takes.
 *
 * What the reader found is shown before anything is generated. A wrong blank
 * is visible there, at the only moment where it costs nothing - once the
 * interview has run, a mis-read cell means an answer in the wrong place in a
 * document someone will sign.
 */

const KIND_LABEL: Record<string, string> = {
  docx: "Word",
  xlsx: "Excel",
  pptx: "PowerPoint",
  pdf: "PDF",
};

const ACCEPT = ".docx,.xlsx,.xlsm,.pptx,.pdf";

function FileGlyph({ kind }: { kind: string }) {
  const tone =
    kind === "xlsx"
      ? "text-accent-mint"
      : kind === "pptx"
        ? "text-accent-fire"
        : kind === "pdf"
          ? "text-poppy-500"
          : "text-sky-400";
  return (
    <span
      className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-ink-600 bg-ink-900 font-mono text-[9px] font-bold uppercase ${tone}`}
      aria-hidden="true"
    >
      {kind}
    </span>
  );
}

function bytes(size: number): string {
  return size < 1024 * 1024
    ? `${Math.max(1, Math.round(size / 1024))} Ko`
    : `${(size / 1024 / 1024).toFixed(1)} Mo`;
}

export function DocumentWorkshop({
  onOpen,
  onError,
}: {
  onOpen: (detail: SessionDetail) => void;
  onError: (message: string) => void;
}) {
  const [documents, setDocuments] = useState<UploadedDocument[] | null>(null);
  const [selected, setSelected] = useState<DocumentDetail | UploadResult | null>(null);
  const [uploading, setUploading] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const reload = useCallback(async () => {
    try {
      setDocuments(await api<UploadedDocument[]>("/documents"));
    } catch {
      setDocuments([]);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const questions = selected && "questions" in selected ? selected.questions : null;
  const ready = Boolean(questions?.some((q) => q.question));

  // The upload answers with what was *found* and the questions call answers
  // with how each one is phrased. Both are listed the same way, so they are
  // flattened to one shape here rather than branched over in the markup.
  const items: { id: string; section: string; text: string; columns: string[] }[] = (
    questions ?? (selected as UploadResult | null)?.preview ?? []
  ).map((item) => ({
    id: item.id,
    section: item.section,
    // Before the questions are written there is only the document's own
    // wording, which is what the reader found and the honest thing to show.
    text: (item as { question?: string }).question || item.label,
    columns: item.columns,
  }));

  async function accept(file: File | undefined) {
    if (!file || uploading) return;
    setUploading(true);
    setSelected(null);
    try {
      const result = await uploadDocument(file);
      setSelected(result);
      void reload();
      if (result.slots === 0) {
        onError("Aucun emplacement à remplir n'a été trouvé dans ce fichier.");
      }
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Le fichier n'a pas pu être envoyé.");
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  }

  async function open(document: UploadedDocument) {
    setSelected(null);
    try {
      setSelected(await api<DocumentDetail>(`/documents/${document.id}`));
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Document introuvable.");
    }
  }

  async function prepare() {
    if (!selected) return;
    setPreparing(true);
    try {
      const done = await api<DocumentDetail>(`/documents/${selected.id}/questions`, {
        method: "POST",
      });
      setSelected({ ...(selected as DocumentDetail), ...done });
    } catch (err) {
      onError(
        err instanceof ApiError ? err.message : "La rédaction des questions a échoué.",
      );
    } finally {
      setPreparing(false);
    }
  }

  async function start() {
    if (!selected) return;
    setStarting(true);
    try {
      onOpen(
        await api<SessionDetail>(`/documents/${selected.id}/session`, { method: "POST" }),
      );
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Ouverture impossible.");
      setStarting(false);
    }
  }

  async function forget(document: UploadedDocument) {
    try {
      await api<void>(`/documents/${document.id}`, { method: "DELETE" });
      if (selected?.id === document.id) setSelected(null);
      void reload();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Suppression impossible.");
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl px-5 py-10">
      <motion.header
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      >
        <h1 className="font-display text-[28px] font-bold leading-tight text-ink-100">
          Votre document, <span className="text-poppy-500">rempli par l&apos;entretien</span>
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-300">
          Déposez un questionnaire Word, Excel, PowerPoint ou un PDF à champs. Il est lu
          ici même, sur cette machine ; vous récupérez le fichier d&apos;origine complété,
          dans sa mise en forme.
        </p>
      </motion.header>

      {/* ---- 1. deposit ---------------------------------------------------- */}
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void accept(e.dataTransfer.files?.[0]);
        }}
        className={`mt-7 flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-all duration-200 ${
          dragging
            ? "border-poppy-500 bg-poppy-500/10"
            : "border-ink-600 bg-ink-850/50 hover:border-ink-500 hover:bg-ink-800/50"
        }`}
      >
        <input
          ref={input}
          type="file"
          accept={ACCEPT}
          className="sr-only"
          onChange={(e) => void accept(e.target.files?.[0])}
        />
        {uploading ? (
          <>
            <Spinner />
            <p className="mt-3 text-sm text-ink-200">Lecture du document…</p>
          </>
        ) : (
          <>
            <svg
              className="h-7 w-7 text-ink-400"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M12 16V4m0 0L8 8m4-4 4 4M4 17v1a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3v-1"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <p className="mt-3 text-sm font-medium text-ink-100">
              Glissez un fichier ici, ou cliquez pour le choisir
            </p>
            <p className="mt-1 text-xs text-ink-400">
              .docx · .xlsx · .pptx · .pdf — 12 Mo maximum
            </p>
          </>
        )}
      </label>

      {/* ---- 2. what was found --------------------------------------------- */}
      <AnimatePresence mode="wait">
        {selected && (
          <motion.section
            key={selected.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.28 }}
            className="mt-6 rounded-2xl border border-ink-600/80 bg-ink-850/70 p-5"
          >
            <div className="flex items-start gap-3">
              <FileGlyph kind={selected.kind} />
              <div className="min-w-0 flex-1">
                <div className="truncate font-semibold text-ink-100">
                  {selected.title || selected.filename}
                </div>
                <div className="mt-0.5 text-xs text-ink-400">
                  {KIND_LABEL[selected.kind] ?? selected.kind} · {bytes(selected.size_bytes)} ·{" "}
                  {selected.slots} question{selected.slots > 1 ? "s" : ""}
                  {selected.grids > 0 &&
                    ` dont ${selected.grids} tableau${selected.grids > 1 ? "x" : ""}`}
                </div>
              </div>
            </div>

            {selected.notes?.length > 0 && (
              <ul className="mt-4 space-y-1.5 rounded-xl border border-accent-fire/25 bg-accent-fire/10 p-3">
                {selected.notes.map((note, i) => (
                  <li key={i} className="text-xs leading-relaxed text-ink-200">
                    {note}
                  </li>
                ))}
              </ul>
            )}

            {selected.slots > 0 && (
              <>
                <div className="mt-5 flex items-baseline justify-between">
                  <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-400">
                    {ready ? "Questions rédigées" : "Emplacements détectés"}
                  </h2>
                  <span className="text-[11px] text-ink-500">
                    {ready
                      ? "Relisez-les avant de commencer"
                      : "Vérifiez que ce sont bien les champs à remplir"}
                  </span>
                </div>

                <ol className="mt-3 max-h-80 space-y-2 overflow-y-auto pr-1">
                  {items.map((item, index) => (
                    <li
                      key={item.id}
                      className="rounded-xl border border-ink-700/70 bg-ink-900/60 px-3.5 py-2.5"
                    >
                      <div className="flex items-start gap-2.5">
                        <span className="mt-0.5 font-mono text-[10px] text-ink-500">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <div className="min-w-0 flex-1">
                          {item.section && (
                            <div className="truncate text-[10px] uppercase tracking-wide text-ink-500">
                              {item.section}
                            </div>
                          )}
                          <div className="text-sm text-ink-100">{item.text}</div>
                          {item.columns.length > 0 && (
                            <div className="mt-1 flex flex-wrap gap-1">
                              {item.columns.map((column) => (
                                <span
                                  key={column}
                                  className="rounded bg-ink-700/70 px-1.5 py-0.5 text-[10px] text-ink-300"
                                >
                                  {column}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </li>
                  ))}
                </ol>

                <div className="mt-5 flex flex-wrap gap-3">
                  {!ready ? (
                    <button onClick={prepare} disabled={preparing} className="btn-primary">
                      {preparing ? <Spinner /> : null}
                      {preparing ? "Rédaction des questions…" : "Préparer l'entretien"}
                    </button>
                  ) : (
                    <button onClick={start} disabled={starting} className="btn-primary">
                      {starting ? <Spinner /> : null}
                      {starting ? "Ouverture…" : "Démarrer l'entretien"}
                    </button>
                  )}
                  {preparing && (
                    <p className="self-center text-xs text-ink-400">
                      Le modèle tourne sur cette machine : comptez quelques secondes par
                      question.
                    </p>
                  )}
                </div>
              </>
            )}
          </motion.section>
        )}
      </AnimatePresence>

      {/* ---- 3. what was uploaded before ----------------------------------- */}
      {documents && documents.length > 0 && (
        <section className="mt-9">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-400">
            Vos documents
          </h2>
          <div className="mt-3 grid gap-2">
            {documents.map((document) => (
              <div
                key={document.id}
                className={`flex items-center gap-3 rounded-xl border px-3.5 py-2.5 transition ${
                  selected?.id === document.id
                    ? "border-poppy-500/60 bg-poppy-500/10"
                    : "border-ink-700/70 bg-ink-900/50 hover:border-ink-600"
                }`}
              >
                <FileGlyph kind={document.kind} />
                <button onClick={() => open(document)} className="min-w-0 flex-1 text-left">
                  <div className="truncate text-sm font-medium text-ink-100">
                    {document.title || document.filename}
                  </div>
                  <div className="truncate text-[11px] text-ink-400">
                    {document.slots} question{document.slots > 1 ? "s" : ""} ·{" "}
                    {new Date(document.created_at).toLocaleDateString("fr-FR")}
                  </div>
                </button>
                <button
                  onClick={() => forget(document)}
                  aria-label={`Supprimer ${document.filename}`}
                  title="Supprimer ce document et ses questions"
                  className="shrink-0 rounded-lg p-2 text-ink-500 transition hover:bg-ink-800 hover:text-poppy-500"
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path
                      d="M4 7h16M10 11v6M14 11v6M5 7l1 13h12l1-13M9 7V4h6v3"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
