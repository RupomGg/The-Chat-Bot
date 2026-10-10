"use client";
import { Moon, Sun } from "@phosphor-icons/react";

// The icon follows the .dark class via CSS, so nothing needs to read state on the server.
export function ThemeToggle() {
  const flip = () => {
    const dark = document.documentElement.classList.toggle("dark");
    try { localStorage.setItem("theme", dark ? "dark" : "light"); } catch {}
  };
  return (
    <button type="button" onClick={flip} aria-label="Switch light or dark mode"
      className="grid size-10 place-items-center rounded-full bg-surface ring-1 ring-line ring-inset hover:text-brand">
      <Moon size={18} className="[.dark_&]:hidden" aria-hidden />
      <Sun size={18} className="hidden [.dark_&]:block" aria-hidden />
    </button>
  );
}
