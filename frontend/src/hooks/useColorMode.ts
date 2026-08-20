import { useCallback, useEffect, useState } from "react";

export type ColorMode = "light" | "dark";

const STORAGE_KEY = "colorMode";

function readStoredMode(): ColorMode {
  try {
    return localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

/** Stamps the mode onto <html> so the `[data-theme="dark"]` token remap in
 * index.css repaints the whole app. Light mode removes the attribute (light
 * is the default `:root` block, not a named theme). */
function applyColorMode(mode: ColorMode) {
  if (mode === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
}

/** Dark/light mode shared by both Vite entries (student + teacher).
 * Deliberately defaults to light rather than following the OS preference —
 * young students shouldn't open the app to a surprise dark screen; dark is
 * an explicit per-device opt-in stored in localStorage. */
export default function useColorMode(): [ColorMode, () => void] {
  const [mode, setMode] = useState<ColorMode>(readStoredMode);

  useEffect(() => {
    applyColorMode(mode);
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // Private browsing — the toggle still works for this page load.
    }
  }, [mode]);

  const toggle = useCallback(() => {
    setMode((current) => (current === "dark" ? "light" : "dark"));
  }, []);

  return [mode, toggle];
}
