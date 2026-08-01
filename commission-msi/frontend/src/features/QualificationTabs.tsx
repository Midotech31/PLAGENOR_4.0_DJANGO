/** Onglets « Pièces », « Informations » et « Contrôle administratif ». */

import { useState } from 'react';

import { api } from '../services/api';
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

export function PiecesTab({ dossierId, onChanged }: { dossierId: string; onChanged: () => void }) {
  const { t } = useLocale();
  const pieces = useAsync(() => api.listPieces(dossierId), [dossierId]);
  const vocabulary = useAsync(() => api.vocabulary(), []);
  const [drafts, setDrafts] = useState<Record<string, { status: string; comment: string }>>({});
  const [error, setError] = useState<unknown>(null);

  async function save(pieceId: string, currentStatus: string) {
    const draft = drafts[pieceId] ?? { status: currentStatus, comment: '' };
    setError(null);
    try {
      await api.updatePiece(dossierId, pieceId, draft);
      pieces.reload();
      onChanged();
    } catch (cause) {
      setError(cause);
    }
  }

  return (
    <Card title={t('tab.pieces')}>
      {pieces.data && <Notice tone="incertain">{pieces.data.notice}</Notice>}
      <ErrorBanner error={error} />
      {pieces.loading && <Loading label={t('common.loading')} />}
      <div className="tableau-conteneur">
        <table>
          <thead>
            <tr>
              <th scope="col">{t('common.label')}</th>
              <th scope="col">{t('common.status')}</th>
              <th scope="col">{t('common.source')}</th>
              <th scope="col">{t('pieces.comment')}</th>
              <th scope="col">{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {(pieces.data?.items ?? []).map((piece) => {
              const draft = drafts[piece.id] ?? { status: piece.status, comment: piece.comment ?? '' };
              return (
                <tr key={piece.id}>
                  <td>
                    {piece.label}
                    {piece.sensitivity === 'RESTREINT' && (
                      <>
                        <br />
                        <Badge tone="incertain">{t('pieces.restricted')}</Badge>
                      </>
                    )}
                  </td>
                  <td>
                    <Badge>{piece.status}</Badge>
                    <select
                      aria-label={`${t('common.status')} — ${piece.label}`}
                      value={draft.status}
                      onChange={(event) =>
                        setDrafts({ ...drafts, [piece.id]: { ...draft, status: event.target.value } })
                      }
                    >
                      {(vocabulary.data?.piece_status ?? []).map((status) => (
                        <option key={status} value={status}>
                          {status}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    {piece.detected_page_no ? `${t('common.page')} ${piece.detected_page_no}` : '—'}
                    {piece.detection_excerpt && <p className="aide">{piece.detection_excerpt}</p>}
                  </td>
                  <td>
                    <textarea
                      aria-label={`${t('pieces.comment')} — ${piece.label}`}
                      value={draft.comment}
                      onChange={(event) =>
                        setDrafts({ ...drafts, [piece.id]: { ...draft, comment: event.target.value } })
                      }
                    />
                  </td>
                  <td>
                    <button type="button" onClick={() => save(piece.id, piece.status)}>
                      {t('common.save')}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function InformationsTab({
  dossierId,
  onChanged,
}: {
  dossierId: string;
  onChanged: () => void;
}) {
  const { t } = useLocale();
  const items = useAsync(() => api.listItems(dossierId), [dossierId]);
  const vocabulary = useAsync(() => api.vocabulary(), []);
  const [drafts, setDrafts] = useState<
    Record<string, { value: string; status: string; reason: string; page: string; excerpt: string; manual: boolean }>
  >({});
  const [error, setError] = useState<unknown>(null);

  async function save(itemId: string, fallback: { value: string; status: string }) {
    const draft =
      drafts[itemId] ??
      { value: fallback.value, status: fallback.status, reason: '', page: '', excerpt: '', manual: false };
    setError(null);
    try {
      await api.updateItem(dossierId, itemId, {
        value: draft.value,
        status: draft.status,
        reason: draft.reason,
        page_no: draft.page ? Number(draft.page) : null,
        source_excerpt: draft.excerpt || null,
        manual_entry_validated: draft.manual,
      });
      items.reload();
      onChanged();
    } catch (cause) {
      setError(cause);
    }
  }

  return (
    <Card title={t('tab.informations')}>
      {items.data && <Notice tone="incertain">{items.data.notice}</Notice>}
      <ErrorBanner error={error} />
      {items.loading && <Loading label={t('common.loading')} />}
      {(items.data?.items ?? []).map((item) => {
        const draft =
          drafts[item.id] ?? {
            value: item.current_value ?? '',
            status: item.status,
            reason: '',
            page: item.page_no ? String(item.page_no) : '',
            excerpt: item.source_excerpt ?? '',
            manual: item.manual_entry_validated,
          };
        return (
          <details key={item.id} className="carte">
            <summary>
              <strong>{item.label}</strong> <Badge>{item.status}</Badge>{' '}
              {item.reinforced_control && <Badge tone="incertain">{t('informations.reinforced')}</Badge>}
            </summary>
            {item.initial_value && (
              <p className="aide">
                {t('informations.initial')} : {item.initial_value}
              </p>
            )}
            <Field label={t('informations.value')} htmlFor={`valeur-${item.id}`}>
              <input
                id={`valeur-${item.id}`}
                value={draft.value}
                onChange={(event) => setDrafts({ ...drafts, [item.id]: { ...draft, value: event.target.value } })}
              />
            </Field>
            <div className="grille-2">
              <Field label={t('common.status')} htmlFor={`statut-${item.id}`}>
                <select
                  id={`statut-${item.id}`}
                  value={draft.status}
                  onChange={(event) =>
                    setDrafts({ ...drafts, [item.id]: { ...draft, status: event.target.value } })
                  }
                >
                  {(vocabulary.data?.information_status ?? []).map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t('informations.sourcePage')} htmlFor={`page-${item.id}`}>
                <input
                  id={`page-${item.id}`}
                  type="number"
                  min={1}
                  value={draft.page}
                  onChange={(event) => setDrafts({ ...drafts, [item.id]: { ...draft, page: event.target.value } })}
                />
              </Field>
            </div>
            <Field label={t('informations.excerpt')} htmlFor={`extrait-${item.id}`}>
              <textarea
                id={`extrait-${item.id}`}
                value={draft.excerpt}
                onChange={(event) => setDrafts({ ...drafts, [item.id]: { ...draft, excerpt: event.target.value } })}
              />
            </Field>
            <Field label={t('alertes.comment')} htmlFor={`motif-${item.id}`}>
              <input
                id={`motif-${item.id}`}
                value={draft.reason}
                onChange={(event) => setDrafts({ ...drafts, [item.id]: { ...draft, reason: event.target.value } })}
              />
            </Field>
            <label htmlFor={`manuel-${item.id}`}>
              <input
                id={`manuel-${item.id}`}
                type="checkbox"
                style={{ width: 'auto', marginInlineEnd: '0.4rem' }}
                checked={draft.manual}
                onChange={(event) => setDrafts({ ...drafts, [item.id]: { ...draft, manual: event.target.checked } })}
              />
              {t('informations.manual')}
            </label>
            <p>
              <button
                type="button"
                className="bouton-principal"
                onClick={() => save(item.id, { value: item.current_value ?? '', status: item.status })}
              >
                {t('common.save')}
              </button>
            </p>
          </details>
        );
      })}
    </Card>
  );
}

export function ControleTab({ dossierId, onChanged }: { dossierId: string; onChanged: () => void }) {
  const { t } = useLocale();
  const checks = useAsync(() => api.listChecks(dossierId), [dossierId]);
  const vocabulary = useAsync(() => api.vocabulary(), []);
  const [drafts, setDrafts] = useState<Record<string, { status: string; explanation: string }>>({});
  const [error, setError] = useState<unknown>(null);

  async function save(checkId: string, fallback: string) {
    const draft = drafts[checkId] ?? { status: fallback, explanation: '' };
    setError(null);
    try {
      await api.updateCheck(dossierId, checkId, draft);
      checks.reload();
      onChanged();
    } catch (cause) {
      setError(cause);
    }
  }

  return (
    <Card title={t('tab.controle')}>
      {checks.data && <Notice>{checks.data.notice}</Notice>}
      <ErrorBanner error={error} />
      {checks.loading && <Loading label={t('common.loading')} />}
      {(checks.data?.items ?? []).length === 0 && !checks.loading && <Empty>{t('common.none')}</Empty>}
      <div className="tableau-conteneur">
        <table>
          <thead>
            <tr>
              <th scope="col">{t('common.label')}</th>
              <th scope="col">{t('common.status')}</th>
              <th scope="col">{t('alertes.comment')}</th>
              <th scope="col">{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {(checks.data?.items ?? []).map((check) => {
              const draft = drafts[check.id] ?? {
                status: check.status,
                explanation: check.explanation ?? '',
              };
              return (
                <tr key={check.id}>
                  <td>{check.label}</td>
                  <td>
                    <Badge>{check.status}</Badge>
                    <select
                      aria-label={`${t('common.status')} — ${check.label}`}
                      value={draft.status}
                      onChange={(event) =>
                        setDrafts({ ...drafts, [check.id]: { ...draft, status: event.target.value } })
                      }
                    >
                      {(vocabulary.data?.control_status ?? []).map((status) => (
                        <option key={status} value={status}>
                          {status}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <textarea
                      aria-label={`${t('alertes.comment')} — ${check.label}`}
                      value={draft.explanation}
                      onChange={(event) =>
                        setDrafts({ ...drafts, [check.id]: { ...draft, explanation: event.target.value } })
                      }
                    />
                  </td>
                  <td>
                    <button type="button" onClick={() => save(check.id, check.status)}>
                      {t('common.save')}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
