import { useEffect, useState } from "react";
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
        className="flex items-center gap-1.5 border border-ink-600 hover:border-brass-500 text-parchment-200 text-[12px] font-mono px-3 py-1 rounded-sm transition-colors"
      >
        Sign in with GitHub
      </button>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {user.avatarUrl && (
        <img
          src={user.avatarUrl}
          alt={`${user.login}'s GitHub avatar`}
          className="w-5 h-5 rounded-full"
          referrerPolicy="no-referrer"
        />
      )}
      <span className="text-[12px] font-mono text-parchment-300">{user.login}</span>
      <button
        type="button"
        onClick={handleLogout}
        disabled={loggingOut}
        className="text-[12px] font-mono text-parchment-500 hover:text-parchment-200 disabled:opacity-40"
      >
        Sign out
      </button>
    </div>
  );
}
