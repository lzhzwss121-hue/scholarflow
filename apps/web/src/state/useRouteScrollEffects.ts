import { useEffect, useRef, type RefObject } from "react";
import type { ViewId } from "../mockData";

export function useRouteScrollEffects({
  activeView,
  hasHydratedDirectionReview,
  paperId,
  workflowMainRef,
}: {
  activeView: ViewId;
  hasHydratedDirectionReview: boolean;
  paperId: string;
  workflowMainRef: RefObject<HTMLElement | null>;
}) {
  const previousRouteIdentityRef = useRef<string | null>(null);
  const routeIdentity = `${activeView}:${paperId}`;

  useEffect(() => {
    const previousRouteIdentity = previousRouteIdentityRef.current;
    previousRouteIdentityRef.current = routeIdentity;
    if (previousRouteIdentity === routeIdentity) {
      return;
    }
    workflowMainRef.current?.scrollTo({ top: 0, behavior: "auto" });
  }, [routeIdentity, workflowMainRef]);

  useEffect(() => {
    if (!paperId || !hasHydratedDirectionReview) {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      document
        .querySelector<HTMLElement>("#direction-paper-title")
        ?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [paperId, hasHydratedDirectionReview]);
}
