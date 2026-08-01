/** Point d'entrée local. Designed by Prof. Merzoug Mohamed. */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';
import { LocaleProvider } from './components/ui';
import './styles/theme.css';

const container = document.getElementById('root');
if (container === null) {
  throw new Error('Élément racine introuvable.');
}

createRoot(container).render(
  <StrictMode>
    <LocaleProvider>
      <App />
    </LocaleProvider>
  </StrictMode>,
);
