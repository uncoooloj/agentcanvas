import { useChanges } from "@/lib/changeset"
import type { ChangeEntry } from "@/lib/changeset"
import { ChangeTray } from "./ChangeTray"
import { HandoffOverlay } from "./HandoffOverlay"
import { StepComposer } from "./StepComposer"
import type { EditRequest, StagedEdit } from "@/lib/edits"

interface Props {
  request: EditRequest | null
  onSubmitEdit: (edit: StagedEdit) => void
  onCancelEdit: () => void
  onHandoffDone: () => void
  onSelectChange: (change: ChangeEntry) => void
  onModifyChange: (change: ChangeEntry) => void
}

// One dynamic surface at the bottom: compose an edit, review staged changes,
// or watch the assistant carry them out — only one shows at a time.
export function BottomDock({
  request,
  onSubmitEdit,
  onCancelEdit,
  onHandoffDone,
  onSelectChange,
  onModifyChange,
}: Props) {
  const phase = useChanges((s) => s.handoff.phase)

  if (phase !== "composing") {
    return <HandoffOverlay onAcknowledge={onHandoffDone} />
  }
  if (request) {
    return <StepComposer request={request} onSubmit={onSubmitEdit} onCancel={onCancelEdit} />
  }
  return <ChangeTray onSelectChange={onSelectChange} onModifyChange={onModifyChange} />
}
