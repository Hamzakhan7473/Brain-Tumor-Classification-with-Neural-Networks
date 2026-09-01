/**
 * SF Symbol–style line icons (iOS). Stroke-based, no emoji / AI clipart.
 */

import React from "react";

export type IosSymbolName =
  | "chart.bar"
  | "eye"
  | "doc.text"
  | "lock.shield"
  | "person.2"
  | "checkmark.seal"
  | "arrow.up.doc"
  | "tray.full"
  | "camera"
  | "folder"
  | "cube"
  | "sparkle";

type Props = {
  name: IosSymbolName;
  size?: number;
  className?: string;
  strokeWidth?: number;
};

function pathsFor(name: IosSymbolName): React.ReactNode {
  switch (name) {
    case "sparkle":
      return (
        <path
          d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z"
          strokeLinejoin="round"
        />
      );
    case "chart.bar":
      return (
        <>
          <path d="M6 20V10" strokeLinecap="round" />
          <path d="M12 20V4" strokeLinecap="round" />
          <path d="M18 20v-6" strokeLinecap="round" />
        </>
      );
    case "eye":
      return (
        <>
          <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" />
          <circle cx="12" cy="12" r="3" />
        </>
      );
    case "doc.text":
      return (
        <>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6" />
          <path d="M8 13h8M8 17h5" strokeLinecap="round" />
        </>
      );
    case "lock.shield":
      return (
        <>
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <path d="M9 12l2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </>
      );
    case "person.2":
      return (
        <>
          <circle cx="9" cy="8" r="3" />
          <path d="M3 20v-1a5 5 0 0 1 5-5h2a5 5 0 0 1 5 5v1" strokeLinecap="round" />
          <path d="M16 11a3 3 0 1 0 0-6" strokeLinecap="round" />
          <path d="M21 20v-1a4 4 0 0 0-3-3.87" strokeLinecap="round" />
        </>
      );
    case "checkmark.seal":
      return (
        <>
          <circle cx="12" cy="12" r="10" />
          <path d="M8 12l2.5 2.5L16 9" strokeLinecap="round" strokeLinejoin="round" />
        </>
      );
    case "arrow.up.doc":
      return (
        <>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6" />
          <path d="M12 11V6M12 6l-2.5 2.5M12 6l2.5 2.5" strokeLinecap="round" strokeLinejoin="round" />
        </>
      );
    case "tray.full":
      return (
        <>
          <path d="M3 7h18l-2 11H5L3 7z" strokeLinejoin="round" />
          <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" strokeLinecap="round" />
        </>
      );
    case "camera":
      return (
        <>
          <path d="M5 7h2l2-2h6l2 2h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z" />
          <circle cx="12" cy="13" r="3.5" />
        </>
      );
    case "folder":
      return (
        <>
          <path d="M4 20h16a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1h-5l-2-2H4a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1z" />
        </>
      );
    case "cube":
      return (
        <>
          <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z" strokeLinejoin="round" />
          <path d="M12 12l8-4.5M12 12v9M12 12L4 7.5" strokeLinejoin="round" />
        </>
      );
    default:
      return null;
  }
}

export function IosSymbol({ name, size = 22, className, strokeWidth = 1.75 }: Props) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {pathsFor(name)}
    </svg>
  );
}
