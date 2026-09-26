// Loads the hero scene after first paint so it never delays the headline.
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
const canvas = document.getElementById('hero-canvas');
const boot = () => import('./hero3d.js').then((m) => m.initHero(canvas, { reduced })).catch(() => {});
if (canvas) ('requestIdleCallback' in window ? requestIdleCallback(boot, { timeout: 800 }) : setTimeout(boot, 200));
