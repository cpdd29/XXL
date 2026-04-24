"use client"

import { useState } from "react"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/ui/alert-dialog"
import { Button } from "@/shared/ui/button"
import { useDeleteBrainSkill } from "@/modules/capability/hooks/use-brain-skills"
import { toast } from "@/shared/hooks/use-toast"
import type { BrainSkillItem } from "@/shared/types"

export function BrainSkillManagementActions({
  skill,
  onDeleted,
}: {
  skill: BrainSkillItem
  onDeleted?: (skillId: string) => void
}) {
  const [deleteOpen, setDeleteOpen] = useState(false)
  const deleteBrainSkill = useDeleteBrainSkill()

  const handleDelete = async () => {
    try {
      const response = await deleteBrainSkill.mutateAsync(skill.id)
      toast({
        title: "Skill 已删除",
        description: response.message,
      })
      setDeleteOpen(false)
      onDeleted?.(skill.id)
    } catch (error) {
      const message = error instanceof Error ? error.message : "Skill 删除失败"
      toast({
        title: "Skill 删除失败",
        description: message,
        variant: "destructive",
      })
    }
  }

  return (
    <>
      <Button
        variant="secondary"
        size="sm"
        className="h-7 px-2 text-xs text-destructive"
        disabled={deleteBrainSkill.isPending}
        onClick={() => setDeleteOpen(true)}
      >
        删除
      </Button>

      <AlertDialog
        open={deleteOpen}
        onOpenChange={(open) => {
          if (deleteBrainSkill.isPending) return
          setDeleteOpen(open)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除 Skill</AlertDialogTitle>
            <AlertDialogDescription>
              确认删除“{skill.name}”吗？删除后将无法继续在 Agent 中绑定该 Skill。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteBrainSkill.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleteBrainSkill.isPending}
              onClick={(event) => {
                event.preventDefault()
                void handleDelete()
              }}
            >
              {deleteBrainSkill.isPending ? "删除中..." : "确认删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
