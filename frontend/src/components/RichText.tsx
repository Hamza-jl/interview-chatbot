import { Fragment, type ReactNode } from "react";

/**
 * Minimal formatter for assistant text: bold spans, line breaks and dash lists.
 *
 * It builds React nodes rather than HTML strings - `dangerouslySetInnerHTML` is
 * never used anywhere in this application, so model output (or anything a user
 * typed) can not introduce markup into the page.
 */
function inline(text: string, keyPrefix: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={`${keyPrefix}-b${i}`} className="font-semibold text-ink-100">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <Fragment key={`${keyPrefix}-t${i}`}>{part}</Fragment>;
  });
}

export function RichText({ text }: { text: string }) {
  const blocks = text.split("\n");
  const nodes: ReactNode[] = [];
  let bullets: string[] = [];

  const flush = (key: string) => {
    if (!bullets.length) return;
    nodes.push(
      <ul key={key} className="my-2 space-y-1 pl-1">
        {bullets.map((item, i) => (
          <li key={i} className="flex gap-2">
            <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-poppy-500" aria-hidden="true" />
            <span>{inline(item, `${key}-${i}`)}</span>
          </li>
        ))}
      </ul>,
    );
    bullets = [];
  };

  blocks.forEach((line, index) => {
    const trimmed = line.trim();
    if (/^[-•]\s+/.test(trimmed)) {
      bullets.push(trimmed.replace(/^[-•]\s+/, ""));
      return;
    }
    flush(`ul-${index}`);
    if (!trimmed) {
      nodes.push(<div key={`sp-${index}`} className="h-2" />);
      return;
    }
    nodes.push(
      <p key={`p-${index}`} className="whitespace-pre-wrap">
        {inline(line, `p-${index}`)}
      </p>,
    );
  });
  flush("ul-end");

  return <>{nodes}</>;
}
