/**
 * Variant colors mapped to frontend/src/styles/global.css :root:
 *   primary:   --green-700 background, --white text
 *   secondary: --green-50 bg, --green-700 text, --green-300 border
 *   ghost:     transparent, --green-700 text / --green-300 border hover --green-50
 *   danger:    --green-900 bg, --white text (mono stand-in — no reds in palette)
 */

import React from "react";
import { Link, type LinkProps } from "react-router-dom";

export type IosButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type IosButtonSize = "sm" | "md" | "lg";

export type IosButtonProps = {
  variant?: IosButtonVariant;
  size?: IosButtonSize;
  loading?: boolean;
  fullWidth?: boolean;
  disabled?: boolean;
  type?: "button" | "submit" | "reset";
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
};

const VARIANT_CLASS: Record<IosButtonVariant, string> = {
  primary: "ios-btn--primary",
  secondary: "ios-btn--secondary",
  ghost: "ios-btn--ghost",
  danger: "ios-btn--danger",
};

const SIZE_CLASS: Record<IosButtonSize, string> = {
  sm: "ios-btn--sm",
  md: "ios-btn--md",
  lg: "ios-btn--lg",
};

function Spinner() {
  return (
    <svg
      className="ios-spinner ios-spinner--motion ios-animated"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      aria-hidden
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray="43"
        opacity="0.35"
      />
      <circle
        cx="12"
        cy="12"
        r="9"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray="43"
        strokeDashoffset="20"
      />
    </svg>
  );
}

export function IosButton({
  variant = "primary",
  size = "md",
  loading = false,
  fullWidth = false,
  disabled = false,
  type = "button",
  children,
  className = "",
  style,
  onClick,
}: IosButtonProps): React.ReactElement {
  const v = VARIANT_CLASS[variant];
  const s = SIZE_CLASS[size];
  const block = fullWidth ? "ios-btn--block" : "";

  return (
    <button
      type={type}
      disabled={disabled || loading}
      onClick={onClick}
      className={`ios-btn ${v} ${s} ${block} ios-animated ${className}`.trim()}
      style={style}
    >
      {loading ? <Spinner /> : null}
      {children}
    </button>
  );
}

export type IosLinkButtonProps = Omit<LinkProps, "className"> & {
  variant?: IosButtonVariant;
  size?: IosButtonSize;
  fullWidth?: boolean;
  className?: string;
  disabled?: boolean;
  children: React.ReactNode;
};

export function IosLinkButton({
  variant = "primary",
  size = "md",
  fullWidth = false,
  className = "",
  disabled = false,
  children,
  style,
  onClick,
  ...rest
}: IosLinkButtonProps): React.ReactElement {
  const v = VARIANT_CLASS[variant];
  const s = SIZE_CLASS[size];
  const block = fullWidth ? "ios-btn--block" : "";

  return (
    <Link
      {...rest}
      aria-disabled={disabled || undefined}
      tabIndex={disabled ? -1 : rest.tabIndex}
      className={`ios-btn ${v} ${s} ${block} ios-animated ${className}`.trim()}
      style={
        disabled
          ? { ...style, pointerEvents: "none", opacity: 0.45, cursor: "not-allowed" }
          : style
      }
      onClick={(e) => {
        if (disabled) {
          e.preventDefault();
          return;
        }
        onClick?.(e);
      }}
    >
      {children}
    </Link>
  );
}
