import { Command, GitBranch, Moon, PanelsTopLeft, Sun, Workflow, GitCompareArrows } from "lucide-react"
import { useMemo } from "react"
import { useShallow } from "zustand/react/shallow"
import { toast } from "sonner"
import { BrandMark } from "@/components/BrandMark"
import { diffCounts, isPendingRun, runnerLabels, studioTabs } from "@/lib/studioTypes"
import { useStudioStore, visibleDocument } from "@/lib/studioStore"

export function DiffCounts({ counts, showZero = false }: { counts: ReturnType<typeof diffCounts>; showZero?: boolean }) {
  if (!showZero && !counts.added && !counts.modified && !counts.removed) return null
  return (
    <span className="s-counts" aria-label={`${counts.added} added, ${counts.modified} modified, ${counts.removed} removed`}>
      {(showZero || counts.added > 0) && <span data-diff="added" aria-hidden="true">+{counts.added}</span>}
      {(showZero || counts.modified > 0) && <span data-diff="modified" aria-hidden="true">~{counts.modified}</span>}
      {(showZero || counts.removed > 0) && <span data-diff="removed" aria-hidden="true">−{counts.removed}</span>}
    </span>
  )
}

const tabIcons = { system: PanelsTopLeft, flows: Workflow, diff: GitCompareArrows }

export function CopyMappingPrompt({ workspace, diffBase, kind = "map" }: {
  workspace: string
  diffBase?: string | null
  kind?: "map" | "diff"
}) {
  async function copy() {
    const task = kind === "map"
      ? "Map the repo’s architecture and product journeys."
      : `Map the behavioral changes in ${diffBase ? `the Git comparison against ${diffBase}` : "the working tree"}. Mark additions, modifications, and removals.`
    const prompt = [
      `Use AgentCanvas Studio for the workspace ${workspace || "in this directory"}.`,
      task,
      "Follow the installed AgentCanvas v3 Studio document schema and save the map at .agentcanvas/studio.json.",
      "Ground steps in workspace-relative code references and preserve existing graph IDs when behavior is unchanged.",
      "Leave application code untouched. Tell me when the map is ready so I can reload Studio.",
    ].join("\n")
    try {
      await navigator.clipboard.writeText(prompt)
      toast.success("Prompt copied")
    } catch {
      toast.error("Clipboard is unavailable.")
    }
  }
  return <button type="button" className="s-button s-primary" onClick={() => void copy()}>Copy Prompt</button>
}

export function StudioTopBar({ onWelcome, focusCommand }: { onWelcome: () => void; focusCommand: () => void }) {
  const { activeTab, setTab, darkMode, setDarkMode, startRun, git, mode, workspace, name, preferredRunner, mapped, runRunner, busy, live, proposal } =
    useStudioStore(useShallow((state) => ({
      activeTab: state.activeTab, setTab: state.setTab, darkMode: state.darkMode, setDarkMode: state.setDarkMode, startRun: state.startRun,
      git: state.data?.git, mode: state.data?.mode, workspace: state.data?.workspace, name: state.data?.workspace_name,
      preferredRunner: state.data?.runner.preferred ?? "copy", mapped: state.data?.has_mapped_canvas,
      runRunner: state.data?.active_run?.runner, busy: isPendingRun(state.data?.active_run),
      live: state.data?.active_run?.status === "queued" || state.data?.active_run?.status === "running",
      proposal: state.data?.active_run?.status === "awaiting_approval" ? state.data.active_run.proposed_document : null,
    })))
  const document = useStudioStore(visibleDocument)
  const counts = useMemo(() => diffCounts((proposal ?? document)?.flows.flatMap((flow) => flow.nodes) ?? []), [proposal, document])
  if (!git) return null
  const workspaceName = name || "Workspace"
  const runner = busy && runRunner ? runRunner : preferredRunner
  const kind = activeTab === "diff" ? "diff" : "map"
  const action = kind === "diff" ? "Diff Branch" : mapped ? "Refresh" : "Map Repo"

  return (
    <header className="s-topbar">
      <div className="s-workspace">
        <button type="button" className="s-brand" onClick={onWelcome} aria-label="AgentCanvas home"><BrandMark /><span>AgentCanvas</span></button>
        <span className="s-workspace-divider" aria-hidden="true" />
        <div className="s-workspace-details">
          <strong title={workspaceName}>{workspaceName}</strong>
          {git.branch && <span title={git.branch} className="s-branch"><GitBranch size={12} /><code>{git.branch}</code>{git.dirty && <i title="Uncommitted changes" />}</span>}
        </div>
        {mode === "demo" && <span className="s-sandbox"><i />Interactive Sandbox</span>}
      </div>

      <nav className="s-tabs" aria-label="Studio views">
        {studioTabs.map((tab, index) => {
          const Icon = tabIcons[tab]
          return <button type="button" key={tab} aria-current={activeTab === tab ? "page" : undefined} title={`${tab} (${index + 1})`} onClick={() => setTab(tab)}>
            <Icon size={15} /><span className="capitalize">{tab}</span>{tab === "diff" && <DiffCounts counts={counts} />}
          </button>
        })}
      </nav>

      <div className="s-top-actions">
        <span className="s-runner" title={`${runnerLabels[runner]}${mode === "demo" ? " simulated" : ""}`}>
          <i data-live={live} data-copy={runner === "copy"} />
          <span>{runnerLabels[runner]}{runner !== "copy" && (busy ? " · Active" : " · Ready")}</span>
        </span>
        {runner === "copy"
          ? <CopyMappingPrompt workspace={workspace ?? ""} diffBase={git.diff_base} kind={kind} />
          : <button type="button" className="s-button s-primary" disabled={busy} onClick={() => void startRun({ kind })}>{action}</button>}
        <button type="button" className="s-button s-command-button" onClick={focusCommand} aria-label="Focus command dock"><Command size={14} /><span>K</span></button>
        <button type="button" className="s-icon" onClick={() => setDarkMode(!darkMode)} aria-label={darkMode ? "Use light theme" : "Use dark theme"}>
          {darkMode ? <Sun size={17} /> : <Moon size={17} />}
        </button>
      </div>
    </header>
  )
}
