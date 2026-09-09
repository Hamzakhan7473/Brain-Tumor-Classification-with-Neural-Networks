import React, { createContext, useContext } from "react";
import { useAppTheme, type AppTheme } from "../hooks/useAppTheme";

type AppThemeContextValue = {
  theme: AppTheme;
  isDark: boolean;
  setTheme: (t: AppTheme) => void;
  toggleTheme: () => void;
};

const AppThemeContext = createContext<AppThemeContextValue | null>(null);

export function AppThemeProvider(props: { children: React.ReactNode }): React.ReactElement {
  const value = useAppTheme();
  return (
    <AppThemeContext.Provider value={value}>
      <div className={`app-modern${value.isDark ? " app-modern--dark" : ""}`}>{props.children}</div>
    </AppThemeContext.Provider>
  );
}

export function useTheme(): AppThemeContextValue {
  const ctx = useContext(AppThemeContext);
  if (!ctx) throw new Error("useTheme must be used within AppThemeProvider");
  return ctx;
}
