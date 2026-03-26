"use client";

import {
  IconBookmark,
  IconHome,
  IconMapPin,
  IconSearch,
  IconUser,
} from "./icons";

export type BottomNavTab = "home" | "local" | "search" | "saved" | "profile";

type BottomNavProps = {
  active: BottomNavTab;
  onChange: (tab: BottomNavTab) => void;
};

const item = (on: boolean) =>
  `relative flex flex-1 flex-col items-center justify-center gap-0.5 rounded-xl py-1.5 text-[10px] font-semibold transition-[transform,color,background-color] duration-200 ease-out active:scale-[0.96] motion-reduce:transition-none motion-reduce:active:scale-100 sm:text-[11px] ${
    on
      ? "bg-[var(--cb-accent-soft)] text-[var(--cb-nav-active)]"
      : "text-[var(--cb-nav-inactive)] hover:text-[var(--cb-text-secondary)]"
  }`;

export function BottomNav({ active, onChange }: BottomNavProps) {
  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-40 px-3 pb-[max(0.45rem,env(safe-area-inset-bottom))] pt-2"
      aria-label="Primary"
    >
      <div className="mx-auto flex max-w-lg items-stretch justify-around rounded-2xl border border-[var(--cb-nav-border)] bg-[var(--cb-nav-bg)] p-1.5 shadow-premium backdrop-blur-xl sm:max-w-2xl">
        <button
          type="button"
          className={item(active === "home")}
          onClick={() => onChange("home")}
          aria-current={active === "home" ? "page" : undefined}
        >
          <IconHome className="h-5 w-5" />
          Home
        </button>
        <button
          type="button"
          className={item(active === "local")}
          onClick={() => onChange("local")}
          aria-current={active === "local" ? "page" : undefined}
        >
          <IconMapPin className="h-5 w-5" />
          Local
        </button>
        <button
          type="button"
          className={item(active === "search")}
          onClick={() => onChange("search")}
          aria-current={active === "search" ? "page" : undefined}
        >
          <IconSearch className="h-5 w-5" />
          Search
        </button>
        <button
          type="button"
          className={item(active === "saved")}
          onClick={() => onChange("saved")}
          aria-current={active === "saved" ? "page" : undefined}
        >
          <IconBookmark className="h-5 w-5" />
          Saved
        </button>
        <button
          type="button"
          className={item(active === "profile")}
          onClick={() => onChange("profile")}
          aria-current={active === "profile" ? "page" : undefined}
        >
          <IconUser className="h-5 w-5" />
          Profile
        </button>
      </div>
    </nav>
  );
}
