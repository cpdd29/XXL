"use client"

import "@xyflow/react/dist/style.css"

import { type ChangeEvent, Fragment, useEffect, useMemo, useState } from "react"
import {
  Background,
  Controls,
  type Edge,
  MiniMap,
  ReactFlow,
  type Node,
  type NodeMouseHandler,
} from "@xyflow/react"
import {
  ChevronDown,
  ChevronRight,
  Database,
  FileText,
  Folder,
  FolderPlus,
  FolderOpen,
  HardDrive,
  Network,
  Pencil,
  RefreshCw,
  Save,
  Trash2,
  Upload,
} from "lucide-react"
import {
  useCreateKnowledgeVaultFolder,
  useDeleteKnowledgeVaultEntry,
  useImportKnowledgeVaultFiles,
  useKnowledgeVaults,
  useRenameKnowledgeVaultEntry,
  useScanKnowledgeVaultPreview,
  useTriggerKnowledgeVaultSync,
} from "@/modules/knowledge/hooks/use-knowledge"
import { ApiError } from "@/platform/api/errors"
import { toast } from "@/shared/hooks/use-toast"
import type {
  KnowledgeMarkdownFile,
  KnowledgeVaultRegistry,
  KnowledgeVaultScanResult,
} from "@/shared/types"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/shared/ui/dialog"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/shared/ui/empty"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import { ScrollArea } from "@/shared/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select"
import { Skeleton } from "@/shared/ui/skeleton"
import { Tabs, TabsList, TabsTrigger } from "@/shared/ui/tabs"
import { Textarea } from "@/shared/ui/textarea"
import { cn } from "@/shared/utils"

type KnowledgeSourceBucket = "internal" | "external"
type TreeNodeKind = "root" | "vault" | "folder" | "file"
type ViewMode = "document" | "graph"

type TreeNode = {
  id: string
  name: string
  kind: TreeNodeKind
  bucket: KnowledgeSourceBucket
  path: string
  vaultId: string | null
  vaultName: string | null
  file: KnowledgeMarkdownFile | null
  children: TreeNode[]
  childCount: number
}

type ParentOption = {
  value: string
  vaultId: string
  label: string
  relativePath: string
}

type UploadDraft = {
  parentValue: string
  file: File | null
}

type RenameDraft = {
  newName: string
}

type CreateFolderDraft = {
  parentValue: string
  name: string
}

type EditContentDraft = {
  content: string
}

type MarkdownBlock =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "quote"; items: string[] }
  | { type: "code"; lines: string[] }

const ROOT_IDS = {
  internal: "root:internal",
  external: "root:external",
} as const

const initialUploadDraft: UploadDraft = {
  parentValue: "",
  file: null,
}

const initialRenameDraft: RenameDraft = {
  newName: "",
}

const initialCreateFolderDraft: CreateFolderDraft = {
  parentValue: "",
  name: "",
}

const initialEditContentDraft: EditContentDraft = {
  content: "",
}

function normalizeLineBreaks(value: string) {
  return value.replace(/\r\n/g, "\n")
}

function normalizeBaseName(fileName: string) {
  const normalized = fileName.replace(/\.[^.]+$/, "").trim()
  return normalized || "untitled"
}

function normalizeMarkdownFileName(fileName: string) {
  const baseName = normalizeBaseName(fileName)
  const safeName = baseName.replace(/[\\/:*?"<>|]+/g, "-").trim() || "untitled"
  return `${safeName}.md`
}

function fileExtension(fileName: string) {
  const matched = /\.([^.]+)$/.exec(fileName)
  return matched ? `.${matched[1].toLowerCase()}` : ""
}

function normalizeNoteKey(value: string) {
  return normalizeBaseName(value).toLowerCase().trim()
}

function hashString(value: string) {
  let hash = 0
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(index)
    hash |= 0
  }
  return Math.abs(hash)
}

function extractWikiLinks(rawMarkdown: string) {
  const matches = rawMarkdown.matchAll(/\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]/g)
  const results: string[] = []
  const seen = new Set<string>()
  for (const match of matches) {
    const candidate = normalizeNoteKey(match[1] ?? "")
    if (!candidate || seen.has(candidate)) continue
    seen.add(candidate)
    results.push(candidate)
  }
  return results
}

async function toMarkdownUpload(file: File) {
  const extension = fileExtension(file.name)
  const supportedTextFile =
    extension === ".md" ||
    extension === ".markdown" ||
    extension === ".txt" ||
    file.type.startsWith("text/")

  if (!supportedTextFile) {
    throw new Error("当前仅支持上传 Markdown 或纯文本文件，后续再补复杂文档转换。")
  }

  const rawText = normalizeLineBreaks(await file.text())
  const normalizedName = normalizeMarkdownFileName(file.name)

  if (extension === ".md" || extension === ".markdown") {
    return {
      fileName: normalizedName,
      content: rawText,
    }
  }

  const title = normalizeBaseName(file.name)
  const body = rawText.trim()
  return {
    fileName: normalizedName,
    content: body ? `# ${title}\n\n${body}\n` : `# ${title}\n`,
  }
}

function formatTime(value?: string | null): string {
  if (!value) return "--"
  const timestamp = Date.parse(value)
  if (!Number.isFinite(timestamp)) return value
  return new Date(timestamp).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function sortTreeNodes(items: TreeNode[]) {
  return [...items].sort((left, right) => {
    const weight = (node: TreeNode) => {
      if (node.kind === "folder") return 0
      if (node.kind === "file") return 1
      return 0
    }
    const weightDiff = weight(left) - weight(right)
    if (weightDiff !== 0) return weightDiff
    return left.name.localeCompare(right.name, "zh-CN")
  })
}

function buildVaultNode(
  vault: KnowledgeVaultRegistry,
  bucket: KnowledgeSourceBucket,
  preview: KnowledgeVaultScanResult | null,
) {
  const rootChildren: TreeNode[] = []

  function upsertDirectory(nodes: TreeNode[], segments: string[], currentPath = "") {
    const [currentSegment, ...restSegments] = segments
    if (!currentSegment) return

    const nextPath = currentPath ? `${currentPath}/${currentSegment}` : currentSegment
    let target = nodes.find((item) => item.name === currentSegment && item.kind === "folder")
    if (!target) {
      target = {
        id: `${vault.vaultId}:${nextPath}`,
        name: currentSegment,
        kind: "folder",
        bucket,
        path: nextPath,
        vaultId: vault.vaultId,
        vaultName: vault.vaultName,
        file: null,
        children: [],
        childCount: 0,
      }
      nodes.push(target)
    }

    if (restSegments.length > 0) {
      upsertDirectory(target.children, restSegments, nextPath)
    }
  }

  function upsertPath(
    nodes: TreeNode[],
    segments: string[],
    file: KnowledgeMarkdownFile,
    currentPath = "",
  ) {
    const [currentSegment, ...restSegments] = segments
    if (!currentSegment) return

    const nextPath = currentPath ? `${currentPath}/${currentSegment}` : currentSegment
    const isLeaf = restSegments.length === 0
    const existing = nodes.find((item) => item.name === currentSegment)

    if (existing) {
      if (!isLeaf) {
        upsertPath(existing.children, restSegments, file, nextPath)
      }
      return
    }

    const nextNode: TreeNode = {
      id: `${vault.vaultId}:${nextPath}`,
      name: currentSegment,
      kind: isLeaf ? "file" : "folder",
      bucket,
      path: nextPath,
      vaultId: vault.vaultId,
      vaultName: vault.vaultName,
      file: isLeaf ? file : null,
      children: [],
      childCount: 0,
    }
    nodes.push(nextNode)

    if (!isLeaf) {
      upsertPath(nextNode.children, restSegments, file, nextPath)
    }
  }

  for (const directoryPath of preview?.directories ?? []) {
    upsertDirectory(rootChildren, directoryPath.split("/").filter(Boolean))
  }

  for (const item of preview?.items ?? []) {
    upsertPath(rootChildren, item.relativePath.split("/").filter(Boolean), item)
  }

  function hydrateChildren(items: TreeNode[]): TreeNode[] {
    return sortTreeNodes(
      items.map((item) => {
        const hydratedChildren = hydrateChildren(item.children)
        return {
          ...item,
          children: hydratedChildren,
          childCount: hydratedChildren.length,
        }
      }),
    )
  }

  const children = hydrateChildren(rootChildren)

  return {
    id: `vault:${vault.vaultId}`,
    name: vault.vaultName,
    kind: "vault" as const,
    bucket,
    path: "",
    vaultId: vault.vaultId,
    vaultName: vault.vaultName,
    file: null,
    children,
    childCount: preview?.fileCount ?? children.length,
  }
}

function buildTree(
  vaults: KnowledgeVaultRegistry[],
  previewMap: Record<string, KnowledgeVaultScanResult | null>,
) {
  const internalVaults = vaults.filter((item) => item.sourceType === "managed_fs")
  const externalVaults = vaults.filter((item) => item.sourceType !== "managed_fs")

  const internalRoot: TreeNode = {
    id: ROOT_IDS.internal,
    name: "内部知识库",
    kind: "root",
    bucket: "internal",
    path: "",
    vaultId: null,
    vaultName: null,
    file: null,
    children: sortTreeNodes(
      internalVaults.map((vault) => buildVaultNode(vault, "internal", previewMap[vault.vaultId] ?? null)),
    ),
    childCount: internalVaults.length,
  }

  const externalRoot: TreeNode = {
    id: ROOT_IDS.external,
    name: "外部知识库",
    kind: "root",
    bucket: "external",
    path: "",
    vaultId: null,
    vaultName: null,
    file: null,
    children: sortTreeNodes(
      externalVaults.map((vault) => buildVaultNode(vault, "external", previewMap[vault.vaultId] ?? null)),
    ),
    childCount: externalVaults.length,
  }

  return [internalRoot, externalRoot]
}

function flattenParentOptions(nodes: TreeNode[]) {
  const options: ParentOption[] = []

  function walk(node: TreeNode) {
    if (node.bucket !== "internal") return
    if ((node.kind === "vault" || node.kind === "folder") && node.vaultId) {
      const label = node.kind === "vault" ? `${node.name} / 根目录` : `${node.vaultName} / ${node.path}`
      options.push({
        value: `${node.vaultId}::${node.path}`,
        vaultId: node.vaultId,
        label,
        relativePath: node.path,
      })
    }
    node.children.forEach(walk)
  }

  nodes.forEach(walk)
  return options
}

function findNodeById(nodes: TreeNode[], nodeId: string | null): TreeNode | null {
  if (!nodeId) return null
  for (const node of nodes) {
    if (node.id === nodeId) return node
    const nested = findNodeById(node.children, nodeId)
    if (nested) return nested
  }
  return null
}

function findParentNode(nodes: TreeNode[], childId: string | null, parent: TreeNode | null = null): TreeNode | null {
  if (!childId) return null
  for (const node of nodes) {
    if (node.id === childId) return parent
    const nested = findParentNode(node.children, childId, node)
    if (nested) return nested
  }
  return null
}

function collectFileNodes(node: TreeNode | null): TreeNode[] {
  if (!node) return []
  if (node.kind === "file") return [node]
  return node.children.flatMap((child) => collectFileNodes(child))
}

function treeNodeIcon(node: TreeNode, expanded: boolean) {
  if (node.kind === "root") {
    return node.bucket === "internal" ? <Database className="size-4 text-primary" /> : <HardDrive className="size-4 text-muted-foreground" />
  }
  if (node.kind === "vault") return <Database className="size-4 text-primary" />
  if (node.kind === "folder") return expanded ? <FolderOpen className="size-4 text-muted-foreground" /> : <Folder className="size-4 text-muted-foreground" />
  return <FileText className="size-4 text-muted-foreground" />
}

function buildGraphData(scopeNode: TreeNode | null) {
  const fileNodes = collectFileNodes(scopeNode)
  const columns = Math.max(2, Math.ceil(Math.sqrt(Math.max(fileNodes.length, 1))))
  const nodeIndexByKey = new Map<string, string>()

  fileNodes.forEach((item) => {
    nodeIndexByKey.set(normalizeNoteKey(item.name), item.id)
  })

  const nodes: Node[] = fileNodes.map((item, index) => {
    const row = Math.floor(index / columns)
    const column = index % columns
    const hash = hashString(item.id)
    return {
      id: item.id,
      position: {
        x: column * 220 + (hash % 55) - 25,
        y: row * 160 + (hash % 45) - 20,
      },
      data: {
        label: normalizeBaseName(item.name),
      },
      draggable: true,
      style: {
        borderRadius: 14,
        border: "1px solid hsl(var(--border))",
        background: "hsl(var(--card))",
        padding: "10px 14px",
        color: "hsl(var(--foreground))",
        fontSize: 13,
        boxShadow: "0 12px 30px rgba(15, 23, 42, 0.08)",
      },
    }
  })

  const edges: Edge[] = []
  const seenEdgeIds = new Set<string>()

  for (const item of fileNodes) {
    const links = extractWikiLinks(item.file?.rawMarkdown ?? "")
    for (const link of links) {
      const targetId = nodeIndexByKey.get(link)
      if (!targetId || targetId === item.id) continue
      const edgeId = `${item.id}::${targetId}`
      const reverseEdgeId = `${targetId}::${item.id}`
      if (seenEdgeIds.has(edgeId) || seenEdgeIds.has(reverseEdgeId)) continue
      seenEdgeIds.add(edgeId)
      edges.push({
        id: edgeId,
        source: item.id,
        target: targetId,
        animated: false,
        style: {
          stroke: "rgba(100, 116, 139, 0.42)",
          strokeWidth: 1.35,
        },
      })
    }
  }

  return { nodes, edges, fileCount: fileNodes.length }
}

function parseMarkdownBlocks(rawMarkdown: string) {
  const lines = normalizeLineBreaks(rawMarkdown).split("\n")
  const blocks: MarkdownBlock[] = []
  let paragraphBuffer: string[] = []
  let listBuffer: string[] = []
  let listOrdered = false
  let quoteBuffer: string[] = []
  let codeBuffer: string[] = []
  let inCodeBlock = false

  function flushParagraph() {
    if (paragraphBuffer.length === 0) return
    blocks.push({
      type: "paragraph",
      text: paragraphBuffer.join(" "),
    })
    paragraphBuffer = []
  }

  function flushList() {
    if (listBuffer.length === 0) return
    blocks.push({
      type: "list",
      ordered: listOrdered,
      items: [...listBuffer],
    })
    listBuffer = []
    listOrdered = false
  }

  function flushQuote() {
    if (quoteBuffer.length === 0) return
    blocks.push({
      type: "quote",
      items: [...quoteBuffer],
    })
    quoteBuffer = []
  }

  function flushCode() {
    if (codeBuffer.length === 0) return
    blocks.push({
      type: "code",
      lines: [...codeBuffer],
    })
    codeBuffer = []
  }

  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      flushParagraph()
      flushList()
      flushQuote()
      if (inCodeBlock) {
        flushCode()
        inCodeBlock = false
      } else {
        inCodeBlock = true
      }
      continue
    }

    if (inCodeBlock) {
      codeBuffer.push(line)
      continue
    }

    if (!line.trim()) {
      flushParagraph()
      flushList()
      flushQuote()
      continue
    }

    const headingMatch = /^(#{1,6})\s+(.+)$/.exec(line)
    if (headingMatch) {
      flushParagraph()
      flushList()
      flushQuote()
      blocks.push({
        type: "heading",
        level: headingMatch[1].length,
        text: headingMatch[2].trim(),
      })
      continue
    }

    const quoteMatch = /^>\s?(.*)$/.exec(line)
    if (quoteMatch) {
      flushParagraph()
      flushList()
      quoteBuffer.push(quoteMatch[1])
      continue
    }

    const orderedListMatch = /^\d+\.\s+(.+)$/.exec(line)
    if (orderedListMatch) {
      flushParagraph()
      flushQuote()
      if (listBuffer.length === 0) {
        listOrdered = true
      }
      listBuffer.push(orderedListMatch[1])
      continue
    }

    const unorderedListMatch = /^[-*]\s+(.+)$/.exec(line)
    if (unorderedListMatch) {
      flushParagraph()
      flushQuote()
      if (listBuffer.length === 0) {
        listOrdered = false
      }
      listBuffer.push(unorderedListMatch[1])
      continue
    }

    paragraphBuffer.push(line.trim())
  }

  flushParagraph()
  flushList()
  flushQuote()
  flushCode()

  return blocks
}

function renderInlineText(text: string) {
  const tokens = text.split(/(\[\[[^\]]+\]\]|\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean)
  return tokens.map((token, index) => {
    if (token.startsWith("[[") && token.endsWith("]]")) {
      return (
        <span
          key={`${token}-${index}`}
          className="rounded-md bg-primary/10 px-1.5 py-0.5 text-primary"
        >
          {token.slice(2, -2)}
        </span>
      )
    }
    if (token.startsWith("**") && token.endsWith("**")) {
      return (
        <strong key={`${token}-${index}`} className="font-semibold text-foreground">
          {token.slice(2, -2)}
        </strong>
      )
    }
    if (token.startsWith("`") && token.endsWith("`")) {
      return (
        <code
          key={`${token}-${index}`}
          className="rounded-md bg-muted px-1.5 py-0.5 text-[0.92em] text-foreground"
        >
          {token.slice(1, -1)}
        </code>
      )
    }
    return <Fragment key={`${token}-${index}`}>{token}</Fragment>
  })
}

function MarkdownPreview({ rawMarkdown }: { rawMarkdown: string }) {
  const blocks = useMemo(() => parseMarkdownBlocks(rawMarkdown), [rawMarkdown])

  return (
    <div className="space-y-5 text-[15px] leading-7 text-foreground">
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          const headingClassMap: Record<number, string> = {
            1: "text-3xl font-semibold tracking-tight text-foreground",
            2: "text-2xl font-semibold text-foreground",
            3: "text-xl font-semibold text-foreground",
            4: "text-lg font-semibold text-foreground",
            5: "text-base font-semibold text-foreground",
            6: "text-sm font-semibold uppercase tracking-[0.18em] text-muted-foreground",
          }
          return (
            <div key={`heading-${index}`} className={headingClassMap[block.level] ?? headingClassMap[3]}>
              {renderInlineText(block.text)}
            </div>
          )
        }

        if (block.type === "paragraph") {
          return (
            <p key={`paragraph-${index}`} className="text-foreground">
              {renderInlineText(block.text)}
            </p>
          )
        }

        if (block.type === "list") {
          const ListTag = block.ordered ? "ol" : "ul"
          return (
            <ListTag
              key={`list-${index}`}
              className={cn(
                "space-y-2 pl-5 text-foreground",
                block.ordered ? "list-decimal" : "list-disc",
              )}
            >
              {block.items.map((item, itemIndex) => (
                <li key={`item-${itemIndex}`}>{renderInlineText(item)}</li>
              ))}
            </ListTag>
          )
        }

        if (block.type === "quote") {
          return (
            <blockquote
              key={`quote-${index}`}
              className="border-l-2 border-border pl-4 text-muted-foreground"
            >
              {block.items.map((item, itemIndex) => (
                <p key={`quote-item-${itemIndex}`}>{renderInlineText(item)}</p>
              ))}
            </blockquote>
          )
        }

        return (
          <pre
            key={`code-${index}`}
            className="overflow-x-auto rounded-xl border border-border bg-muted/90 px-4 py-3 text-sm leading-6 text-foreground"
          >
            {block.lines.join("\n")}
          </pre>
        )
      })}
    </div>
  )
}

function TreeBranch({
  nodes,
  expandedNodeIds,
  selectedNodeId,
  onToggle,
  onSelect,
  depth = 0,
}: {
  nodes: TreeNode[]
  expandedNodeIds: Set<string>
  selectedNodeId: string | null
  onToggle: (nodeId: string) => void
  onSelect: (nodeId: string) => void
  depth?: number
}) {
  return (
    <div className="space-y-0.5">
      {nodes.map((node) => {
        const expanded = expandedNodeIds.has(node.id)
        const selected = selectedNodeId === node.id
        const hasChildren = node.children.length > 0
        return (
          <div key={node.id}>
            <button
              type="button"
              onClick={() => {
                onSelect(node.id)
                if (hasChildren) onToggle(node.id)
              }}
              className={cn(
                "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-foreground transition-colors hover:bg-muted/70",
                selected && "bg-muted text-foreground",
              )}
              style={{ paddingLeft: `${depth * 14 + 12}px` }}
            >
              {hasChildren ? (
                expanded ? (
                  <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
                ) : (
                  <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                )
              ) : (
                <span className="block w-4 shrink-0" />
              )}
              {treeNodeIcon(node, expanded)}
              <span className="min-w-0 flex-1 truncate">{node.name}</span>
              {node.kind !== "file" ? (
                <span className="text-[11px] text-muted-foreground">{node.childCount}</span>
              ) : null}
            </button>
            {hasChildren && expanded ? (
              <TreeBranch
                nodes={node.children}
                expandedNodeIds={expandedNodeIds}
                selectedNodeId={selectedNodeId}
                onToggle={onToggle}
                onSelect={onSelect}
                depth={depth + 1}
              />
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

export default function KnowledgeCapabilityPage() {
  const vaultsQuery = useKnowledgeVaults()
  const scanPreviewMutation = useScanKnowledgeVaultPreview()
  const importFilesMutation = useImportKnowledgeVaultFiles()
  const updateFileMutation = useImportKnowledgeVaultFiles()
  const syncVaultMutation = useTriggerKnowledgeVaultSync()
  const createFolderMutation = useCreateKnowledgeVaultFolder()
  const renameEntryMutation = useRenameKnowledgeVaultEntry()
  const deleteEntryMutation = useDeleteKnowledgeVaultEntry()

  const [previewMap, setPreviewMap] = useState<Record<string, KnowledgeVaultScanResult | null>>({})
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(
    new Set([ROOT_IDS.internal, ROOT_IDS.external]),
  )
  const [loadingTree, setLoadingTree] = useState(false)
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false)
  const [uploadDraft, setUploadDraft] = useState<UploadDraft>(initialUploadDraft)
  const [createFolderDialogOpen, setCreateFolderDialogOpen] = useState(false)
  const [createFolderDraft, setCreateFolderDraft] = useState<CreateFolderDraft>(initialCreateFolderDraft)
  const [renameDialogOpen, setRenameDialogOpen] = useState(false)
  const [renameDraft, setRenameDraft] = useState<RenameDraft>(initialRenameDraft)
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [editContentDraft, setEditContentDraft] = useState<EditContentDraft>(initialEditContentDraft)
  const [viewMode, setViewMode] = useState<ViewMode>("graph")

  const vaults = useMemo(() => vaultsQuery.data?.items ?? [], [vaultsQuery.data?.items])
  const treeRoots = useMemo(() => buildTree(vaults, previewMap), [vaults, previewMap])
  const parentOptions = useMemo(() => flattenParentOptions(treeRoots), [treeRoots])
  const selectedNode = useMemo(() => findNodeById(treeRoots, selectedNodeId), [treeRoots, selectedNodeId])
  const selectedParentNode = useMemo(
    () => findParentNode(treeRoots, selectedNodeId),
    [treeRoots, selectedNodeId],
  )
  const selectedFileNode = selectedNode?.kind === "file" ? selectedNode : null
  const selectedManagedNode =
    selectedNode &&
    selectedNode.bucket === "internal" &&
    selectedNode.vaultId &&
    selectedNode.kind !== "root" &&
    selectedNode.kind !== "vault"
      ? selectedNode
      : null
  const selectedEditableFileNode =
    selectedFileNode &&
    selectedFileNode.bucket === "internal" &&
    selectedFileNode.vaultId
      ? selectedFileNode
      : null
  const canRenameSelectedNode = Boolean(selectedManagedNode)
  const canDeleteSelectedNode = Boolean(selectedManagedNode)
  const graphScopeNode = useMemo(() => {
    if (!selectedNode) return treeRoots[0] ?? null
    if (selectedNode.kind === "file") return selectedParentNode ?? selectedNode
    return selectedNode
  }, [selectedNode, selectedParentNode, treeRoots])
  const graphData = useMemo(() => buildGraphData(graphScopeNode), [graphScopeNode])
  const activeScopeLabel = useMemo(() => {
    if (!graphScopeNode) return "知识图谱"
    if (graphScopeNode.kind === "root") return graphScopeNode.name
    if (graphScopeNode.kind === "vault") return graphScopeNode.vaultName ?? graphScopeNode.name
    return graphScopeNode.path || graphScopeNode.name
  }, [graphScopeNode])

  function expandNodePath(vaultId: string, relativePath: string) {
    setExpandedNodeIds((current) => {
      const next = new Set(current)
      next.add(ROOT_IDS.internal)
      next.add(`vault:${vaultId}`)
      let currentPath = ""
      for (const segment of relativePath.split("/").slice(0, -1)) {
        currentPath = currentPath ? `${currentPath}/${segment}` : segment
        next.add(`${vaultId}:${currentPath}`)
      }
      return next
    })
  }

  async function refreshAllTrees() {
    if (vaults.length === 0) {
      setPreviewMap({})
      return
    }

    setLoadingTree(true)
    try {
      const failedVaults: string[] = []
      const results = await Promise.all(
        vaults.map(async (vault) => {
          try {
            const preview = await scanPreviewMutation.mutateAsync({
              vaultId: vault.vaultId,
              limit: 200,
            })
            return [vault.vaultId, preview] as const
          } catch {
            failedVaults.push(vault.vaultName)
            return [vault.vaultId, null] as const
          }
        }),
      )
      setPreviewMap(Object.fromEntries(results))
      if (failedVaults.length > 0) {
        const failedLabel =
          failedVaults.length > 3
            ? `${failedVaults.slice(0, 3).join("、")} 等 ${failedVaults.length} 个知识仓`
            : failedVaults.join("、")
        toast({
          title: "部分知识库加载失败",
          description: `${failedLabel} 的目录预览未能完成，请检查知识仓路径或稍后重试。`,
          variant: "destructive",
        })
      }
    } finally {
      setLoadingTree(false)
    }
  }

  useEffect(() => {
    void refreshAllTrees()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vaults.map((item) => item.vaultId).join("|")])

  useEffect(() => {
    if (!selectedNodeId) {
      setSelectedNodeId(ROOT_IDS.internal)
      return
    }
    if (!findNodeById(treeRoots, selectedNodeId)) {
      setSelectedNodeId(ROOT_IDS.internal)
    }
  }, [selectedNodeId, treeRoots])

  function toggleNode(nodeId: string) {
    setExpandedNodeIds((current) => {
      const next = new Set(current)
      if (next.has(nodeId)) next.delete(nodeId)
      else next.add(nodeId)
      return next
    })
  }

  function preferredParentValueForSelection() {
    if (selectedNode?.bucket === "internal" && selectedNode.vaultId) {
      return `${selectedNode.vaultId}::${
        selectedNode.kind === "folder"
          ? selectedNode.path
          : selectedNode.kind === "vault"
            ? ""
            : selectedParentNode?.path ?? ""
      }`
    }
    return parentOptions[0]?.value ?? ""
  }

  function openUploadDialog() {
    if (parentOptions.length === 0) {
      toast({
        title: "暂无可上传的内部知识库",
        description: "请先在“知识库管理”里创建平台托管知识仓。",
        variant: "destructive",
      })
      return
    }

    setUploadDraft({
      parentValue: preferredParentValueForSelection(),
      file: null,
    })
    setUploadDialogOpen(true)
  }

  function openCreateFolderDialog() {
    if (parentOptions.length === 0) {
      toast({
        title: "暂无可创建目录的内部知识库",
        description: "请先在“知识库管理”里创建平台托管知识仓。",
        variant: "destructive",
      })
      return
    }
    setCreateFolderDraft({
      parentValue: preferredParentValueForSelection(),
      name: "",
    })
    setCreateFolderDialogOpen(true)
  }

  async function handleUpload() {
    const selectedParent = parentOptions.find((item) => item.value === uploadDraft.parentValue)
    if (!selectedParent || !uploadDraft.file) {
      toast({
        title: "请先补全上传信息",
        description: "父节点和上传文件都需要填写。",
        variant: "destructive",
      })
      return
    }

    try {
      const markdownFile = await toMarkdownUpload(uploadDraft.file)
      const relativeName = selectedParent.relativePath
        ? `${selectedParent.relativePath}/${markdownFile.fileName}`
        : markdownFile.fileName

      const importResponse = await importFilesMutation.mutateAsync({
        vaultId: selectedParent.vaultId,
        payload: {
          files: [
            {
              fileName: relativeName,
              content: markdownFile.content,
            },
          ],
        },
      })

      await syncVaultMutation.mutateAsync({ vaultId: selectedParent.vaultId })
      await refreshAllTrees()

      setUploadDialogOpen(false)
      setUploadDraft(initialUploadDraft)
      setSelectedNodeId(`${selectedParent.vaultId}:${relativeName}`)
      expandNodePath(selectedParent.vaultId, relativeName)
      setViewMode("document")

      toast({
        title: "上传成功",
        description: `${importResponse.totalFiles} 个文件已转换为 Markdown 并写入内部知识库。`,
      })
    } catch (error) {
      const description =
        error instanceof ApiError || error instanceof Error ? error.message : "知识文档上传失败。"
      toast({
        title: "上传失败",
        description,
        variant: "destructive",
      })
    }
  }

  async function handleCreateFolder() {
    const selectedParent = parentOptions.find((item) => item.value === createFolderDraft.parentValue)
    if (!selectedParent || !createFolderDraft.name.trim()) {
      toast({
        title: "请先补全目录信息",
        description: "父节点和目录名称都需要填写。",
        variant: "destructive",
      })
      return
    }

    try {
      const response = await createFolderMutation.mutateAsync({
        vaultId: selectedParent.vaultId,
        payload: {
          parentPath: selectedParent.relativePath || null,
          name: createFolderDraft.name.trim(),
        },
      })
      await refreshAllTrees()
      if (response.nextPath) {
        setSelectedNodeId(`${selectedParent.vaultId}:${response.nextPath}`)
        expandNodePath(selectedParent.vaultId, response.nextPath)
      }
      setCreateFolderDialogOpen(false)
      setCreateFolderDraft(initialCreateFolderDraft)
      toast({
        title: "目录创建成功",
        description: response.message,
      })
    } catch (error) {
      toast({
        title: "目录创建失败",
        description: error instanceof Error ? error.message : "知识目录创建失败。",
        variant: "destructive",
      })
    }
  }

  function openRenameDialog() {
    if (!selectedManagedNode) {
      toast({
        title: "当前节点不可重命名",
        description: "请选择内部知识库中的文件或目录节点。",
        variant: "destructive",
      })
      return
    }
    setRenameDraft({ newName: selectedManagedNode.name })
    setRenameDialogOpen(true)
  }

  function openEditDialog() {
    if (!selectedEditableFileNode?.file || !selectedEditableFileNode.vaultId) {
      toast({
        title: "当前文件不可编辑",
        description: "请选择内部知识库中的 Markdown 文件。",
        variant: "destructive",
      })
      return
    }
    setEditContentDraft({
      content: selectedEditableFileNode.file.rawMarkdown,
    })
    setEditDialogOpen(true)
  }

  async function handleRenameEntry() {
    if (!selectedManagedNode?.vaultId) return
    if (!renameDraft.newName.trim()) {
      toast({
        title: "请填写新的节点名称",
        variant: "destructive",
      })
      return
    }

    try {
      const response = await renameEntryMutation.mutateAsync({
        vaultId: selectedManagedNode.vaultId,
        payload: {
          path: selectedManagedNode.path,
          newName: renameDraft.newName.trim(),
        },
      })
      await refreshAllTrees()
      if (response.nextPath) {
        setSelectedNodeId(`${selectedManagedNode.vaultId}:${response.nextPath}`)
        expandNodePath(selectedManagedNode.vaultId, response.nextPath)
      }
      setRenameDialogOpen(false)
      setRenameDraft(initialRenameDraft)
      toast({
        title: "重命名成功",
        description: response.message,
      })
    } catch (error) {
      toast({
        title: "重命名失败",
        description: error instanceof Error ? error.message : "知识节点重命名失败。",
        variant: "destructive",
      })
    }
  }

  async function handleDeleteEntry() {
    if (!selectedManagedNode?.vaultId) {
      toast({
        title: "当前节点不可删除",
        description: "请选择内部知识库中的文件或目录节点。",
        variant: "destructive",
      })
      return
    }
    const confirmed = window.confirm(`确认删除「${selectedManagedNode.name}」吗？`)
    if (!confirmed) return

    try {
      const nextSelectedNodeId =
        selectedParentNode?.id && selectedParentNode.kind !== "root"
          ? selectedParentNode.id
          : `vault:${selectedManagedNode.vaultId}`
      const response = await deleteEntryMutation.mutateAsync({
        vaultId: selectedManagedNode.vaultId,
        payload: {
          path: selectedManagedNode.path,
        },
      })
      await refreshAllTrees()
      setSelectedNodeId(nextSelectedNodeId)
      toast({
        title: "删除成功",
        description: response.message,
      })
    } catch (error) {
      toast({
        title: "删除失败",
        description: error instanceof Error ? error.message : "知识节点删除失败。",
        variant: "destructive",
      })
    }
  }

  async function handleSaveFileContent() {
    if (!selectedEditableFileNode?.vaultId || !selectedEditableFileNode.path) {
      toast({
        title: "当前文件不可保存",
        description: "请选择内部知识库中的 Markdown 文件。",
        variant: "destructive",
      })
      return
    }

    try {
      await updateFileMutation.mutateAsync({
        vaultId: selectedEditableFileNode.vaultId,
        payload: {
          files: [
            {
              fileName: selectedEditableFileNode.path,
              content: editContentDraft.content,
            },
          ],
        },
      })
      await syncVaultMutation.mutateAsync({ vaultId: selectedEditableFileNode.vaultId })
      await refreshAllTrees()
      setSelectedNodeId(`${selectedEditableFileNode.vaultId}:${selectedEditableFileNode.path}`)
      expandNodePath(selectedEditableFileNode.vaultId, selectedEditableFileNode.path)
      setEditDialogOpen(false)
      setViewMode("document")
      toast({
        title: "文件内容已保存",
        description: "Markdown 正文已更新并同步到知识库索引。",
      })
    } catch (error) {
      toast({
        title: "保存失败",
        description: error instanceof Error ? error.message : "Markdown 内容保存失败。",
        variant: "destructive",
      })
    }
  }

  const handleGraphNodeClick: NodeMouseHandler = (_, node) => {
    setSelectedNodeId(node.id)
  }

  const internalVaultCount = vaults.filter((item) => item.sourceType === "managed_fs").length
  const externalVaultCount = vaults.filter((item) => item.sourceType !== "managed_fs").length

  return (
    <div className="flex min-h-0 flex-1 overflow-hidden bg-background">
      <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-hidden p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">知识库</h1>
            <p className="text-sm text-muted-foreground">
              保留文件目录、文档展示和关系图谱，统一查看内部知识库与外部知识库内容。
            </p>
          </div>
        </div>

        <div className="grid min-h-0 flex-1 gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
          <Card className="flex min-h-0 flex-col overflow-hidden">
            <CardHeader className="gap-4 border-b border-border/70">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="secondary">内部 {internalVaultCount}</Badge>
                  <Badge variant="outline">外部 {externalVaultCount}</Badge>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="outline" size="sm" onClick={() => void refreshAllTrees()} disabled={loadingTree}>
                    <RefreshCw className={cn("size-4", loadingTree && "animate-spin")} />
                    刷新
                  </Button>
                  <Button variant="outline" size="sm" onClick={openCreateFolderDialog}>
                    <FolderPlus className="size-4" />
                    新建目录
                  </Button>
                  <Button size="sm" onClick={openUploadDialog}>
                    <Upload className="size-4" />
                    新增文档
                  </Button>
                  <Button variant="outline" size="sm" onClick={openRenameDialog} disabled={!canRenameSelectedNode}>
                    <Pencil className="size-4" />
                    重命名
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void handleDeleteEntry()}
                    disabled={!canDeleteSelectedNode}
                  >
                    <Trash2 className="size-4" />
                    删除
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 p-0">
              {vaultsQuery.isLoading || loadingTree ? (
                <div className="space-y-3 p-4">
                  {Array.from({ length: 8 }).map((_, index) => (
                    <Skeleton key={index} className="h-10 w-full rounded-lg" />
                  ))}
                </div>
              ) : vaults.length === 0 ? (
                <div className="p-4">
                  <Empty className="min-h-[420px] border border-dashed border-border/70 bg-muted/10">
                    <EmptyHeader>
                      <EmptyMedia variant="icon">
                        <Database />
                      </EmptyMedia>
                      <EmptyTitle>还没有知识库节点</EmptyTitle>
                      <EmptyDescription>先到组织设置里的“知识库管理”创建内部或外部知识仓。</EmptyDescription>
                    </EmptyHeader>
                  </Empty>
                </div>
              ) : (
                <ScrollArea className="h-full">
                  <div className="p-3">
                    <TreeBranch
                      nodes={treeRoots}
                      expandedNodeIds={expandedNodeIds}
                      selectedNodeId={selectedNodeId}
                      onToggle={toggleNode}
                      onSelect={setSelectedNodeId}
                    />
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>

          <Card className="flex min-h-0 min-w-0 flex-col overflow-hidden">
            <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-4 border-b border-border/70">
              <div className="min-w-0 space-y-1">
                <CardTitle className="truncate text-base">
                  {viewMode === "graph"
                    ? "关系图谱"
                    : selectedFileNode
                      ? normalizeBaseName(selectedFileNode.name)
                      : "文件展示"}
                </CardTitle>
                <CardDescription className="truncate">
                  {viewMode === "graph"
                    ? `${activeScopeLabel} · ${graphData.fileCount} 个节点`
                    : selectedFileNode?.path || "选择一个 Markdown 文件查看内容"}
                </CardDescription>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {viewMode === "document" && selectedEditableFileNode ? (
                  <Button variant="outline" size="sm" onClick={openEditDialog}>
                    <Pencil className="size-4" />
                    编辑正文
                  </Button>
                ) : null}
                <Tabs value={viewMode} onValueChange={(value) => setViewMode(value as ViewMode)} className="gap-0">
                  <TabsList>
                    <TabsTrigger value="document">文件展示</TabsTrigger>
                    <TabsTrigger value="graph">关系图谱</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 overflow-hidden p-0">
              {viewMode === "document" ? (
                selectedFileNode?.file ? (
                  <ScrollArea className="h-full">
                    <div className="mx-auto w-full max-w-4xl p-6">
                      <div className="rounded-xl border border-border/70 bg-card px-8 py-8">
                        <div className="mb-8 flex flex-wrap items-start justify-between gap-4 border-b border-border/70 pb-6">
                          <div className="min-w-0">
                            <div className="text-xs font-medium tracking-[0.24em] text-muted-foreground uppercase">
                              Markdown 文档
                            </div>
                            <div className="mt-3 break-words text-3xl font-semibold tracking-tight text-foreground">
                              {normalizeBaseName(selectedFileNode.name)}
                            </div>
                            <div className="mt-2 break-all text-sm text-muted-foreground">
                              {selectedFileNode.path}
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <Badge variant="secondary">MD 文件</Badge>
                            <Badge variant="outline">
                              {selectedFileNode.bucket === "internal" ? "内部知识库" : "外部知识库"}
                            </Badge>
                            {selectedEditableFileNode ? <Badge variant="outline">支持正文编辑</Badge> : null}
                            <Badge variant="outline">更新于 {formatTime(selectedFileNode.file.updatedAt)}</Badge>
                          </div>
                        </div>
                        <MarkdownPreview rawMarkdown={selectedFileNode.file.rawMarkdown} />
                      </div>
                    </div>
                  </ScrollArea>
                ) : (
                  <div className="flex h-full items-center justify-center p-6">
                    <Empty className="min-h-[360px] w-full max-w-2xl border border-dashed border-border/70 bg-muted/10">
                      <EmptyHeader>
                        <EmptyMedia variant="icon">
                          <FileText />
                        </EmptyMedia>
                        <EmptyTitle>请选择 Markdown 文件</EmptyTitle>
                        <EmptyDescription>左侧目录选中具体文件后，这里会展示对应文档内容。</EmptyDescription>
                      </EmptyHeader>
                    </Empty>
                  </div>
                )
              ) : graphData.fileCount === 0 ? (
                <div className="flex h-full items-center justify-center p-6">
                  <Empty className="min-h-[360px] w-full max-w-2xl border border-dashed border-border/70 bg-muted/10">
                    <EmptyHeader>
                      <EmptyMedia variant="icon">
                        <Network />
                      </EmptyMedia>
                      <EmptyTitle>当前分支没有可绘制节点</EmptyTitle>
                      <EmptyDescription>选择一个包含 Markdown 文件的知识库、目录或笔记后，这里会展示关系图谱。</EmptyDescription>
                    </EmptyHeader>
                  </Empty>
                </div>
              ) : (
                <div className="h-full bg-muted/10">
                  <ReactFlow
                    nodes={graphData.nodes}
                    edges={graphData.edges}
                    onNodeClick={handleGraphNodeClick}
                    fitView
                    fitViewOptions={{ padding: 0.25 }}
                    proOptions={{ hideAttribution: true }}
                    minZoom={0.3}
                    maxZoom={1.8}
                    nodesDraggable
                    nodesConnectable={false}
                    elementsSelectable
                  >
                    <MiniMap
                      pannable
                      zoomable
                      maskColor="rgba(15, 23, 42, 0.08)"
                      nodeColor="hsl(var(--muted-foreground))"
                      style={{
                        background: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: 12,
                      }}
                    />
                    <Controls
                      showInteractive={false}
                      style={{
                        borderRadius: 12,
                        overflow: "hidden",
                        boxShadow: "0 10px 28px rgba(15, 23, 42, 0.08)",
                      }}
                    />
                    <Background gap={18} size={1} color="rgba(148, 163, 184, 0.28)" />
                  </ReactFlow>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <Dialog open={uploadDialogOpen} onOpenChange={setUploadDialogOpen}>
          <DialogContent className="sm:max-w-xl">
            <DialogHeader>
              <DialogTitle>上传文档到内部知识库</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="rounded-lg border border-border/70 bg-muted/20 px-4 py-4 text-sm text-muted-foreground">
                Obsidian 的笔记核心是 vault 文件夹中的 Markdown 文件。当前上传会把文本类文件统一转换为
                `.md` 后写入内部知识库。
              </div>

              <div className="space-y-2">
                <Label>
                  父节点 <span className="text-destructive">*</span>
                </Label>
                <Select
                  value={uploadDraft.parentValue}
                  onValueChange={(value) => setUploadDraft((current) => ({ ...current, parentValue: value }))}
                >
                  <SelectTrigger className="h-11">
                    <SelectValue placeholder="请选择内部知识库父节点" />
                  </SelectTrigger>
                  <SelectContent>
                    {parentOptions.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="knowledge-upload-file">
                  上传文件 <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="knowledge-upload-file"
                  type="file"
                  accept=".md,.markdown,.txt,text/plain,text/markdown"
                  className="h-11"
                  onChange={(event: ChangeEvent<HTMLInputElement>) =>
                    setUploadDraft((current) => ({
                      ...current,
                      file: event.target.files?.[0] ?? null,
                    }))
                  }
                />
                <div className="text-xs text-muted-foreground">
                  当前支持 `.md`、`.markdown`、`.txt` 以及浏览器可直接读取的纯文本文件。
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setUploadDialogOpen(false)}>
                取消
              </Button>
              <Button
                onClick={() => void handleUpload()}
                disabled={importFilesMutation.isPending || syncVaultMutation.isPending}
              >
                {importFilesMutation.isPending || syncVaultMutation.isPending ? "上传中..." : "保存"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={createFolderDialogOpen} onOpenChange={setCreateFolderDialogOpen}>
          <DialogContent className="sm:max-w-lg">
            <DialogHeader>
              <DialogTitle>新建知识目录</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>
                  父节点 <span className="text-destructive">*</span>
                </Label>
                <Select
                  value={createFolderDraft.parentValue}
                  onValueChange={(value) => setCreateFolderDraft((current) => ({ ...current, parentValue: value }))}
                >
                  <SelectTrigger className="h-11">
                    <SelectValue placeholder="请选择目录挂载位置" />
                  </SelectTrigger>
                  <SelectContent>
                    {parentOptions.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="knowledge-folder-name">
                  目录名称 <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="knowledge-folder-name"
                  value={createFolderDraft.name}
                  onChange={(event) =>
                    setCreateFolderDraft((current) => ({
                      ...current,
                      name: event.target.value,
                    }))
                  }
                  placeholder="请输入目录名称"
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setCreateFolderDialogOpen(false)}>
                取消
              </Button>
              <Button onClick={() => void handleCreateFolder()} disabled={createFolderMutation.isPending}>
                {createFolderMutation.isPending ? "创建中..." : "保存"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={renameDialogOpen} onOpenChange={setRenameDialogOpen}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>重命名知识节点</DialogTitle>
            </DialogHeader>
            <div className="space-y-2">
              <Label htmlFor="knowledge-rename-name">
                新名称 <span className="text-destructive">*</span>
              </Label>
              <Input
                id="knowledge-rename-name"
                value={renameDraft.newName}
                onChange={(event) => setRenameDraft({ newName: event.target.value })}
                placeholder="请输入新的文件名或目录名"
              />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setRenameDialogOpen(false)}>
                取消
              </Button>
              <Button onClick={() => void handleRenameEntry()} disabled={renameEntryMutation.isPending}>
                {renameEntryMutation.isPending ? "保存中..." : "保存"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
          <DialogContent className="sm:max-w-4xl">
            <DialogHeader>
              <DialogTitle>编辑 Markdown 正文</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="rounded-lg border border-border/70 bg-muted/15 px-4 py-3 text-sm text-muted-foreground">
                当前文件：{selectedEditableFileNode?.path || "--"}
              </div>
              <div className="space-y-2">
                <Label htmlFor="knowledge-edit-content">
                  正文内容 <span className="text-destructive">*</span>
                </Label>
                <Textarea
                  id="knowledge-edit-content"
                  value={editContentDraft.content}
                  onChange={(event) => setEditContentDraft({ content: event.target.value })}
                  className="min-h-[420px] resize-y font-mono text-sm leading-6"
                  placeholder="请输入 Markdown 内容"
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditDialogOpen(false)}>
                取消
              </Button>
              <Button
                onClick={() => void handleSaveFileContent()}
                disabled={updateFileMutation.isPending || syncVaultMutation.isPending}
              >
                <Save className="size-4" />
                {updateFileMutation.isPending || syncVaultMutation.isPending ? "保存中..." : "保存正文"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}
