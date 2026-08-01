/** Tests d'interface : accessibilité, RTL, absence d'écran de connexion. */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { App } from '../src/App';
import { Badge, LocaleProvider, Notice, toneOf } from '../src/components/ui';
import { directionOf, translate } from '../src/i18n';

const DIAGNOSTIC = {
  application: 'Commission MSI',
  version: '1.0.0',
  designed_by: 'Designed by Prof. Merzoug Mohamed',
  bind_host: '127.0.0.1',
  bind_port: 8731,
  listens_locally_only: true,
  network_policy: 'Aucune ressource Internet non autorisée.',
  master_key_present: true,
  ocr: { available: false, note: 'OCR local indisponible.', effective_languages: null },
  security_notes: ['Ne perdez jamais master.key.', 'Activez BitLocker.'],
  limits: [
    "Aucune garantie d'exhaustivité ni de zéro erreur.",
    "L'absence d'alerte ne prouve pas l'absence de risque.",
  ],
};

const DASHBOARD = {
  recent_dossiers: [],
  open_findings: 3,
  pages_needing_ocr: 2,
  missing_pieces: 5,
  reports_generated: 1,
  notice: "L'absence d'alerte ne prouve pas l'absence de risque.",
};

function mockFetch(routes: Record<string, unknown>) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const key = Object.keys(routes).find((route) => url.includes(route));
    if (key === undefined) {
      return new Response(JSON.stringify({ error: { code: 'INTROUVABLE', message: 'inconnue' } }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    return new Response(JSON.stringify(routes[key]), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  });
}

function renderApp() {
  return render(
    <LocaleProvider>
      <App />
    </LocaleProvider>,
  );
}

describe('démarrage local', () => {
  it("ouvre directement le tableau de bord, sans écran de connexion", async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        '/readiness': { ready: true, checks: {}, message: 'prêt' },
        '/diagnostic': DIAGNOSTIC,
        '/tableau-de-bord': DASHBOARD,
        '/vocabulary': { dossier_status: ['NOUVEAU'], priority: ['MOYEN'] },
        '/recherche-web/connectivite': {
          online: false,
          reason: 'hors ligne',
          message: 'Recherche Web indisponible',
          providers: [],
          egress: { network_disabled: true, allowed_domains: [], tls_required: true, notice: 'Aucun PDF ne sort.' },
        },
        '/dossiers': { items: [] },
      }),
    );

    renderApp();

    await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: /Tableau de bord/ })).toBeInTheDocument());
    expect(screen.queryByLabelText(/mot de passe/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /connexion/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /identifiant/i })).not.toBeInTheDocument();
  });

  it('affiche la signature de l’auteur et les limites', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        '/readiness': { ready: true, checks: {}, message: 'prêt' },
        '/diagnostic': DIAGNOSTIC,
        '/tableau-de-bord': DASHBOARD,
        '/vocabulary': { dossier_status: [], priority: [] },
        '/recherche-web/connectivite': {
          online: true,
          reason: 'ok',
          message: 'ok',
          providers: [],
          egress: { network_disabled: false, allowed_domains: ['api.crossref.org'], tls_required: true, notice: 'ok' },
        },
        '/dossiers': { items: [] },
      }),
    );

    renderApp();

    await waitFor(() =>
      expect(screen.getByText('Designed by Prof. Merzoug Mohamed')).toBeInTheDocument(),
    );
    expect(
      await screen.findByText("L'absence d'alerte ne prouve pas l'absence de risque."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Ne perdez jamais master.key/)).toBeInTheDocument();
  });

  it('signale un serveur non prêt sans boucle de redirection', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        '/readiness': { ready: false, checks: { database: false }, message: 'Serveur non prêt.' },
        '/diagnostic': DIAGNOSTIC,
      }),
    );

    renderApp();
    await waitFor(() => expect(screen.getByText('Serveur non prêt.')).toBeInTheDocument());
    expect(screen.queryByRole('heading', { name: /Tableau de bord/ })).not.toBeInTheDocument();
  });
});

describe('accessibilité et internationalisation', () => {
  it('bascule en arabe et applique la direction RTL', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        '/readiness': { ready: true, checks: {}, message: 'prêt' },
        '/diagnostic': DIAGNOSTIC,
        '/tableau-de-bord': DASHBOARD,
        '/vocabulary': { dossier_status: [], priority: [] },
        '/recherche-web/connectivite': {
          online: true,
          reason: 'ok',
          message: 'ok',
          providers: [],
          egress: { network_disabled: false, allowed_domains: [], tls_required: true, notice: 'ok' },
        },
        '/dossiers': { items: [] },
      }),
    );

    renderApp();
    const selector = await screen.findByLabelText(/Langue de l’interface/);
    await userEvent.selectOptions(selector, 'ar');

    await waitFor(() => expect(document.documentElement.dir).toBe('rtl'));
    expect(document.documentElement.lang).toBe('ar');
  });

  it('propose un lien d’évitement vers le contenu principal', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({ '/readiness': { ready: true, checks: {}, message: 'ok' }, '/diagnostic': DIAGNOSTIC }),
    );
    renderApp();
    expect(screen.getByText('Aller au contenu principal')).toHaveAttribute('href', '#contenu');
  });

  it('traduit les libellés clés dans les trois langues', () => {
    expect(translate('fr', 'tab.web')).toBe('Recherche Web et ranking');
    expect(translate('en', 'tab.web')).toBe('Web research and ranking');
    expect(translate('ar', 'alertes.maroc')).toContain('المغرب');
    expect(directionOf('ar')).toBe('rtl');
    expect(directionOf('fr')).toBe('ltr');
  });
});

describe('composants', () => {
  it('n’exprime jamais un statut par la seule couleur', () => {
    render(<Badge>A_VERIFIER</Badge>);
    // Le libellé textuel accompagne toujours la teinte.
    expect(screen.getByText('A_VERIFIER')).toBeInTheDocument();
    expect(toneOf('A_VERIFIER')).toBe('incertain');
    expect(toneOf('CONFIRME')).toBe('ok');
    expect(toneOf('SOURCES_CONTRADICTOIRES')).toBe('critique');
  });

  it('annonce les alertes critiques aux lecteurs d’écran', () => {
    render(<Notice tone="critique">Alerte critique fictive</Notice>);
    expect(screen.getByRole('alert')).toHaveTextContent('Alerte critique fictive');
  });
});
