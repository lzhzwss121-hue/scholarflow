import type { ViewId } from "../mockData";

export type ArtifactTab = "markdown" | "json" | "diff";
export type ApiStatus = "checking" | "online" | "offline";
export type ProjectDraft = {
  title: string;
  description: string;
  keyword: string;
  field: string;
};

export type ViewSelector = (view: ViewId) => void;
