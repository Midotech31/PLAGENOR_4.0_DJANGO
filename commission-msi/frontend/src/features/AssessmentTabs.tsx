/** Onglets « Évaluation », « Alertes », « Notes et conclusion », « Rapports », « Historique ». */

import { useState } from 'react';

import { api } from '../services/api';
import {
  Badge,
  Card,
  Empty,
  ErrorBanner,
  Field,
  IconAlert,
  Loading,
  Notice,
  useAsync,
  useLocale,
} from '../components/ui';

export function EvaluationTab({ dossierId, onChanged }: { dossierId: string; onChanged: () => void }) {
  const { t } = useLocale();
  const state = useAsync(() => api.evaluation(dossierId), [dossierId]);
  const [drafts, setDrafts] = useState<Record<string, { score: string; justification: string; pages: string }>>({});
  const [error, setError] = useState<unknown>(null);

  async function save(key: string, current: { score: number | null; justification: string | null; pages: number[] }) {
    const draft =
      drafts[key] ?? {
        score: current.score === null ? '' : String(current.score),
        justification: current.justification ?? '',
        pages: current.pages.join(', '),
      };
    setError(null);
    try {
      await api.setScore(dossierId, {
        criterion_key: key,
        score: Number(draft.score),
        justification: draft.justification,
        source_pages: draft.pages
          .split(',')
          .map((value) => Number(value.trim()))
          .filter((value) => Number.isInteger(value) && value > 0),
      });
      state.reload();
      onChanged();
    } catch (cause) {
      setError(cause);
    }
  }

  return (
    <Card title={t('tab.evaluation')}>
      <Notice>{t('evaluation.notice')}</Notice>
      <ErrorBanner error={error} />
      {state.loading && <Loading label={t('common.loading')} />}
      {state.data && (
        <>
          {state.data.criteria.map((criterion) => {
            const draft =
              drafts[criterion.key] ?? {
                score: criterion.score === null ? '' : String(criterion.score),
                justification: criterion.justification ?? '',
                pages: criterion.source_pages.join(', '),
              };
            return (
              <div key={criterion.key} className="carte">
                <h3>
                  {criterion.label}{' '}
                  <Badge tone={criterion.score === null ? 'incertain' : 'ok'}>
                    {criterion.score === null ? 'NON SAISIE' : `${criterion.score}/${criterion.max}`}
                  </Badge>
                </h3>
                <div className="grille-2">
                  <Field
                    label={`${t('evaluation.score')} (0 – ${criterion.max})`}
                    htmlFor={`note-${criterion.key}`}
                  >
                    <input
                      id={`note-${criterion.key}`}
                      type="number"
                      min={0}
                      max={criterion.max}
                      value={draft.score}
                      onChange={(event) =>
                        setDrafts({ ...drafts, [criterion.key]: { ...draft, score: event.target.value } })
                      }
                    />
                  </Field>
                  <Field label={t('evaluation.sourcePages')} htmlFor={`pages-${criterion.key}`}>
                    <input
                      id={`pages-${criterion.key}`}
                      value={draft.pages}
                      onChange={(event) =>
                        setDrafts({ ...drafts, [criterion.key]: { ...draft, pages: event.target.value } })
                      }
                    />
                  </Field>
                </div>
                <Field label={t('evaluation.justification')} htmlFor={`justification-${criterion.key}`}>
                  <textarea
                    id={`justification-${criterion.key}`}
                    value={draft.justification}
                    onChange={(event) =>
                      setDrafts({
                        ...drafts,
                        [criterion.key]: { ...draft, justification: event.target.value },
                      })
                    }
                  />
                </Field>
                <button
                  type="button"
                  className="bouton-principal"
                  onClick={() =>
                    save(criterion.key, {
                      score: criterion.score,
                      justification: criterion.justification,
                      pages: criterion.source_pages,
                    })
                  }
                >
                  {t('common.save')}
                </button>
              </div>
            );
          })}
          <Notice tone={state.data.complete ? 'ok' : 'incertain'}>
            {state.data.complete
              ? `${t('evaluation.total')} : ${state.data.total}/${state.data.max_total} — ${state.data.notice}`
              : `${t('evaluation.incomplete')} ${state.data.notice}`}
          </Notice>
        </>
      )}
    </Card>
  );
}

export function AlertesTab({ dossierId, onChanged }: { dossierId: string; onChanged: () => void }) {
  const { t } = useLocale();
  const findings = useAsync(() => api.listFindings(dossierId), [dossierId]);
  const vocabulary = useAsync(() => api.vocabulary(), []);
  const [drafts, setDrafts] = useState<Record<string, { status: string; comment: string; relation: string }>>({});
  const [error, setError] = useState<unknown>(null);

  async function save(findingId: string, fallback: string) {
    const draft = drafts[findingId] ?? { status: fallback, comment: '', relation: '' };
    setError(null);
    try {
      await api.qualifyFinding(dossierId, findingId, {
        status: draft.status,
        comment: draft.comment,
        relation_kind: draft.relation || null,
      });
      findings.reload();
      onChanged();
    } catch (cause) {
      setError(cause);
    }
  }

  const items = findings.data?.items ?? [];
  const maroc = items.filter((item) => item.category === 'MENTIONS_MAROC');
  const others = items.filter((item) => item.category !== 'MENTIONS_MAROC');

  const renderFinding = (finding: (typeof items)[number]) => {
    const draft = drafts[finding.id] ?? {
      status: finding.human_status,
      comment: finding.human_comment ?? '',
      relation: finding.relation_kind ?? '',
    };
    return (
      <div key={finding.id} className="carte">
        <h3>
          <IconAlert /> {finding.label}
        </h3>
        <p className="actions">
          <Badge tone={finding.priority === 'CRITIQUE' ? 'critique' : 'incertain'}>
            {finding.priority}
          </Badge>
          <Badge>{finding.human_status}</Badge>
          <Badge tone="neutre">{finding.rule_code}</Badge>
          {finding.page_no !== null && <Badge tone="neutre">{`${t('common.page')} ${finding.page_no}`}</Badge>}
          {finding.confidence !== null && (
            <Badge tone="neutre">{`${t('common.confidence')} ${Math.round(finding.confidence * 100)} %`}</Badge>
          )}
        </p>
        <p>
          <strong>{t('alertes.trigger')} :</strong> {finding.trigger ?? '—'}
        </p>
        {finding.context && (
          <p>
            <strong>{t('alertes.context')} :</strong> <em>{finding.context}</em>
          </p>
        )}
        <p className="aide">{finding.explanation}</p>
        <p className="aide">
          <strong>{t('alertes.recommended')} :</strong> {finding.recommended_check}
        </p>
        {finding.source_ref && (
          <p className="aide">
            <strong>{t('common.source')} :</strong> {finding.source_ref}
          </p>
        )}
        <div className="grille-2">
          <Field label={t('alertes.humanStatus')} htmlFor={`statut-alerte-${finding.id}`}>
            <select
              id={`statut-alerte-${finding.id}`}
              value={draft.status}
              onChange={(event) =>
                setDrafts({ ...drafts, [finding.id]: { ...draft, status: event.target.value } })
              }
            >
              {(vocabulary.data?.finding_status ?? []).map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </Field>
          {finding.category === 'MENTIONS_MAROC' && (
            <Field label={t('alertes.relation')} htmlFor={`relation-${finding.id}`}>
              <select
                id={`relation-${finding.id}`}
                value={draft.relation}
                onChange={(event) =>
                  setDrafts({ ...drafts, [finding.id]: { ...draft, relation: event.target.value } })
                }
              >
                <option value="">{t('common.none')}</option>
                {(vocabulary.data?.maroc_relations ?? []).map((relation) => (
                  <option key={relation} value={relation}>
                    {relation}
                  </option>
                ))}
              </select>
            </Field>
          )}
        </div>
        <Field label={t('alertes.comment')} htmlFor={`commentaire-${finding.id}`}>
          <textarea
            id={`commentaire-${finding.id}`}
            value={draft.comment}
            onChange={(event) =>
              setDrafts({ ...drafts, [finding.id]: { ...draft, comment: event.target.value } })
            }
          />
        </Field>
        <button type="button" onClick={() => save(finding.id, finding.human_status)}>
          {t('common.save')}
        </button>
      </div>
    );
  };

  return (
    <>
      <Card
        title={t('tab.alertes')}
        actions={
          <button
            type="button"
            onClick={async () => {
              await api.rescanFindings(dossierId);
              findings.reload();
              onChanged();
            }}
          >
            {t('alertes.rescan')}
          </button>
        }
      >
        {findings.data && <Notice tone="incertain">{findings.data.notice}</Notice>}
        <ErrorBanner error={error} />
        {findings.loading && <Loading label={t('common.loading')} />}
      </Card>

      <Card title={t('alertes.maroc')}>
        <Notice tone="incertain">{t('alertes.marocNotice')}</Notice>
        {maroc.length === 0 ? <Empty>{t('common.none')}</Empty> : maroc.map(renderFinding)}
      </Card>

      <Card title={t('tab.alertes')}>
        {others.length === 0 ? <Empty>{t('common.none')}</Empty> : others.map(renderFinding)}
      </Card>
    </>
  );
}

export function NotesTab({ dossierId, onChanged }: { dossierId: string; onChanged: () => void }) {
  const { t } = useLocale();
  const notes = useAsync(() => api.listNotes(dossierId), [dossierId]);
  const vocabulary = useAsync(() => api.vocabulary(), []);
  const [note, setNote] = useState({ body: '', kind: 'NOTE' });
  const [conclusion, setConclusion] = useState({ conclusion: '', motivation: '' });
  const [error, setError] = useState<unknown>(null);

  return (
    <>
      <Card title={t('notes.add')}>
        <ErrorBanner error={error} />
        <Field label={t('notes.kind')} htmlFor="note-type">
          <select
            id="note-type"
            value={note.kind}
            onChange={(event) => setNote({ ...note, kind: event.target.value })}
          >
            <option value="NOTE">NOTE</option>
            <option value="RESERVE">RESERVE</option>
            <option value="QUESTION">QUESTION</option>
          </select>
        </Field>
        <Field label={t('notes.body')} htmlFor="note-corps">
          <textarea
            id="note-corps"
            value={note.body}
            onChange={(event) => setNote({ ...note, body: event.target.value })}
          />
        </Field>
        <button
          type="button"
          className="bouton-principal"
          onClick={async () => {
            setError(null);
            try {
              await api.addNote(dossierId, note);
              setNote({ body: '', kind: note.kind });
              notes.reload();
              onChanged();
            } catch (cause) {
              setError(cause);
            }
          }}
        >
          {t('common.save')}
        </button>
      </Card>

      <Card title={t('notes.conclusion')}>
        <Notice tone="incertain">{t('notes.personalNotice')}</Notice>
        <Field label={t('notes.conclusion')} htmlFor="conclusion-choix">
          <select
            id="conclusion-choix"
            value={conclusion.conclusion}
            onChange={(event) => setConclusion({ ...conclusion, conclusion: event.target.value })}
          >
            <option value="">{t('common.none')}</option>
            {(vocabulary.data?.conclusions ?? []).map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t('notes.motivation')} htmlFor="conclusion-motivation">
          <textarea
            id="conclusion-motivation"
            value={conclusion.motivation}
            onChange={(event) => setConclusion({ ...conclusion, motivation: event.target.value })}
          />
        </Field>
        <button
          type="button"
          className="bouton-principal"
          disabled={!conclusion.conclusion}
          onClick={async () => {
            setError(null);
            try {
              await api.setConclusion(dossierId, conclusion);
              notes.reload();
              onChanged();
            } catch (cause) {
              setError(cause);
            }
          }}
        >
          {t('common.save')}
        </button>
      </Card>

      <Card title={t('tab.notes')}>
        {notes.loading && <Loading label={t('common.loading')} />}
        {(notes.data?.items ?? []).length === 0 && !notes.loading && <Empty>{t('common.none')}</Empty>}
        <ul>
          {(notes.data?.items ?? []).map((entry) => (
            <li key={entry.id}>
              <Badge>{entry.kind}</Badge> {entry.conclusion && <Badge tone="neutre">{entry.conclusion}</Badge>}{' '}
              {entry.body} <span className="aide">— {new Date(entry.created_at).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}

export function RapportsTab({ dossierId, onChanged }: { dossierId: string; onChanged: () => void }) {
  const { t } = useLocale();
  const reports = useAsync(() => api.listReports(dossierId), [dossierId]);
  const [statement, setStatement] = useState('');
  const [layout, setLayout] = useState('harmonise');
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function generate(format: string, official: boolean) {
    setError(null);
    setMessage(null);
    try {
      const created = await api.generateReport(dossierId, { format, official, layout });
      const pages = created.page_count ? ` — ${created.page_count} page(s)` : '';
      setMessage(
        `${format.toUpperCase()} v${created.version}${pages} — SHA-256 ${created.sha256.slice(0, 16)}… — ` +
          t('rapports.downloadStarted'),
      );
      // Le rapport se télécharge dès qu'il est produit : le retrouver dans la
      // liste plus bas était une étape de trop.
      triggerDownload(api.reportUrl(dossierId, created.id));
      reports.reload();
      onChanged();
    } catch (cause) {
      setError(cause);
    }
  }

  function triggerDownload(url: string) {
    const link = document.createElement('a');
    link.href = url;
    link.download = '';
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  return (
    <>
      <Card title={t('rapports.generate')}>
        <Notice tone="incertain">{t('rapports.banner')}</Notice>
        <ErrorBanner error={error} />
        {message && <Notice tone="ok">{message}</Notice>}
        <Field label={t('rapports.layout')} htmlFor="rapport-mise-en-page">
          <select
            id="rapport-mise-en-page"
            value={layout}
            onChange={(event) => setLayout(event.target.value)}
          >
            <option value="harmonise">{t('rapports.layoutHarmonise')}</option>
            <option value="compact">{t('rapports.layoutCompact')}</option>
            <option value="detaille">{t('rapports.layoutDetaille')}</option>
          </select>
        </Field>
        <div className="actions">
          <button type="button" className="bouton-principal" onClick={() => generate('docx', false)}>
            {t('rapports.getDocx')}
          </button>
          <button type="button" className="bouton-principal" onClick={() => generate('pdf', false)}>
            {t('rapports.getPdf')}
          </button>
        </div>
        <p className="aide">{t('rapports.draftExplained')}</p>

        <details>
          <summary>{t('rapports.officialSummary')}</summary>
          <p className="aide">{t('rapports.officialExplained')}</p>
          <div className="actions">
            <button type="button" onClick={() => generate('docx', true)}>
              DOCX — {t('rapports.official')}
            </button>
            <button type="button" onClick={() => generate('pdf', true)}>
              PDF — {t('rapports.official')}
            </button>
          </div>
        </details>
      </Card>

      <Card title={t('rapports.validate')}>
        <Field label={t('rapports.statement')} htmlFor="validation-declaration">
          <textarea
            id="validation-declaration"
            value={statement}
            onChange={(event) => setStatement(event.target.value)}
          />
        </Field>
        <button
          type="button"
          className="bouton-principal"
          onClick={async () => {
            setError(null);
            try {
              await api.validateReport(dossierId, statement);
              setMessage('Validation humaine enregistrée (porte G7).');
              onChanged();
            } catch (cause) {
              setError(cause);
            }
          }}
        >
          {t('common.save')}
        </button>
      </Card>

      <Card title={t('tab.rapports')}>
        {reports.loading && <Loading label={t('common.loading')} />}
        {(reports.data?.items ?? []).length === 0 && !reports.loading && <Empty>{t('common.none')}</Empty>}
        <div className="tableau-conteneur">
          <table>
            <thead>
              <tr>
                <th scope="col">Version</th>
                <th scope="col">Format</th>
                <th scope="col">{t('common.status')}</th>
                <th scope="col">SHA-256</th>
                <th scope="col">{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {(reports.data?.items ?? []).map((report) => (
                <tr key={report.id}>
                  <td>v{report.version}</td>
                  <td>{report.format.toUpperCase()}</td>
                  <td>
                    <Badge tone={report.is_draft ? 'incertain' : 'ok'}>
                      {report.is_draft ? t('rapports.draft') : t('rapports.official')}
                    </Badge>
                  </td>
                  <td className="mono">{report.sha256.slice(0, 20)}…</td>
                  <td>
                    <a
                      className="bouton-discret"
                      href={api.reportUrl(dossierId, report.id)}
                      download
                    >
                      ⬇ {t('rapports.download')}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

export function HistoriqueTab({ dossierId }: { dossierId: string }) {
  const { t } = useLocale();
  const history = useAsync(() => api.history(dossierId), [dossierId]);

  return (
    <Card title={t('tab.historique')}>
      {history.data && <Notice>{history.data.notice}</Notice>}
      {history.loading && <Loading label={t('common.loading')} />}
      <div className="tableau-conteneur">
        <table>
          <thead>
            <tr>
              <th scope="col">{t('historique.date')}</th>
              <th scope="col">{t('historique.action')}</th>
              <th scope="col">{t('historique.summary')}</th>
              <th scope="col">Empreinte</th>
              <th scope="col">{t('historique.actor')}</th>
            </tr>
          </thead>
          <tbody>
            {(history.data?.items ?? []).map((entry) => (
              <tr key={entry.id}>
                <td>{new Date(entry.created_at).toLocaleString()}</td>
                <td>
                  <Badge tone="neutre">{entry.action}</Badge>
                </td>
                <td>{entry.summary}</td>
                <td className="mono">{entry.fingerprint ? `${entry.fingerprint.slice(0, 22)}…` : '—'}</td>
                <td>{entry.actor_label}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
