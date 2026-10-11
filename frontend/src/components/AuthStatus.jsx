import { useEffect, useState } from "react";
import { LogIn } from "lucide-react";
import { getCurrentUser, logout, redirectToGitHubLogin } from "../services/auth";

/**
 * Sign-in state for the header: "Sign in with GitHub" when signed out,
 * avatar + username + sign-out when signed in. Fetches its own state on
 * mount so neither page needs to thread auth state down as props - it's
 * genuinely independent of whatever project is (or isn't) being shown.
 */
export default function AuthStatus() {
  const [user, setUser] = useState(undefined); // undefined = still loading
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getCurrentUser()
      .then((u) => !cancelled && setUser(u))
      .catch(() => !cancelled && setUser(null));
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logout();
      setUser(null);
    } finally {
      setLoggingOut(false);
    }
  }

  if (user === undefined) return null; // avoid a flash of "sign in" before the check resolves

  if (user === null) {
    return (
      <button
        type="button"
        onClick={redirectToGitHubLogin}
        className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-line-strong text-[12.5px] font-medium text-fg-soft hover:text-fg hover:bg-surface-2 transition-colors"
      >
        <LogIn size={14} aria-hidden="true" />
        Sign in with GitHub
      </button>
    );
  }

  return (
    <div className="flex items-center gap-2 h-8 pl-1 pr-2.5 rounded-full border border-line bg-surface">
      {user.avatarUrl && (
        <img
          src={user.avatarUrl}
          alt={`${user.login}'s GitHub avatar`}
          className="w-6 h-6 rounded-full"
          referrerPolicy="no-referrer"
        />
      )}
      <span className="text-[12.5px] font-medium text-fg">{user.login}</span>
      <button
        type="button"
        onClick={handleLogout}
        disabled={loggingOut}
        className="text-[12px] text-muted hover:text-fg disabled:opacity-40"
      >
        Sign out
      </button>
    </div>
  );
}
