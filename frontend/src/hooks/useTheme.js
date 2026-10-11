import { useSyncExternalStore } from "react";

const KEY = "codemap-theme";
const listeners = new Set();

function current() {
  return typeof document !== "undefined" && document.documentElement.dataset.theme === "dark"
    ? "dark"
    : "light";
}

function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // private mode / storage blocked: the theme still applies for this visit
  }
  listeners.forEach((l) => l());
}

/** Works anywhere (no provider needed): the source of truth is the
 * data-theme attribute that index.html sets before first paint. */
export function useTheme() {
  const theme = useSyncExternalStore(subscribe, current, () => "light");
  return { theme, toggle: () => setTheme(theme === "dark" ? "light" : "dark") };
}
