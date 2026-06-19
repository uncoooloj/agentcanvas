import { GitBranch, Play, Zap, type LucideIcon } from "lucide-react"

type RoleKey = "when" | "do" | "if"

interface RoleStyle {
  label: string
  chip: string
  accent: string
  dot: string
  icon: LucideIcon
}

export const ROLE: Record<RoleKey, RoleStyle> = {
  when: {
    label: "When",
    chip: "bg-when-bg text-when-fg",
    accent: "bg-when-accent",
    dot: "bg-when-accent",
    icon: Zap,
  },
  do: {
    label: "Do",
    chip: "bg-act-bg text-act-fg",
    accent: "bg-act-accent",
    dot: "bg-act-accent",
    icon: Play,
  },
  if: {
    label: "If",
    chip: "bg-rule-bg text-rule-fg",
    accent: "bg-rule-accent",
    dot: "bg-rule-accent",
    icon: GitBranch,
  },
}
