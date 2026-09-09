import React from "react";
import { Link } from "react-router-dom";
import { IosSymbol, type IosSymbolName } from "./IosSymbol";

export type GlassTileTint = "cyan" | "teal" | "indigo" | "violet" | "magenta" | "slate";

export type GlassTileItem = {
  label: string;
  symbol: IosSymbolName;
  to?: string;
  onClick?: () => void;
  disabled?: boolean;
  tint?: GlassTileTint;
};

export type GlassTileVariant = "landing" | "app" | "compact" | "inline";

type GlassTilePanelProps = {
  title?: string;
  tiles: GlassTileItem[];
  variant?: GlassTileVariant;
  className?: string;
  "aria-label"?: string;
};

function GlassTile({ item, iconSize }: { item: GlassTileItem; iconSize: number }) {
  const tileClass = `glass-tile${item.tint ? ` glass-tile--${item.tint}` : ""}`;
  const inner = (
    <>
      <IosSymbol name={item.symbol} size={iconSize} strokeWidth={1.65} />
      <span>{item.label}</span>
    </>
  );

  if (item.to) {
    return (
      <Link to={item.to} className={tileClass} aria-label={item.label}>
        {inner}
      </Link>
    );
  }

  return (
    <button
      type="button"
      className={tileClass}
      onClick={item.onClick}
      disabled={item.disabled}
      aria-label={item.label}
    >
      {inner}
    </button>
  );
}

/** Frosted glass shortcut row — navigation & exploration (not primary CTAs). */
export function GlassTilePanel({
  title,
  tiles,
  variant = "app",
  className,
  "aria-label": ariaLabel,
}: GlassTilePanelProps): React.ReactElement {
  const iconSize = variant === "compact" || variant === "inline" ? 24 : 26;
  const panelClass = [
    "glass-tile-panel",
    `glass-tile-panel--${variant}`,
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <section className={panelClass} aria-label={ariaLabel ?? title ?? "Shortcuts"}>
      <div className="glass-tile-bg" aria-hidden />
      {title ? <h2 className="glass-tile-title">{title}</h2> : null}
      <div className="glass-tile-row">
        {tiles.map((tile) => (
          <GlassTile key={`${tile.label}-${tile.to ?? "btn"}`} item={tile} iconSize={iconSize} />
        ))}
      </div>
    </section>
  );
}

export const APP_WORKFLOW_TILES: GlassTileItem[] = [
  { to: "/upload", label: "Upload", symbol: "arrow.up.doc", tint: "cyan" },
  { to: "/bicr-review", label: "BICR", symbol: "eye", tint: "teal" },
  { to: "/report", label: "Reports", symbol: "doc.text", tint: "indigo" },
  { to: "/shadow-queue", label: "Shadow", symbol: "tray.full", tint: "violet" },
  { to: "/clinical-feedback", label: "Feedback", symbol: "checkmark.seal", tint: "magenta" },
  { to: "/docs-assistant", label: "Docs", symbol: "doc.text", tint: "slate" },
];
