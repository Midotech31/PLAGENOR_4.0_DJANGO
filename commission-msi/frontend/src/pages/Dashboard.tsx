/** Tableau de bord : ouverture directe, sans compte ni écran de connexion. */

import { useState } from 'react';

import { api } from '../services/api';
import type { DossierSummary } from '../services/api';
import {
  Badge,
  Card,
  Empty,
  ErrorBanner,
  Field,
  IconGlobe,
  Loading,
  Notice,
  useAsync,
  useLocale,
} from '../components/ui';

export function Dashboard({ onOpen }: { onOpen: (id: string) => void }) {
  const { t } = useLocale();
  const [filters, setFilters] = useState({ status: '', organizer: '', priority: '', search: '' });
  const [form, setForm] = useState({ reference: '', title: '', organizer: '' });
  const [creationError, setCreationError] = useState<unknown>(null);

  const dashboard = useAsync(() => api.dashboard(), []);
  const vocabulary = useAsync(() => api.vocabulary(), []);
  const connectivity = useAsync(() => api.connectivity(), []);
  const dossiers = useAsync(
    () => api.listDossiers(filters as unknown as Record<string, string>),
    [filters.status, filters.organizer, filters.priority, filters.search],
  );

  async function createDossier(event: React.FormEvent) {
    event.preventDefault();
    setCreationError(null);
    try {
      const created = await api.createDossier(form);
      setForm({ reference: '', title: '', organizer: '' });
      dossiers.reload();
      dashboard.reload();
      onOpen(created.id);
    } catch (error) {
      setCreationError(error);
    }
  }

  return (
    <>
      <h1>{t('dashboard.title')}</h1>
      <Notice>{t('app.principle')}</Notice>

      {dashboard.loading && <Loading label={t('common.loading')} />}
      <ErrorBanner error={dashboard.error} />

      {dashboard.data && (
        <>
          <div className="grille" style={{ marginBottom: '1rem' }}>
            <Stat value={dashboard.data.open_findings} label={t('dashboard.openFindings')} />
            <Stat value={dashboard.data.pages_needing_ocr} label={t('dashboard.pagesNeedingOcr')} />
            <Stat value={dashboard.data.missing_pieces} label={t('dashboard.missingPieces')} />
            <Stat value={dashboard.data.reports_generated} label={t('dashboard.reports')} />
          </div>
          <Notice tone="incertain">{dashboard.data.notice}</Notice>
        </>
      )}

      {connectivity.data && (
        <Card
          title={
            <>
              <IconGlobe /> {t('dashboard.connectivity')}
            </>
          }
        >
          <p>
            <Badge tone={connectivity.data.online ? 'ok' : 'incertain'}>
              {connectivity.data.online ? t('dashboard.online') : t('dashboard.offline')}
            </Badge>{' '}
            {connectivity.data.reason}
          </p>
          {!connectivity.data.online && <Notice tone="incertain">{t('web.unavailable')}</Notice>}
          <p className="aide">
            {t('dashboard.providers')} :{' '}
            {connectivity.data.providers.length === 0
              ? t('common.none')
              : connectivity.data.providers
                  .map((provider) => `${provider.name} (${provider.enabled ? 'actif' : 'désactivé'})`)
                  .join(', ')}
          </p>
          <p className="aide">{connectivity.data.egress.notice}</p>
        </Card>
      )}

      <div className="grille-2">
        <Card title={t('dashboard.filters')}>
          <Field label={t('dashboard.search')} htmlFor="filtre-recherche">
            <input
              id="filtre-recherche"
              type="search"
              value={filters.search}
              onChange={(event) => setFilters({ ...filters, search: event.target.value })}
            />
          </Field>
          <Field label={t('dashboard.status')} htmlFor="filtre-statut">
            <select
              id="filtre-statut"
              value={filters.status}
              onChange={(event) => setFilters({ ...filters, status: event.target.value })}
            >
              <option value="">{t('dashboard.all')}</option>
              {vocabulary.data?.dossier_status.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t('dashboard.organizer')} htmlFor="filtre-organisateur">
            <input
              id="filtre-organisateur"
              value={filters.organizer}
              onChange={(event) => setFilters({ ...filters, organizer: event.target.value })}
            />
          </Field>
          <Field label={t('dashboard.priority')} htmlFor="filtre-priorite">
            <select
              id="filtre-priorite"
              value={filters.priority}
              onChange={(event) => setFilters({ ...filters, priority: event.target.value })}
            >
              <option value="">{t('dashboard.all')}</option>
              {vocabulary.data?.priority.map((priority) => (
                <option key={priority} value={priority}>
                  {priority}
                </option>
              ))}
            </select>
          </Field>
        </Card>

        <Card title={t('dashboard.newDossier')}>
          <form onSubmit={createDossier}>
            <Field label={t('dashboard.reference')} htmlFor="nouveau-reference">
              <input
                id="nouveau-reference"
                required
                value={form.reference}
                onChange={(event) => setForm({ ...form, reference: event.target.value })}
              />
            </Field>
            <Field label={t('dashboard.dossierTitle')} htmlFor="nouveau-titre">
              <input
                id="nouveau-titre"
                required
                value={form.title}
                onChange={(event) => setForm({ ...form, title: event.target.value })}
              />
            </Field>
            <Field label={t('dashboard.organizer')} htmlFor="nouveau-organisateur">
              <input
                id="nouveau-organisateur"
                required
                value={form.organizer}
                onChange={(event) => setForm({ ...form, organizer: event.target.value })}
              />
            </Field>
            <ErrorBanner error={creationError} />
            <button type="submit" className="bouton-principal">
              {t('dashboard.create')}
            </button>
          </form>
        </Card>
      </div>

      <Card title={t('dashboard.recent')}>
        {dossiers.loading && <Loading label={t('common.loading')} />}
        <ErrorBanner error={dossiers.error} />
        {dossiers.data && dossiers.data.items.length === 0 && <Empty>{t('dashboard.empty')}</Empty>}
        {dossiers.data && dossiers.data.items.length > 0 && (
          <div className="tableau-conteneur">
            <table>
              <caption className="aide">{t('dashboard.recent')}</caption>
              <thead>
                <tr>
                  <th scope="col">{t('dashboard.reference')}</th>
                  <th scope="col">{t('dashboard.dossierTitle')}</th>
                  <th scope="col">{t('dashboard.organizer')}</th>
                  <th scope="col">{t('dossier.status')}</th>
                  <th scope="col">{t('dossier.pages')}</th>
                  <th scope="col">{t('dossier.openFindings')}</th>
                  <th scope="col">{t('dossier.score')}</th>
                  <th scope="col">{t('common.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {dossiers.data.items.map((item: DossierSummary) => (
                  <tr key={item.id}>
                    <td className="mono">{item.reference}</td>
                    <td>{item.title}</td>
                    <td>{item.organizer}</td>
                    <td>
                      <Badge>{item.status}</Badge>
                    </td>
                    <td>{item.page_count}</td>
                    <td>{item.open_findings}</td>
                    <td>
                      {item.score_total === null ? '—' : `${item.score_total}/${item.score_max}`}
                    </td>
                    <td>
                      <button type="button" className="bouton-discret" onClick={() => onOpen(item.id)}>
                        {t('common.actions')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div className="statistique">
      <div className="valeur">{value}</div>
      <div className="libelle">{label}</div>
    </div>
  );
}
