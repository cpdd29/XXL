"use client"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import type { Agent, Workflow, WorkflowTrigger } from "@/types"
import type { EditableWorkflowNode, WorkflowEditorMeta } from "./workflow-inspector"
import {
  getWorkflowTriggerFieldMeta,
  getWorkflowTriggerOptions,
  getWorkflowTriggerValue,
  nextWorkflowTriggerByType,
  patchWorkflowTriggerValue,
} from "./workflow-trigger-config"

interface WorkflowNodeConfigDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  selectedNode?: EditableWorkflowNode
  workflowMeta: WorkflowEditorMeta
  agents: Agent[]
  workflows: Workflow[]
  canEditConfiguration: boolean
  onTriggerChange: (trigger: WorkflowTrigger) => void
  onNodeLabelChange: (label: string) => void
  onNodeDescriptionChange: (description: string) => void
  onNodeAgentChange: (agentId?: string) => void
  onNodeWorkflowChange: (workflowId?: string) => void
  onNodeConfigChange: (key: string, value?: string | null) => void
}

const nodeTypeLabels: Record<string, string> = {
  trigger: "触发节点",
  agent: "Agent 节点",
  condition: "条件节点",
  parallel: "并行节点",
  merge: "合流节点",
  workflow: "子工作流节点",
  tool: "历史工具节点",
  transform: "转换节点",
  output: "输出节点",
  aggregate: "聚合节点",
}

function getNodeConfigValue(node: EditableWorkflowNode | undefined, key: string) {
  const value = node?.config?.[key]
  if (value === null || value === undefined) return ""
  return String(value)
}

function NodeSection({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-3 rounded-xl border border-border bg-card/60 p-4">
      <div className="text-sm font-medium text-foreground">{title}</div>
      {children}
    </div>
  )
}

export function WorkflowNodeConfigDialog({
  open,
  onOpenChange,
  selectedNode,
  workflowMeta,
  agents,
  workflows,
  canEditConfiguration,
  onTriggerChange,
  onNodeLabelChange,
  onNodeDescriptionChange,
  onNodeAgentChange,
  onNodeWorkflowChange,
  onNodeConfigChange,
}: WorkflowNodeConfigDialogProps) {
  const nodeType = selectedNode?.type ?? "agent"
  const triggerFieldMeta = getWorkflowTriggerFieldMeta(workflowMeta.trigger.type)
  const triggerTypeOptions = getWorkflowTriggerOptions(workflowMeta.trigger.type)

  return (
    <Dialog open={open && Boolean(selectedNode)} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] gap-0 overflow-hidden p-0 sm:max-w-3xl">
        <DialogHeader className="border-b border-border px-6 py-5 pr-12">
          <div className="flex items-center gap-3">
            <DialogTitle className="text-base">
              {selectedNode ? `配置 ${selectedNode.label}` : "节点配置"}
            </DialogTitle>
            {selectedNode ? <Badge variant="secondary">{nodeTypeLabels[nodeType] ?? nodeType}</Badge> : null}
          </div>
        </DialogHeader>

        {selectedNode ? (
          <>
            <ScrollArea className="max-h-[calc(85vh-132px)]">
              <div className="space-y-4 p-6">
                <NodeSection title="基础信息">
                  <div className="space-y-3">
                    <div className="space-y-2">
                      <div className="text-xs text-muted-foreground">节点名称</div>
                      <Input
                        value={selectedNode.label}
                        disabled={!canEditConfiguration}
                        onChange={(event) => onNodeLabelChange(event.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <div className="text-xs text-muted-foreground">节点说明</div>
                      <Textarea
                        rows={3}
                        value={selectedNode.description ?? ""}
                        disabled={!canEditConfiguration}
                        placeholder="补充这个节点负责什么、输入输出是什么"
                        onChange={(event) => onNodeDescriptionChange(event.target.value)}
                      />
                    </div>
                  </div>
                </NodeSection>

                {nodeType === "trigger" ? (
                  <NodeSection title="触发条件">
                    <div className="space-y-3">
                      <div className="space-y-2">
                        <div className="text-xs text-muted-foreground">触发类型</div>
                        <Select
                          value={workflowMeta.trigger.type}
                          disabled={!canEditConfiguration}
                          onValueChange={(value) =>
                            onTriggerChange(
                              nextWorkflowTriggerByType(
                                value as WorkflowTrigger["type"],
                                workflowMeta.trigger,
                              ),
                            )
                          }
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {triggerTypeOptions.map((option) => (
                              <SelectItem key={option.value} value={option.value}>
                                {option.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2">
                        <div className="text-xs text-muted-foreground">{triggerFieldMeta.label}</div>
                        <Input
                          value={getWorkflowTriggerValue(workflowMeta.trigger)}
                          disabled={!canEditConfiguration}
                          placeholder={triggerFieldMeta.placeholder}
                          onChange={(event) =>
                            onTriggerChange(
                              patchWorkflowTriggerValue(workflowMeta.trigger, event.target.value),
                            )
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <div className="text-xs text-muted-foreground">自然语言规则</div>
                        <Textarea
                          rows={3}
                          value={workflowMeta.trigger.naturalLanguageRule ?? ""}
                          disabled={!canEditConfiguration}
                          placeholder="例如：仅当用户表达退款且需要人工审核时命中"
                          onChange={(event) =>
                            onTriggerChange({
                              ...workflowMeta.trigger,
                              naturalLanguageRule: event.target.value || null,
                            })
                          }
                        />
                      </div>
                    </div>
                  </NodeSection>
                ) : null}

                {nodeType === "agent" ? (
                  <NodeSection title="Agent 配置">
                    <div className="space-y-3">
                      <div className="space-y-2">
                        <div className="text-xs text-muted-foreground">绑定 Agent</div>
                        <Select
                          value={selectedNode.agentId ?? "__unbound__"}
                          disabled={!canEditConfiguration}
                          onValueChange={(value) =>
                            onNodeAgentChange(value === "__unbound__" ? undefined : value)
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="选择一个 Agent" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__unbound__">未绑定</SelectItem>
                            {agents.map((agent) => (
                              <SelectItem key={agent.id} value={agent.id}>
                                {agent.name} · {agent.type}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2">
                        <div className="text-xs text-muted-foreground">Agent 任务说明</div>
                        <Textarea
                          rows={4}
                          value={getNodeConfigValue(selectedNode, "instruction")}
                          disabled={!canEditConfiguration}
                          placeholder="例如：负责检查输入内容是否涉及敏感风险，并产出审查结论"
                          onChange={(event) =>
                            onNodeConfigChange("instruction", event.target.value || null)
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <div className="text-xs text-muted-foreground">输出要求</div>
                        <Textarea
                          rows={3}
                          value={getNodeConfigValue(selectedNode, "outputRequirement")}
                          disabled={!canEditConfiguration}
                          placeholder="例如：输出风险等级、拦截原因、建议动作，格式为结构化 JSON"
                          onChange={(event) =>
                            onNodeConfigChange("outputRequirement", event.target.value || null)
                          }
                        />
                      </div>
                    </div>
                  </NodeSection>
                ) : null}

                {nodeType === "tool" ? (
                  <NodeSection title="历史工具节点">
                    <div className="rounded-xl border border-warning/20 bg-warning/5 px-4 py-3 text-sm leading-6 text-foreground">
                      当前节点属于历史兼容节点。后续建议改成 Agent 节点，并在对应 Agent 内配置工具能力。
                    </div>
                  </NodeSection>
                ) : null}

                {nodeType === "workflow" ? (
                  <NodeSection title="子工作流配置">
                    <div className="space-y-3">
                      <div className="space-y-2">
                        <div className="text-xs text-muted-foreground">绑定子工作流</div>
                        <Select
                          value={selectedNode.workflowId ?? "__unbound__"}
                          disabled={!canEditConfiguration}
                          onValueChange={(value) =>
                            onNodeWorkflowChange(value === "__unbound__" ? undefined : value)
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="选择一个子工作流" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__unbound__">未绑定</SelectItem>
                            {workflows.map((workflow) => (
                              <SelectItem key={workflow.id} value={workflow.id}>
                                {workflow.name} · {workflow.version}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2">
                        <div className="text-xs text-muted-foreground">交接说明</div>
                        <Textarea
                          rows={4}
                          value={getNodeConfigValue(selectedNode, "handoffNote")}
                          disabled={!canEditConfiguration}
                          placeholder="说明父流程传什么、子流程完成后回传什么"
                          onChange={(event) =>
                            onNodeConfigChange("handoffNote", event.target.value || null)
                          }
                        />
                      </div>
                    </div>
                  </NodeSection>
                ) : null}

                {nodeType === "condition" ? (
                  <NodeSection title="条件规则配置">
                    <div className="space-y-3">
                      <div className="space-y-2">
                        <div className="text-xs text-muted-foreground">判断表达式</div>
                        <Textarea
                          rows={4}
                          value={getNodeConfigValue(selectedNode, "expression")}
                          disabled={!canEditConfiguration}
                          placeholder="例如：intent == 'refund' && riskLevel >= 2"
                          onChange={(event) =>
                            onNodeConfigChange("expression", event.target.value || null)
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <div className="text-xs text-muted-foreground">分支说明</div>
                        <Textarea
                          rows={3}
                          value={getNodeConfigValue(selectedNode, "branchNote")}
                          disabled={!canEditConfiguration}
                          placeholder="说明 true / false 各自进入什么分支"
                          onChange={(event) =>
                            onNodeConfigChange("branchNote", event.target.value || null)
                          }
                        />
                      </div>
                    </div>
                  </NodeSection>
                ) : null}

                {nodeType === "parallel" ? (
                  <NodeSection title="并行策略配置">
                    <div className="space-y-3">
                      <div className="space-y-2">
                        <div className="text-xs text-muted-foreground">并行策略</div>
                        <Textarea
                          rows={4}
                          value={getNodeConfigValue(selectedNode, "strategy")}
                          disabled={!canEditConfiguration}
                          placeholder="例如：按知识检索、起草回复、风险检查三路并发"
                          onChange={(event) =>
                            onNodeConfigChange("strategy", event.target.value || null)
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <div className="text-xs text-muted-foreground">最大并发数</div>
                        <Input
                          value={getNodeConfigValue(selectedNode, "maxConcurrency")}
                          disabled={!canEditConfiguration}
                          placeholder="例如：3"
                          onChange={(event) =>
                            onNodeConfigChange("maxConcurrency", event.target.value || null)
                          }
                        />
                      </div>
                    </div>
                  </NodeSection>
                ) : null}

                {nodeType === "merge" || nodeType === "aggregate" ? (
                  <NodeSection title="结果合流配置">
                    <div className="space-y-2">
                      <div className="text-xs text-muted-foreground">合流策略</div>
                      <Textarea
                        rows={4}
                        value={getNodeConfigValue(selectedNode, "mergeStrategy")}
                        disabled={!canEditConfiguration}
                        placeholder="例如：优先使用风险检查后的版本，再补齐检索摘要"
                        onChange={(event) =>
                          onNodeConfigChange("mergeStrategy", event.target.value || null)
                        }
                      />
                    </div>
                  </NodeSection>
                ) : null}

                {nodeType === "transform" ? (
                  <NodeSection title="转换配置">
                    <div className="space-y-2">
                      <div className="text-xs text-muted-foreground">转换规则</div>
                      <Textarea
                        rows={5}
                        value={getNodeConfigValue(selectedNode, "transformRule")}
                        disabled={!canEditConfiguration}
                        placeholder="例如：把检索结果转成客户可读的结论 + 证据列表"
                        onChange={(event) =>
                          onNodeConfigChange("transformRule", event.target.value || null)
                        }
                      />
                    </div>
                  </NodeSection>
                ) : null}

                {nodeType === "output" ? (
                  <NodeSection title="输出配置">
                    <div className="space-y-2">
                      <div className="text-xs text-muted-foreground">输出要求</div>
                      <Textarea
                        rows={5}
                        value={getNodeConfigValue(selectedNode, "outputRequirement")}
                        disabled={!canEditConfiguration}
                        placeholder="例如：输出最终结论、执行摘要、风险说明和下一步建议"
                        onChange={(event) =>
                          onNodeConfigChange("outputRequirement", event.target.value || null)
                        }
                      />
                    </div>
                  </NodeSection>
                ) : null}
              </div>
            </ScrollArea>

            <DialogFooter className="border-t border-border px-6 py-4">
              <Button type="button" onClick={() => onOpenChange(false)}>
                完成设置
              </Button>
            </DialogFooter>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
