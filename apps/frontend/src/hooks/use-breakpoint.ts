import { useCallback, useEffect, useState } from "react";

export type Breakpoint = "mobile" | "tablet" | "desktop";

const MOBILE_MAX = 767;
const TABLET_MIN = 768;
const TABLET_MAX = 1279;
const DESKTOP_MIN = 1280;

function getBreakpoint(width: number): Breakpoint {
  if (width < TABLET_MIN) return "mobile";
  if (width < DESKTOP_MIN) return "tablet";
  return "desktop";
}

export function useBreakpoint(): Breakpoint {
  const [breakpoint, setBreakpoint] = useState<Breakpoint>(() =>
    typeof window !== "undefined"
      ? getBreakpoint(window.innerWidth)
      : "desktop",
  );

  const handleResize = useCallback(() => {
    setBreakpoint(getBreakpoint(window.innerWidth));
  }, []);

  useEffect(() => {
    window.addEventListener("resize", handleResize);
    // Also handle orientation change for tablets
    window.addEventListener("orientationchange", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("orientationchange", handleResize);
    };
  }, [handleResize]);

  return breakpoint;
}

export { MOBILE_MAX, TABLET_MIN, TABLET_MAX, DESKTOP_MIN };
