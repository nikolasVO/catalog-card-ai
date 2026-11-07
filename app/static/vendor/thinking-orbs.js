/*
 * Thinking Orbs — working/orbits state, adapted to plain JavaScript.
 * Copyright (c) 2026 Jakub Antalik. MIT License, see licenses/thinking-orbs.txt.
 * Source: Jakubantalik/Libraries.dev, packages/thinking-orbs/src/
 * Engine math and the 20/32/64 working presets are from upstream.
 * This local adapter adds canvas lifecycle, visibility and reduced-motion handling.
 * Not the React package; no framework or CDN is required.
 */
(() => {
  'use strict';
  const presets = {
    64: { speed: 1.885, count: 1, size: 1 },
    32: { speed: 2.9072, count: 0.4251, size: 1.6849 },
    20: { speed: 3.9, count: 0.238, size: 2.4 }
  };
  function hashD(a, b) {
    const h = Math.sin(a * 12.9898 + b * 78.233) * 43758.5453;
    return h - Math.floor(h);
  }
  function makeProj(yaw, tilt, cx, cy, scale) {
    const st = Math.sin(tilt), ct = Math.cos(tilt);
    const sy = Math.sin(yaw), cyw = Math.cos(yaw);
    return (x, y, z) => {
      const x1 = x * cyw + z * sy;
      const z1 = -x * sy + z * cyw;
      const y1 = y * ct - z1 * st;
      const z2 = y * st + z1 * ct;
      return [cx + x1 * scale, cy - y1 * scale, z2];
    };
  }
  function frameOrbits(size, t, o) {
    const cx = size / 2, cy = size / 2;
    const R = (size / 2) * 0.82;
    const pt = makeProj(t * 0.12, 0.3, cx, cy, 1);
    const rs = (size / 300) ** (o.rsPow ?? 0.6);
    const dots = [];
    const orbitN = o.orbitN ?? 12, ghostN = o.ghostN ?? 40, particles = o.particles ?? 3;
    for (let orb = 0; orb < orbitN; orb++) {
      const h1 = hashD(orb, 1.7), h2 = hashD(orb, 5.2), h3 = hashD(orb, 8.9);
      const ro = R * (0.45 + 0.52 * h1);
      const th = h1 * 2 * Math.PI, phi = Math.acos(2 * h2 - 1);
      const nx = Math.sin(phi) * Math.cos(th), ny = Math.cos(phi), nz = Math.sin(phi) * Math.sin(th);
      let ux = -ny, uy = nx;
      const uz = 0;
      const ul = Math.max(1e-6, Math.sqrt(ux * ux + uy * uy));
      ux /= ul; uy /= ul;
      const vx = ny * uz - nz * uy, vy = nz * ux - nx * uz, vz = nx * uy - ny * ux;
      const speed = (0.25 + 0.55 * h3) * (h3 > 0.5 ? 1 : -1);
      for (let k = 0; k < ghostN; k++) {
        const a = (k / ghostN) * 2 * Math.PI;
        const [px, py, z] = pt(
          (ux * Math.cos(a) + vx * Math.sin(a)) * ro,
          (uy * Math.cos(a) + vy * Math.sin(a)) * ro,
          (uz * Math.cos(a) + vz * Math.sin(a)) * ro
        );
        const depth = (z / ro + 1) / 2;
        dots.push({ x: px, y: py, z, r: (o.ghostR ?? 0.9) * rs, white: 0.72, a: (o.ghostA ?? 0.5) * (0.4 + 0.6 * depth) });
      }
      for (let m = 0; m < particles; m++) {
        const a = t * speed + (m / particles) * 2 * Math.PI + h2 * 6;
        const [px, py, z] = pt(
          (ux * Math.cos(a) + vx * Math.sin(a)) * ro,
          (uy * Math.cos(a) + vy * Math.sin(a)) * ro,
          (uz * Math.cos(a) + vz * Math.sin(a)) * ro
        );
        const depth = (z / ro + 1) / 2;
        dots.push({ x: px, y: py, z, r: ((o.partR ?? 1.2) + (o.partRDepth ?? 1.6) * depth) * rs, white: 0.3 - 0.22 * depth });
      }
    }
    const visible = dots.filter(d => (d.a ?? 1) >= 0.02);
    for (const d of visible) d.r = Math.max(o.rMin ?? 0.3, d.r);
    return visible.sort((a, b) => a.z - b.z);
  }
  function mount(canvas, { size = 64, paused = false, speed = 1 } = {}) {
    const ctx = canvas.getContext('2d');
    if (!ctx) return { setPaused() {}, destroy() {} };
    const preset = presets[size] || presets[64];
    const opts = {
      orbitN: Math.max(1, Math.round(12 * preset.count)),
      ghostN: Math.max(1, Math.round(40 * preset.count)),
      ghostR: 0.9 * preset.size, ghostA: 0.5, particles: 3,
      partR: 1.2 * preset.size, partRDepth: 1.6 * preset.size, rsPow: 0.6, rMin: 0.3
    };
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * ratio; canvas.height = size * ratio;
    canvas.style.width = size + 'px'; canvas.style.height = size + 'px';
    ctx.scale(ratio, ratio);
    const media = matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0, t = 0.8, previous = null, disposed = false;
    function draw() {
      ctx.clearRect(0, 0, size, size);
      for (const d of frameOrbits(size, t, opts)) {
        const w = Math.min(1, Math.max(0, d.white));
        const g = Math.round(w * 255);
        ctx.fillStyle = `rgba(${g},${g},${g},${d.a ?? 1})`;
        ctx.beginPath(); ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2); ctx.fill();
      }
    }
    function tick(now) {
      if (disposed || paused || media.matches || document.hidden) return;
      if (previous !== null) t += Math.min((now - previous) / 1000, 0.05) * preset.speed * speed;
      previous = now; draw(); frame = requestAnimationFrame(tick);
    }
    function sync() {
      cancelAnimationFrame(frame); previous = null; draw();
      if (!disposed && !paused && !media.matches && !document.hidden) frame = requestAnimationFrame(tick);
    }
    document.addEventListener('visibilitychange', sync);
    media.addEventListener('change', sync);
    sync();
    return {
      setPaused(value) { paused = value; sync(); },
      destroy() { disposed = true; cancelAnimationFrame(frame); document.removeEventListener('visibilitychange', sync); media.removeEventListener('change', sync); }
    };
  }
  window.ThinkingOrbs = { mount };
})();
