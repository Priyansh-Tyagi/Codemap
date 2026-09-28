import { Link } from "react-router-dom";

export default function Wordmark() {
  return (
    <Link to="/" className="flex items-center gap-2 flex-shrink-0">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <circle cx="4" cy="15" r="2.2" fill="#c08a3f" />
        <circle cx="16" cy="5" r="2.2" fill="#7c8397" />
        <circle cx="16" cy="15" r="2.2" fill="#7c8397" />
        <path
          d="M6 14 L14 6 M14 6 L14 15 M14 15 L6 15"
          stroke="#323a4d"
          strokeWidth="1.4"
          fill="none"
        />
      </svg>
      <span className="font-display text-[15px] font-semibold text-parchment-100">
        CodeMap
      </span>
    </Link>
  );
}
