import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ApiError,
  api,
  type ChatResponse,
  type ExportResult,
  type Message,
  type SessionDetail,
  type AnswerRow,
  type PendingAnswer,
  type SessionState,
  type User,
} from "../lib/api";
import { Composer } from "./Composer";
import { ProgressRail } from "./ProgressRail";
import { RichText } from "./RichText";
import { SecurityBadge, WindowDots } from "./Brand";
import { ReviewGate } from "./ReviewGate";
import { ThankYou } from "./ThankYou";
import { VerificationPanel } from "./VerificationPanel";

type Props = {
  detail: SessionDetail;
  user: User;
  onExit: () => void;
  onError: (message: string) => void;
};

export function Chat({ detail, user, onExit, onError }: Props) {
  const [state, setState] = useState<SessionState>(detail.state);
  const [messages, setMessages] = useState<Message[]>(detail.messages);
  const [busy, setBusy] = useState(false);
  const [railOpen, setRailOpen] = useState(false);
  const [pending, setPending] = useState<PendingAnswer | null>(null);
  const [editing, setEditing] = useState<PendingAnswer | null>(null);
  const [answers, setAnswers] = useState<AnswerRow[]>([]);
  const [exported, setExported] = useState<ExportResult | null>(null);
  const [finishing, setFinishing] = useState(false);
  // Having the document and being shown the completion screen are two
  // different things: reopening a closed interview to relire an answer must
  // not throw the "Merci" panel over the transcript.
  const [recapOpen, setRecapOpen] = useState(false);

  const endRef = useRef<HTMLDivElement>(null);

  const loadAnswers = useCallback(
    async (sessionId: string) => {
      try {
        setAnswers(await api<AnswerRow[]>(`/sessions/${sessionId}/answers`));
      } catch {
        /* the rail simply shows no question list */
      }
    },
    [],
  );
  const scrollHost = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: messages.length > 2 ? "smooth" : "auto" });
  }, [messages, busy]);

  const finalise = useCallback(
    async (sessionId: string) => {
      setFinishing(true);
      try {
        const result = await api<ExportResult>(`/sessions/${sessionId}/export`, { method: "POST" });
        setExported(result);
      } catch (err) {
        onError(
          err instanceof ApiError ? err.message : "La génération du document a echoue.",
        );
      } finally {
        setFinishing(false);
      }
    },
    [onError],
  );

  useEffect(() => {
    void loadAnswers(state.id);
  }, [loadAnswers, state.id, state.answered]);

  // A session reopened after completion should still offer its document -
  // silently, so the transcript is what you land on.
  useEffect(() => {
    if (state.status === "completed" && !exported && !finishing) void finalise(state.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function send(body: string) {
    const optimistic: Message = {
      id: `local-${Date.now()}`,
      role: "user",
      body,
      intent: null,
      created_at: new Date().toISOString(),
    };
    setMessages((m) => [...m, optimistic]);
    setBusy(true);
    try {
      const res = await api<ChatResponse>(`/sessions/${state.id}/messages`, {
        method: "POST",
        body: { message: body },
      });
      setMessages((m) => [...m, res.reply]);
      setState(res.state);
      setPending(res.pending);
      if (res.completed) {
        await finalise(res.state.id);
        setRecapOpen(true);
      }
    } catch (err) {
      setMessages((m) => m.filter((msg) => msg.id !== optimistic.id));
      onError(err instanceof ApiError ? err.message : "Envoi impossible.");
    } finally {
      setBusy(false);
    }
  }

  async function resolveDraft(
    path: "confirm" | "discard",
    value: string | null,
    rows: Record<string, string>[] | null,
  ) {
    if (!pending) return;
    setBusy(true);
    try {
      const res = await api<ChatResponse>(`/sessions/${state.id}/${path}`, {
        method: "POST",
        body: { question_id: pending.question_id, value, rows },
      });
      setMessages((m) => [...m, res.reply]);
      setState(res.state);
      setPending(null);
      if (res.completed) {
        await finalise(res.state.id);
        setRecapOpen(true);
      }
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Enregistrement impossible.");
    } finally {
      setBusy(false);
    }
  }

  function openForEdit(questionId: string) {
    const row = answers.find((a) => a.question_id === questionId);
    if (!row) return;
    // Columns, prompt and example come from the plan rather than from the
    // stored payload: a point that was never answered has no rows to infer a
    // column set from, and that is exactly the point most likely to be opened.
    setEditing({
      question_id: row.question_id,
      label: row.label,
      section: row.section,
      kind: row.kind as PendingAnswer["kind"],
      prompt: row.prompt,
      help: row.help,
      example: row.example,
      columns: row.columns,
      value: row.value,
      rows: row.rows,
    });
  }

  async function saveEdit(
    value: string | null,
    rows: Record<string, string>[] | null,
  ) {
    if (!editing) return;
    setBusy(true);
    try {
      await api<AnswerRow>(`/sessions/${state.id}/answers`, {
        method: "PUT",
        body: { question_id: editing.question_id, value, rows },
      });
      const detail = await api<SessionDetail>(`/sessions/${state.id}`);
      setMessages(detail.messages);
      setState(detail.state);
      await loadAnswers(state.id);
      setEditing(null);
      // Filling a hole in an interview that is already closed has to rebuild
      // the document, or the correction lives only in the database while the
      // deliverable on offer still has the hole.
      if (detail.state.status === "completed") await finalise(state.id);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Correction impossible.");
    } finally {
      setBusy(false);
    }
  }

  async function finish(acknowledge: boolean) {
    setBusy(true);
    try {
      const res = await api<ChatResponse>(`/sessions/${state.id}/finish`, {
        method: "POST",
        body: { acknowledge },
      });
      setMessages((m) => [...m, res.reply]);
      setState(res.state);
      await finalise(res.state.id);
      setRecapOpen(true);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Clôture impossible.");
    } finally {
      setBusy(false);
    }
  }

  const question = state.question;

  return (
    <div className="mx-auto flex h-[calc(100vh-4.5rem)] w-full max-w-[80rem] px-3 pb-4 sm:px-5">
      <div className="panel relative flex w-full overflow-hidden">
        {/* ------------------------------------------------ rail ------- */}
        <aside
          className={`absolute inset-y-0 left-0 z-30 flex w-[16.5rem] shrink-0 flex-col overflow-hidden border-r border-ink-600/70 bg-ink-950 backdrop-blur-xl transition-transform duration-300 lg:static lg:translate-x-0 lg:bg-ink-900 ${
            railOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          {/* min-h-0 lets the section list scroll instead of pushing the header
              out of the column - without it the entity name is clipped away. */}
          <div className="min-h-0 flex-1">
            <ProgressRail state={state} answers={answers} onEdit={openForEdit} />
          </div>
          <div className="shrink-0 border-t border-ink-600/70 p-3">
            <button onClick={onExit} className="btn-ghost w-full !py-2 text-sm">
              Changer de structure
            </button>
          </div>
        </aside>

        {railOpen && (
          <button
            aria-label="Fermer le panneau"
            className="absolute inset-0 z-20 bg-ink-100/40 lg:hidden"
            onClick={() => setRailOpen(false)}
          />
        )}

        {/* ---------------------------------------------- console ------ */}
        <section className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center gap-3 border-b border-ink-600/70 px-4 py-3 sm:px-6">
            <button
              onClick={() => setRailOpen((v) => !v)}
              className="grid h-8 w-8 place-items-center rounded-lg border border-ink-600 text-ink-300 hover:text-ink-100 lg:hidden"
              aria-label="Afficher l'avancement"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </button>

            <div className="hidden lg:block">
              <WindowDots />
            </div>

            <div className="min-w-0 flex-1 lg:border-l lg:border-ink-600/70 lg:pl-4">
              {question ? (
                <>
                  <div className="truncate text-[11px] font-medium uppercase tracking-[.12em] text-ink-400">
                    {question.section}
                  </div>
                  <div className="truncate text-sm font-semibold text-ink-100">{question.label}</div>
                </>
              ) : state.awaiting_review ? (
                <>
                  <div className="truncate text-[11px] font-medium uppercase tracking-[.12em] text-ink-400">
                    Revue finale
                  </div>
                  <div className="truncate text-sm font-semibold text-ink-100">
                    {state.missing.length === 0
                      ? "Prêt à clôturer"
                      : `${state.missing.length} point${state.missing.length > 1 ? "s" : ""} à compléter`}
                  </div>
                </>
              ) : (
                <div className="text-sm font-semibold text-accent-mint">Entretien terminé</div>
              )}
            </div>

            <div className="hidden items-center gap-2 sm:flex">
              {state.degraded ? (
                <span
                  title="Le moteur d'analyse est momentanement indisponible : vos réponses sont enregistrées telles quelles."
                  className="rounded-lg border border-accent-fire/30 bg-accent-fire/10 px-2.5 py-1 text-[11px] font-medium text-accent-fire"
                >
                  Mode dégradé
                </span>
              ) : (
                state.engine && (
                  <span
                    title={`Analyse assuree par ${state.engine}`}
                    className="rounded-lg border border-ink-600 bg-ink-800/70 px-2.5 py-1 text-[11px] font-medium text-ink-300"
                  >
                    {state.engine.includes("local") ? "Local" : "Cloud"} · {state.engine.replace(" (local)", "")}
                  </span>
                )
              )}
              <span className="rounded-lg border border-ink-600 bg-ink-800/70 px-2.5 py-1 font-mono text-[11px] text-ink-300">
                {question ? `${question.index + 1}/${question.total}` : `${state.total}/${state.total}`}
              </span>
              <SecurityBadge label="Chiffré" />
            </div>
          </header>

          <div ref={scrollHost} className="scroll-slim flex-1 overflow-y-auto px-4 py-6 sm:px-6">
            <div className="mx-auto max-w-3xl space-y-5">
              {question && messages.length <= 1 && <QuestionCard question={question} />}

              {messages.map((message, index) => (
                <Bubble key={message.id} message={message} user={user} index={index} />
              ))}

              <AnimatePresence>{busy && <Typing />}</AnimatePresence>
              <div ref={endRef} />
            </div>
          </div>

          {pending ? (
            <div className="border-t border-ink-600 bg-ink-900 px-6 py-4 text-center">
              <p className="text-sm text-ink-300">
                Vérifiez la réponse dans le panneau, puis confirmez pour continuer.
              </p>
            </div>
          ) : state.status === "completed" ? (
            <div className="border-t border-ink-600 bg-ink-900 px-6 py-5 text-center">
              <p className="text-sm text-ink-300">
                {finishing
                  ? "Génération du document en cours…"
                  : "Cet entretien est clôturé. Le document est disponible ci-dessous."}
              </p>
              {exported && (
                <button onClick={() => setRecapOpen(true)} className="btn-primary mt-3">
                  Revoir le récapitulatif
                </button>
              )}
            </div>
          ) : state.awaiting_review ? (
            <ReviewGate
              state={state}
              busy={busy}
              onOpen={openForEdit}
              onFinish={finish}
            />
          ) : (
            <Composer question={question} busy={busy} onSend={send} />
          )}
        </section>

        {pending && (
          <VerificationPanel
            pending={pending}
            busy={busy}
            onConfirm={(value, rows) => resolveDraft("confirm", value, rows)}
            onDiscard={() => resolveDraft("discard", null, null)}
          />
        )}

        {!pending && editing && (
          <VerificationPanel
            pending={editing}
            busy={busy}
            mode="edit"
            onConfirm={saveEdit}
            onDiscard={() => setEditing(null)}
          />
        )}
      </div>

      <AnimatePresence>
        {recapOpen && exported && state.status === "completed" && (
          <ThankYou
            key="thank-you"
            result={exported}
            state={state}
            user={user}
            onClose={() => setRecapOpen(false)}
            onExit={onExit}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

/* --------------------------------------------------------------------- */
function QuestionCard({ question }: { question: NonNullable<SessionState["question"]> }) {
  if (!question.help && !question.example) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-2xl border border-ink-600/70 bg-ink-800/40 p-4"
    >
      {question.help && <p className="text-sm leading-relaxed text-ink-300">{question.help}</p>}
      {question.example && (
        <p className="mt-2 text-[13px] text-ink-400">
          <span className="font-semibold text-ink-300">Exemple : </span>
          {question.example}
        </p>
      )}
    </motion.div>
  );
}

function Bubble({ message, user, index }: { message: Message; user: User; index: number }) {
  const mine = message.role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.01, 0.15) }}
      className={`flex items-start gap-3 ${mine ? "flex-row-reverse" : ""}`}
    >
      <Avatar mine={mine} user={user} />
      <div className={`max-w-[85%] ${mine ? "items-end" : ""}`}>
        <div
          className={`rounded-2xl px-4 py-3 text-[15px] leading-relaxed ${
            mine
              ? "rounded-tr-md bg-poppy-500 text-white shadow-glow"
              : "rounded-tl-md border border-ink-600/70 bg-ink-800/70 text-ink-200"
          }`}
        >
          <RichText text={message.body} />
        </div>
        {message.intent && message.intent !== "système" && !mine && (
          <div className="mt-1.5 px-1 text-[11px] text-ink-400">
            {intentLabel(message.intent)}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function intentLabel(intent: string): string {
  switch (intent) {
    case "question":
      return "Réponse à votre question — rien n'a été enregistré";
    case "mixte":
      return "Question traitée et réponse enregistrée";
    case "salutation":
      return "Échange de courtoisie — rien n'a été enregistré";
    case "navigation":
      return "Navigation";
    case "hors_sujet":
      return "Hors périmètre de l'atelier";
    default:
      return "Réponse enregistrée";
  }
}

function Avatar({ mine, user }: { mine: boolean; user: User }) {
  if (mine) {
    const initials = user.full_name
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0])
      .join("")
      .toUpperCase();
    return (
      <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-ink-600 bg-ink-800 text-[11px] font-semibold text-ink-300">
        {initials}
      </div>
    );
  }
  return (
    <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-poppy-500 shadow-glow">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M12 2.5 14.2 9l6.8 2.2-6.8 2.2L12 20l-2.2-6.6L3 11.2 9.8 9 12 2.5Z"
          fill="#fff"
        />
      </svg>
    </div>
  );
}

function Typing() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="flex items-center gap-3"
    >
      <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-poppy-500">
        <span className="h-2 w-2 rounded-full bg-white/90 animate-blink" />
      </div>
      <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-md border border-ink-600/70 bg-ink-800/70 px-4 py-3.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 rounded-full bg-ink-300 animate-blink"
            style={{ animationDelay: `${i * 0.18}s` }}
          />
        ))}
      </div>
    </motion.div>
  );
}
