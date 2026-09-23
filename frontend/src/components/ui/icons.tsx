// Authored icons: one 1.5px stroke, square caps, 16px grid, matching the terminal's 1px rules.

type IconProps = { className?: string };

export function GripIcon({ className }: IconProps) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <g fill="currentColor">
        <rect x="4" y="3" width="2.5" height="2.5" />
        <rect x="9.5" y="3" width="2.5" height="2.5" />
        <rect x="4" y="6.75" width="2.5" height="2.5" />
        <rect x="9.5" y="6.75" width="2.5" height="2.5" />
        <rect x="4" y="10.5" width="2.5" height="2.5" />
        <rect x="9.5" y="10.5" width="2.5" height="2.5" />
      </g>
    </svg>
  );
}

export function ExternalIcon({ className }: IconProps) {
  return (
    <svg className={className} width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path
        d="M9 3h4v4M13 3 7.5 8.5M11 9.5V13H3V5h3.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="square"
      />
    </svg>
  );
}

export function ChevronIcon({ className }: IconProps) {
  return (
    <svg className={className} width="12" height="12" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path d="m5 3 5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="square" />
    </svg>
  );
}
