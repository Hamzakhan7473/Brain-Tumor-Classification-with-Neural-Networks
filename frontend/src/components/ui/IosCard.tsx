/**
 * Colors — global.css :root:
 * Surface / card tint: --surface, --white in shadows
 * Border: color-mix of --line (.ns-card-frame)
 * Typography: --ink-mute (--muted), --ink-mid headings
 */

import React from "react";

export type IosCardProps = {
  label?: string;
  title?: string;
  children: React.ReactNode;
  className?: string;
  padding?: boolean;
};

export function IosCard({
  label,
  title,
  children,
  className = "",
  padding = true,
}: IosCardProps): React.ReactElement {
  const head = Boolean(label || title);
  return (
    <div
      className={`ns-card-frame ns-bg-card-solid rounded-ios-lg overflow-hidden font-ios ios-soft-shadow ${className}`.trim()}
    >
      {head ? (
        <div className="ios-card-header">
          {label ? (
            <p
              className="text-ios-caption2 font-semibold text-ns-muted uppercase"
              style={{ letterSpacing: "0.12em", marginBottom: 2 }}
            >
              {label}
            </p>
          ) : null}
          {title ? <p className="text-ios-subhead font-semibold text-ns-heading">{title}</p> : null}
        </div>
      ) : null}
      <div className={padding ? "ios-pad-card" : undefined}>{children}</div>
    </div>
  );
}
