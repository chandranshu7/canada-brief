"use client";

import { useTheme } from "@/components/ThemeProvider";
import { APP_VERSION } from "@/lib/appInfo";
import type { FollowTopicId } from "@/lib/followedTopics";
import {
  TOPIC_DEFINITIONS,
  topicLabel,
} from "@/lib/followedTopics";
import type { FeedMode, LocationPreference } from "@/lib/locationPreference";
import type { ThemePreference } from "@/lib/theme";

type ProfileScreenProps = {
  feedMode: FeedMode;
  onFeedModeChange: (mode: FeedMode) => void;
  location: LocationPreference;
  /** Opens Local tab so the user can pick a city (existing flow). */
  onGoToLocalSettings: () => void;
  savedCount: number;
  onClearSaved: () => void;
  onResetFeedPreferences: () => void;
  apiBaseUrl?: string;
  followedTopics: readonly FollowTopicId[];
  onToggleFollowTopic: (id: FollowTopicId) => void;
};

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-[var(--cb-card-border)] bg-[var(--cb-card-bg)] p-4 shadow-sm ring-1 ring-[var(--cb-card-ring)] sm:p-5">
      <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--cb-text-tertiary)]">
        {title}
      </h2>
      <div className="mt-4 space-y-4">{children}</div>
    </section>
  );
}

function SegmentedThree<T extends string>({
  value,
  options,
  onChange,
  labels,
}: {
  value: T;
  options: readonly T[];
  onChange: (v: T) => void;
  labels: Record<T, string>;
}) {
  return (
    <div
      className="flex rounded-xl border border-[var(--cb-border)] bg-[var(--cb-surface)] p-0.5"
      role="group"
    >
      {options.map((opt) => {
        const on = value === opt;
        return (
          <button
            key={opt}
            type="button"
            onClick={() => onChange(opt)}
            className={`flex-1 rounded-lg px-2 py-2 text-center text-xs font-semibold transition sm:text-sm ${
              on
                ? "bg-[var(--cb-chip-cat-active-bg)] text-[var(--cb-chip-cat-active-text)] shadow-sm"
                : "text-[var(--cb-text-secondary)] hover:bg-[var(--cb-badge-muted-bg)] hover:text-[var(--cb-text)]"
            }`}
            aria-pressed={on}
          >
            {labels[opt]}
          </button>
        );
      })}
    </div>
  );
}

function formatLocation(loc: LocationPreference): string {
  if (loc.city && loc.province) {
    return (loc.label || `${loc.city}, ${loc.province}`).trim();
  }
  return "Not set";
}

const THEME_OPTIONS = ["dark", "light", "system"] as const satisfies readonly ThemePreference[];

const THEME_LABELS: Record<(typeof THEME_OPTIONS)[number], string> = {
  dark: "Dark",
  light: "Light",
  system: "System",
};

const FEED_OPTIONS = ["general", "local"] as const satisfies readonly FeedMode[];

const FEED_LABELS: Record<FeedMode, string> = {
  general: "General",
  local: "Local",
};

export function ProfileScreen({
  feedMode,
  onFeedModeChange,
  location,
  onGoToLocalSettings,
  savedCount,
  onClearSaved,
  onResetFeedPreferences,
  apiBaseUrl,
  followedTopics,
  onToggleFollowTopic,
}: ProfileScreenProps) {
  const { preference, resolved, setPreference } = useTheme();
  const resolvedThemeLabel = resolved === "dark" ? "Dark" : "Light";

  return (
    <div className="space-y-4 pb-2">
      <header className="px-0.5">
        <h1 className="text-xl font-bold tracking-tight text-[var(--cb-text)]">
          Profile
        </h1>
        <p className="mt-1 text-sm text-[var(--cb-text-tertiary)]">
          Preferences and data on this device.
        </p>
      </header>

      <Section title="Preferences">
        <div>
          <p className="text-sm font-medium text-[var(--cb-text)]">Theme</p>
          <p className="mt-0.5 text-xs text-[var(--cb-text-tertiary)]">
            Appearance ({resolvedThemeLabel} now)
          </p>
          <div className="mt-2">
            <SegmentedThree
              value={preference}
              options={THEME_OPTIONS}
              onChange={(p) => setPreference(p)}
              labels={THEME_LABELS}
            />
          </div>
        </div>

        <div>
          <p className="text-sm font-medium text-[var(--cb-text)]">
            Default feed mode
          </p>
          <p className="mt-0.5 text-xs text-[var(--cb-text-tertiary)]">
            Which tab opens when you start the app.
          </p>
          <div className="mt-2">
            <SegmentedThree
              value={feedMode}
              options={FEED_OPTIONS}
              onChange={onFeedModeChange}
              labels={FEED_LABELS}
            />
          </div>
        </div>

        <div>
          <p className="text-sm font-medium text-[var(--cb-text)]">
            Local area
          </p>
          <p className="mt-1 text-sm text-[var(--cb-text-secondary)]">
            {formatLocation(location)}
          </p>
          <button
            type="button"
            onClick={onGoToLocalSettings}
            className="mt-2 rounded-lg border border-[var(--cb-border)] bg-[var(--cb-surface)] px-3 py-2 text-xs font-semibold text-[var(--cb-text)] transition hover:border-[var(--cb-card-hover-border)] hover:bg-[var(--cb-badge-muted-bg)]"
          >
            Choose city in Local tab
          </button>
        </div>
      </Section>

      <Section title="Topics you follow">
        <div>
          <p className="text-sm font-medium text-[var(--cb-text)]">
            Personalize your feed
          </p>
          <p className="mt-0.5 text-xs text-[var(--cb-text-tertiary)]">
            We match headlines using simple keywords — no account needed. Tap to
            follow or unfollow.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {TOPIC_DEFINITIONS.map((t) => {
              const on = followedTopics.includes(t.id);
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => onToggleFollowTopic(t.id)}
                  aria-pressed={on}
                  className={`rounded-full border px-3 py-1.5 text-[12px] font-semibold transition-[transform,background-color,border-color,color] duration-200 ease-out active:scale-[0.98] motion-reduce:transition-none motion-reduce:active:scale-100 ${
                    on
                      ? "border-transparent bg-[var(--cb-chip-cat-active-bg)] text-[var(--cb-chip-cat-active-text)] shadow-sm"
                      : "border-[var(--cb-border)] bg-[var(--cb-surface)] text-[var(--cb-text-secondary)] hover:border-[var(--cb-text-tertiary)] hover:bg-[var(--cb-badge-muted-bg)]"
                  }`}
                >
                  {on ? "✓ " : ""}
                  {topicLabel(t.id)}
                </button>
              );
            })}
          </div>
          {followedTopics.length === 0 ? (
            <p className="mt-3 text-xs leading-relaxed text-[var(--cb-text-muted)]">
              Follow topics like AI, jobs, or housing to personalize your feed.
            </p>
          ) : null}
          <p className="mt-3 text-xs leading-relaxed text-[var(--cb-text-muted)]">
            The main feed also boosts categories you open, save, and search for — learned
            on this device only.
          </p>
        </div>
      </Section>

      <Section title="Your activity">
        <ul className="space-y-3 text-sm">
          <li className="flex justify-between gap-4 border-b border-[var(--cb-border-subtle)] pb-3">
            <span className="text-[var(--cb-text-secondary)]">Saved stories</span>
            <span className="font-semibold tabular-nums text-[var(--cb-text)]">
              {savedCount}
            </span>
          </li>
          <li className="flex justify-between gap-4 border-b border-[var(--cb-border-subtle)] pb-3">
            <span className="text-[var(--cb-text-secondary)]">Feed preference</span>
            <span className="text-right font-medium text-[var(--cb-text)]">
              {feedMode === "local" ? "Local" : "General"}
            </span>
          </li>
          <li className="flex justify-between gap-4">
            <span className="text-[var(--cb-text-secondary)]">Local city</span>
            <span className="max-w-[60%] text-right text-[var(--cb-text)]">
              {location.city ? formatLocation(location) : "—"}
            </span>
          </li>
        </ul>
      </Section>

      <Section title="Manage">
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          <button
            type="button"
            onClick={onClearSaved}
            className="rounded-xl border border-[var(--cb-border)] bg-[var(--cb-surface)] px-4 py-2.5 text-sm font-semibold text-[var(--cb-text)] transition hover:border-amber-500/50 hover:bg-[var(--cb-badge-muted-bg)]"
          >
            Clear all saved stories
          </button>
          <button
            type="button"
            onClick={onResetFeedPreferences}
            className="rounded-xl border border-[var(--cb-border)] bg-[var(--cb-surface)] px-4 py-2.5 text-sm font-semibold text-[var(--cb-text)] transition hover:border-[var(--cb-card-hover-border)] hover:bg-[var(--cb-badge-muted-bg)]"
          >
            Reset feed preferences
          </button>
        </div>
        <p className="text-xs leading-relaxed text-[var(--cb-text-muted)]">
          Clearing saved stories cannot be undone. Resetting feed preferences restores
          Canada-wide mode and clears your selected city (saved bookmarks are kept).
        </p>
      </Section>

      <Section title="About">
        <div>
          <p className="text-lg font-semibold text-[var(--cb-text)]">Canada Brief</p>
          <p className="mt-2 text-sm leading-relaxed text-[var(--cb-text-secondary)]">
            A calmer, mobile-first Canadian news reader. Browse national coverage or
            drill into your city and region — all in one place.
          </p>
          <p className="mt-3 text-xs text-[var(--cb-text-muted)]">
            Version {APP_VERSION}
          </p>
          {apiBaseUrl ? (
            <p className="mt-2 text-xs text-[var(--cb-text-muted)]">
              API{" "}
              <code className="rounded bg-[var(--cb-code-bg)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--cb-code-text)]">
                {apiBaseUrl}
              </code>
            </p>
          ) : null}
          <p className="mt-4 text-xs text-[var(--cb-text-tertiary)]">
            Feedback & contact: coming soon.
          </p>
        </div>
      </Section>
    </div>
  );
}
