import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import {Theme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {App} from './App';

// Order matters: Astryx's reset, then its component styles, then the theme's
// token overrides, then our own. The first three sit in Astryx's CSS layers;
// ours sit outside them, so the approved mock's look always wins.
import '@astryxdesign/core/reset.css';
import '@astryxdesign/core/astryx.css';
import '@astryxdesign/theme-neutral/theme.css';
import './tokens.css';
import './app.css';

const mount = document.getElementById('root');
if (!mount) throw new Error('The page is missing its root element.');

createRoot(mount).render(
  <StrictMode>
    <Theme theme={neutralTheme}>
      <App />
    </Theme>
  </StrictMode>,
);
