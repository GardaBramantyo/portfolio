// Page interactions. Every animation has a job:
// hero entry sets hierarchy, counters give numbers weight, the slider hint teaches the drag,
// the pinned pan turns demos into a gallery, the stack sequences the scripts, the line shows progression.
(() => {
  const root = document.documentElement;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const reveal = () => root.classList.add('ready');

  /* Nav background once the page leaves the top (IntersectionObserver, no scroll listener) */
  const nav = document.getElementById('nav');
  const sentinel = document.createElement('div');
  sentinel.style.cssText = 'position:absolute;top:0;left:0;height:80px;width:1px;pointer-events:none';
  document.body.prepend(sentinel);
  new IntersectionObserver(([e]) => nav.classList.toggle('is-stuck', !e.isIntersecting)).observe(sentinel);

  /* Before/after slider */
  const compare = document.getElementById('compare');
  if (compare) {
    const range = compare.querySelector('input[type=range]');
    const set = (v) => { compare.style.setProperty('--pos', v + '%'); range.value = v; };
    range.addEventListener('input', () => set(range.value));
    compare.addEventListener('pointerdown', (ev) => {
      if (ev.pointerType !== 'mouse') return; // touch uses the native range input so vertical scroll still works
      const move = (e) => {
        const r = compare.getBoundingClientRect();
        set(Math.round(Math.min(100, Math.max(0, ((e.clientX - r.left) / r.width) * 100))));
      };
      move(ev);
      compare.setPointerCapture(ev.pointerId);
      compare.addEventListener('pointermove', move);
      compare.addEventListener('pointerup', () => compare.removeEventListener('pointermove', move), { once: true });
    });
    compare._set = set;
  }

  /* Demo frames: travel distance for the hover scroll-through */
  const sizeFrames = () => document.querySelectorAll('.demo').forEach((d) => {
    const view = d.querySelector('.frame-view');
    const img = view.querySelector('img');
    const h = img.clientHeight || (view.clientWidth * img.height) / img.width;
    d.style.setProperty('--travel', -(h - view.clientHeight) + 'px');
  });
  addEventListener('resize', sizeFrames);
  document.querySelectorAll('.frame-view img').forEach((img) => img.complete ? sizeFrames() : img.addEventListener('load', sizeFrames));
  sizeFrames();

  /* Magnetic buttons: small pull toward the cursor as hover feedback */
  if (!reduced && matchMedia('(hover: hover)').matches) {
    document.querySelectorAll('[data-magnetic]').forEach((btn) => {
      btn.addEventListener('pointermove', (e) => {
        const r = btn.getBoundingClientRect();
        btn.style.setProperty('--bx', ((e.clientX - r.left - r.width / 2) * 0.22).toFixed(1) + 'px');
        btn.style.setProperty('--by', ((e.clientY - r.top - r.height / 2) * 0.3).toFixed(1) + 'px');
      });
      btn.addEventListener('pointerleave', () => { btn.style.setProperty('--bx', '0px'); btn.style.setProperty('--by', '0px'); });
    });
  }

  const gsap = window.gsap;
  const ST = window.ScrollTrigger;
  if (!gsap || !ST || reduced) { reveal(); return; }
  gsap.registerPlugin(ST);

  reveal();

  /* Section reveals */
  gsap.set('[data-reveal]', { opacity: 0 });
  ST.batch('[data-reveal]', {
    start: 'top 88%',
    once: true,
    onEnter: (els) => gsap.fromTo(els, { y: 28, opacity: 0 }, { y: 0, opacity: 1, duration: 1, ease: 'expo.out', stagger: 0.08, overwrite: true }),
  });

  /* Counters */
  document.querySelectorAll('[data-count]').forEach((el) => {
    const end = +el.dataset.count;
    const comma = el.dataset.format === 'comma';
    const obj = { v: 0 };
    el.textContent = '0';
    gsap.to(obj, {
      v: end, duration: 1.6, ease: 'power3.out',
      scrollTrigger: { trigger: el, start: 'top 92%', once: true },
      onUpdate: () => { const n = Math.round(obj.v); el.textContent = comma ? n.toLocaleString('en-US') : n; },
    });
  });

  /* Slider hint: sweep once so people see it moves */
  if (compare) {
    const s = { v: 50 };
    gsap.timeline({ scrollTrigger: { trigger: compare, start: 'top 70%', once: true } })
      .to(s, { v: 82, duration: 0.9, ease: 'power2.inOut', onUpdate: () => compare._set(Math.round(s.v)) })
      .to(s, { v: 38, duration: 1.1, ease: 'power2.inOut', onUpdate: () => compare._set(Math.round(s.v)) })
      .to(s, { v: 50, duration: 0.7, ease: 'power2.out', onUpdate: () => compare._set(Math.round(s.v)) });
  }

  const mm = gsap.matchMedia();
  mm.add('(min-width: 1024px)', () => {
    /* Landing demos: vertical scroll pans the gallery sideways */
    const pan = document.querySelector('.pan');
    const track = pan.querySelector('.pan-track');
    pan.classList.add('is-pinned');
    const distance = () => track.scrollWidth - innerWidth;
    const tween = gsap.to(track, {
      x: () => -distance(),
      ease: 'none',
      scrollTrigger: { trigger: pan, start: 'top top', end: () => '+=' + distance(), pin: true, scrub: 0.8, invalidateOnRefresh: true, anticipatePin: 1 },
    });
    sizeFrames();

    /* Scripts: the previous card sinks back as the next one slides over it */
    const cards = gsap.utils.toArray('.stack-card');
    cards.forEach((card, i) => {
      if (i === cards.length - 1) return;
      gsap.to(card, {
        scale: 0.94, opacity: 0.45, ease: 'none',
        scrollTrigger: { trigger: cards[i + 1], start: 'top bottom', end: 'top 30%', scrub: true },
      });
    });

    /* Process line draws as you read down the steps */
    gsap.fromTo('.process-line .draw', { strokeDashoffset: 1 }, {
      strokeDashoffset: 0, ease: 'none',
      scrollTrigger: { trigger: '.process', start: 'top 75%', end: 'bottom 60%', scrub: true },
    });

    /* Portrait: slow drift inside its frame for depth */
    gsap.fromTo('.portrait img', { yPercent: -6 }, {
      yPercent: 4, ease: 'none',
      scrollTrigger: { trigger: '.portrait', start: 'top bottom', end: 'bottom top', scrub: true },
    });

    return () => { pan.classList.remove('is-pinned'); tween.kill(); };
  });

  addEventListener('load', () => ST.refresh());
})();
