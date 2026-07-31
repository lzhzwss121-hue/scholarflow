import {
  BookOpen,
  BrainCircuit,
  FileText,
  FlaskConical,
  GitBranch,
  LayoutDashboard,
  Plus,
  Table2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ViewId } from "../../mockData";

export const navIcons: Record<ViewId, LucideIcon> = {
  dashboard: LayoutDashboard,
  "new-project": Plus,
  "paper-table": Table2,
  "direction-review": FileText,
  "paper-memory": BrainCircuit,
  "paper-reader": BookOpen,
  "gap-board": GitBranch,
  "experiment-planner": FlaskConical,
};
