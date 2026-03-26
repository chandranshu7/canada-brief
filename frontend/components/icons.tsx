import type { SVGProps } from "react";

/** Base classes + optional size from caller; default size only when className omitted. */
function svgClass(className: string | undefined): string {
  const base = "inline-block shrink-0";
  if (className?.trim()) {
    return `${base} ${className}`;
  }
  return `${base} h-4 w-4`;
}

export function IconSearch({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={svgClass(className)}
      {...props}
    >
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}

export function IconRss({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden
      className={svgClass(className)}
      {...props}
    >
      <path d="M6.503 20.752A2.25 2.25 0 0 1 4.25 18.5a14.25 14.25 0 0 1 14.25-14.25.75.75 0 0 1 .75.75v2.25a.75.75 0 0 1-.75.75 11.25 11.25 0 0 0-11.25 11.25.75.75 0 0 1-.75.75h-2.25zM4.25 12.75a.75.75 0 0 1 .75-.75 8.25 8.25 0 0 1 8.25 8.25.75.75 0 0 1-.75.75h-2.25a.75.75 0 0 1-.75-.75 5.25 5.25 0 0 0-5.25-5.25.75.75 0 0 1-.75-.75v-2.25zM6 18a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z" />
    </svg>
  );
}

export function IconAlert({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={svgClass(className)}
      {...props}
    >
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
      <path d="M10.3 3.3 2.7 17a1.94 1.94 0 0 0 1.7 2.8h15.2a1.94 1.94 0 0 0 1.7-2.8L13.7 3.3a1.94 1.94 0 0 0-3.4 0z" />
    </svg>
  );
}

export function IconHome({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={svgClass(className)}
      {...props}
    >
      <path d="M3 9.5 12 3l9 6.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1V9.5z" />
    </svg>
  );
}

export function IconMapPin({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={svgClass(className)}
      {...props}
    >
      <path d="M12 21c-4-3.5-7-7.2-7-11a7 7 0 1 1 14 0c0 3.8-3 7.5-7 11z" />
      <circle cx="12" cy="10" r="2.5" />
    </svg>
  );
}

/** Outline bookmark (unsaved state). */
export function IconBookmark({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={svgClass(className)}
      {...props}
    >
      <path d="M6 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v17l-6-3-6 3V4z" />
    </svg>
  );
}

/** Filled bookmark (saved state). */
export function IconBookmarkFilled({
  className,
  ...props
}: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      stroke="none"
      aria-hidden
      className={svgClass(className)}
      {...props}
    >
      <path d="M6 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v17l-6-3-6 3V4z" />
    </svg>
  );
}

export function IconUser({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={svgClass(className)}
      {...props}
    >
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 20.5c1.5-3 4-4.5 7-4.5s5.5 1.5 7 4.5" />
    </svg>
  );
}

export function IconSparkle({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden
      className={svgClass(className)}
      {...props}
    >
      <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z" />
    </svg>
  );
}
