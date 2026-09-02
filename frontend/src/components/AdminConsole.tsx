import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  ApiError,
  api,
  type ProgressReport,
  type ProgressRow,
  type ResetReport,
} from "../lib/api";
import { Spinner } from "./AuthFlow";

/**
 * Where the collection stands, across every entity.
 *
 * Deliberately counts and labels only: an administrator sees how far each
 * entity has got and which points are outstanding, never what was answered.
 * The answers stay encrypted per field, and this screen is not a way around
 * that - the endpoint behind it does not read them either.
 */
type Props = {
  onError: (message: string) => void;
  onClose: () => void;
};

const STATUS: Record<ProgressRow["status"], { label: string; className: string }> = {
  non_demarre: { label: "Non démarré", className: "border-ink-600 bg-ink-800/70 text-ink-400" },
  in_progress: { label: "En cours", className: "border-poppy-500/40 bg-poppy-500/10 text-poppy-500" },
  completed: {
    label: "Terminé",
    className: "border-accent-mint/40 bg-accent-mint/15 text-accent-mint",
  },
};

type Filter = "tous" | ProgressRow["status"];

export function AdminConsole({ onError, onClose }: Props) {
  const [report, setReport] = useState<ProgressReport | null>(null);
  const [filter, setFilter] = useState<Filter>("tous");
  const [query, setQuery] = useState("");
  const [confirming, setConfirming] = useState<ProgressRow | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setReport(await api<ProgressReport>("/admin/progress"));
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Chargement impossible.");
    }
  }, [onError]);

  useEffect(() => {
    void load();
  }, [load]);

  async function reset(row: ProgressRow) {
    if (!row.session_id) return;
    setBusy(true);
    try {
      const result = await api<ResetReport>(`/admin/sessions/${row.session_id}/reset`, {
        method: "POST",
      });
      setConfirming(null);
      await load();
      onError(
        `Entretien de ${result.structure} réinitialisé — ${result.answers_deleted} réponse(s) supprimée(s).`,
      );
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Réinitialisation impossible.");
    } finally {
      setBusy(false);
    }
  }

  const visible = useMemo(() => {
    if (!report) return [];
    const needle = query.trim().toLowerCase();
    return report.rows.filter((row) => {
      if (filter !== "tous" && row.status !== filter) return false;
      if (!needle) return true;
      return (
        row.structure.toLowerCase().includes(needle) ||
        row.code.toLowerCase().includes(needle) ||
        (row.participant?.email ?? "").toLowerCase().includes(needle)
      );
    });
  }, [report, filter, query]);

  const coverage = report && report.points_total
    ? Math.round((100 * report.points_answered) / report.points_total)
    : 0;

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-8">
      <motion.header
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.32 }}
        className="flex flex-wrap items-start justify-between gap-4"
      >
        <div>
          <h1 className="font-display text-[26px] font-bold leading-tight text-ink-100">
            Suivi de la <span className="text-poppy-500">collecte</span>
          </h1>
          <p className="mt-1.5 text-sm text-ink-300">
            Avancement par entité. Le contenu des réponses n&apos;est pas consultable ici.
          </p>
        </div>
        <button onClick={onClose} className="btn-ghost !py-2 text-sm">
          Revenir à l&apos;entretien
        </button>
      </motion.header>

      {report === null ? (
        <div className="mt-8 grid gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-2xl border border-ink-600/70 bg-ink-850/60" />
          ))}
        </div>
      ) : (
        <>
          <div className="mt-7 grid gap-3 sm:grid-cols-4">
            <Stat value={`${report.completed}`} label="entretiens clôturés" tone="mint" />
            <Stat value={`${report.in_progress}`} label="en cours" tone="poppy" />
            <Stat value={`${report.not_started}`} label="non démarrés" tone="muted" />
            <Stat value={`${coverage} %`} label={`${report.points_answered} / ${report.points_total} points`} tone="poppy" />
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-2">
            {(["tous", "in_progress", "completed", "non_demarre"] as Filter[]).map((value) => (
              <button
                key={value}
                onClick={() => setFilter(value)}
                className={`rounded-lg border px-3 py-1.5 text-[12.5px] font-medium transition ${
                  filter === value
                    ? "border-poppy-500/60 bg-poppy-500/10 text-poppy-500"
                    : "border-ink-600 bg-ink-850/60 text-ink-300 hover:border-ink-500"
                }`}
              >
                {value === "tous" ? "Tous" : STATUS[value].label}
              </button>
            ))}
            <input
              className="field ml-auto !mt-0 max-w-xs !py-2 text-sm"
              placeholder="Rechercher une entité…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Rechercher une entité"
            />
          </div>

          <div className="mt-4 overflow-hidden rounded-2xl border border-ink-600/70">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[52rem] border-collapse text-left">
                <thead>
                  <tr className="border-b border-ink-600/70 bg-ink-850/60">
                    <Th>Entité</Th>
                    <Th>État</Th>
                    <Th className="w-[16rem]">Avancement</Th>
                    <Th>Participant</Th>
                    <Th>Dernière activité</Th>
                    <Th className="text-right">Action</Th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((row) => (
                    <tr key={row.structure_id} className="border-b border-ink-600/40 last:border-0">
                      <Td>
                        <div className="font-medium text-ink-100">{row.structure}</div>
                        <div className="mt-0.5 flex items-center gap-1.5">
                          <span className="rounded-md bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-ink-400">
                            {row.code}
                          </span>
                          {row.template_kind === "dsi" && (
                            <span className="rounded-md bg-accent-fire/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent-fire">
                              DSI
                            </span>
                          )}
                        </div>
                      </Td>
                      <Td>
                        <span
                          className={`inline-block rounded-md border px-2 py-0.5 text-[11px] font-semibold ${STATUS[row.status].className}`}
                        >
                          {STATUS[row.status].label}
                        </span>
                      </Td>
                      <Td>
                        {row.total === 0 ? (
                          <span className="text-[12px] text-ink-400">—</span>
                        ) : (
                          <>
                            <div className="flex items-center gap-2">
                              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-800">
                                <div
                                  className={`h-full rounded-full ${
                                    row.status === "completed" ? "bg-accent-mint" : "bg-poppy-500"
                                  }`}
                                  style={{ width: `${row.percent}%` }}
                                />
                              </div>
                              <span className="shrink-0 font-mono text-[11px] tabular-nums text-ink-300">
                                {row.answered}/{row.total}
                              </span>
                            </div>
                            {row.missing.length > 0 && (
                              <div
                                className="mt-1 truncate text-[11px] text-ink-400"
                                title={row.missing.join(", ")}
                              >
                                {row.missing.length} point(s) sans réponse
                              </div>
                            )}
                          </>
                        )}
                      </Td>
                      <Td>
                        {row.participant ? (
                          <>
                            <div className="text-[12.5px] text-ink-200">{row.participant.name}</div>
                            <div className="truncate text-[11px] text-ink-400">
                              {row.participant.email}
                            </div>
                          </>
                        ) : (
                          <span className="text-[12px] text-ink-400">—</span>
                        )}
                      </Td>
                      <Td>
                        <span className="text-[12px] text-ink-300">{when(row.last_activity_at)}</span>
                      </Td>
                      <Td className="text-right">
                        {row.session_id ? (
                          <button
                            onClick={() => setConfirming(row)}
                            className="rounded-lg border border-ink-600 px-2.5 py-1.5 text-[11.5px] font-medium text-ink-300 transition hover:border-accent-fire/50 hover:text-accent-fire"
                          >
                            Réinitialiser
                          </button>
                        ) : (
                          <span className="text-[11.5px] text-ink-500">rien à effacer</span>
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {visible.length === 0 && (
              <p className="px-4 py-8 text-center text-sm text-ink-400">
                Aucune entité ne correspond.
              </p>
            )}
          </div>
        </>
      )}

      {/* A reset destroys collected answers, so it is never one click. */}
      {confirming && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-ink-100/40 p-4 backdrop-blur-md"
          role="dialog"
          aria-modal="true"
        >
          <motion.div
            initial={{ opacity: 0, y: 18, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            className="panel w-full max-w-md p-6"
          >
            <h2 className="font-display text-lg font-bold text-ink-100">
              Réinitialiser l&apos;entretien ?
            </h2>
            <p className="mt-2.5 text-[13.5px] leading-relaxed text-ink-300">
              Toutes les réponses de{" "}
              <strong className="text-ink-100">{confirming.structure}</strong> seront
              supprimées et l&apos;entretien repartira de la première question.
              {confirming.answered > 0 && (
                <>
                  {" "}
                  <strong className="text-accent-fire">
                    {confirming.answered} point(s) renseigné(s)
                  </strong>{" "}
                  seront perdus.
                </>
              )}
            </p>
            <p className="mt-2.5 text-[12.5px] leading-relaxed text-ink-400">
              Les documents déjà produits sont conservés, et l&apos;opération est inscrite
              au journal d&apos;audit. Elle est irréversible.
            </p>
            <div className="mt-6 flex gap-2">
              <button
                onClick={() => setConfirming(null)}
                disabled={busy}
                className="btn-ghost flex-1"
              >
                Annuler
              </button>
              <button
                onClick={() => reset(confirming)}
                disabled={busy}
                className="btn-primary flex-1"
              >
                {busy ? <Spinner /> : null}
                Réinitialiser
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}

function when(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Stat({ value, label, tone }: { value: string; label: string; tone: "mint" | "poppy" | "muted" }) {
  const colour =
    tone === "mint" ? "text-accent-mint" : tone === "poppy" ? "text-poppy-500" : "text-ink-300";
  return (
    <div className="rounded-2xl border border-ink-600/70 bg-ink-850/60 px-4 py-3.5">
      <div className={`font-display text-2xl font-bold tabular-nums ${colour}`}>{value}</div>
      <div className="mt-0.5 text-[11.5px] leading-tight text-ink-400">{label}</div>
    </div>
  );
}

function Th({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <th
      className={`px-4 py-2.5 text-[10.5px] font-semibold uppercase tracking-[.1em] text-ink-400 ${className}`}
    >
      {children}
    </th>
  );
}

function Td({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <td className={`px-4 py-3 align-top ${className}`}>{children}</td>;
}
