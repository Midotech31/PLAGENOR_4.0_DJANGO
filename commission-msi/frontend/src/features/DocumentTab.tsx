/** Onglet « Document » : écran partagé lecteur / texte extrait. */

import { useEffect, useState } from 'react';

import { api } from '../services/api';
import type { PageInfo } from '../services/api';
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

export function DocumentTab({ dossierId, onChanged }: { dossierId: string; onChanged: () => void }) {
  const { t } = useLocale();
  const pages = useAsync(() => api.listPages(dossierId), [dossierId]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<PageInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [ocrText, setOcrText] = useState<string | null>(null);
  const [correction, setCorrection] = useState({ text: '', reason: '' });
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<{ page_id: string; page_no: number; excerpt: string }[]>([]);
  const [analysis, setAnalysis] = useState<
    { etape: string; resultat: string; traite: number; echecs: number }[] | null
  >(null);
  const [analysisNotice, setAnalysisNotice] = useState<string | null>(null);

  useEffect(() => {
    const list = pages.data?.items ?? [];
    if (list.length > 0 && selected === null) {
      setSelected(list[0].id);
    }
  }, [pages.data, selected]);

  useEffect(() => {
    if (!selected) return;
    setOcrText(null);
    api
      .getPage(dossierId, selected)
      .then((page) => {
        setDetail(page);
        setCorrection({ text: page.current_text ?? '', reason: '' });
      })
      .catch(setError);
  }, [dossierId, selected]);

  async function importDocument(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await api.importDocument(dossierId, file);
      pages.reload();
      onChanged();
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
      event.target.value = '';
    }
  }

  async function runFullAnalysis() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.fullAnalysis(dossierId);
      setAnalysis(result.steps);
      setAnalysisNotice(result.notice);
      pages.reload();
      onChanged();
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  }

  async function runOcr(force: boolean) {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.runOcr(dossierId, selected, force);
      setOcrText(result.text);
      const page = await api.getPage(dossierId, selected);
      setDetail(page);
      pages.reload();
      onChanged();
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  }

  async function saveCorrection(event: React.FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await api.correctPage(dossierId, selected, correction.text, correction.reason);
      const page = await api.getPage(dossierId, selected);
      setDetail(page);
      setCorrection({ text: page.current_text ?? '', reason: '' });
      onChanged();
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  }

  async function search(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const found = await api.searchInDossier(dossierId, query);
      setResults(found.items);
    } catch (cause) {
      setError(cause);
    }
  }

  const list = pages.data?.items ?? [];

  return (
    <>
      <Card title={t('document.import')}>
        <input
          type="file"
          accept="application/pdf"
          aria-label={t('document.import')}
          onChange={importDocument}
          disabled={busy}
        />
        <p className="aide">
          Le PDF original est conservé chiffré et strictement inchangé ; son empreinte SHA-256 est
          enregistrée. L’analyse démarre automatiquement après l’import.
        </p>
        <ErrorBanner error={error} />
      </Card>

      {list.length > 0 && (
        <Card
          title={t('analysis.title')}
          actions={
            <button
              type="button"
              className="bouton-principal"
              onClick={runFullAnalysis}
              disabled={busy}
            >
              {busy ? t('analysis.running') : t('analysis.run')}
            </button>
          }
        >
          <Notice>{t('analysis.intro')}</Notice>
          {analysis && (
            <div className="tableau-conteneur">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t('analysis.step')}</th>
                    <th scope="col">{t('analysis.result')}</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.map((step) => (
                    <tr key={step.etape}>
                      <td>
                        <Badge tone={step.echecs > 0 ? 'incertain' : 'ok'}>{step.etape}</Badge>
                      </td>
                      <td>{step.resultat}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {analysisNotice && <Notice tone="incertain">{analysisNotice}</Notice>}
        </Card>
      )}

      {pages.loading && <Loading label={t('common.loading')} />}
      {!pages.loading && list.length === 0 && (
        <Card>
          <Empty>{t('document.noDocument')}</Empty>
        </Card>
      )}

      {list.length > 0 && (
        <>
          <Card title={t('document.searchInText')}>
            <form onSubmit={search} className="actions">
              <input
                aria-label={t('document.searchInText')}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                minLength={2}
              />
              <button type="submit">{t('document.searchInText')}</button>
            </form>
            {results.length > 0 && (
              <ul>
                {results.map((result) => (
                  <li key={result.page_id}>
                    <button
                      type="button"
                      className="bouton-discret"
                      onClick={() => setSelected(result.page_id)}
                    >
                      {t('document.viewSource')} — {t('common.page')} {result.page_no}
                    </button>{' '}
                    <span className="aide">{result.excerpt}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <div className="liste-pages" role="group" aria-label={t('document.page')}>
            {list.map((page) => (
              <button
                key={page.id}
                type="button"
                className="puce-page"
                aria-current={selected === page.id}
                onClick={() => setSelected(page.id)}
              >
                {page.page_no}
                {page.needs_ocr ? ' •' : ''}
              </button>
            ))}
          </div>

          {detail && (
            <div className="split-document">
              <Card title={`${t('document.originalPage')} ${detail.page_no}`}>
                {selected && (
                  <img
                    className="apercu-page"
                    src={api.pageImageUrl(dossierId, selected)}
                    alt={`${t('document.originalPage')} ${detail.page_no}`}
                  />
                )}
              </Card>

              <div>
                <Card title={t('document.extractedText')}>
                  <p className="actions">
                    <Badge>{detail.mode}</Badge>
                    <Badge tone={detail.uncertain ? 'incertain' : 'ok'}>
                      {t('document.confidence')} :{' '}
                      {detail.confidence === null
                        ? '—'
                        : `${Math.round(detail.confidence * 100)} %`}
                    </Badge>
                    {detail.needs_ocr && <Badge tone="incertain">{t('document.needsOcr')}</Badge>}
                    {detail.is_blank && <Badge>{t('document.blank')}</Badge>}
                    {detail.is_difficult && <Badge tone="incertain">{t('document.difficult')}</Badge>}
                    {detail.duplicate_of !== null && (
                      <Badge tone="incertain">
                        {t('document.duplicate')} ({t('common.page')} {detail.duplicate_of})
                      </Badge>
                    )}
                  </p>
                  {detail.notice && <Notice tone="incertain">{detail.notice}</Notice>}
                  {(detail.needs_ocr || detail.uncertain) && <OcrCapability />}
                  <div className="actions" style={{ marginBottom: '0.6rem' }}>
                    <button type="button" onClick={() => runOcr(false)} disabled={busy}>
                      {t('document.runOcr')}
                    </button>
                    <button type="button" className="bouton-discret" onClick={() => runOcr(true)} disabled={busy}>
                      {t('document.runOcr')} (forcer)
                    </button>
                  </div>
                  <pre className="texte-extrait">
                    {ocrText ?? detail.current_text ?? t('common.none')}
                  </pre>
                </Card>

                <Card title={t('document.correct')}>
                  <Notice>{t('document.initialKept')}</Notice>
                  <form onSubmit={saveCorrection}>
                    <Field label={t('document.extractedText')} htmlFor="correction-texte">
                      <textarea
                        id="correction-texte"
                        value={correction.text}
                        onChange={(event) => setCorrection({ ...correction, text: event.target.value })}
                      />
                    </Field>
                    <Field label={t('document.reason')} htmlFor="correction-motif">
                      <input
                        id="correction-motif"
                        minLength={8}
                        required
                        value={correction.reason}
                        onChange={(event) =>
                          setCorrection({ ...correction, reason: event.target.value })
                        }
                      />
                    </Field>
                    <button type="submit" className="bouton-principal" disabled={busy}>
                      {t('common.save')}
                    </button>
                  </form>
                  {detail.corrections && detail.corrections.length > 0 && (
                    <ul className="aide">
                      {detail.corrections.map((entry) => (
                        <li key={entry.id}>
                          {new Date(entry.created_at).toLocaleString()} — {entry.evaluator_label} —{' '}
                          {entry.reason}
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}

// --------------------------------------------------------------------------
// Ce que le poste sait lire
// --------------------------------------------------------------------------

/**
 * Pourquoi ce bloc existe : une page arabe parfaitement nette peut ressortir
 * « illisible » alors que la page n'est pas en cause — le poste n'a simplement
 * aucun moteur qui connaisse cette écriture. Tesseract sans son paquet « ara »
 * ne lit pas l'arabe, et RapidOCR non plus : sur une page arabe il a été mesuré
 * renvoyant « rmg » à 62 % de confiance.
 *
 * Laisser l'évaluateur devant « contenu illisible » revient à lui faire
 * soupçonner son document, retoucher son scan, recommencer — pour un manque qui
 * se répare en dix minutes. Le bloc ne s'affiche donc que là où la question se
 * pose, et il nomme l'action à faire.
 */
function OcrCapability() {
  const { t } = useLocale();
  const state = useAsync(() => api.ocrDiagnostic(), []);

  if (state.loading || state.error || !state.data) return null;
  const { barreaux, arabe_lisible, manque_pour_l_arabe } = state.data;

  return (
    <details className="aide" style={{ marginBottom: '0.6rem' }}>
      <summary>
        {t('document.enginesTitle')}{' '}
        <Badge tone={arabe_lisible ? 'ok' : 'critique'}>
          {arabe_lisible ? t('document.arabicReadable') : t('document.arabicNotReadable')}
        </Badge>
      </summary>
      {!arabe_lisible && (
        <Notice tone="critique">
          {t('document.arabicMissing')}
          <ul>
            {manque_pour_l_arabe.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Notice>
      )}
      <ul>
        {barreaux.map((engine) => (
          <li key={engine.moteur}>
            <Badge tone={engine.disponible ? 'ok' : 'neutre'}>{engine.moteur}</Badge>{' '}
            {engine.disponible ? t('document.engineAvailable') : t('document.engineAbsent')}
            {engine.langues.length > 0 && ` — ${engine.langues.join(', ')}`}
            <br />
            {engine.portee}
          </li>
        ))}
      </ul>
    </details>
  );
}
