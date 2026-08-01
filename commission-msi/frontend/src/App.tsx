/**
 * Coquille de l'application.
 *
 * Démarrage local : vérification de santé du serveur puis ouverture directe du
 * tableau de bord. Aucun écran de configuration, aucun écran de connexion,
 * aucune redirection.
 */

import { useState } from 'react';

import { api } from './services/api';
import { LOCALES } from './i18n';
import type { Locale } from './i18n';
import { Card, ErrorBanner, Loading, Notice, useAsync, useLocale } from './components/ui';
import { Dashboard } from './pages/Dashboard';
import { DossierWorkspace } from './pages/DossierWorkspace';

export function App() {
  const { t, locale, setLocale } = useLocale();
  const [openDossier, setOpenDossier] = useState<string | null>(null);
  const readiness = useAsync(() => api.readiness(), []);
  const diagnostic = useAsync(() => api.diagnostic(), []);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#contenu">
        {t('app.skip')}
      </a>

      <header className="app-header">
        <div>
          <h1>{t('app.title')}</h1>
          <div className="sous-titre">{t('app.subtitle')}</div>
        </div>
        <div className="espace">
          <label htmlFor="choix-langue" style={{ color: '#b9cdd6' }}>
            {t('app.language')}
          </label>
          <select
            id="choix-langue"
            value={locale}
            onChange={(event) => setLocale(event.target.value as Locale)}
          >
            {LOCALES.map((entry) => (
              <option key={entry.code} value={entry.code}>
                {entry.label}
              </option>
            ))}
          </select>
        </div>
      </header>

      <main className="app-main" id="contenu">
        {readiness.loading && <Loading label={t('common.loading')} />}
        <ErrorBanner error={readiness.error} />

        {readiness.data && !readiness.data.ready && (
          <Notice tone="critique">{readiness.data.message}</Notice>
        )}

        {readiness.data?.ready &&
          (openDossier === null ? (
            <Dashboard onOpen={setOpenDossier} />
          ) : (
            <DossierWorkspace dossierId={openDossier} onBack={() => setOpenDossier(null)} />
          ))}

        {diagnostic.data && (
          <Card title={t('limits.title')}>
            <ul className="limites">
              {diagnostic.data.limits.map((limit) => (
                <li key={limit}>{limit}</li>
              ))}
            </ul>
            <ul className="limites aide">
              {diagnostic.data.security_notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
            <p className="aide">
              {diagnostic.data.network_policy} — écoute locale :{' '}
              {diagnostic.data.bind_host}:{diagnostic.data.bind_port} —{' '}
              {diagnostic.data.ocr.available
                ? `OCR local : ${diagnostic.data.ocr.effective_languages}`
                : diagnostic.data.ocr.note}
            </p>
          </Card>
        )}
      </main>

      <footer className="app-footer">
        <span>
          {diagnostic.data ? `${diagnostic.data.application} — v${diagnostic.data.version}` : ''}
        </span>
        <span className="signature">{t('app.signature')}</span>
      </footer>
    </div>
  );
}
