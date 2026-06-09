"use client";

import { useEffect, useState } from "react";

/** Avoid SSR/client DOM mismatch for browser-only widgets (e.g. Recharts). */
export function useMounted() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted;
}
