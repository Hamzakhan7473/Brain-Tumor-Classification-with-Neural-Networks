import React from "react";
import { AppThemeProvider } from "../../context/AppThemeContext";

/** Login / signup — modern theme without full AppShell nav. */
export function AuthShell({ children }: { children: React.ReactNode }): React.ReactElement {
  return (
    <AppThemeProvider>
      <div className="auth-page">
        <div className="auth-page-inner">{children}</div>
      </div>
    </AppThemeProvider>
  );
}
