import { useCallback, useEffect, useRef } from "react";

export type RequestScope =
  | "workspace"
  | "resources"
  | "artifact"
  | "agent"
  | "literature"
  | "direction"
  | "paper-card"
  | "memory"
  | "rag"
  | "decision";

export type RequestGuard = {
  signal: AbortSignal;
  isCurrent: () => boolean;
  isAborted: () => boolean;
  finish: () => void;
};

type RequestState = Record<
  RequestScope,
  { id: number; controller: AbortController | null }
>;

function createRequestState(): RequestState {
  return {
    workspace: { id: 0, controller: null },
    resources: { id: 0, controller: null },
    artifact: { id: 0, controller: null },
    agent: { id: 0, controller: null },
    literature: { id: 0, controller: null },
    direction: { id: 0, controller: null },
    "paper-card": { id: 0, controller: null },
    memory: { id: 0, controller: null },
    rag: { id: 0, controller: null },
    decision: { id: 0, controller: null },
  };
}

export function useRequestCoordinator(activeProjectId: string | null) {
  const activeProjectIdRef = useRef<string | null>(activeProjectId);
  const requestStateRef = useRef<RequestState>(createRequestState());

  useEffect(() => {
    activeProjectIdRef.current = activeProjectId;
  }, [activeProjectId]);

  const beginRequest = useCallback((scope: RequestScope): RequestGuard => {
    const previous = requestStateRef.current[scope];
    previous.controller?.abort("superseded");
    const controller = new AbortController();
    const requestId = previous.id + 1;
    requestStateRef.current[scope] = { id: requestId, controller };
    return {
      signal: controller.signal,
      isCurrent: () =>
        requestStateRef.current[scope].id === requestId &&
        !controller.signal.aborted,
      isAborted: () => controller.signal.aborted,
      finish: () => {
        if (requestStateRef.current[scope].id === requestId) {
          requestStateRef.current[scope].controller = null;
        }
      },
    };
  }, []);

  const cancelRequests = useCallback((scopes: RequestScope[]) => {
    scopes.forEach((scope) => {
      const state = requestStateRef.current[scope];
      state.controller?.abort("project-switch");
      state.controller = null;
      state.id += 1;
    });
  }, []);

  useEffect(
    () => () => {
      cancelRequests(Object.keys(requestStateRef.current) as RequestScope[]);
    },
    [cancelRequests],
  );

  return {
    activeProjectIdRef,
    beginRequest,
    cancelRequests,
  };
}
