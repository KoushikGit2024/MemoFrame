import { useEffect, useState } from "react";
import { mediaUrl } from "../lib/api";
import { initials } from "../lib/utils";
import type { PersonRecord } from "../types/memoframe";

interface PersonAvatarProps {
  person?: PersonRecord | null;
  size?: "sm" | "md" | "lg";
  accent?: "default" | "violet" | "amber" | "success";
}

const ACCENT_RING: Record<NonNullable<PersonAvatarProps["accent"]>, string> = {
  default: "border-subtle",
  violet: "border-violet/70",
  amber: "border-amber/60",
  success: "border-success/70",
};

export default function PersonAvatar({
  person,
  size = "sm",
  accent = "default",
}: PersonAvatarProps) {
  const [loaded, setLoaded] = useState(false);
  const [err, setErr] = useState(false);

  // Reset error state and loading when person or cover crop changes
  useEffect(() => {
    setErr(false);
    setLoaded(false);
  }, [person?.id, person?.cover_crop_path]);

  const src = !err && person?.cover_crop_path ? mediaUrl(person.cover_crop_path) : "";
  const dims =
    size === "lg"
      ? "w-14 h-14 text-sm"
      : size === "md"
        ? "w-10 h-10 text-xs"
        : "w-7 h-7 text-[11px]";

  return (
    <span
      className={`${dims} shrink-0 rounded-xs bg-input border ${ACCENT_RING[accent]} overflow-hidden inline-flex items-center justify-center font-semibold text-secondary relative select-none`}
    >
      {/* Background Initials Fallback - ALWAYS visible under image if image is missing or loading */}
      <span className="text-secondary/90 font-medium z-0">{initials(person?.name)}</span>

      {/* Shimmer overlay while loading image */}
      {src && !loaded && !err && (
        <span className="absolute inset-0 bg-elevated/70 animate-shimmer z-10" />
      )}

      {/* Face Crop Image */}
      {src && !err && (
        <img
          src={src}
          alt={person?.name || ""}
          ref={img => {
            // If image is already cached by browser, mark loaded immediately
            if (img && img.complete && img.naturalWidth > 0 && !loaded) {
              setLoaded(true);
            }
          }}
          onLoad={() => setLoaded(true)}
          onError={() => setErr(true)}
          className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-150 z-20 ${
            loaded ? "opacity-100" : "opacity-0"
          }`}
        />
      )}
    </span>
  );
}
