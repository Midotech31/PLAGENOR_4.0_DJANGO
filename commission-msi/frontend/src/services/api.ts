/**
 * Client de l'API locale. Toutes les requêtes visent le backend 127.0.0.1
 * servi sur la même origine : aucune ressource distante n'est appelée ici.
 */

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, unknown> };
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody | null, fallback: string) {
    super(body?.error?.message ?? fallback);
    this.name = 'ApiError';
    this.status = status;
    this.code = body?.error?.code ?? 'ERREUR';
    this.details = body?.error?.details ?? {};
  }
}

const BASE = '/api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      body = null;
    }
    throw new ApiError(response.status, body, `Requête refusée (${response.status}).`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

const get = <T>(path: string) => request<T>(path);
const post = <T>(path: string, payload?: unknown) =>
  request<T>(path, { method: 'POST', body: payload === undefined ? undefined : JSON.stringify(payload) });

// ---------------------------------------------------------------- types

export interface Health {
  status: string;
  application: string;
  version: string;
  designed_by: string;
  authentication: string;
}

export interface Readiness {
  ready: boolean;
  checks: Record<string, boolean>;
  message: string;
}

export interface Diagnostic {
  application: string;
  version: string;
  designed_by: string;
  bind_host: string;
  bind_port: number;
  listens_locally_only: boolean;
  network_policy: string;
  master_key_present: boolean;
  ocr: { available: boolean; note: string; effective_languages: string | null };
  security_notes: string[];
  limits: string[];
}

export interface DossierSummary {
  id: string;
  reference: string;
  title: string;
  organizer: string;
  status: string;
  priority: string;
  page_count: number;
  sha256: string | null;
  open_findings: number;
  pages_needing_ocr: number;
  missing_pieces: number;
  score_total: number | null;
  score_max: number;
  international_scope_declared: boolean | null;
  report_validated_at: string | null;
  created_at: string;
  updated_at: string;
  gates?: Record<string, GateState>;
}

export interface GateState {
  satisfied: boolean;
  message: string;
  details: Record<string, unknown>;
}

export interface Dashboard {
  recent_dossiers: DossierSummary[];
  open_findings: number;
  pages_needing_ocr: number;
  missing_pieces: number;
  reports_generated: number;
  notice: string;
}

export interface PageInfo {
  id: string;
  page_no: number;
  mode: string;
  confidence: number | null;
  char_count: number;
  image_count: number;
  rotation: number;
  needs_ocr: boolean;
  is_blank: boolean;
  is_difficult: boolean;
  duplicate_of: number | null;
  uncertain: boolean;
  notice: string | null;
  original_text?: string | null;
  current_text?: string | null;
  corrections?: { id: string; reason: string; created_at: string; evaluator_label: string }[];
}

export interface PieceInfo {
  id: string;
  piece_key: string;
  label: string;
  status: string;
  sensitivity: string;
  detected_page_no: number | null;
  detection_excerpt: string | null;
  comment: string | null;
}

export interface ItemInfo {
  id: string;
  key: string;
  label: string;
  initial_value: string | null;
  current_value: string | null;
  source_excerpt: string | null;
  page_no: number | null;
  extraction_mode: string;
  status: string;
  reinforced_control: boolean;
  manual_entry_validated: boolean;
}

export interface CheckInfo {
  id: string;
  check_key: string;
  label: string;
  status: string;
  explanation: string | null;
  page_no: number | null;
}

export interface EvaluationState {
  criteria: {
    key: string;
    label: string;
    max: number;
    score: number | null;
    justification: string | null;
    source_pages: number[];
  }[];
  missing: string[];
  complete: boolean;
  total: number | null;
  max_total: number;
  notice: string;
}

export interface FindingInfo {
  id: string;
  category: string;
  rule_code: string;
  label: string;
  trigger: string | null;
  context: string | null;
  page_no: number | null;
  priority: string;
  confidence: number | null;
  explanation: string;
  recommended_check: string;
  source_ref: string | null;
  relation_kind: string | null;
  human_status: string;
  human_comment: string | null;
}

export interface NoteInfo {
  id: string;
  kind: string;
  body: string | null;
  conclusion: string | null;
  page_no: number | null;
  author_label: string;
  created_at: string;
}

export interface ReportInfo {
  id: string;
  format: string;
  is_draft: boolean;
  version: number;
  sha256: string;
  created_at: string;
}

export interface AuditEntry {
  id: string;
  action: string;
  summary: string;
  fingerprint: string | null;
  actor_label: string;
  created_at: string;
}

export interface Vocabulary {
  dossier_status: string[];
  information_status: string[];
  piece_status: string[];
  control_status: string[];
  finding_status: string[];
  priority: string[];
  conclusions: string[];
  maroc_relations: string[];
  gates: string[];
}

export interface Connectivity {
  online: boolean;
  reason: string;
  message: string;
  providers: { name: string; enabled: boolean; configured: boolean; tier: string }[];
  egress: {
    network_disabled: boolean;
    allowed_domains: string[];
    tls_required: boolean;
    notice: string;
  };
}

export interface WebQueryInfo {
  id: string;
  subject_kind: string;
  subject_label: string;
  query_text: string;
  purpose: string;
  approved: boolean;
  provider: string | null;
  sent_at: string | null;
  result_count: number;
  error_message: string | null;
  redaction_report: Record<string, unknown>;
}

export interface WebRunDetail {
  id: string;
  dossier_id: string;
  status: string;
  connectivity_ok: boolean | null;
  approved_by: string | null;
  failure_reason: string | null;
  queries: WebQueryInfo[];
  sources: {
    id: string;
    url: string;
    domain: string;
    title: string | null;
    publisher: string | null;
    published_on: string | null;
    consulted_at: string;
    tier: string;
    excerpt: string | null;
  }[];
  claims: {
    id: string;
    agent_name: string;
    subject_label: string;
    statement: string | null;
    nature: string;
    status: string;
    human_status: string;
    confidence: number | null;
    sources: string[];
    independent_source_count: number;
  }[];
  notice: string;
}

export interface RankingAxis {
  id: string;
  axis_key: string;
  label: string;
  max: number;
  proposed_score: number | null;
  uncertainty_low: number | null;
  uncertainty_high: number | null;
  not_provided: boolean;
  display_score: number | string;
  justification: string | null;
  sources: string[];
  human_decision: string;
  human_score: number | null;
}

export interface RankingView {
  id: string;
  title: string;
  total: number | null;
  grade: string;
  agreement_level: number | null;
  blocked_reason: string | null;
  axes: RankingAxis[];
  disagreements: { subject_label: string; axis_key: string | null; description: string }[];
  separation_notice: string;
  created_at: string;
}

// ---------------------------------------------------------------- appels

export const api = {
  health: () => get<Health>('/health'),
  readiness: () => get<Readiness>('/readiness'),
  diagnostic: () => get<Diagnostic>('/diagnostic'),
  vocabulary: () => get<Vocabulary>('/vocabulary'),
  limits: () => get<{ limits: string[] }>('/limites'),

  dashboard: () => get<Dashboard>('/dossiers/tableau-de-bord'),
  listDossiers: (params: Record<string, string>) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, value]) => value !== ''),
    ).toString();
    return get<{ items: DossierSummary[] }>(`/dossiers${query ? `?${query}` : ''}`);
  },
  createDossier: (payload: { reference: string; title: string; organizer: string }) =>
    post<DossierSummary>('/dossiers', payload),
  getDossier: (id: string) => get<DossierSummary>(`/dossiers/${id}`),
  setDossierStatus: (id: string, status: string) => post(`/dossiers/${id}/etat`, { status }),
  archiveDossier: (id: string) => post(`/dossiers/${id}/archiver`),

  importDocument: async (id: string, file: File) => {
    const body = new FormData();
    body.append('file', file);
    return request<{ id: string; page_count: number; sha256: string }>(
      `/dossiers/${id}/documents`,
      { method: 'POST', body },
    );
  },
  fullAnalysis: (id: string) =>
    post<{
      steps: { etape: string; resultat: string; traite: number; echecs: number }[];
      web_run_id: string | null;
      notice: string;
    }>(`/dossiers/${id}/analyse-complete`),
  listPages: (id: string) => get<{ items: PageInfo[] }>(`/dossiers/${id}/pages`),
  getPage: (id: string, pageId: string) => get<PageInfo>(`/dossiers/${id}/pages/${pageId}`),
  pageImageUrl: (id: string, pageId: string, dpi = 150) =>
    `${BASE}/dossiers/${id}/pages/${pageId}/image?dpi=${dpi}`,
  runOcr: (id: string, pageId: string, force = false) =>
    post<{ text: string; confidence: number | null; uncertain: boolean; notice: string }>(
      `/dossiers/${id}/pages/${pageId}/ocr?force=${force}`,
    ),
  correctPage: (id: string, pageId: string, corrected_text: string, reason: string) =>
    post(`/dossiers/${id}/pages/${pageId}/correction`, { corrected_text, reason }),
  searchInDossier: (id: string, q: string) =>
    get<{ items: { page_id: string; page_no: number; excerpt: string }[] }>(
      `/dossiers/${id}/recherche?q=${encodeURIComponent(q)}`,
    ),

  listPieces: (id: string) => get<{ items: PieceInfo[]; notice: string }>(`/dossiers/${id}/pieces`),
  updatePiece: (id: string, pieceId: string, payload: { status: string; comment: string }) =>
    post(`/dossiers/${id}/pieces/${pieceId}`, payload),

  listItems: (id: string) =>
    get<{ items: ItemInfo[]; notice: string }>(`/dossiers/${id}/informations`),
  updateItem: (
    id: string,
    itemId: string,
    payload: {
      value: string;
      status: string;
      reason: string;
      page_no?: number | null;
      source_excerpt?: string | null;
      manual_entry_validated?: boolean;
    },
  ) => post<ItemInfo>(`/dossiers/${id}/informations/${itemId}`, payload),

  listChecks: (id: string) =>
    get<{ items: CheckInfo[]; notice: string }>(`/dossiers/${id}/controle-administratif`),
  updateCheck: (
    id: string,
    checkId: string,
    payload: { status: string; explanation: string; page_no?: number | null },
  ) => post(`/dossiers/${id}/controle-administratif/${checkId}`, payload),

  evaluation: (id: string) => get<EvaluationState>(`/dossiers/${id}/evaluation`),
  setScore: (
    id: string,
    payload: { criterion_key: string; score: number; justification: string; source_pages: number[] },
  ) => post<EvaluationState>(`/dossiers/${id}/evaluation`, payload),

  listFindings: (id: string, category?: string) =>
    get<{ items: FindingInfo[]; notice: string }>(
      `/dossiers/${id}/alertes${category ? `?category=${encodeURIComponent(category)}` : ''}`,
    ),
  qualifyFinding: (
    id: string,
    findingId: string,
    payload: { status: string; comment: string; relation_kind?: string | null },
  ) => post(`/dossiers/${id}/alertes/${findingId}`, payload),
  rescanFindings: (id: string) => post<{ created: number; open: number }>(`/dossiers/${id}/alertes/recalcul`),

  listNotes: (id: string) => get<{ items: NoteInfo[] }>(`/dossiers/${id}/notes`),
  addNote: (id: string, payload: { body: string; kind: string }) =>
    post(`/dossiers/${id}/notes`, payload),
  setConclusion: (id: string, payload: { conclusion: string; motivation: string }) =>
    post<{ notice: string }>(`/dossiers/${id}/conclusion`, payload),

  listReports: (id: string) => get<{ items: ReportInfo[] }>(`/dossiers/${id}/rapports`),
  generateReport: (id: string, payload: { format: string; official: boolean }) =>
    post<ReportInfo>(`/dossiers/${id}/rapports`, payload),
  reportUrl: (id: string, reportId: string) => `${BASE}/dossiers/${id}/rapports/${reportId}/fichier`,
  validateReport: (id: string, statement: string) =>
    post<{ validated_at: string }>(`/dossiers/${id}/rapports/validation-humaine`, { statement }),

  history: (id: string) => get<{ items: AuditEntry[]; notice: string }>(`/dossiers/${id}/historique`),
  audit: (limit = 200) => get<{ items: AuditEntry[] }>(`/audit?limit=${limit}`),

  connectivity: () => get<Connectivity>('/recherche-web/connectivite'),
  listWebRuns: (id: string) =>
    get<{ items: { id: string; status: string; created_at: string }[]; enriched_state: { complete: boolean; message: string } }>(
      `/dossiers/${id}/recherche-web`,
    ),
  prepareWebRun: (id: string, scope_note: string) =>
    post<WebRunDetail>(`/dossiers/${id}/recherche-web`, { scope_note }),
  getWebRun: (runId: string) => get<WebRunDetail>(`/recherche-web/${runId}`),
  editWebQuery: (runId: string, queryId: string, query_text: string, approved: boolean) =>
    post(`/recherche-web/${runId}/requetes/${queryId}`, { query_text, approved }),
  approveWebRun: (runId: string, approved_by: string) =>
    post(`/recherche-web/${runId}/approbation`, { approved_by }),
  executeWebRun: (runId: string) =>
    post<{ status: string; online: boolean; sources: number; claims: number; message: string }>(
      `/recherche-web/${runId}/execution`,
    ),
  setWebRunStatus: (runId: string, status: string, justification = '') =>
    post(`/recherche-web/${runId}/etat`, { status, justification }),
  markEnrichedComplete: (id: string) => post(`/dossiers/${id}/analyse-enrichie`),
  qualifyClaim: (claimId: string, status: string, comment: string) =>
    post(`/recherche-web/affirmations/${claimId}`, { status, comment }),

  ranking: (id: string) =>
    get<{ ranking: RankingView | null; title: string; message?: string }>(`/dossiers/${id}/ranking`),
  rankingAxes: () =>
    get<{ title: string; warning: string; axes: { key: string; label: string; max: number }[] }>(
      '/ranking/axes',
    ),
  reviewRankingAxis: (
    axisId: string,
    payload: { decision: string; score?: number | null; justification: string },
  ) => post<{ notice: string }>(`/ranking/axes/${axisId}`, payload),

  rules: () => get<{ items: Record<string, unknown>[]; notice: string }>('/regles'),
  conflicts: () => get<{ items: Record<string, unknown>[] }>('/contradictions'),
  sources: () => get<{ items: Record<string, unknown>[]; notice: string }>('/sources'),
  verifySources: () => post<{ items: Record<string, unknown>[] }>('/sources/verification'),
  requirements: () => get<{ items: Record<string, unknown>[]; notice: string }>('/exigences'),

  backups: () => get<{ items: Record<string, unknown>[]; warning: string }>('/sauvegardes'),
  createBackup: () => post<{ id: string; warning: string }>('/sauvegardes'),
  verifyBackup: (id: string) => post<{ valid: boolean; message: string }>(`/sauvegardes/${id}/verification`),
};
