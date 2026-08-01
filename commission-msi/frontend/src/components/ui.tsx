/**
 * Composants d'interface accessibles et réutilisables.
 * Icônes SVG locales, aucune bibliothèque distante.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { directionOf, translate } from '../i18n';
import type { Locale, TranslationKey } from '../i18n';

// ------------------------------------------------------------------ i18n

interface LocaleContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>('fr');

  useEffect(() => {
    const direction = directionOf(locale);
    document.documentElement.lang = locale;
    document.documentElement.dir = direction;
  }, [locale]);

  const value = useMemo<LocaleContextValue>(
    () => ({ locale, setLocale, t: (key) => translate(locale, key) }),
    [locale],
  );
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleContextValue {
  const context = useContext(LocaleContext);
  if (context === null) {
    throw new Error('useLocale doit être utilisé dans un LocaleProvider.');
  }
  return context;
}

// ------------------------------------------------------------------ statuts

/**
 * Détermine la teinte d'un statut. L'information n'est jamais portée par la
 * seule couleur : le libellé textuel est toujours affiché.
 */
export function toneOf(status: string): 'neutre' | 'ok' | 'incertain' | 'critique' {
  const value = (status || '').toUpperCase();
  if (['CONFIRME', 'CONFIRMEE', 'VALIDE', 'SOURCE_OFFICIELLE_TROUVEE', 'SOURCES_CONCORDANTES', 'FAIT_VERIFIE', 'ACCEPTE'].includes(value)) {
    return 'ok';
  }
  if (['NON_CONFORME', 'INCOHERENT', 'CRITIQUE', 'SOURCES_CONTRADICTOIRES', 'REJETE', 'ECHOUEE'].includes(value)) {
    return 'critique';
  }
  if (
    ['A_VERIFIER', 'INCERTAIN', 'INCOMPLET', 'INCOMPLETE', 'ILLISIBLE', 'ABSENTE', 'DETECTEE', 'ELEVE', 'HOMONYMIE_POSSIBLE', 'RUMEUR', 'NON_ETABLI', 'NR'].includes(
      value,
    )
  ) {
    return 'incertain';
  }
  return 'neutre';
}

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  const resolved = tone ?? (typeof children === 'string' ? toneOf(children) : 'neutre');
  const mapped = ['neutre', 'ok', 'incertain', 'critique'].includes(resolved)
    ? resolved
    : toneOf(resolved);
  return <span className={`badge badge-${mapped}`}>{children}</span>;
}

export function Card({
  title,
  children,
  actions,
}: {
  title?: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="carte">
      {(title || actions) && (
        <div className="carte-titre">
          {title && <h2>{title}</h2>}
          {actions && <div className="espace actions">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Notice({
  tone = 'info',
  children,
}: {
  tone?: 'info' | 'incertain' | 'critique' | 'ok';
  children: ReactNode;
}) {
  return (
    <p className={`encart encart-${tone}`} role={tone === 'critique' ? 'alert' : undefined}>
      {children}
    </p>
  );
}

export function Field({
  label,
  hint,
  children,
  htmlFor,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  htmlFor?: string;
}) {
  return (
    <div className="champ">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && <p className="aide">{hint}</p>}
    </div>
  );
}

export function Tabs({
  tabs,
  active,
  onChange,
  label,
}: {
  tabs: { id: string; label: string; badge?: number }[];
  active: string;
  onChange: (id: string) => void;
  label: string;
}) {
  return (
    <div className="onglets" role="tablist" aria-label={label}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          id={`onglet-${tab.id}`}
          aria-selected={active === tab.id}
          aria-controls={`panneau-${tab.id}`}
          className="onglet"
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
          {tab.badge !== undefined && tab.badge > 0 ? ` (${tab.badge})` : ''}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div role="tabpanel" id={`panneau-${id}`} aria-labelledby={`onglet-${id}`} tabIndex={0}>
      {children}
    </div>
  );
}

export function Loading({ label }: { label: string }) {
  return (
    <p className="chargement" role="status" aria-live="polite">
      {label}
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="vide">{children}</p>;
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  return (
    <p className="encart encart-critique" role="alert">
      {message}
    </p>
  );
}

// ------------------------------------------------------------------ hooks

export function useAsync<T>(loader: () => Promise<T>, deps: unknown[]): {
  data: T | null;
  error: unknown;
  loading: boolean;
  reload: () => void;
} {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    loader()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((cause) => {
        if (!cancelled) setError(cause);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { data, error, loading, reload };
}

// ------------------------------------------------------------------ icônes

export function IconShield() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        d="M12 2 4 5v6c0 5 3.4 9.3 8 11 4.6-1.7 8-6 8-11V5l-8-3Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function IconAlert() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        d="M12 4 2.5 20h19L12 4Zm0 6v5m0 3h.01"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function IconGlobe() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path
        d="M3 12h18M12 3c2.5 3 2.5 15 0 18M12 3c-2.5 3-2.5 15 0 18"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
      />
    </svg>
  );
}
