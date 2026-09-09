import React from "react";

type AppPageProps = {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
  wide?: boolean;
};

/** Consistent in-app page shell — matches dashboard / upload layout. */
export function AppPage({ title, subtitle, children, className, wide }: AppPageProps): React.ReactElement {
  return (
    <div className={`app-page ${className ?? ""}`.trim()}>
      <div className={`app-page-inner${wide ? " app-page-inner--wide" : ""}`}>
        {title || subtitle ? (
          <header className="app-page-header">
            {title ? <h1>{title}</h1> : null}
            {subtitle ? <p>{subtitle}</p> : null}
          </header>
        ) : null}
        {children}
      </div>
    </div>
  );
}
