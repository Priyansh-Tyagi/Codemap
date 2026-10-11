import { Link } from "react-router-dom";

/** The mark is three nodes in three category colours joined by edges: the
 * thing the product draws, drawn small. */
export default function Wordmark() {
  return (
    <Link to="/" className="flex items-center gap-2 flex-shrink-0 rounded-md" aria-label="CodeMap home">
      <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
        <path d="M6.5 16 L11 6.5 M11 6.5 L16 16 M6.5 16 H16" stroke="var(--line-strong)" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="11" cy="5.5" r="3" fill="#6C8EF5" />
        <circle cx="5.5" cy="16.5" r="3" fill="#4FBFA8" />
        <circle cx="16.5" cy="16.5" r="3" fill="#E0925C" />
      </svg>
      <span className="text-[16px] font-semibold tracking-tight text-fg">CodeMap</span>
    </Link>
  );
}
