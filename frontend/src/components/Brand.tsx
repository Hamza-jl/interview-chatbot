import { motion } from "framer-motion";

/**
 * Devoteam roundel: the lowercase "d" in White on a Red Poppy disc.
 *
 * Red Poppy (#f8485e) is the brand primary; White is treated as an active
 * colour rather than an absence of one, which is why the counter of the "d" is
 * cut out of the disc rather than filled with a darker tone.
 */
export function Logo({ size = 34 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      role="img"
      aria-label="Devoteam"
    >
      <circle cx="24" cy="24" r="24" fill="#f8485e" />
      {/* Bowl of the "d": a ring, so the disc shows through the counter. */}
      <circle cx="21" cy="29.5" r="8.25" stroke="#ffffff" strokeWidth="4.5" fill="none" />
      {/* Ascender. */}
      <rect x="27" y="9.5" width="4.5" height="28.25" rx="2.25" fill="#ffffff" />
    </svg>
  );
}

/**
 * Full lock-up. The wordmark is set in the UI typeface rather than traced from
 * the brand font, so it stays legible at small sizes and in dark surfaces.
 */
export function Wordmark({
  compact = false,
  size = 34,
}: {
  compact?: boolean;
  size?: number;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <Logo size={size} />
      <div className="leading-none">
        <div className="font-display text-[17px] font-bold lowercase tracking-[-.01em] text-ink-100">
          devoteam
        </div>
        {!compact && (
          <div className="mt-1 text-[10px] font-medium uppercase tracking-[.18em] text-ink-400">
            PCA · Etat des lieux
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Ambient light, drawn from the secondary palette - which the brand reserves
 * for backgrounds and graphics. Decorative only; nothing here carries meaning.
 */
export function AmbientGlow() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <motion.div className="absolute -right-32 -top-40 h-[34rem] w-[34rem] rounded-full bg-poppy-300/60 blur-[120px] animate-breathe" />
      <motion.div
        className="absolute -bottom-48 -left-36 h-[30rem] w-[30rem] rounded-full bg-aqua/55 blur-[130px] animate-breathe"
        style={{ animationDelay: "3s" }}
      />
      <motion.div
        className="absolute right-1/4 top-1/2 h-[22rem] w-[22rem] rounded-full bg-beige/45 blur-[120px] animate-breathe"
        style={{ animationDelay: "5s" }}
      />
      <div className="absolute inset-0 bg-[linear-gradient(rgba(60,60,58,.028)_1px,transparent_1px),linear-gradient(90deg,rgba(60,60,58,.028)_1px,transparent_1px)] bg-[size:56px_56px]" />
    </div>
  );
}

/** Three-dot chrome that frames the console, echoing a desktop application. */
export function WindowDots() {
  return (
    <div className="flex items-center gap-2">
      <span className="h-3 w-3 rounded-full bg-[#FF5F57]" />
      <span className="h-3 w-3 rounded-full bg-[#FEBC2E]" />
      <span className="h-3 w-3 rounded-full bg-[#28C840]" />
    </div>
  );
}

export function SecurityBadge({ label = "Chiffre de bout en bout" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-lg border border-accent-mint/30 bg-accent-mint/10 px-2.5 py-1 text-[11px] font-medium text-accent-mint">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M12 2 4 5.5v6c0 5 3.4 9.4 8 10.5 4.6-1.1 8-5.5 8-10.5v-6L12 2Z"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinejoin="round"
        />
        <path d="m9 12 2 2 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
      {label}
    </span>
  );
}
