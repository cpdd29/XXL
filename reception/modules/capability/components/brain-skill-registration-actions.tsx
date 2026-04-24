"use client"

import { type ChangeEvent, useRef, useState } from "react"
import { Upload } from "lucide-react"
import { Button } from "@/shared/ui/button"
import { useUploadBrainSkill } from "@/modules/capability/hooks/use-brain-skills"
import { toast } from "@/shared/hooks/use-toast"

const ACCEPTED_FILE_TYPES = ".json,.yaml,.yml,.md"

export function BrainSkillRegistrationActions() {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const [pendingFileName, setPendingFileName] = useState("")
  const uploadBrainSkill = useUploadBrainSkill()

  const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    setPendingFileName(file.name)

    try {
      const content = await file.text()
      if (!content.trim()) {
        throw new Error("Skill 文件内容为空，请检查后重试。")
      }

      const response = await uploadBrainSkill.mutateAsync({
        fileName: file.name,
        content,
      })

      toast({
        title: "Skill 已上传",
        description: response.message,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : "Skill 上传失败"
      toast({
        title: "Skill 上传失败",
        description: message,
        variant: "destructive",
      })
    } finally {
      setPendingFileName("")
      event.target.value = ""
    }
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_FILE_TYPES}
        className="sr-only"
        onChange={(event) => void handleFileChange(event)}
      />

      <Button
        variant="outline"
        size="sm"
        className="shrink-0"
        disabled={uploadBrainSkill.isPending}
        onClick={() => inputRef.current?.click()}
      >
        <Upload className="mr-2 size-4" />
        {uploadBrainSkill.isPending
          ? pendingFileName
            ? `上传 ${pendingFileName}...`
            : "上传中..."
          : "上传 Skill"}
      </Button>
    </>
  )
}
