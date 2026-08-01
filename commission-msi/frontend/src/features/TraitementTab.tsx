/**
 * Onglet « Traitement » : le bouton principal, l'écran de progression et le
 * résultat de l'analyse automatique.
 *
 * Trois principes gouvernent cet écran :
 *
 * 1. le travail vit en base, pas dans le navigateur — fermer l'onglet, changer
 *    de dossier ou redémarrer l'application ne perd rien ;
 * 2. le score et l'avis sont affichés comme des **propositions motivées**,
 *    jamais comme une décision ;
 * 3. chaque constat renvoie à sa preuve et à sa page source.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { api } from '../services/api';
import type { Assessment, CriterionRow, JobView } from '../services/api';
import {
  Badge,
  Card,
  Empty,
  ErrorBanner,
  Field,
  Loading,
  Notice,
  useAsync,
  useLocale,
} from '../components/ui';

const ACTIVE_STATES = new Set([
  'QUEUED',
  'VALIDATING',
  'EXTRACTING',
  'OCR',
  'STRUCTURING',
  'REGULATORY_CHECK',
  'SCIENTIFIC_SCORING',
  'WEB_RESEARCH',
  'INDEPENDENT_AUDIT',
  'REPORT_BUILDING',
  'REPORT_QA',
]);

const STATUS_TONE: Record<string, 'ok' | 'incertain' | 'critique' | 'neutre'> = {
  C: 'ok',
  PC: 'incertain',
  NC: 'critique',
  NV: 'incertain',
};

const AVIS_TONE: Record<string, 'ok' | 'incertain' | 'critique'> = {
  FAVORABLE: 'ok',
  FAVORABLE_SOUS_RESERVES: 'incertain',
  AJOURNEMENT_POUR_COMPLEMENTS: 'incertain',
  REQUALIFICATION_NATIONALE_A_EXAMINER: 'incertain',
  TRANSMISSION_TUTELLE_AVEC_ALERTE_MOTIVEE: 'critique',
  NON_DETERMINABLE_INFORMATION_INSUFFISANTE: 'incertain',
};

const AVIS_LIST = Object.keys(AVIS_TONE);

export function TraitementTab({
  dossierId,
  onChanged,
}: {
  dossierId: string;
  onChanged: () => void;
}) {
  const { t } = useLocale();
  const [job, setJob] = useState<JobView | null>(null);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const mode = useAsync(() => api.analysisMode(), []);
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [state, current] = await Promise.all([
        api.processingState(dossierId),
        api.assessment(dossierId),
      ]);
      setJob(state.job);
      setAssessment(current);
      return state.job;
    } catch (cause) {
      setError(cause);
      return null;
    }
  }, [dossierId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Suivi de la progression : l'état vient toujours du serveur, jamais d'un
  // compteur local qui pourrait mentir après un rechargement.
  useEffect(() => {
    if (job === null || !ACTIVE_STATES.has(job.state)) {
      return undefined;
    }
    timer.current = window.setInterval(() => {
      void refresh().then((next) => {
        if (next && !ACTIVE_STATES.has(next.state)) {
          onChanged();
        }
      });
    }, 1500);
    return () => {
      if (timer.current !== null) window.clearInterval(timer.current);
    };
  }, [job, refresh, onChanged]);

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refresh();
      onChanged();
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  }

  const running = job !== null && ACTIVE_STATES.has(job.state);

  return (
    <>
      <Card
        title={t('processing.title')}
        actions={
          <button
            type="button"
            className="bouton-principal"
            onClick={() => act(() => api.startProcessing(dossierId))}
            disabled={busy || running}
          >
            {running ? t('processing.running') : t('processing.start')}
          </button>
        }
      >
        <Notice>{t('processing.intro')}</Notice>
        {mode.data && (
          <p className="aide">
            {t('processing.mode')} : <Badge>{mode.data.mode}</Badge> {mode.data.notice}
          </p>
        )}
        <ErrorBanner error={error} />

        {job === null && <Empty>{t('processing.none')}</Empty>}

        {job !== null && (
          <>
            <p className="actions">
              <Badge tone={running ? 'incertain' : job.state === 'COMPLETED' ? 'ok' : 'critique'}>
                {job.step_label}
              </Badge>
              <Badge tone="neutre">{`${job.progress} %`}</Badge>
              <Badge tone="neutre">
                {t('processing.pages')} : {job.pages_done}/{job.pages_total}
              </Badge>
              <Badge tone="neutre">
                {t('processing.searches')} : {job.searches_done}
              </Badge>
              <Badge tone="neutre">
                {t('processing.validations')} : {job.validations_done}
              </Badge>
              <Badge tone="neutre">
                {t('processing.attempt')} : {job.attempt}/{job.max_attempts}
              </Badge>
            </p>

            <progress max={100} value={job.progress} aria-label={job.step_label} />
            <p className="aide">{job.estimate}</p>
            <p className="aide">{t('processing.durable')}</p>

            {job.error_message && <Notice tone="critique">{job.error_message}</Notice>}

            <div className="actions">
              {running && (
                <button
                  type="button"
                  onClick={() => act(() => api.cancelProcessing(dossierId, job.id))}
                  disabled={busy}
                >
                  {t('processing.cancel')}
                </button>
              )}
              {job.can_resume && (
                <button
                  type="button"
                  onClick={() => act(() => api.resumeProcessing(dossierId, job.id))}
                  disabled={busy}
                >
                  {t('processing.resume')}
                </button>
              )}
              <button
                type="button"
                className="bouton-discret"
                onClick={() => act(() => api.runAssessment(dossierId))}
                disabled={busy || running}
              >
                {t('processing.rerun')}
              </button>
            </div>

            {job.steps_done.length > 0 && (
              <details>
                <summary>{t('processing.steps')}</summary>
                <ul className="aide">
                  {job.steps_done.map((step) => (
                    <li key={step}>
                      <Badge tone="ok">{step}</Badge> {t('processing.stepDone')}
                    </li>
                  ))}
                  {job.steps_remaining.map((step) => (
                    <li key={step}>
                      <Badge tone="neutre">{step}</Badge> {t('processing.stepPending')}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </Card>

      {assessment && (
        <>
          <DecisionCard dossierId={dossierId} assessment={assessment} onChanged={refresh} />
          <ScoreCard dossierId={dossierId} assessment={assessment} onChanged={refresh} />
          <MatrixCard dossierId={dossierId} assessment={assessment} onChanged={refresh} />
        </>
      )}
    </>
  );
}

// --------------------------------------------------------------------------
// Avis proposé
// --------------------------------------------------------------------------

function DecisionCard({
  dossierId,
  assessment,
  onChanged,
}: {
  dossierId: string;
  assessment: Assessment;
  onChanged: () => void;
}) {
  const { t } = useLocale();
  const [avis, setAvis] = useState('');
  const [motivation, setMotivation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const decision = assessment.decision;

  if (!decision) {
    return (
      <Card title={t('decision.title')}>
        <Empty>{t('decision.none')}</Empty>
      </Card>
    );
  }

  async function retain(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.retainDecision(dossierId, avis, motivation);
      setMotivation('');
      onChanged();
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title={t('decision.title')}>
      <p className="actions">
        <Badge tone={AVIS_TONE[decision.avis] ?? 'incertain'}>{decision.label}</Badge>
        {decision.scientific_total !== null && (
          <Badge tone="neutre">{`${t('decision.score')} : ${decision.scientific_total}/100`}</Badge>
        )}
        <Badge tone="neutre">{`${t('decision.referential')} ${decision.referential_version}`}</Badge>
      </p>
      <p>{decision.motivation}</p>
      {/* La mention est obligatoire et ne dépend d'aucune option. */}
      <Notice tone="incertain">{decision.disclaimer}</Notice>

      {decision.required_complements.length > 0 && (
        <>
          <h3>{t('decision.complements')}</h3>
          <ul>
            {decision.required_complements.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}

      {decision.reserves.length > 0 && (
        <>
          <h3>{t('decision.reserves')}</h3>
          <ul>
            {decision.reserves.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}

      <details>
        <summary>{t('decision.rules')}</summary>
        <ul className="aide">
          {decision.triggered_rules.map((rule) => (
            <li key={rule.rule}>
              <strong>{rule.rule}</strong> — {rule.explanation}
              {rule.criteria.length > 0 && ` (${rule.criteria.join(', ')})`}
            </li>
          ))}
        </ul>
      </details>

      <form onSubmit={retain}>
        <h3>{t('decision.retain')}</h3>
        <Field label={t('decision.retainedAvis')} htmlFor="avis-retenu">
          <select
            id="avis-retenu"
            value={avis}
            required
            onChange={(event) => setAvis(event.target.value)}
          >
            <option value="">—</option>
            {AVIS_LIST.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t('decision.motivation')} htmlFor="avis-motivation">
          <textarea
            id="avis-motivation"
            minLength={8}
            required
            value={motivation}
            onChange={(event) => setMotivation(event.target.value)}
          />
        </Field>
        <button type="submit" className="bouton-principal" disabled={busy}>
          {t('common.save')}
        </button>
      </form>
      {decision.human_decision && (
        <Notice tone="ok">
          {t('decision.retained')} : {decision.human_decision}
          {decision.decided_by ? ` — ${decision.decided_by}` : ''}
        </Notice>
      )}
      <ErrorBanner error={error} />
    </Card>
  );
}

// --------------------------------------------------------------------------
// Score scientifique
// --------------------------------------------------------------------------

function ScoreCard({
  dossierId,
  assessment,
  onChanged,
}: {
  dossierId: string;
  assessment: Assessment;
  onChanged: () => void;
}) {
  const { t } = useLocale();
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ score: 0, justification: '' });
  const [error, setError] = useState<unknown>(null);
  const score = assessment.score;

  if (!score) {
    return (
      <Card title={t('score.title')}>
        <Empty>{t('score.none')}</Empty>
      </Card>
    );
  }

  async function save(key: string) {
    setError(null);
    try {
      await api.overrideSubScore(dossierId, key, draft.score, draft.justification);
      setEditing(null);
      onChanged();
    } catch (cause) {
      setError(cause);
    }
  }

  return (
    <Card title={`${t('score.title')} — ${score.total}/${score.maximum}`}>
      <Notice>{t('score.intro')}</Notice>
      <p className="aide">
        {t('score.grid')} {score.grid_version} — {t('score.proposed')} : {score.proposed_total}/
        {score.maximum}
      </p>
      <ErrorBanner error={error} />

      {score.families.map((family) => (
        <details key={family.key} open>
          <summary>
            {family.label} — {family.score}/{family.max}
          </summary>
          <div className="tableau-conteneur">
            <table>
              <thead>
                <tr>
                  <th scope="col">{t('score.subcriterion')}</th>
                  <th scope="col">{t('score.note')}</th>
                  <th scope="col">{t('score.justification')}</th>
                  <th scope="col">{t('score.evidence')}</th>
                  <th scope="col">{t('common.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {family.subscores.map((sub) => (
                  <tr key={sub.key}>
                    <td>{sub.label}</td>
                    <td>
                      <Badge tone={sub.score === 0 ? 'incertain' : 'ok'}>
                        {sub.score}/{sub.max}
                      </Badge>
                      {sub.human_score !== null && (
                        <span className="aide"> ({t('score.proposedWas')} {sub.proposed_score})</span>
                      )}
                    </td>
                    <td>{sub.justification}</td>
                    <td className="mono aide">{sub.evidence_ids.join(', ') || '—'}</td>
                    <td>
                      {editing === sub.key ? (
                        <>
                          <input
                            type="number"
                            min={0}
                            max={sub.max}
                            aria-label={t('score.note')}
                            value={draft.score}
                            onChange={(event) =>
                              setDraft({ ...draft, score: Number(event.target.value) })
                            }
                          />
                          <input
                            aria-label={t('score.justification')}
                            placeholder={t('matrix.commentPlaceholder')}
                            minLength={8}
                            value={draft.justification}
                            onChange={(event) =>
                              setDraft({ ...draft, justification: event.target.value })
                            }
                          />
                          <span className="aide">
                            {draft.justification.trim().length < 8
                              ? t('matrix.commentRequired')
                              : t('matrix.commentOk')}
                          </span>
                          <button
                            type="button"
                            onClick={() => save(sub.key)}
                            disabled={draft.justification.trim().length < 8}
                          >
                            {t('common.save')}
                          </button>
                          <button
                            type="button"
                            className="bouton-discret"
                            onClick={() => setEditing(null)}
                          >
                            {t('common.cancel')}
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          className="bouton-discret"
                          onClick={() => {
                            setEditing(sub.key);
                            setDraft({ score: sub.score, justification: '' });
                          }}
                        >
                          {t('score.correct')}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ))}
    </Card>
  );
}

// --------------------------------------------------------------------------
// Matrice réglementaire
// --------------------------------------------------------------------------

function MatrixCard({
  dossierId,
  assessment,
  onChanged,
}: {
  dossierId: string;
  assessment: Assessment;
  onChanged: () => void;
}) {
  const { t } = useLocale();
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ status: 'C', comment: '' });
  const [error, setError] = useState<unknown>(null);

  if (assessment.criteria.length === 0) {
    return (
      <Card title={t('matrix.title')}>
        <Empty>{t('matrix.none')}</Empty>
      </Card>
    );
  }

  async function qualify(code: string) {
    setError(null);
    try {
      await api.qualifyCriterion(dossierId, code, draft.status, draft.comment);
      setEditing(null);
      onChanged();
    } catch (cause) {
      setError(cause);
    }
  }

  return (
    <Card title={`${t('matrix.title')} (${assessment.criteria.length})`}>
      <Notice>{t('matrix.intro')}</Notice>
      <ErrorBanner error={error} />
      <div className="tableau-conteneur">
        <table>
          <thead>
            <tr>
              <th scope="col">{t('matrix.code')}</th>
              <th scope="col">{t('matrix.criterion')}</th>
              <th scope="col">{t('matrix.status')}</th>
              <th scope="col">{t('matrix.finding')}</th>
              <th scope="col">{t('matrix.evidence')}</th>
              <th scope="col">{t('matrix.source')}</th>
              <th scope="col">{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {assessment.criteria.map((row: CriterionRow) => (
              <tr key={row.code}>
                <td className="mono">{row.code}</td>
                <td>
                  {row.label}
                  {row.blocking && <Badge tone="incertain">{t('matrix.blocking')}</Badge>}
                </td>
                <td>
                  <Badge tone={STATUS_TONE[row.status] ?? 'neutre'}>{row.status}</Badge>
                  {row.human_status && (
                    <span className="aide"> ({t('matrix.proposedWas')} {row.proposed_status})</span>
                  )}
                </td>
                <td>{row.finding}</td>
                <td className="mono aide">{row.evidence_ids.join(', ') || '—'}</td>
                <td className="aide">
                  {row.exact_source}
                  {row.page ? ` — p. ${row.page}` : ''}
                </td>
                <td>
                  {editing === row.code ? (
                    <div className="qualification">
                      <select
                        aria-label={t('matrix.status')}
                        value={draft.status}
                        onChange={(event) => setDraft({ ...draft, status: event.target.value })}
                      >
                        {['C', 'PC', 'NC', 'NV'].map((value) => (
                          <option key={value} value={value}>
                            {value}
                          </option>
                        ))}
                      </select>
                      <input
                        aria-label={t('matrix.comment')}
                        placeholder={t('matrix.commentPlaceholder')}
                        minLength={8}
                        value={draft.comment}
                        onChange={(event) => setDraft({ ...draft, comment: event.target.value })}
                      />
                      {/* La règle est annoncée avant l'envoi plutôt que subie
                          sous forme de refus du serveur. */}
                      <span className="aide">
                        {draft.comment.trim().length < 8
                          ? t('matrix.commentRequired')
                          : t('matrix.commentOk')}
                      </span>
                      <button
                        type="button"
                        onClick={() => qualify(row.code)}
                        disabled={draft.comment.trim().length < 8}
                      >
                        {t('common.save')}
                      </button>
                      <button
                        type="button"
                        className="bouton-discret"
                        onClick={() => setEditing(null)}
                      >
                        {t('common.cancel')}
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="bouton-discret"
                      onClick={() => {
                        setEditing(row.code);
                        setDraft({ status: row.status, comment: '' });
                      }}
                    >
                      {t('matrix.qualify')}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// --------------------------------------------------------------------------
// Registre de preuves et contrôle qualité
// --------------------------------------------------------------------------

export function PreuvesTab({ dossierId }: { dossierId: string }) {
  const { t } = useLocale();
  const evidence = useAsync(() => api.evidence(dossierId), [dossierId]);
  const qa = useAsync(() => api.qualityControl(dossierId), [dossierId]);
  const disagreements = useAsync(() => api.disagreements(dossierId), [dossierId]);

  return (
    <>
      <Card title={t('evidence.title')}>
        <Notice>{t('evidence.intro')}</Notice>
        {evidence.loading && <Loading label={t('common.loading')} />}
        <ErrorBanner error={evidence.error} />
        {evidence.data && evidence.data.items.length === 0 && <Empty>{t('evidence.none')}</Empty>}
        {evidence.data && evidence.data.items.length > 0 && (
          <div className="tableau-conteneur">
            <table>
              <thead>
                <tr>
                  <th scope="col">{t('evidence.reference')}</th>
                  <th scope="col">{t('evidence.kind')}</th>
                  <th scope="col">{t('evidence.locator')}</th>
                  <th scope="col">{t('evidence.excerpt')}</th>
                  <th scope="col">{t('evidence.fingerprint')}</th>
                </tr>
              </thead>
              <tbody>
                {evidence.data.items.map((item) => (
                  <tr key={item.id}>
                    <td className="mono">{item.reference}</td>
                    <td>
                      <Badge tone={item.sensitivity === 'RESTREINT' ? 'critique' : 'neutre'}>
                        {item.kind}
                      </Badge>
                    </td>
                    <td>{item.locator ?? '—'}</td>
                    <td className="aide">{item.excerpt}</td>
                    <td className="mono aide">{(item.content_sha256 ?? '—').slice(0, 16)}…</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={t('qa.title')}>
        {qa.loading && <Loading label={t('common.loading')} />}
        <ErrorBanner error={qa.error} />
        {qa.data && qa.data.checks.length === 0 && <Empty>{qa.data.notice ?? t('qa.none')}</Empty>}
        {qa.data && qa.data.checks.length > 0 && (
          <>
            <p className="actions">
              <Badge tone={qa.data.passed ? 'ok' : 'critique'}>
                {qa.data.passed ? t('qa.passed') : t('qa.failed')}
              </Badge>
              <Badge tone="neutre">
                {qa.data.checks.length} {t('qa.checks')}
              </Badge>
            </p>
            <ul>
              {qa.data.checks.map((check) => (
                <li key={check.key}>
                  <Badge tone={check.passed ? 'ok' : check.blocking ? 'critique' : 'incertain'}>
                    {check.passed ? '✓' : '✗'}
                  </Badge>{' '}
                  {check.label} — <span className="aide">{check.detail}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <Card title={t('disagreement.title')}>
        {disagreements.data && (
          <>
            <Notice tone="incertain">{disagreements.data.notice}</Notice>
            {disagreements.data.items.length === 0 ? (
              <Empty>{t('disagreement.none')}</Empty>
            ) : (
              <ul>
                {disagreements.data.items.map((item) => (
                  <li key={String(item.id)}>
                    <Badge tone={item.resolved ? 'ok' : 'incertain'}>
                      {String(item.criterion_code ?? '—')}
                    </Badge>{' '}
                    {String(item.reason)}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </Card>
    </>
  );
}
