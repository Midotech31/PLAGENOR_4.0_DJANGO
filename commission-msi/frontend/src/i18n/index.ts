/**
 * Internationalisation locale : français, anglais et arabe (RTL).
 * Aucune ressource distante, aucun service de traduction en ligne.
 */

export type Locale = 'fr' | 'en' | 'ar';

export const LOCALES: { code: Locale; label: string; dir: 'ltr' | 'rtl' }[] = [
  { code: 'fr', label: 'Français', dir: 'ltr' },
  { code: 'en', label: 'English', dir: 'ltr' },
  { code: 'ar', label: 'العربية', dir: 'rtl' },
];

const fr = {
  'app.title': 'Commission MSI — Examen des manifestations scientifiques internationales',
  'app.subtitle': 'Application locale — aucun compte, aucune connexion, aucune donnée en ligne pour le cœur documentaire',
  'app.signature': 'Designed by Prof. Merzoug Mohamed',
  'app.skip': 'Aller au contenu principal',
  'app.language': 'Langue de l’interface',
  'app.principle':
    'L’application extrait, vérifie, classe, compare, signale et prépare. L’évaluateur humain contrôle, interprète, apprécie et décide.',

  'nav.dashboard': 'Tableau de bord',
  'nav.back': 'Retour au tableau de bord',

  'dashboard.title': 'Tableau de bord',
  'dashboard.openFindings': 'Alertes ouvertes',
  'dashboard.pagesNeedingOcr': 'Pages nécessitant un OCR',
  'dashboard.missingPieces': 'Pièces manquantes',
  'dashboard.reports': 'Rapports générés',
  'dashboard.recent': 'Dossiers récents',
  'dashboard.filters': 'Filtres et recherche',
  'dashboard.search': 'Recherche globale',
  'dashboard.status': 'Statut',
  'dashboard.organizer': 'Organisateur',
  'dashboard.priority': 'Priorité',
  'dashboard.all': 'Tous',
  'dashboard.newDossier': 'Créer un dossier',
  'dashboard.reference': 'Référence',
  'dashboard.dossierTitle': 'Intitulé',
  'dashboard.create': 'Créer',
  'dashboard.empty': 'Aucun dossier ne correspond aux filtres.',
  'dashboard.connectivity': 'Connectivité Internet',
  'dashboard.online': 'En ligne',
  'dashboard.offline': 'Hors ligne',
  'dashboard.providers': 'Fournisseurs de recherche',

  'dossier.pages': 'Pages',
  'dossier.status': 'État',
  'dossier.score': 'Score saisi',
  'dossier.openFindings': 'Alertes ouvertes',
  'dossier.gates': 'Portes de validation',

  'tab.document': 'Document',
  'tab.pieces': 'Pièces',
  'tab.informations': 'Informations',
  'tab.controle': 'Contrôle administratif',
  'tab.evaluation': 'Évaluation scientifique',
  'tab.alertes': 'Alertes et points sensibles',
  'tab.notes': 'Notes et conclusion',
  'tab.rapports': 'Rapports',
  'tab.web': 'Recherche Web et ranking',
  'tab.historique': 'Historique',

  'document.import': 'Importer le PDF original',
  'document.page': 'Page',
  'document.originalPage': 'Page originale',
  'document.extractedText': 'Texte extrait',
  'document.mode': 'Mode d’extraction',
  'document.confidence': 'Confiance',
  'document.anomalies': 'Anomalies de page',
  'document.runOcr': 'Lancer l’OCR local',
  'document.correct': 'Corriger le texte',
  'document.searchInText': 'Rechercher dans le texte',
  'document.viewSource': 'Voir la source',
  'document.blank': 'Page blanche',
  'document.duplicate': 'Doublon probable',
  'document.difficult': 'Page difficile',
  'document.needsOcr': 'OCR requis',
  'document.noDocument': 'Aucun document importé pour ce dossier.',
  'document.reason': 'Motif de la correction',
  'document.initialKept': 'Le texte initial est toujours conservé.',

  'pieces.notice': 'La détection d’un titre ne vaut jamais confirmation de la validité de la pièce.',
  'pieces.restricted': 'Section restreinte — documents d’identité',
  'pieces.comment': 'Commentaire de qualification',

  'informations.notice':
    'Chaque information possède une source ou reste au statut A_VERIFIER. Les champs à contrôle renforcé exigent une relecture attentive.',
  'informations.reinforced': 'Contrôle renforcé',
  'informations.value': 'Valeur',
  'informations.sourcePage': 'Page source',
  'informations.excerpt': 'Extrait source',
  'informations.manual': 'Saisie manuelle validée par l’évaluateur',
  'informations.initial': 'Valeur initiale',

  'evaluation.notice': 'Aucune note n’est proposée par le système. Le total est une simple somme.',
  'evaluation.score': 'Note',
  'evaluation.justification': 'Justification obligatoire',
  'evaluation.sourcePages': 'Pages sources (séparées par une virgule)',
  'evaluation.total': 'Total saisi',
  'evaluation.incomplete': 'Grille incomplète : le total n’est pas calculé.',

  'alertes.notice':
    'Une alerte est une demande de vérification humaine. Elle ne produit ni note, ni conformité, ni décision. L’absence d’alerte ne prouve pas l’absence de risque.',
  'alertes.trigger': 'Terme déclencheur',
  'alertes.context': 'Contexte',
  'alertes.recommended': 'Vérification recommandée',
  'alertes.humanStatus': 'Statut humain',
  'alertes.comment': 'Motivation (8 caractères minimum)',
  'alertes.relation': 'Qualification de la relation',
  'alertes.rescan': 'Recalculer les alertes',
  'alertes.maroc': 'Mentions relatives au Maroc — vérification institutionnelle obligatoire',
  'alertes.marocNotice':
    'Point de vigilance institutionnelle — vérifier les instructions officielles applicables à la session avant toute conclusion.',

  'notes.add': 'Ajouter une note',
  'notes.kind': 'Type',
  'notes.body': 'Contenu',
  'notes.conclusion': 'Conclusion personnelle',
  'notes.motivation': 'Motivation obligatoire',
  'notes.personalNotice':
    'Proposition personnelle de l’évaluateur — ne vaut pas décision de la commission.',

  'rapports.generate': 'Générer un rapport',
  'rapports.draft': 'Brouillon',
  'rapports.official': 'Officiel',
  'rapports.validate': 'Validation humaine du rapport (porte G7)',
  'rapports.statement': 'Déclaration de validation',
  'rapports.download': 'Télécharger',
  'rapports.banner': 'Projet de rapport — validation humaine obligatoire',

  'web.title': 'Recherche Web contrôlée',
  'web.prepare': 'Préparer une campagne',
  'web.scopeNote': 'Périmètre de la campagne',
  'web.queries': 'Requêtes à relire avant envoi',
  'web.approveQuery': 'Approuver cette requête',
  'web.approveRun': 'Approuver la campagne',
  'web.execute': 'Lancer la recherche',
  'web.pause': 'Mettre en pause',
  'web.dismiss': 'Écarter avec justification',
  'web.sources': 'Sources consultées',
  'web.claims': 'Affirmations des agents',
  'web.unavailable':
    'Recherche Web indisponible — analyse enrichie incomplète, vérification humaine externe obligatoire.',
  'web.noUpload':
    'Aucun PDF, aucune pièce, aucun document d’identité et aucune note interne ne quitte le poste. Seule la requête minimale approuvée est transmise.',
  'web.ranking': 'Classement externe indicatif',
  'web.rankingNotice':
    'Classement externe indicatif assisté par IA — non décisionnel, fondé sur des sources publiques consultées à la date indiquée. Il ne modifie jamais la grille scientifique officielle.',
  'web.disagreement': 'DESACCORD_AGENTS — ARBITRAGE_HUMAIN_OBLIGATOIRE',
  'web.notProvided': 'NR — NON RENSEIGNE',
  'web.markComplete': 'Marquer l’analyse enrichie comme aboutie',
  'web.axisDecision': 'Décision de l’évaluateur',

  'historique.notice':
    'Le journal ne contient jamais une valeur sensible en clair : seules des empreintes SHA-256.',
  'historique.action': 'Action',
  'historique.summary': 'Résumé',
  'historique.date': 'Date',
  'historique.actor': 'Auteur',

  'limits.title': 'Limites de l’application',
  'common.save': 'Enregistrer',
  'common.cancel': 'Annuler',
  'common.loading': 'Chargement…',
  'common.error': 'Erreur',
  'common.none': 'Aucun',
  'common.page': 'page',
  'common.status': 'Statut',
  'common.label': 'Libellé',
  'common.actions': 'Actions',
  'common.confidence': 'Confiance',
  'common.source': 'Source',
  'common.uncertain': 'Contenu illisible ou insuffisamment fiable — vérification humaine obligatoire.',
} as const;

type Dictionary = Record<keyof typeof fr, string>;

const en: Dictionary = {
  ...fr,
  'app.title': 'MSI Commission — Review of international scientific events',
  'app.subtitle':
    'Local application — no account, no login, no online data for the document core',
  'app.signature': 'Designed by Prof. Merzoug Mohamed',
  'app.skip': 'Skip to main content',
  'app.language': 'Interface language',
  'app.principle':
    'The application extracts, verifies, classifies, compares, flags and prepares. The human evaluator checks, interprets, assesses and decides.',
  'nav.dashboard': 'Dashboard',
  'nav.back': 'Back to dashboard',
  'dashboard.title': 'Dashboard',
  'dashboard.openFindings': 'Open alerts',
  'dashboard.pagesNeedingOcr': 'Pages requiring OCR',
  'dashboard.missingPieces': 'Missing documents',
  'dashboard.reports': 'Generated reports',
  'dashboard.recent': 'Recent files',
  'dashboard.filters': 'Filters and search',
  'dashboard.search': 'Global search',
  'dashboard.status': 'Status',
  'dashboard.organizer': 'Organiser',
  'dashboard.priority': 'Priority',
  'dashboard.all': 'All',
  'dashboard.newDossier': 'Create a file',
  'dashboard.reference': 'Reference',
  'dashboard.dossierTitle': 'Title',
  'dashboard.create': 'Create',
  'dashboard.empty': 'No file matches the filters.',
  'dashboard.connectivity': 'Internet connectivity',
  'dashboard.online': 'Online',
  'dashboard.offline': 'Offline',
  'dashboard.providers': 'Search providers',
  'tab.document': 'Document',
  'tab.pieces': 'Documents',
  'tab.informations': 'Information',
  'tab.controle': 'Administrative check',
  'tab.evaluation': 'Scientific assessment',
  'tab.alertes': 'Alerts and sensitive points',
  'tab.notes': 'Notes and conclusion',
  'tab.rapports': 'Reports',
  'tab.web': 'Web research and ranking',
  'tab.historique': 'History',
  'alertes.notice':
    'An alert is a request for human verification. It never produces a score, a compliance statement or a decision. The absence of an alert does not prove the absence of risk.',
  'web.unavailable':
    'Web research unavailable — enriched analysis incomplete, external human verification required.',
  'web.rankingNotice':
    'Indicative external ranking assisted by AI — non-decisional, based on public sources consulted on the stated date. It never modifies the official scientific grid.',
  'common.uncertain': 'Content unreadable or insufficiently reliable — human verification required.',
};

const ar: Dictionary = {
  ...fr,
  'app.title': 'لجنة التظاهرات العلمية الدولية — فحص الملفات',
  'app.subtitle': 'تطبيق محلي — بدون حساب، بدون تسجيل دخول، وبدون إرسال بيانات للنواة الوثائقية',
  'app.signature': 'Designed by Prof. Merzoug Mohamed',
  'app.skip': 'الانتقال إلى المحتوى الرئيسي',
  'app.language': 'لغة الواجهة',
  'app.principle':
    'يقوم التطبيق بالاستخراج والتحقق والتصنيف والمقارنة والتنبيه والتحضير. أما المقيّم البشري فهو من يراقب ويفسّر ويقدّر ويقرّر.',
  'nav.dashboard': 'لوحة القيادة',
  'nav.back': 'العودة إلى لوحة القيادة',
  'dashboard.title': 'لوحة القيادة',
  'dashboard.openFindings': 'التنبيهات المفتوحة',
  'dashboard.pagesNeedingOcr': 'صفحات تتطلب قراءة ضوئية',
  'dashboard.missingPieces': 'الوثائق الناقصة',
  'dashboard.reports': 'التقارير المُنشأة',
  'dashboard.recent': 'الملفات الأخيرة',
  'dashboard.filters': 'التصفية والبحث',
  'dashboard.search': 'بحث شامل',
  'dashboard.status': 'الحالة',
  'dashboard.organizer': 'الجهة المنظمة',
  'dashboard.priority': 'الأولوية',
  'dashboard.all': 'الكل',
  'dashboard.newDossier': 'إنشاء ملف',
  'dashboard.reference': 'المرجع',
  'dashboard.dossierTitle': 'العنوان',
  'dashboard.create': 'إنشاء',
  'dashboard.empty': 'لا يوجد ملف مطابق للتصفية.',
  'dashboard.connectivity': 'الاتصال بالإنترنت',
  'dashboard.online': 'متصل',
  'dashboard.offline': 'غير متصل',
  'dashboard.providers': 'مزودو البحث',
  'tab.document': 'الوثيقة',
  'tab.pieces': 'الوثائق المطلوبة',
  'tab.informations': 'المعلومات',
  'tab.controle': 'المراقبة الإدارية',
  'tab.evaluation': 'التقييم العلمي',
  'tab.alertes': 'التنبيهات والنقاط الحساسة',
  'tab.notes': 'الملاحظات والخلاصة',
  'tab.rapports': 'التقارير',
  'tab.web': 'البحث على الإنترنت والتصنيف',
  'tab.historique': 'السجل',
  'alertes.maroc': 'الإشارات المتعلقة بالمغرب — تحقق مؤسساتي إلزامي',
  'alertes.notice':
    'التنبيه هو طلب تحقق بشري. لا ينتج عنه أي نقطة أو مطابقة أو قرار. وغياب التنبيه لا يثبت غياب الخطر.',
  'web.unavailable': 'البحث على الإنترنت غير متاح — التحليل المعمّق غير مكتمل، والتحقق البشري الخارجي إلزامي.',
  'common.uncertain': 'محتوى غير مقروء أو غير موثوق بدرجة كافية — التحقق البشري إلزامي.',
};

const DICTIONARIES: Record<Locale, Dictionary> = { fr, en, ar };

export type TranslationKey = keyof typeof fr;

export function translate(locale: Locale, key: TranslationKey): string {
  return DICTIONARIES[locale][key] ?? DICTIONARIES.fr[key] ?? key;
}

export function directionOf(locale: Locale): 'ltr' | 'rtl' {
  return LOCALES.find((entry) => entry.code === locale)?.dir ?? 'ltr';
}
