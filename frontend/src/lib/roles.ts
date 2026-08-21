import { GitBranch, Play, Zap, type LucideIcon } from "lucide-react"
import { StepRole } from "./types"

export enum RuleRole {
  If = "if",
}

type RoleKey = StepRole | RuleRole

interface RoleStyle {
  label: string
  chip: string
  accent: string
  dot: string
  icon: LucideIcon
}

export const ROLE: Record<RoleKey, RoleStyle> = {
  [StepRole.When]: {
    label: "When",
    chip: "bg-when-bg text-when-fg",
    accent: "bg-when-accent",
    dot: "bg-when-accent",
    icon: Zap,
  },
  [StepRole.Do]: {
    label: "Do",
    chip: "bg-act-bg text-act-fg",
    accent: "bg-act-accent",
    dot: "bg-act-accent",
    icon: Play,
  },
  [RuleRole.If]: {
    label: "If",
    chip: "bg-rule-bg text-rule-fg",
    accent: "bg-rule-accent",
    dot: "bg-rule-accent",
    icon: GitBranch,
  },
}
