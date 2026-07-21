"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Two-step destructive action: the first request arms the control, the second
 * request for the same id (within the timeout) executes. Anything else disarms.
 */
export function useArmedAction(timeoutMs = 3200) {
  const [armedId, setArmedId] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    []
  );

  const disarm = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    setArmedId(null);
  };

  const request = (id: string, execute: () => void) => {
    if (armedId === id) {
      disarm();
      execute();
      return;
    }
    disarm();
    setArmedId(id);
    timerRef.current = setTimeout(() => setArmedId(null), timeoutMs);
  };

  return { armedId, request, disarm };
}
