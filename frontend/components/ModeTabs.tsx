"use client";

import type { FeedMode } from "@/lib/locationPreference";

type ModeTabsProps = {
  mode: FeedMode;
  onModeChange: (mode: FeedMode) => void;
};

const tabBase =
  "min-w-[6.5rem] flex-1 rounded-full px-4 py-2.5 text-sm font-semibold transition sm:min-w-[8rem]";
const inactive = "text-slate-600 hover:bg-slate-100/90";
const active = "bg-slate-900 text-white shadow-sm shadow-slate-900/15";

export function ModeTabs({ mode, onModeChange }: ModeTabsProps) {
  return (
    <div
      className="flex w-full max-w-md gap-1 rounded-full bg-slate-100/90 p-1 ring-1 ring-slate-200/80"
      role="tablist"
      aria-label="Feed mode"
    >
      <button
        type="button"
        role="tab"
        aria-selected={mode === "general"}
        className={`${tabBase} ${mode === "general" ? active : inactive}`}
        onClick={() => onModeChange("general")}
      >
        General
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={mode === "local"}
        className={`${tabBase} ${mode === "local" ? active : inactive}`}
        onClick={() => onModeChange("local")}
      >
        Local
      </button>
    </div>
  );
}
