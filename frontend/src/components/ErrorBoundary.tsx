import { Component, type ErrorInfo, type ReactNode } from "react";
import { Wordmark } from "./Brand";

type Props = { children: ReactNode };
type State = { failed: boolean };

/**
 * Last line of defence for the interview screen.
 *
 * Without a boundary, any render error unmounts the whole tree and leaves a
 * blank page - during an interview that reads as "I have lost my answers".
 * Nothing is lost in reality: every recorded answer is already sealed and
 * persisted server-side, so the recovery path is simply to reload.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Deliberately not shipped to a third-party collector: a stack trace from
    // this screen can carry fragments of confidential interview content.
    console.error("Interface error:", error.message, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;

    return (
      <div className="grid min-h-screen place-items-center px-5">
        <div className="panel w-full max-w-md p-8 text-center">
          <div className="mb-6 flex justify-center">
            <Wordmark />
          </div>
          <h1 className="font-display text-xl font-bold text-ink-100">
            L&apos;affichage a rencontré un problème
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-ink-300">
            Vos réponses déjà enregistrées sont conservées en lieu sur : elles ont ete chiffrées
            et sauvegardees au fur et a mesure de l&apos;entretien. Rechargez la page pour reprendre
            là où vous en etiez.
          </p>
          <button onClick={() => window.location.reload()} className="btn-primary mt-6 w-full">
            Recharger la page
          </button>
        </div>
      </div>
    );
  }
}
