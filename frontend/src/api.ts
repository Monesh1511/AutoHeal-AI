const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

export type Status = 'open' | 'recovered' | 'escalated' | 'pending' | 'failed'
export type Incident = {
  id: number
  title: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  status: Status
  source: string
  alert_details: string | null
  created_at: string
  updated_at: string
}
export type Detail = Incident & {
  diagnostic_checks: { id: number; check_name: string; status: string; result: string | null; checked_at: string }[]
  hypotheses: { id: number; description: string; confidence: number; status: string; evidence: string | null; created_at: string }[]
  repair_attempts: { id: number; action: string; status: string; output: string | null; attempted_at: string }[]
  verification_results: { id: number; check_name: string; status: string; details: string | null; verified_at: string }[]
  escalations: Escalation[]
  audit_logs: { id: number; event_type: string; message: string; created_at: string }[]
}
export type Escalation = { id: number; incident_id: number; reason: string; status: string; created_at: string }
export type Metrics = { total_incidents: number; recovered_incidents: number; escalated_incidents: number; recovery_success_rate: number; total_projects: number; open_errors: number; critical_errors: number; awaiting_approval: number; failed_repairs: number }
export type Sandbox = { active_fault: string | null; service_status: string; configuration_status: string; last_action: string | null }
export type User = { id: number; username: string; full_name: string; role: string }
export type Project = { id: number; identifier: string; name: string; language: string; description: string; status: string; last_analyzed_at: string | null; github_url: string | null }
export type Approval = {
  id: number
  incident_id: number
  patch_id: number
  status: string
  message: string
  reason: string | null
  requested_at: string
  decided_at: string | null
  recipient_email: string
  notification_status: string
  report_filename: string | null
  incident_title: string | null
  project_name: string | null
}
export type ApprovalReport = {
  id: number
  approval_id: number
  filename: string
  recipient_email: string
  notification_status: string
  content: string
  created_at: string
  updated_at: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem('autoheal_token')
  const response = await fetch(`${baseUrl}${path}`, { headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init?.headers }, ...init })
  if (!response.ok) {
    const body = await response.text()
    throw new Error(body || `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string }>('/api/health'),
  readiness: () => request<{ status: string; database: string }>('/api/health/ready'),
  metrics: () => request<Metrics>('/api/metrics'),
  incidents: (limit = 100) => request<Incident[]>(`/api/incidents?limit=${limit}`),
  incident: (id: number) => request<Detail>(`/api/incidents/${id}`),
  createIncident: (payload: { title: string; severity: Incident['severity']; source: string; alert_details: string }) =>
    request<Incident>('/api/incidents', { method: 'POST', body: JSON.stringify(payload) }),
  recover: (id: number) => request<{ incident_id: number; status: string }>(`/api/incidents/${id}/recover`, { method: 'POST' }),
  escalations: () => request<Escalation[]>('/api/escalations'),
  sandbox: () => request<Sandbox>('/api/sandbox'),
  inject: (fault: string) => request<{ state: Sandbox; message: string }>(`/api/sandbox/faults/${fault}`, { method: 'POST' }),
  reset: () => request<{ state: Sandbox; message: string }>('/api/sandbox/reset', { method: 'POST' }),
  login: (payload: { username: string; password: string }) => request<{ access_token: string; user: User }>('/api/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  me: () => request<User>('/api/auth/me'),
  projects: () => request<Project[]>('/api/projects'),
  updateProjectGithub: (id: number, github_url: string) =>
    request<Project>(`/api/projects/${id}/github`, { method: 'PUT', body: JSON.stringify({ github_url }) }),
  removeProjectGithub: (id: number) =>
    request<Project>(`/api/projects/${id}/github`, { method: 'DELETE' }),
  approvals: () => request<Approval[]>('/api/approvals'),
  approvalReport: (id: number) => request<ApprovalReport>(`/api/approvals/${id}/report`),
  downloadApprovalReport: async (id: number, filename: string) => {
    const token = localStorage.getItem('autoheal_token')
    const response = await fetch(`${baseUrl}/api/approvals/${id}/report/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!response.ok) throw new Error(`Report download failed (${response.status})`)
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(url)
  },
  approve: (id: number) => request<Approval>(`/api/approvals/${id}/approve`, { method: 'POST' }),
  reject: (id: number, reason?: string) => request<Approval>(`/api/approvals/${id}/reject`, { method: 'POST', body: JSON.stringify({ reason }) }),
}
