type FeedEmptyStateProps = {
  title: string;
  description: string;
  /** `muted` = same as default — subtle editorial card. */
  variant?: "default" | "muted" | "error";
  action?: { label: string; onClick: () => void };
};

/**
 * Short, polished copy blocks for empty feed, no matches, and recoverable errors.
 */
export function FeedEmptyState({
  title,
  description,
  variant = "default",
  action,
}: FeedEmptyStateProps) {
  const surface =
    variant === "error"
      ? "border-[var(--cb-error-border)] bg-[var(--cb-error-bg)]"
      : "border-[var(--cb-card-border)] bg-[var(--cb-surface)] ring-1 ring-[var(--cb-card-ring)]";

  const titleClass =
    variant === "error"
      ? "text-[var(--cb-error-title)]"
      : "text-[var(--cb-text)]";

  const bodyClass =
    variant === "error"
      ? "text-[var(--cb-error-body)]"
      : "text-[var(--cb-text-tertiary)]";

  return (
    <div
      className={`rounded-2xl border px-5 py-10 text-center transition-opacity duration-200 ease-out motion-reduce:transition-none ${surface}`}
      role={variant === "error" ? "alert" : undefined}
    >
      <p className={`text-base font-semibold ${titleClass}`}>{title}</p>
      <p className={`mt-2 text-sm leading-relaxed ${bodyClass}`}>{description}</p>
      {action ? (
        <button
          type="button"
          onClick={action.onClick}
          className="mt-6 rounded-xl bg-[var(--cb-button-primary-bg)] px-5 py-2.5 text-sm font-semibold text-[var(--cb-button-primary-text)] transition duration-200 ease-out hover:bg-[var(--cb-button-primary-hover)] active:scale-[0.98] motion-reduce:active:scale-100"
        >
          {action.label}
        </button>
      ) : null}
    </div>
  );
}
