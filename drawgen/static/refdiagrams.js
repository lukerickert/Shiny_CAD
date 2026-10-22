// SVG profile diagrams for the thread and hole reference tables (reference.js).
(function () {
  const S = 'stroke="#223" stroke-width="1.4" fill="none"';
  const T = 'stroke="#2b4a6f" stroke-width="0.9" fill="none"';
  const D = 'stroke="#2b4a6f" stroke-width="0.9" fill="none" stroke-dasharray="5 3"';
  const F = 'font-family="sans-serif" font-size="11" fill="#1d2a3a"';
  const pts = a => a.map(p => p.join(",")).join(" ");

  /** Vertical dimension between y1 and y2 at x (arrows inside), label to the right. */
  function vdim(x, y1, y2, label, side) {
    const a = Math.min(y1, y2), b = Math.max(y1, y2);
    const tx = side === "left" ? x - 6 : x + 6, anchor = side === "left" ? "end" : "start";
    return `<line x1="${x}" y1="${a}" x2="${x}" y2="${b}" ${T}/>` +
      `<polygon points="${pts([[x, a], [x - 3, a + 8], [x + 3, a + 8]])}" fill="#2b4a6f"/>` +
      `<polygon points="${pts([[x, b], [x - 3, b - 8], [x + 3, b - 8]])}" fill="#2b4a6f"/>` +
      `<text x="${tx}" y="${(a + b) / 2 + 4}" text-anchor="${anchor}" ${F}>${label}</text>`;
  }
  function hdim(y, x1, x2, label) {
    return `<line x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" ${T}/>` +
      `<polygon points="${pts([[x1, y], [x1 + 8, y - 3], [x1 + 8, y + 3]])}" fill="#2b4a6f"/>` +
      `<polygon points="${pts([[x2, y], [x2 - 8, y - 3], [x2 - 8, y + 3]])}" fill="#2b4a6f"/>` +
      `<text x="${(x1 + x2) / 2}" y="${y - 6}" text-anchor="middle" ${F}>${label}</text>`;
  }
  const hline = (x1, x2, y, style, label, lx) => `<line x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" ${style}/>` + (label ? `<text x="${lx}" y="${y - 3}" ${F}>${label}</text>` : "");

  /** Text with a white background box (readable over hatching). */
  function boxText(x, y, label, anchor) {
    const w = label.length * 6.6 + 6, h = 14;
    const bx = anchor === "middle" ? x - w / 2 : anchor === "end" ? x - w : x - 3;
    return `<rect x="${bx}" y="${y - 11}" width="${w}" height="${h}" fill="#fff" fill-opacity="0.92"/><text x="${x}" y="${y}" text-anchor="${anchor || "start"}" ${F}>${label}</text>`;
  }

  /** Metric ISO thread (ISO 68-1): nut (internal thread) above the profile and bolt (external thread) below, both
   *  hatched; diameters as dimension lines from the thread axis (bolt: d, d2, d3 on the left; nut: D, D2, D1 on
   *  the right); H, h3, H1, P and the root radius; formulas listed under the figure. */
  function metric() {
    const P = 200, H = 0.866025 * P, x0 = 170, yd = 110, t = Math.tan(Math.PI / 6);
    const yD1 = yd + 0.625 * H, yd3 = yd + 17 / 24 * H, yd2 = yd + 0.5 * H, yTop = yd - H / 8, yBot = yd + 7 / 8 * H;
    const yAxis = yd + H + 90, yNut = yTop - 30, yBolt = yAxis - 34;
    let x = x0, prof = [[x, yd]];
    for (let i = 0; i < 2; i++) {
      x += P / 8; prof.push([x, yd]);
      x += 0.625 * H * t; prof.push([x, yD1]);
      x += P / 4; prof.push([x, yD1]);
      x += 0.625 * H * t; prof.push([x, yd]);
    }
    x += P / 8; prof.push([x, yd]);
    const xe = x;
    let bolt = `M ${x0} ${yd}`;
    for (let i = 0; i < 2; i++) {
      const xa = x0 + P / 8 + i * P, xf = xa + 0.625 * H * t, xg = xf + P / 4;
      const xr1 = xa + (yd3 - 10 - yd) * t, xr2 = xg + 0.625 * H * t - (yd3 - 10 - yd) * t;
      bolt += ` L ${xa} ${yd} L ${xr1} ${yd3 - 10} Q ${(xr1 + xr2) / 2} ${yd3 + 13} ${xr2} ${yd3 - 10} L ${xg + 0.625 * H * t} ${yd}`;
    }
    bolt += ` L ${xe} ${yd}`;
    const nutPoly = pts([[x0 - 10, yNut], [x0 - 10, yd]].concat(prof).concat([[xe + 10, yd], [xe + 10, yNut]]));
    const boltClip = bolt + ` L ${xe + 10} ${yd} L ${xe + 10} ${yBolt} L ${x0 - 10} ${yBolt} L ${x0 - 10} ${yd} Z`;
    let hatch = "", hatch2 = "";
    for (let hx = x0 - 600; hx < xe + 600; hx += 10) {
      hatch += `<line x1="${hx}" y1="${yAxis}" x2="${hx + 600}" y2="${yAxis - 600}" stroke="#9aa6b3" stroke-width="0.8"/>`;
      hatch2 += `<line x1="${hx}" y1="${yAxis - 600}" x2="${hx + 600}" y2="${yAxis}" stroke="#c4a484" stroke-width="0.8"/>`;
    }
    let tri = "";
    for (let i = 0; i < 2; i++) {
      const xa = x0 + P / 16 + i * P;
      tri += `<polyline points="${pts([[xa, yTop], [xa + P / 2, yBot], [xa + P, yTop]])}" ${D}/>`;
    }
    const xl = x0 - 14, xr = xe + 14;
    const dia = (xx, y, label, side) => `<line x1="${xx}" y1="${y}" x2="${xx}" y2="${yAxis}" ${T}/>` +
      `<polygon points="${pts([[xx, y], [xx - 3, y + 8], [xx + 3, y + 8]])}" fill="#2b4a6f"/>` +
      `<polygon points="${pts([[xx, yAxis], [xx - 3, yAxis - 8], [xx + 3, yAxis - 8]])}" fill="#2b4a6f"/>` +
      boxText(side === "left" ? xx - 5 : xx + 5, (y + yAxis) / 2 + 4, label, side === "left" ? "end" : "start");
    const xH = xr + 110, xh3 = xr + 150, xH1 = xr + 190;
    const ext = (y, xa, xb) => `<line x1="${xa}" y1="${y}" x2="${xb}" y2="${y}" ${T}/>`;
    const apex2 = x0 + P / 16 + P / 2;
    const flat8 = x0 + P + P / 8 + 0.625 * H * t + P / 4 + 0.625 * H * t;     // start of the last crest flat
    const flat4 = x0 + P / 8 + 0.625 * H * t;                                   // start of the first root flat
    const W = xH1 + 60, Hh = yAxis + 150;
    const formulas = ["H = 0.866 P (height of the fundamental triangle)", "d2 = D2 = d − 0.6495 P (pitch diameter)", "d3 = d − 1.2269 P (bolt minor diameter)",
      "D1 = d − 1.0825 P (nut minor diameter, tap drill)", "h3 = 17/24 H = 0.6134 P (bolt thread depth)", "H1 = 5/8 H = 0.5413 P (nut thread depth)",
      "R = H/6 = 0.1443 P (bolt root radius, min 0.125 P)", "Diameter lines from the thread axis show half diameters"];
    return `<svg viewBox="0 0 ${W} ${Hh}" width="${W}" height="${Hh}" class="ref-svg">` +
      `<defs><clipPath id="clipNut"><polygon points="${nutPoly}"/></clipPath><clipPath id="clipBolt"><path d="${boltClip}"/></clipPath></defs>` +
      `<g clip-path="url(#clipNut)">${hatch2}</g><g clip-path="url(#clipBolt)">${hatch}</g>` +
      `<line x1="${x0 - 10}" y1="${yNut}" x2="${xe + 10}" y2="${yNut}" ${S}/><line x1="${x0 - 10}" y1="${yBolt}" x2="${xe + 10}" y2="${yBolt}" ${S}/>` +
      hline(xl - 76, xr + 76, yd, D) + hline(xl - 76, xr + 76, yd2, D) + hline(xl - 76, xr + 76, yD1, D) + hline(xl - 76, xr + 76, yd3, D) +
      ext(yd, xr + 76, xH1 + 6) + ext(yd3, xr + 76, xh3 + 6) + ext(yD1, xr + 76, xH1 + 6) + ext(yTop, xe + 10, xH + 6) + ext(yBot, xe + 10, xH + 6) +
      tri + `<polyline points="${pts(prof)}" ${S}/>` + `<path d="${bolt}" ${S}/>` +
      `<line x1="${x0 - 110}" y1="${yAxis}" x2="${xe + 110}" y2="${yAxis}" stroke="#223" stroke-width="0.8" stroke-dasharray="12 3 2 3"/>` +
      `<text x="${xe + 114}" y="${yAxis + 4}" ${F}>thread axis</text>` +
      `<text x="${x0 - 10}" y="${yNut - 30}" ${F}>nut (internal thread, brown hatch): D, D2, D1; thread depth H1</text>` +
      `<text x="${x0 - 10}" y="${yBolt + 20}" ${F}>bolt (external thread, grey hatch): d, d2, d3; thread depth h3</text>` +
      dia(xl, yd3, "d3", "left") + dia(xl - 32, yd2, "d2", "left") + dia(xl - 64, yd, "d", "left") +
      dia(xr, yD1, "D1", "right") + dia(xr + 32, yd2, "D2", "right") + dia(xr + 64, yd, "D", "right") +
      vdim(xH, yTop, yBot, "", "right") + boxText(xH + 6, (yTop + yBot) / 2 + 4, "H", "start") +
      vdim(xh3, yd, yd3, "", "right") + boxText(xh3 + 6, (yd + yd3) / 2 + 4, "h3", "start") +
      vdim(xH1, yd, yD1, "", "right") + boxText(xH1 + 6, (yd + yD1) / 2 - 10, "H1", "start") +
      hdim(yNut - 12, apex2, apex2 + P, "P") +
      ext(yTop, flat8 - 2, flat8 + P / 8 + 2) + hdim(yTop - 10, flat8, flat8 + P / 8, "P/8") +
      hdim(yD1 - 12, flat4, flat4 + P / 4, "") + boxText(flat4 + P / 8, yD1 - 18, "P/4", "middle") +
      boxText(apex2, yBot + 18, "60°", "middle") +
      boxText(x0 + P / 16 + 3 * P / 2 + 18, yd3 + 26, "R", "start") +
      formulas.map((f, i) => `<text x="${x0 - 110}" y="${yAxis + 32 + i * 15}" ${F}>${f}</text>`).join("") +
      `</svg>`;
  }

  /** Trapezoidal thread (ISO 2904): external thread (screw, grey hatch) below and internal thread (nut, brown hatch)
   *  above, flank angle 30 deg, crest clearance ac at the major and minor diameters; diameters from the axis. */
  function trapezoidal() {
    const P = 170, ac = 0.125 * P, H1 = 0.5 * P, h3 = H1 + ac, x0 = 150, t = Math.tan(Math.PI / 12);
    const yD4 = 60, yd = yD4 + ac, yd2 = yd + H1 / 2, yD1 = yd + H1, yd3 = yD1 + ac;
    const yAxis = yd3 + 90, yNut = yD4 - 26, yBolt = yAxis - 28;
    const b = 0.366 * P - 0.54 * ac;           // root width of the external thread at d3
    const crest = P / 2 - 2 * (H1 / 2) * t;    // crest width at d
    const run = h3 * t;
    let x = x0, ext = [[x, yd3]];
    for (let i = 0; i < 2; i++) {
      x += b / 2; ext.push([x, yd3]); x += run; ext.push([x, yd]); x += crest; ext.push([x, yd]); x += run; ext.push([x, yd3]); x += b / 2; ext.push([x, yd3]);
    }
    const xe = x;
    const int = [];
    const flats = [];
    for (const p of ext) { const last = flats[flats.length - 1]; if (last && last[0][1] === p[1]) last[1] = p; else flats.push([p, p]); }
    for (const [p, q] of flats) {
      if (p[1] === yd3) int.push([p[0] - ac * t, yD1], [q[0] + ac * t, yD1]);
      else int.push([p[0] + ac * t, yD4], [q[0] - ac * t, yD4]);
    }
    const nutPoly = pts([[x0 - 10, yNut], [x0 - 10, yD1]].concat(int).concat([[xe + 10, yD1], [xe + 10, yNut]]));
    const boltPoly = pts([[x0 - 10, yBolt], [x0 - 10, yd3]].concat(ext).concat([[xe + 10, yd3], [xe + 10, yBolt]]));
    let hatch = "", hatch2 = "";
    for (let hx = x0 - 400; hx < xe + 400; hx += 9) {
      hatch += `<line x1="${hx}" y1="${yAxis}" x2="${hx + 400}" y2="${yAxis - 400}" stroke="#8a97a6" stroke-width="0.8"/>`;
      hatch2 += `<line x1="${hx}" y1="${yAxis - 400}" x2="${hx + 400}" y2="${yAxis}" stroke="#b08968" stroke-width="0.8"/>`;
    }
    const xl = x0 - 12, xr = xe + 12;
    const dia = (xx, y, label, side) => `<line x1="${xx}" y1="${y}" x2="${xx}" y2="${yAxis}" ${T}/>` +
      `<polygon points="${pts([[xx, y], [xx - 3, y + 8], [xx + 3, y + 8]])}" fill="#2b4a6f"/>` +
      `<polygon points="${pts([[xx, yAxis], [xx - 3, yAxis - 8], [xx + 3, yAxis - 8]])}" fill="#2b4a6f"/>` +
      `<text x="${side === "left" ? xx - 5 : xx + 5}" y="${(y + yAxis) / 2 + 4}" text-anchor="${side === "left" ? "end" : "start"}" ${F}>${label}</text>`;
    const W = Math.max(xr + 260, 900), Hh = yAxis + 60;
    return `<svg viewBox="0 0 ${W} ${Hh}" width="${W}" height="${Hh}" class="ref-svg">` +
      `<defs><clipPath id="clipNutT"><polygon points="${nutPoly}"/></clipPath><clipPath id="clipBoltT"><polygon points="${boltPoly}"/></clipPath></defs>` +
      `<g clip-path="url(#clipNutT)">${hatch2}</g><g clip-path="url(#clipBoltT)">${hatch}</g>` +
      `<line x1="${x0 - 10}" y1="${yNut}" x2="${xe + 10}" y2="${yNut}" ${S}/><line x1="${x0 - 10}" y1="${yBolt}" x2="${xe + 10}" y2="${yBolt}" ${S}/>` +
      hline(xl - 70, xr + 70, yD4, D) + hline(xl - 70, xr + 70, yd, D) + hline(xl - 70, xr + 70, yd2, D) + hline(xl - 70, xr + 70, yD1, D) + hline(xl - 70, xr + 70, yd3, D) +
      `<polyline points="${pts(ext)}" ${S}/>` + `<polyline points="${pts(int)}" stroke="#7a3b1e" stroke-width="1.4" fill="none"/>` +
      `<line x1="${x0 - 100}" y1="${yAxis}" x2="${xe + 100}" y2="${yAxis}" stroke="#223" stroke-width="0.8" stroke-dasharray="12 3 2 3"/>` +
      `<text x="${xe + 104}" y="${yAxis + 4}" ${F}>thread axis</text>` +
      `<text x="${x0 - 10}" y="${yNut - 8}" ${F}>nut (internal thread, brown): D4, D2, D1; thread depth H4 = h3</text>` +
      `<text x="${x0 - 10}" y="${yBolt + 16}" ${F}>screw (external thread, grey): d, d2, d3; thread depth h3</text>` +
      dia(xl, yd3, "d3", "left") + dia(xl - 28, yd2, "d2", "left") + dia(xl - 56, yd, "d", "left") +
      dia(xr, yD1, "D1", "right") + dia(xr + 28, yd2, "D2", "right") + dia(xr + 56, yD4, "D4", "right") +
      vdim(xr + 100, yD4, yd, "ac", "right") + vdim(xr + 100, yD1, yd3, "ac", "right") +
      vdim(xr + 130, yd, yD1, "H1", "right") + vdim(xr + 160, yd, yd3, "h3", "right") +
      hdim(yNut + 12, x0 + b / 2 + run, x0 + b / 2 + run + P, "P") +
      hdim(yd3 + 14, x0 + b / 2 + 2 * run + crest, x0 + b + 2 * run + crest, "b") +
      `<text x="${x0 + b / 2 + run + crest + 8}" y="${yd2 - 10}" ${F}>15°</text>` +
      `<text x="${x0 + b / 2 + run + crest / 2 - 8}" y="${yd - 8}" ${F}>R1</text>` +
      `<text x="${x0 + P + b + 2 * run + crest + 4}" y="${yd3 - 6}" ${F}>R2</text>` +
      `<text x="${x0 - 100}" y="${yAxis + 30}" ${F}>d2 = D2 = d − 0.5 P; d3 = d − 2 h3; D1 = d − P; D4 = d + 2 ac; H1 = 0.5 P; h3 = H4 = 0.5 P + ac; b = 0.366 P − 0.54 ac; flank angle 30°</text>` +
      `<text x="${x0 - 100}" y="${yAxis + 48}" ${F}>ac = 0.15 (P 1.5), 0.25 (P 2–5), 0.5 (P 6–12), 1 (P 14–44); R1 max = 0.5 ac at the crests, R2 max = ac at the roots; diameter lines from the axis show half diameters</text>` +
      `</svg>`;
  }

  /** Counterbore and countersink cross-sections. */
  function holes() {
    const F2 = F;
    const cb = (ox) => {
      const d = 36, d1 = 60, t = 34, top = 30, bot = 150;
      const cx = ox + 70;
      return `<polyline points="${pts([[ox, top], [cx - d1 / 2, top], [cx - d1 / 2, top + t], [cx - d / 2, top + t], [cx - d / 2, bot], [ox, bot]])}" ${S}/>` +
        `<polyline points="${pts([[ox + 140, top], [cx + d1 / 2, top], [cx + d1 / 2, top + t], [cx + d / 2, top + t], [cx + d / 2, bot], [ox + 140, bot]])}" ${S}/>` +
        `<line x1="${cx}" y1="${top - 10}" x2="${cx}" y2="${bot + 10}" stroke="#2b4a6f" stroke-width="0.8" stroke-dasharray="8 3 2 3"/>` +
        hdim(top - 12, cx - d1 / 2, cx + d1 / 2, "counterbore ⌀ d1") + hdim(bot + 26, cx - d / 2, cx + d / 2, "through hole ⌀ dh") +
        vdim(cx + d1 / 2 + 16, top, top + t, "t", "right") +
        `<text x="${ox}" y="${bot + 52}" ${F2}>Counterbore DIN 974-1 (ISO 4762, DIN 7984)</text>`;
    };
    const cs = (ox) => {
      const d = 36, d2 = 76, t = 20, top = 30, bot = 150;
      const cx = ox + 70;
      return `<polyline points="${pts([[ox, top], [cx - d2 / 2, top], [cx - d / 2, top + t], [cx - d / 2, bot], [ox, bot]])}" ${S}/>` +
        `<polyline points="${pts([[ox + 140, top], [cx + d2 / 2, top], [cx + d / 2, top + t], [cx + d / 2, bot], [ox + 140, bot]])}" ${S}/>` +
        `<line x1="${cx}" y1="${top - 10}" x2="${cx}" y2="${bot + 10}" stroke="#2b4a6f" stroke-width="0.8" stroke-dasharray="8 3 2 3"/>` +
        hdim(top - 12, cx - d2 / 2, cx + d2 / 2, "countersink ⌀ d2") + hdim(bot + 26, cx - d / 2, cx + d / 2, "through hole ⌀ dh") +
        vdim(cx + d2 / 2 + 16, top, top + t, "t1", "right") +
        `<text x="${cx}" y="${top + t + 16}" text-anchor="middle" ${F2}>90°</text>` +
        `<text x="${ox}" y="${bot + 52}" ${F2}>Countersink 90°: DIN 74 F (ISO 10642), ISO 15065</text>`;
    };
    const tap = (ox) => {
      const dd = 44, dD1 = 34, top = 30, bot = 150;
      const cx = ox + 70;
      let z = "";
      for (let y = top + 8; y < bot - 6; y += 10) z += `<polyline points="${pts([[cx - dD1 / 2, y], [cx - dd / 2, y + 5], [cx - dD1 / 2, y + 10]])}" ${T}/><polyline points="${pts([[cx + dD1 / 2, y], [cx + dd / 2, y + 5], [cx + dD1 / 2, y + 10]])}" ${T}/>`;
      return `<polyline points="${pts([[ox, top], [cx - dD1 / 2, top], [cx - dD1 / 2, bot], [ox, bot]])}" ${S}/>` +
        `<polyline points="${pts([[ox + 140, top], [cx + dD1 / 2, top], [cx + dD1 / 2, bot], [ox + 140, bot]])}" ${S}/>` + z +
        `<line x1="${cx}" y1="${top - 10}" x2="${cx}" y2="${bot + 10}" stroke="#2b4a6f" stroke-width="0.8" stroke-dasharray="8 3 2 3"/>` +
        hdim(top - 12, cx - dd / 2, cx + dd / 2, "thread ⌀ d") + hdim(bot + 26, cx - dD1 / 2, cx + dD1 / 2, "tap drill ≈ D1") +
        `<text x="${ox}" y="${bot + 52}" ${F2}>Tapped hole (DIN 336 tap drill)</text>`;
    };
    return `<svg viewBox="0 0 840 220" width="840" height="220" class="ref-svg">` + tap(20) + cb(290) + cs(560) + `</svg>`;
  }

  window.refDiagrams = { metric, trapezoidal, holes };
})();
