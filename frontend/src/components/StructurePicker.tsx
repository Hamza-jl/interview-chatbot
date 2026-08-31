import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ApiError, api, type SessionDetail, type SessionState, type Structure } from "../lib/api";
import { Spinner } from "./AuthFlow";
import { CompletedInterview } from "./CompletedInterview";

export function StructurePicker({
  onOpen,
  onError,
}: {
  onOpen: (detail: SessionDetail) => void;
  onError: (message: string) => void;
}) {
  const [structures, setStructures] = useState<Structure[] | null>(null);
  const [sessions, setSessions] = useState<SessionState[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [closed, setClosed] = useState<Structure | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [list, existing] = await Promise.all([
          api<Structure[]>("/structures"),
          api<SessionState[]>("/sessions"),
        ]);
        setStructures(list);
        setSessions(existing);
        if (list.length === 1) setSelected(list[0].id);
      } catch (err) {
        onError(err instanceof ApiError ? err.message : "Chargement impossible.");
        setStructures([]);
      }
    })();
  }, [onError]);

  const progressByStructure = useMemo(() => {
    const map = new Map<string, SessionState>();
    for (const session of sessions) {
      // A closed interview wins over an open one for the same entity: it is
      // the one that decides whether the structure can still be documented.
      const held = map.get(session.structure.id);
      if (held && held.status === "completed") continue;
      map.set(session.structure.id, session);
    }
    return map;
  }, [sessions]);

  const selectedSession = selected ? progressByStructure.get(selected) ?? null : null;
  const isClosed = selectedSession?.status === "completed";

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle || !structures) return structures ?? [];
    return structures.filter(
      (s) =>
        s.name.toLowerCase().includes(needle) ||
        s.code.toLowerCase().includes(needle) ||
        (s.parent ?? "").toLowerCase().includes(needle),
    );
  }, [structures, query]);

  async function start() {
    if (!selected || !structures) return;
    // A closed interview is never restarted - the server refuses too, this
    // just means the refusal is not what the interviewee meets first.
    if (isClosed) {
      setClosed(structures.find((s) => s.id === selected) ?? null);
      return;
    }
    setBusy(true);
    try {
      const detail = await api<SessionDetail>("/sessions", {
        method: "POST",
        body: { structure_id: selected },
      });
      onOpen(detail);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Ouverture impossible.");
      setBusy(false);
    }
  }

  /** Reopen a closed interview read-only, to relire or correct an answer. */
  async function consult(session: SessionState) {
    try {
      onOpen(await api<SessionDetail>(`/sessions/${session.id}`));
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Ouverture impossible.");
      setClosed(null);
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
          Quelle structure allons-nous <span className="text-poppy-500">documenter</span> ?
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-300">
          Sélectionnez l&apos;entité dont vous avez la responsabilité.
        </p>
      </motion.header>

      {structures && structures.length > 5 && (
        <div className="relative mt-7">
          <svg
            className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
            <path d="m20 20-3.5-3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <input
            className="field pl-11"
            placeholder="Rechercher une direction…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Rechercher une structure"
          />
        </div>
      )}

      {structures === null ? (
        <div className="mt-7 grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-[92px] animate-pulse rounded-2xl border border-ink-600/70 bg-ink-850/60" />
          ))}
        </div>
      ) : (
        <div className="mt-7 grid gap-3 sm:grid-cols-2">
          <AnimatePresence mode="popLayout">
            {visible.map((structure, index) => {
              const progress = progressByStructure.get(structure.id);
              const active = selected === structure.id;
              return (
                <motion.button
                  key={structure.id}
                  layout
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.97 }}
                  transition={{ duration: 0.28, delay: Math.min(index * 0.03, 0.25) }}
                  onClick={() => setSelected(structure.id)}
                  aria-pressed={active}
                  className={`group relative overflow-hidden rounded-2xl border p-4 text-left transition-all duration-200 ${
                    active
                      ? "border-poppy-500/70 bg-poppy-500/10 shadow-glow"
                      : "border-ink-600/80 bg-ink-850/70 hover:border-ink-500 hover:bg-ink-800/70"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span
                          className={`rounded-md px-1.5 py-0.5 font-mono text-[10px] font-semibold ${
                            active ? "bg-poppy-500 text-white" : "bg-ink-700 text-ink-300"
                          }`}
                        >
                          {structure.code}
                        </span>
                        {structure.template_kind === "dsi" && (
                          <span className="rounded-md bg-accent-fire/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent-fire">
                            Modèle DSI
                          </span>
                        )}
                      </div>
                      <div className="mt-2 truncate font-semibold text-ink-100">{structure.name}</div>
                      {structure.parent && (
                        <div className="mt-0.5 truncate text-xs text-ink-400">{structure.parent}</div>
                      )}
                    </div>
                    <span
                      className={`mt-1 grid h-5 w-5 shrink-0 place-items-center rounded-full border transition ${
                        active ? "border-poppy-500 bg-poppy-500" : "border-ink-500"
                      }`}
                      aria-hidden="true"
                    >
                      {active && (
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none">
                          <path
                            d="m5 13 4 4L19 7"
                            stroke="#fff"
                            strokeWidth="3"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      )}
                    </span>
                  </div>

                  {progress && (
                    <div className="mt-3 flex items-center gap-2">
                      <div className="h-1 flex-1 overflow-hidden rounded-full bg-ink-700">
                        <div
                          className={`h-full ${
                            progress.status === "completed" ? "bg-accent-mint" : "bg-poppy-500"
                          }`}
                          style={{ width: `${progress.percent}%` }}
                        />
                      </div>
                      {progress.status === "completed" ? (
                        <span className="inline-flex shrink-0 items-center gap-1 rounded-md border border-accent-mint/40 bg-accent-mint/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent-mint">
                          <svg width="9" height="9" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                            <path
                              d="m5 13 4 4L19 7"
                              stroke="currentColor"
                              strokeWidth="3.4"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                          Terminé
                        </span>
                      ) : (
                        <span className="shrink-0 text-[11px] font-medium text-ink-400">
                          En cours · {progress.percent} %
                        </span>
                      )}
                    </div>
                  )}
                </motion.button>
              );
            })}
          </AnimatePresence>
        </div>
      )}

      {structures && visible.length === 0 && (
        <p className="mt-8 text-center text-sm text-ink-400">
          Aucune structure ne correspond à votre recherche.
        </p>
      )}

      <div className="sticky bottom-5 mt-8 flex justify-center">
        <button
          onClick={start}
          disabled={!selected || busy}
          className={`min-w-[16rem] ${isClosed ? "btn-ghost !bg-ink-900" : "btn-primary"}`}
        >
          {busy ? <Spinner /> : null}
          {busy
            ? "Ouverture de l'entretien…"
            : isClosed
              ? "Entretien terminé — voir le document"
              : selectedSession
                ? `Reprendre l'entretien · ${selectedSession.percent} %`
                : "Démarrer l'entretien"}
        </button>
      </div>

      <AnimatePresence>
        {closed && selectedSession && (
          <CompletedInterview
            key="already-done"
            structure={closed}
            session={selectedSession}
            onConsult={() => consult(selectedSession)}
            onClose={() => setClosed(null)}
            onError={onError}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
