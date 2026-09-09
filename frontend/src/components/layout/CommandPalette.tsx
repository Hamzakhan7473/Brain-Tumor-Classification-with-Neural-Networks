import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CaseSummary, listCases } from "../../api/client";
import { useTheme } from "../../context/AppThemeContext";

type CommandItem = {
  id: string;
  label: string;
  hint?: string;
  action: () => void;
};

type CommandPaletteProps = {
  open: boolean;
  onClose: () => void;
};

const NAV_COMMANDS: Omit<CommandItem, "action">[] = [
  { id: "dashboard", label: "Dashboard", hint: "Home" },
  { id: "upload", label: "Upload & predict", hint: "New scan" },
  { id: "bicr", label: "BICR review", hint: "Dual-read workflow" },
  { id: "shadow", label: "Shadow queue", hint: "Pilot ops" },
  { id: "feedback", label: "Clinical feedback", hint: "Review AI output" },
  { id: "report", label: "Report draft", hint: "Structured report" },
  { id: "docs", label: "Docs assistant", hint: "Ask SOPs" },
  { id: "inbox", label: "Inbox", hint: "Messages" },
  { id: "auths", label: "Prior auths", hint: "Worklist" },
];

const ROUTES: Record<string, string> = {
  dashboard: "/dashboard",
  upload: "/upload",
  bicr: "/bicr-review",
  shadow: "/shadow-queue",
  feedback: "/clinical-feedback",
  report: "/report",
  docs: "/docs-assistant",
  inbox: "/inbox",
  auths: "/auths",
};

export function CommandPalette({ open, onClose }: CommandPaletteProps): React.ReactElement | null {
  const navigate = useNavigate();
  const { toggleTheme, isDark } = useTheme();
  const [query, setQuery] = useState("");
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActiveIndex(0);
    void listCases({ limit: 30 })
      .then(setCases)
      .catch(() => setCases([]));
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  const run = useCallback(
    (fn: () => void) => {
      fn();
      onClose();
    },
    [onClose],
  );

  const items = useMemo((): CommandItem[] => {
    const q = query.trim().toLowerCase();
    const nav = NAV_COMMANDS.filter(
      (c) => !q || c.label.toLowerCase().includes(q) || (c.hint || "").toLowerCase().includes(q),
    ).map((c) => ({
      ...c,
      action: () => navigate(ROUTES[c.id] || "/dashboard"),
    }));

    const caseHits =
      q.length >= 3
        ? cases
            .filter(
              (c) =>
                (c.study_instance_uid || "").toLowerCase().includes(q) ||
                (c.site_id || "").toLowerCase().includes(q),
            )
            .slice(0, 6)
            .map((c) => ({
              id: `case-${c.study_instance_uid}`,
              label: `Open case · ${c.study_instance_uid}`,
              hint: [c.site_id, c.label].filter(Boolean).join(" · ") || "Case detail",
              action: () => navigate(`/cases/${encodeURIComponent(c.study_instance_uid)}`),
            }))
        : [];

    const system: CommandItem[] = [];
    if (!q || "theme dark light".includes(q)) {
      system.push({
        id: "theme",
        label: isDark ? "Switch to light mode" : "Switch to dark mode",
        hint: "Appearance",
        action: toggleTheme,
      });
    }

    return [...caseHits, ...nav, ...system];
  }, [cases, isDark, navigate, query, toggleTheme]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, Math.max(items.length - 1, 0)));
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
      }
      if (e.key === "Enter" && items[activeIndex]) {
        e.preventDefault();
        run(items[activeIndex].action);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeIndex, items, onClose, open, run]);

  if (!open) return null;

  return (
    <div className="cmdk-overlay" role="presentation" onClick={onClose}>
      <div
        className="cmdk-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="cmdk-input-wrap">
          <span className="cmdk-search-icon" aria-hidden>
            ⌕
          </span>
          <input
            ref={inputRef}
            className="cmdk-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search pages, cases, actions…"
            aria-label="Command search"
          />
          <kbd className="cmdk-kbd">esc</kbd>
        </div>
        <ul className="cmdk-list" role="listbox">
          {items.length === 0 ? (
            <li className="cmdk-empty">No matches</li>
          ) : (
            items.map((item, idx) => (
              <li key={item.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={idx === activeIndex}
                  className={`cmdk-item${idx === activeIndex ? " cmdk-item--active" : ""}`}
                  onMouseEnter={() => setActiveIndex(idx)}
                  onClick={() => run(item.action)}
                >
                  <span className="cmdk-item-label">{item.label}</span>
                  {item.hint ? <span className="cmdk-item-hint">{item.hint}</span> : null}
                </button>
              </li>
            ))
          )}
        </ul>
        <div className="cmdk-footer">
          <span>
            <kbd>↑</kbd> <kbd>↓</kbd> navigate
          </span>
          <span>
            <kbd>↵</kbd> open
          </span>
        </div>
      </div>
    </div>
  );
}

export function useCommandPalette(): { open: boolean; setOpen: (v: boolean) => void; toggle: () => void } {
  const [open, setOpen] = useState(false);
  const toggle = useCallback(() => setOpen((v) => !v), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);

  return { open, setOpen, toggle };
}
