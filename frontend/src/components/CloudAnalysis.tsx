import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ApiError,
  api,
  type CloudResult,
  type OutboundPreview,
} from "../lib/api";
import { Spinner } from "./AuthFlow";

/**
 * Lecture d'un fichier par un modèle distant.
 *
 * C'est la seule partie de l'application qui sort du réseau, et l'écran le dit
 * avant d'agir plutôt qu'après : on montre le contenu exact qui partirait, ce
 * qui en a été retiré, et vers quels modèles il irait. Un nom de client repéré
 * ici coûte une correction de configuration ; repéré dans les journaux d'un
 * fournisseur, il coûte autre chose.
 */
export function CloudAnalysis({
  documentId,
  found,
  onUnderstood,
  onError,
}: {
  documentId: string;
  /** Emplacements trouvés par le lecteur local. Zéro = c'est la seule issue. */
  found: number;
  onUnderstood: (result: CloudResult) => void;
  onError: (message: string) => void;
}) {
  const [preview, setPreview] = useState<OutboundPreview | null>(null);
  const [showText, setShowText] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<CloudResult | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await api<OutboundPreview>(`/documents/${documentId}/outbound`);
        if (alive) setPreview(data);
      } catch {
        if (alive) setPreview(null);
      }
    })();
    return () => {
      alive = false;
    };
  }, [documentId]);

  async function run() {
    setRunning(true);
    try {
      const data = await api<CloudResult>(`/documents/${documentId}/understand`, {
        method: "POST",
      });
      setResult(data);
      onUnderstood(data);
    } catch (err) {
      onError(
        err instanceof ApiError ? err.message : "L'analyse distante a échoué.",
      );
    } finally {
      setRunning(false);
    }
  }

  if (!preview) return null;

  if (!preview.available) {
    return (
      <div className="mt-5 rounded-xl border border-ink-600/70 bg-ink-900/40 p-4">
        <h3 className="text-sm font-semibold text-ink-100">Analyse distante désactivée</h3>
        <p className="mt-1.5 text-xs leading-relaxed text-ink-400">
          Ce serveur lit les fichiers avec le modèle local uniquement. Pour lire
          un scan, une photo ou un format que le modèle local ne comprend pas,
          activez <code className="font-mono text-[11px]">OPENROUTER_ENABLED</code>.
        </p>
      </div>
    );
  }

  const redactions = Object.entries(preview.redactions);

  return (
    <div className="mt-5 rounded-xl border border-accent-lagoon/30 bg-accent-lagoon/[0.06] p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink-100">
          Lecture par un modèle distant
        </h3>
        <span className="font-mono text-[10px] uppercase tracking-wide text-ink-400">
          sort du réseau
        </span>
      </div>

      <p className="mt-1.5 text-xs leading-relaxed text-ink-300">
        {found === 0
          ? "Rien n'a pu être repéré dans ce fichier sur cette machine : il n'a " +
            "ni champ ni case vide à remplir. Un modèle distant, lui, peut le " +
            "lire et dire quelles informations il attend. "
          : "Le modèle local sait reformuler une question posée sur un blanc " +
            "déjà repéré. Il ne sait pas regarder un fichier inconnu et deviner " +
            "ce qu'il demande. Cette étape-là, et elle seule, est confiée à un " +
            "modèle distant. "}
        <b className="text-ink-200">Les réponses de l'entretien ne partent jamais.</b>
      </p>

      {/* ---- ce qui partirait ------------------------------------------ */}
      <div className="mt-3 rounded-lg border border-ink-600/70 bg-ink-900/60 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
            Ce qui serait envoyé
          </span>
          <button
            onClick={() => setShowText((v) => !v)}
            className="rounded-md border border-ink-600 px-2 py-1 text-[11px] text-ink-300 transition hover:border-ink-500 hover:text-ink-100"
          >
            {showText ? "Masquer" : "Voir le contenu exact"}
          </button>
        </div>

        <p className="mt-1.5 font-mono text-[11px] text-ink-300">{preview.summary}</p>

        {redactions.length > 0 && (
          <p className="mt-1.5 text-[11px] leading-relaxed text-accent-mint">
            Retiré avant envoi :{" "}
            {redactions.map(([k, n]) => `${n} ${k.toLowerCase()}`).join(", ")}.
          </p>
        )}
        {redactions.length === 0 && (
          <p className="mt-1.5 text-[11px] leading-relaxed text-ink-400">
            Aucun identifiant détecté à retirer. Vérifiez le contenu si le
            document porte un nom de client.
          </p>
        )}

        <AnimatePresence>
          {showText && (
            <motion.pre
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-md border border-ink-700 bg-ink-950 p-2.5 font-mono text-[10.5px] leading-relaxed text-ink-300"
            >
              {preview.text || "(aucun texte extractible — le fichier sera lu comme une image)"}
            </motion.pre>
          )}
        </AnimatePresence>
      </div>

      <p className="mt-2 text-[11px] text-ink-400">
        Modèles essayés dans l'ordre : {preview.models.join(" → ")}
      </p>

      {!preview.fillable && (
        <p className="mt-2 text-[11px] leading-relaxed text-accent-fire">
          Ce format ne peut pas être rempli sur place : les réponses seront
          livrées dans un nouveau document, pas dans le fichier d'origine.
        </p>
      )}

      {/* ---- action ----------------------------------------------------- */}
      {!result && (
        <button
          onClick={run}
          disabled={running}
          className="btn-primary mt-3.5 !py-2 text-sm"
        >
          {running ? <Spinner /> : null}
          {running ? "Lecture en cours…" : "Envoyer et analyser"}
        </button>
      )}
      {running && (
        <p className="mt-2 text-[11px] text-ink-400">
          Les modèles gratuits réfléchissent avant de répondre : comptez une à
          deux minutes.
        </p>
      )}

      {/* ---- résultat ---------------------------------------------------- */}
      {result && (
        <div className="mt-3.5 rounded-lg border border-accent-mint/30 bg-accent-mint/10 p-3">
          <p className="text-xs leading-relaxed text-ink-200">
            Lu par <b>{result.model}</b> en {result.seconds}s.{" "}
            <b>{result.fields.length}</b> champ(s) identifié(s), dont{" "}
            <b>{result.matched}</b> rattaché(s) à un emplacement réel du fichier.
          </p>
          {result.invented > 0 && (
            <p className="mt-1.5 text-[11px] leading-relaxed text-accent-fire">
              {result.invented} emplacement(s) proposé(s) par le modèle
              n'existaient pas dans le fichier : ces réponses seront collectées
              mais pas écrites automatiquement.
            </p>
          )}
          {result.attempts.length > 1 && (
            <p className="mt-1.5 font-mono text-[10.5px] text-ink-400">
              {result.attempts.join(" → ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
