/**
 * Onglet « Recherche Web et ranking ».
 *
 * Chaque requête est relue et approuvée par l'évaluateur avant tout envoi.
 * Le classement externe est indicatif et strictement séparé de la grille
 * scientifique officielle.
 */

import { useState } from 'react';

import { api } from '../services/api';
import type { WebRunDetail } from '../services/api';
import {
  Badge,
  Card,
  Empty,
  ErrorBanner,
  Field,
  IconGlobe,
  IconShield,
  Loading,
  Notice,
  useAsync,
  useLocale,
} from '../components/ui';

export function WebRankingTab({ dossierId, onChanged }: { dossierId: string; onChanged: () => void }) {
  const { t } = useLocale();
  const connectivity = useAsync(() => api.connectivity(), []);
  const runs = useAsync(() => api.listWebRuns(dossierId), [dossierId]);
  const ranking = useAsync(() => api.ranking(dossierId), [dossierId]);

  const [detail, setDetail] = useState<WebRunDetail | null>(null);
  const [scopeNote, setScopeNote] = useState('');
  const [approver, setApprover] = useState('Prof. Merzoug Mohamed');
  const [queryDrafts, setQueryDrafts] = useState<Record<string, string>>({});
  const [dismissal, setDismissal] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function guarded(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  }

  const online = connectivity.data?.online ?? false;

  return (
    <>
      <Card
        title={
          <>
            <IconGlobe /> {t('web.title')}
          </>
        }
      >
        <Notice tone="ok">
          <IconShield /> {t('web.noUpload')}
        </Notice>
        {!online && <Notice tone="incertain">{t('web.unavailable')}</Notice>}
        <ErrorBanner error={error} />
        {message && <Notice tone="ok">{message}</Notice>}

        {connectivity.data && (
          <p className="aide">
            <Badge tone={online ? 'ok' : 'incertain'}>
              {online ? t('dashboard.online') : t('dashboard.offline')}
            </Badge>{' '}
            {connectivity.data.reason} — domaines autorisés :{' '}
            <span className="mono">{connectivity.data.egress.allowed_domains.join(', ')}</span>
          </p>
        )}

        <Field label={t('web.scopeNote')} htmlFor="web-perimetre">
          <textarea
            id="web-perimetre"
            value={scopeNote}
            onChange={(event) => setScopeNote(event.target.value)}
          />
        </Field>
        <button
          type="button"
          className="bouton-principal"
          disabled={busy}
          onClick={() =>
            guarded(async () => {
              const prepared = await api.prepareWebRun(dossierId, scopeNote);
              setDetail(prepared);
              runs.reload();
              onChanged();
            })
          }
        >
          {t('web.prepare')}
        </button>
      </Card>

      {runs.data && (
        <Card title="Campagnes">
          <Notice tone={runs.data.enriched_state.complete ? 'ok' : 'incertain'}>
            {runs.data.enriched_state.message}
          </Notice>
          {runs.data.items.length === 0 ? (
            <Empty>{t('common.none')}</Empty>
          ) : (
            <ul>
              {runs.data.items.map((run) => (
                <li key={run.id}>
                  <Badge>{run.status}</Badge>{' '}
                  <button
                    type="button"
                    className="bouton-discret"
                    onClick={() => guarded(async () => setDetail(await api.getWebRun(run.id)))}
                  >
                    {run.id.slice(0, 8)}… — {new Date(run.created_at).toLocaleString()}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              guarded(async () => {
                await api.markEnrichedComplete(dossierId);
                runs.reload();
                onChanged();
              })
            }
          >
            {t('web.markComplete')}
          </button>
        </Card>
      )}

      {detail && (
        <>
          <Card title={t('web.queries')}>
            <Notice tone="incertain">
              Relisez et modifiez chaque requête : seul le texte approuvé quitte le poste.
            </Notice>
            <div className="tableau-conteneur">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Sujet</th>
                    <th scope="col">Requête</th>
                    <th scope="col">Objet</th>
                    <th scope="col">{t('common.status')}</th>
                    <th scope="col">{t('common.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.queries.map((query) => (
                    <tr key={query.id}>
                      <td>
                        <Badge tone="neutre">{query.subject_kind}</Badge> {query.subject_label}
                      </td>
                      <td>
                        <input
                          aria-label={`Requête — ${query.subject_label}`}
                          value={queryDrafts[query.id] ?? query.query_text}
                          onChange={(event) =>
                            setQueryDrafts({ ...queryDrafts, [query.id]: event.target.value })
                          }
                        />
                      </td>
                      <td className="aide">{query.purpose}</td>
                      <td>
                        <Badge tone={query.approved ? 'ok' : 'incertain'}>
                          {query.approved ? 'APPROUVEE' : 'A_RELIRE'}
                        </Badge>
                        {query.error_message && <p className="aide">{query.error_message}</p>}
                      </td>
                      <td>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() =>
                            guarded(async () => {
                              await api.editWebQuery(
                                detail.id,
                                query.id,
                                queryDrafts[query.id] ?? query.query_text,
                                true,
                              );
                              setDetail(await api.getWebRun(detail.id));
                            })
                          }
                        >
                          {t('web.approveQuery')}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Field label="Approbateur" htmlFor="web-approbateur">
              <input
                id="web-approbateur"
                value={approver}
                onChange={(event) => setApprover(event.target.value)}
              />
            </Field>
            <div className="actions">
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  guarded(async () => {
                    await api.approveWebRun(detail.id, approver);
                    setDetail(await api.getWebRun(detail.id));
                  })
                }
              >
                {t('web.approveRun')}
              </button>
              <button
                type="button"
                className="bouton-principal"
                disabled={busy}
                onClick={() =>
                  guarded(async () => {
                    const result = await api.executeWebRun(detail.id);
                    setMessage(result.message);
                    setDetail(await api.getWebRun(detail.id));
                    ranking.reload();
                    runs.reload();
                    onChanged();
                  })
                }
              >
                {t('web.execute')}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  guarded(async () => {
                    await api.setWebRunStatus(detail.id, 'EN_PAUSE');
                    setDetail(await api.getWebRun(detail.id));
                  })
                }
              >
                {t('web.pause')}
              </button>
            </div>

            <Field label={t('web.dismiss')} htmlFor="web-ecart">
              <input
                id="web-ecart"
                value={dismissal}
                onChange={(event) => setDismissal(event.target.value)}
              />
            </Field>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                guarded(async () => {
                  await api.setWebRunStatus(detail.id, 'ECARTEE_PAR_HUMAIN', dismissal);
                  setDetail(await api.getWebRun(detail.id));
                  runs.reload();
                })
              }
            >
              {t('web.dismiss')}
            </button>
          </Card>

          <Card title={t('web.sources')}>
            {detail.sources.length === 0 ? (
              <Empty>{t('common.none')}</Empty>
            ) : (
              <div className="tableau-conteneur">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Palier</th>
                      <th scope="col">Titre</th>
                      <th scope="col">URL</th>
                      <th scope="col">Publiée</th>
                      <th scope="col">Consultée</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.sources.map((source) => (
                      <tr key={source.id}>
                        <td>
                          <Badge tone="neutre">{source.tier}</Badge>
                        </td>
                        <td>{source.title}</td>
                        <td className="mono">{source.url}</td>
                        <td>{source.published_on ?? '—'}</td>
                        <td>{new Date(source.consulted_at).toLocaleDateString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title={t('web.claims')}>
            <Notice tone="incertain">{detail.notice}</Notice>
            {detail.claims.length === 0 ? (
              <Empty>{t('common.none')}</Empty>
            ) : (
              detail.claims.map((claim) => (
                <div key={claim.id} className="carte">
                  <p className="actions">
                    <Badge tone="neutre">{claim.agent_name}</Badge>
                    <Badge>{claim.nature}</Badge>
                    <Badge>{claim.status}</Badge>
                    <Badge tone="neutre">{`${claim.independent_source_count} source(s)`}</Badge>
                  </p>
                  <p>{claim.statement}</p>
                  {claim.sources.length > 0 && (
                    <ul className="aide">
                      {claim.sources.map((url) => (
                        <li key={url} className="mono">
                          {url}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))
            )}
          </Card>
        </>
      )}

      <Card title={t('web.ranking')}>
        <Notice tone="incertain">{t('web.rankingNotice')}</Notice>
        {ranking.loading && <Loading label={t('common.loading')} />}
        {ranking.data?.ranking === null && <Empty>{ranking.data.message}</Empty>}
        {ranking.data?.ranking && (
          <>
            <p className="actions">
              <Badge tone={ranking.data.ranking.grade === 'NR' ? 'incertain' : 'ok'}>
                {ranking.data.ranking.grade}
              </Badge>
              <Badge tone="neutre">
                {ranking.data.ranking.total === null
                  ? t('web.notProvided')
                  : `${ranking.data.ranking.total}/100`}
              </Badge>
            </p>
            {ranking.data.ranking.blocked_reason && (
              <Notice tone="critique">{ranking.data.ranking.blocked_reason}</Notice>
            )}
            <div className="tableau-conteneur">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Axe</th>
                    <th scope="col">Proposition</th>
                    <th scope="col">Incertitude</th>
                    <th scope="col">Justification sourcée</th>
                    <th scope="col">{t('web.axisDecision')}</th>
                  </tr>
                </thead>
                <tbody>
                  {ranking.data.ranking.axes.map((axis) => (
                    <tr key={axis.id}>
                      <td>
                        {axis.label} <span className="aide">/ {axis.max}</span>
                      </td>
                      <td>
                        <Badge tone={axis.not_provided ? 'incertain' : 'neutre'}>
                          {axis.not_provided ? t('web.notProvided') : String(axis.display_score)}
                        </Badge>
                      </td>
                      <td className="aide">
                        {axis.uncertainty_low === null
                          ? '—'
                          : `${axis.uncertainty_low} – ${axis.uncertainty_high}`}
                      </td>
                      <td className="aide">
                        {axis.justification} ({axis.sources.length} source(s))
                      </td>
                      <td>
                        <Badge>{axis.human_decision}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {ranking.data.ranking.disagreements.length > 0 && (
              <>
                <h3>{t('web.disagreement')}</h3>
                <ul>
                  {ranking.data.ranking.disagreements.map((item, index) => (
                    <li key={index}>{item.description}</li>
                  ))}
                </ul>
              </>
            )}
            <Notice>{ranking.data.ranking.separation_notice}</Notice>
          </>
        )}
      </Card>
    </>
  );
}
