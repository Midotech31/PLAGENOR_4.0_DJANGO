/**
 * Onglet « Traitement » : bouton principal, écran de progression, matrice,
 * score et avis proposé.
 *
 * Ce que ces tests protègent : l'avis ne doit jamais s'afficher comme une
 * décision, chaque constat doit montrer sa preuve et son fondement, et le
 * bouton principal ne doit pas relancer un traitement déjà actif.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '../src/components/ui';
import { TraitementTab } from '../src/features/TraitementTab';

const MODE = {
  mode: 'LOCAL_ONLY',
  available: true,
  model_id: null,
  notice: 'Mode LOCAL_ONLY : ce mode ne fournit pas le même niveau de lecture sémantique.',
  external_transmission: false,
  modes: ['LOCAL_ONLY', 'HYBRID_STRICT'],
  recommended: 'HYBRID_STRICT',
  identity_documents_transmitted: false,
  original_pdf_transmitted: false,
  guarantees: ['Le PDF original reste chiffré en local.'],
};

const COMPLETED_JOB = {
  id: 'job-1',
  dossier_id: 'dossier-1',
  state: 'COMPLETED',
  step_label: 'Terminé',
  progress: 100,
  pages_total: 4,
  pages_done: 4,
  searches_done: 6,
  validations_done: 31,
  attempt: 1,
  max_attempts: 3,
  cancel_requested: false,
  error_message: null,
  error_code: null,
  analysis_mode: 'LOCAL_ONLY',
  model_id: null,
  referential_version: '2026.08.1',
  grid_version: '2026.08.1',
  steps_done: ['VALIDATING', 'EXTRACTING'],
  steps_remaining: [],
  started_at: '2026-08-01T10:00:00Z',
  finished_at: '2026-08-01T10:02:00Z',
  can_resume: false,
  estimate: 'Terminé.',
};

const ASSESSMENT = {
  criteria: [
    {
      code: 'A1',
      label: 'Demande, validation, fiche technique et appel à communication',
      family: 'ADMINISTRATIF',
      order: 1,
      status: 'PC',
      proposed_status: 'PC',
      human_status: null,
      finding: '3 pièces sur 4 repérées ; la validation scientifique reste à produire.',
      exact_source: 'Guide du 14/07/2026, pp. 2-3 et 7',
      page: '2-3, 7',
      nature: 'OBLIGATOIRE',
      blocking: true,
      evidence_ids: ['E-P001', 'E-C1A2B3'],
      calculation: null,
      note: null,
      referential_version: '2026.08.1',
    },
    {
      code: 'A2',
      label: 'Programmation annuelle et dépôt au moins 10 jours avant la session',
      family: 'ADMINISTRATIF',
      order: 2,
      status: 'NV',
      proposed_status: 'NV',
      human_status: null,
      finding: "La date de dépôt régional n'est pas documentée. Aucun délai de six mois n'est applicable.",
      exact_source: 'Guide du 14/07/2026, p. 7',
      page: '7',
      nature: 'OBLIGATOIRE',
      blocking: true,
      evidence_ids: ['E-P002'],
      calculation: null,
      note: null,
      referential_version: '2026.08.1',
    },
  ],
  score: {
    total: 42,
    proposed_total: 42,
    validated_total: null,
    maximum: 100,
    grid_version: '2026.08.1',
    families: [
      {
        key: 'pertinence_priorites',
        label: 'Pertinence et priorités',
        score: 12,
        max: 30,
        subscores: [
          {
            key: 'priorite_nationale_demontree',
            label: 'Lien avec une priorité nationale explicitement démontrée',
            score: 0,
            proposed_score: 0,
            human_score: null,
            max: 8,
            justification: 'non documenté — aucun des éléments recherchés n’apparaît au dossier.',
            method: 'EVIDENCE_LEVELS',
            evidence_ids: [],
          },
        ],
      },
    ],
  },
  decision: {
    avis: 'AJOURNEMENT_POUR_COMPLEMENTS',
    label: 'Ajournement pour compléments',
    motivation: 'Des exigences obligatoires ne sont pas démontrées en l’état du dossier.',
    disclaimer:
      'Avis technique proposé par l’application — aide à la décision, ne valant pas décision officielle de la commission ou de la tutelle.',
    triggered_rules: [
      {
        rule: 'R2_SCORE_NON_NEUTRALISANT',
        explanation:
          'Score scientifique proposé : 42/100. Un score élevé ne neutralise aucune non-conformité réglementaire.',
        criteria: [],
        evidence_ids: [],
      },
      {
        rule: 'R1_CRITERE_OBLIGATOIRE_NON_SATISFAIT',
        explanation: '1 critère obligatoire au statut NC ou NV.',
        criteria: ['A2'],
        evidence_ids: ['E-P002'],
      },
    ],
    blocking_criteria: ['A2'],
    reserves: ['A1 — pièces incomplètes'],
    required_complements: ['A2 — date de dépôt régional à documenter.'],
    scientific_total: 42,
    referential_version: '2026.08.1',
    human_decision: null,
    decided_by: null,
  },
};

function mockRoutes(overrides: Record<string, unknown> = {}) {
  const routes: Record<string, unknown> = {
    '/mode-analyse': MODE,
    '/traitement': { job: COMPLETED_JOB, notice: null },
    '/evaluation-automatique': ASSESSMENT,
    '/rapports': PRODUCED_REPORTS,
    '/rapport-details': REPORT_DETAILS,
    ...overrides,
  };
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    // La route la plus spécifique gagne : « /evaluation-automatique » ne doit
    // pas être capturée par une clé plus courte.
    const key = Object.keys(routes)
      .filter((route) => url.includes(route))
      .sort((a, b) => b.length - a.length)[0];
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

const PRODUCED_REPORTS = {
  items: [
    {
      id: 'rap-docx',
      format: 'docx',
      is_draft: true,
      version: 1,
      sha256: 'a'.repeat(64),
      created_at: '2026-08-01T10:02:00Z',
    },
    {
      id: 'rap-pdf',
      format: 'pdf',
      is_draft: true,
      version: 2,
      sha256: 'b'.repeat(64),
      created_at: '2026-08-01T10:02:01Z',
    },
  ],
};

const REPORT_DETAILS = {
  sources: ['Pièce source : dossier.pdf — SHA-256 abc123… (4 pages).'],
  fondements: ['Envoi n° 595/SG du 19 mai 2025 — critères et calendrier.'],
  versions: { referentiel: '2026.08.1', grille: '2026.08.1', application: '2.0.1' },
  preuves: 58,
  regles_de_decision: [
    { regle: 'R1_CRITERE_OBLIGATOIRE_NON_SATISFAIT', motif: '15 critères bloquants.', criteres: ['A1', 'A2'] },
  ],
  controle_en_ligne: {
    profils_controles: 0,
    veille_executee: false,
    constat: "la veille en ligne n'a pas été exécutée pour ce dossier.",
    elements: [],
  },
  contradictions: [],
  desaccords_audit: [],
  faits_orphelins: [],
  legendes: {
    asterisque: 'Un astérisque signale une valeur non confirmée.',
    score_zero: "Un élément non documenté vaut zéro : ce zéro ne préjuge d'aucune incapacité.",
    matrice: 'Légende : C = conforme démontré ; PC = partiellement conforme.',
  },
  principe_probatoire: "aucune déduction à partir de la nationalité, de l'origine.",
  portee_controle: "Ne sont jamais examinés : la nationalité, l'origine ethnique, la religion.",
};

function renderTab() {
  return render(
    <LocaleProvider>
      <TraitementTab dossierId="dossier-1" onChanged={() => undefined} />
    </LocaleProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('onglet Traitement', () => {
  it('affiche le bouton principal et l’état durable du traitement', async () => {
    vi.stubGlobal('fetch', mockRoutes());
    renderTab();

    expect(await screen.findByRole('button', { name: 'Traiter le dossier' })).toBeEnabled();
    expect(await screen.findByText(/reprendra là où il s’est arrêté/)).toBeInTheDocument();
    expect(await screen.findByText('Pages traitées : 4/4')).toBeInTheDocument();
  });

  it('désactive le bouton principal pendant qu’un traitement est actif', async () => {
    vi.stubGlobal(
      'fetch',
      mockRoutes({
        '/traitement': {
          job: { ...COMPLETED_JOB, state: 'REGULATORY_CHECK', progress: 60, can_resume: false },
          notice: null,
        },
      }),
    );
    renderTab();

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Traitement en cours…' })).toBeDisabled(),
    );
    expect(screen.getByRole('button', { name: 'Annuler' })).toBeEnabled();
  });

  it('présente l’avis comme une proposition, jamais comme une décision', async () => {
    vi.stubGlobal('fetch', mockRoutes());
    renderTab();

    expect(await screen.findByText('Ajournement pour compléments')).toBeInTheDocument();
    expect(
      await screen.findByText(/ne valant pas décision officielle de la commission ou de la tutelle/),
    ).toBeInTheDocument();
    // La règle qui interdit la neutralisation par le score est visible.
    await userEvent.click(screen.getByText('Règles de décision déclenchées'));
    expect(
      screen.getByText(/Un score élevé ne neutralise aucune non-conformité réglementaire/),
    ).toBeInTheDocument();
  });

  it('montre chaque constat avec sa preuve et son fondement réglementaire', async () => {
    vi.stubGlobal('fetch', mockRoutes());
    renderTab();

    const row = (await screen.findByText('A2')).closest('tr');
    expect(row).not.toBeNull();
    const cells = within(row as HTMLElement);
    expect(cells.getByText('NV')).toBeInTheDocument();
    expect(cells.getByText(/Aucun délai de six mois n'est applicable/)).toBeInTheDocument();
    expect(cells.getByText('E-P002')).toBeInTheDocument();
    expect(cells.getByText(/Guide du 14\/07\/2026, p\. 7/)).toBeInTheDocument();
  });

  it('affiche une sous-note nulle avec la mention « non documenté »', async () => {
    vi.stubGlobal('fetch', mockRoutes());
    renderTab();

    expect(await screen.findByText('0/8')).toBeInTheDocument();
    expect(
      screen.getByText(/non documenté — aucun des éléments recherchés/),
    ).toBeInTheDocument();
    expect(screen.getByText(/ce zéro ne préjuge d’aucune incapacité réelle/)).toBeInTheDocument();
  });

  it('dit clairement ce que le mode local ne peut pas faire', async () => {
    vi.stubGlobal('fetch', mockRoutes());
    renderTab();

    expect(await screen.findByText('LOCAL_ONLY')).toBeInTheDocument();
    expect(
      screen.getByText(/ne fournit pas le même niveau de lecture sémantique/),
    ).toBeInTheDocument();
  });

  it('propose « Reprendre » après une interruption, sans rien effacer', async () => {
    vi.stubGlobal(
      'fetch',
      mockRoutes({
        '/traitement': {
          job: {
            ...COMPLETED_JOB,
            state: 'FAILED',
            step_label: 'Interrompu',
            progress: 45,
            can_resume: true,
            error_code: 'PermissionError',
            error_message:
              'L’étape « Structuration » n’a pas abouti : un fichier local n’a pas pu être lu ou écrit. Vous pouvez relancer le traitement avec « Reprendre ».',
          },
          notice: null,
        },
      }),
    );
    renderTab();

    expect(await screen.findByRole('button', { name: 'Reprendre' })).toBeEnabled();
    expect(screen.getByText(/n’a pas pu être lu ou écrit/)).toBeInTheDocument();
    // Les résultats déjà produits restent affichés : rien n'a été effacé.
    expect(screen.getByText('Ajournement pour compléments')).toBeInTheDocument();
  });

  it('propose au téléchargement le rapport produit par le traitement, sans second clic', async () => {
    vi.stubGlobal('fetch', mockRoutes());
    renderTab();

    expect(await screen.findByText('Rapport harmonisé produit')).toBeInTheDocument();
    const word = await screen.findByRole('link', { name: /DOCX/ });
    expect(word).toHaveAttribute('href', expect.stringContaining('/rapports/rap-docx/fichier'));
    expect(await screen.findByRole('link', { name: /PDF/ })).toBeInTheDocument();
    // Aucun bouton « générer » : le fichier existe déjà.
    expect(screen.queryByRole('button', { name: /[Gg]énérer/ })).toBeNull();
  });

  it('dit que le fichier est un brouillon et que l’officiel reste un acte humain', async () => {
    vi.stubGlobal('fetch', mockRoutes());
    renderTab();

    expect(await screen.findByText(/brouillons filigranés/)).toBeInTheDocument();
    expect(await screen.findByText(/votre validation explicite/)).toBeInTheDocument();
  });

  it('n’affiche aucun rapport tant que le traitement n’est pas terminé', async () => {
    vi.stubGlobal(
      'fetch',
      mockRoutes({
        '/traitement': { job: { ...COMPLETED_JOB, state: 'REPORT_QA', progress: 96 }, notice: null },
      }),
    );
    renderTab();

    await waitFor(() => expect(screen.getByText('Terminé')).toBeInTheDocument());
    expect(screen.queryByText('Rapport harmonisé produit')).toBeNull();
  });

  it('explique l’absence de rapport plutôt que de laisser un vide', async () => {
    vi.stubGlobal('fetch', mockRoutes({ '/rapports': { items: [] } }));
    renderTab();

    expect(
      await screen.findByText(/un rapport partiellement valide n’est jamais écrit/),
    ).toBeInTheDocument();
  });

  it('montre la traçabilité que le rapport ne porte plus', async () => {
    vi.stubGlobal('fetch', mockRoutes());
    renderTab();

    expect(await screen.findByText('Traçabilité du rapport')).toBeInTheDocument();
    expect(await screen.findByText('58 preuves citables')).toBeInTheDocument();
    expect(await screen.findByText('Application 2.0.1')).toBeInTheDocument();
    // Les règles de décision ne sont montrées qu'une fois, par la carte d'avis.
    expect(screen.getAllByText(/R1_CRITERE_OBLIGATOIRE_NON_SATISFAIT/)).toHaveLength(1);
  });

  it('rappelle à l’écran ce que le contrôle refuse d’examiner', async () => {
    vi.stubGlobal('fetch', mockRoutes());
    renderTab();

    await userEvent.click(await screen.findByText('Contrôle en ligne des profils'));
    expect(
      screen.getByText(/Ne sont jamais examinés : la nationalité/),
    ).toBeInTheDocument();
  });

  it('explique que le rapport suit le format de la commission, sans annexe', async () => {
    vi.stubGlobal('fetch', mockRoutes());
    renderTab();

    expect(await screen.findByText(/sept sections, sans annexe/)).toBeInTheDocument();
  });
});
