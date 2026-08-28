import { motion } from "framer-motion";

import devoteamLogo from "../assets/devoteam.png";
import clientLogo from "../assets/mansa-bank.png";

/**
 * Brand marks.
 *
 * Both are the official artwork rather than a redrawing: getting a logo subtly
 * wrong is worse than not showing one. The client file has an opaque white
 * background, so it is composited with `mix-blend-multiply` to sit cleanly on
 * the page's tinted ground.
 */

export function Logo({ size = 34 }: { size?: number }) {
  return (
    <img
      src={devoteamLogo}
      alt="Devoteam"
      style={{ height: size }}
      className="w-auto shrink-0 select-none"
      draggable={false}
    />
  );
}

export function ClientMark({ height = 30 }: { height?: number }) {
  return (
    <img
      src={clientLogo}
      alt="MANSA BANK"
      style={{ height }}
      className="w-auto shrink-0 select-none mix-blend-multiply"
      draggable={false}
    />
  );
}

/**
 * The co-branded lock-up: the consultancy running the workshop, then the
 * organisation being documented.
 */
export function CoBrand({ compact = false }: { compact?: boolean }) {
  // The client wordmark is all cap-height, so a matching pixel height reads
  // noticeably larger than the roundel-and-lowercase Devoteam lock-up. Sized
  // down to balance optically rather than numerically.
  return (
    <div className="flex items-center gap-4 sm:gap-5">
      <Logo size={compact ? 24 : 38} />
      <span aria-hidden="true" className={`w-px shrink-0 bg-ink-600 ${compact ? "h-6" : "h-9"}`} />
      <ClientMark height={compact ? 16 : 24} />
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

export function SecurityBadge({ label = "Chiffré de bout en bout" }: { label?: string }) {
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
