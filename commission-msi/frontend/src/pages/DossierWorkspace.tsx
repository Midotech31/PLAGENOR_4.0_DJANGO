/** Espace dossier : en-tête permanent et dix onglets. */

import { useState } from 'react';

import { api } from '../services/api';
import {
  Badge,
  Card,
  ErrorBanner,
  Loading,
  Notice,
  TabPanel,
  Tabs,
  useAsync,
  useLocale,
} from '../components/ui';
import { DocumentTab } from '../features/DocumentTab';
import { ControleTab, InformationsTab, PiecesTab } from '../features/QualificationTabs';
import {
  AlertesTab,
  EvaluationTab,
  HistoriqueTab,
  NotesTab,
  RapportsTab,
} from '../features/AssessmentTabs';
import { WebRankingTab } from '../features/WebRankingTab';

const TAB_IDS = [
  'document',
  'pieces',
  'informations',
  'controle',
  'evaluation',
  'alertes',
  'notes',
  'rapports',
  'web',
  'historique',
] as const;

type TabId = (typeof TAB_IDS)[number];

export function DossierWorkspace({ dossierId, onBack }: { dossierId: string; onBack: () => void }) {
  const { t } = useLocale();
  const [active, setActive] = useState<TabId>('document');
  const dossier = useAsync(() => api.getDossier(dossierId), [dossierId]);

  const reload = () => dossier.reload();

  return (
    <>
      <p>
        <button type="button" className="bouton-discret" onClick={onBack}>
          ← {t('nav.back')}
        </button>
      </p>

      {dossier.loading && <Loading label={t('common.loading')} />}
      <ErrorBanner error={dossier.error} />

      {dossier.data && (
        <>
          <Card>
            <h1>{dossier.data.title}</h1>
            <p className="actions">
              <Badge tone="neutre">{dossier.data.reference}</Badge>
              <Badge tone="neutre">{dossier.data.organizer}</Badge>
              <Badge>{dossier.data.status}</Badge>
              <Badge tone="neutre">{`${dossier.data.page_count} ${t('dossier.pages')}`}</Badge>
              <Badge tone={dossier.data.open_findings > 0 ? 'incertain' : 'ok'}>
                {`${t('dossier.openFindings')} : ${dossier.data.open_findings}`}
              </Badge>
              <Badge tone={dossier.data.score_total === null ? 'incertain' : 'ok'}>
                {`${t('dossier.score')} : ${
                  dossier.data.score_total === null
                    ? '—'
                    : `${dossier.data.score_total}/${dossier.data.score_max}`
                }`}
              </Badge>
            </p>
            {dossier.data.sha256 && (
              <p className="aide mono">SHA-256 : {dossier.data.sha256}</p>
            )}
            {dossier.data.gates && (
              <details>
                <summary>{t('dossier.gates')}</summary>
                <ul>
                  {Object.entries(dossier.data.gates).map(([name, state]) => (
                    <li key={name}>
                      <Badge tone={state.satisfied ? 'ok' : 'incertain'}>{name}</Badge> {state.message}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </Card>

          <Tabs
            label={t('nav.dashboard')}
            active={active}
            onChange={(id) => setActive(id as TabId)}
            tabs={[
              { id: 'document', label: t('tab.document') },
              { id: 'pieces', label: t('tab.pieces') },
              { id: 'informations', label: t('tab.informations') },
              { id: 'controle', label: t('tab.controle') },
              { id: 'evaluation', label: t('tab.evaluation') },
              { id: 'alertes', label: t('tab.alertes'), badge: dossier.data.open_findings },
              { id: 'notes', label: t('tab.notes') },
              { id: 'rapports', label: t('tab.rapports') },
              { id: 'web', label: t('tab.web') },
              { id: 'historique', label: t('tab.historique') },
            ]}
          />

          <TabPanel id={active}>
            {active === 'document' && <DocumentTab dossierId={dossierId} onChanged={reload} />}
            {active === 'pieces' && <PiecesTab dossierId={dossierId} onChanged={reload} />}
            {active === 'informations' && <InformationsTab dossierId={dossierId} onChanged={reload} />}
            {active === 'controle' && <ControleTab dossierId={dossierId} onChanged={reload} />}
            {active === 'evaluation' && <EvaluationTab dossierId={dossierId} onChanged={reload} />}
            {active === 'alertes' && <AlertesTab dossierId={dossierId} onChanged={reload} />}
            {active === 'notes' && <NotesTab dossierId={dossierId} onChanged={reload} />}
            {active === 'rapports' && <RapportsTab dossierId={dossierId} onChanged={reload} />}
            {active === 'web' && <WebRankingTab dossierId={dossierId} onChanged={reload} />}
            {active === 'historique' && <HistoriqueTab dossierId={dossierId} />}
          </TabPanel>

          <Notice tone="incertain">{t('common.uncertain')}</Notice>
        </>
      )}
    </>
  );
}
