'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiRequest } from '@/lib/api/client'
import { queryKeys } from '@/lib/api/query-keys'
import type {
  ApprovalActionResponse,
  ApprovalListResponse,
  CreateApprovalRequest,
  ProcessApprovalRequest,
} from '@/types'

interface ApprovalQuery {
  status?: string
  requestType?: string
}

function buildApprovalsPath(params: ApprovalQuery = {}) {
  const searchParams = new URLSearchParams()
  if (params.status && params.status !== 'all') searchParams.set('status', params.status)
  if (params.requestType && params.requestType !== 'all') {
    searchParams.set('requestType', params.requestType)
  }
  const queryString = searchParams.toString()
  return queryString ? `/api/approvals?${queryString}` : '/api/approvals'
}

export function useApprovals(params: ApprovalQuery = {}) {
  return useQuery({
    queryKey: queryKeys.approvals.list(params),
    queryFn: () => apiRequest<ApprovalListResponse>(buildApprovalsPath(params)),
  })
}

export function useCreateApproval() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateApprovalRequest) =>
      apiRequest<ApprovalActionResponse, CreateApprovalRequest>('/api/approvals', {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approvals'] })
    },
  })
}

export function useApproveApproval() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ approvalId, payload }: { approvalId: string; payload?: ProcessApprovalRequest }) =>
      apiRequest<ApprovalActionResponse, ProcessApprovalRequest>(
        `/api/approvals/${encodeURIComponent(approvalId)}/approve`,
        {
          method: 'POST',
          body: payload ?? {},
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approvals'] })
    },
  })
}

export function useRejectApproval() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ approvalId, payload }: { approvalId: string; payload?: ProcessApprovalRequest }) =>
      apiRequest<ApprovalActionResponse, ProcessApprovalRequest>(
        `/api/approvals/${encodeURIComponent(approvalId)}/reject`,
        {
          method: 'POST',
          body: payload ?? {},
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approvals'] })
    },
  })
}
