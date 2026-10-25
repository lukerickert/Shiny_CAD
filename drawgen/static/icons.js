// Toolbar icons: 24 x 24 line drawings (stroke currentColor). Applied to the Part tab command buttons
// ([data-add], key = data-add or the kind in data-init), the Sketch tool and constraint buttons ([data-tool], [data-con]:
// key con_<name>), the Drawings tool buttons ([data-tool]; the Sketch tool: key ann_sketch) and the Assembly and Analysis
// buttons ([data-icon]).
(function () {
  const S = 'fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"';
  const F = 'fill="currentColor" stroke="none"';
  const D = 'fill="none" stroke="currentColor" stroke-width="1.2" stroke-dasharray="2.5 2"';
  // a box in isometric view: top face, front face, side face
  const box = (x, y, w, h, d) => `<path ${S} d="M${x} ${y + d} l${w} 0 l0 ${h} l${-w} 0 Z M${x} ${y + d} l${d} ${-d} l${w} 0 l${-d} ${d} M${x + w} ${y + d} l${d} ${-d} l0 ${h} l${-d} ${d}"/>`;
  const ICONS = {
    // ---- Part: features
    sketch: `<path ${S} d="M4 17 L9 7 L15 15 L20 5"/><path ${D} d="M3 20 H21"/><circle cx="9" cy="7" r="1.4" ${F}/><circle cx="15" cy="15" r="1.4" ${F}/>`,
    axis: `<path ${S} stroke-dasharray="5 2 1 2" d="M3 20 L21 4"/><circle cx="12" cy="12" r="1.6" ${F}/><path ${S} d="M17 4 H21 V8"/>`,
    plane: `<path ${S} d="M3 16 L9 6 H21 L15 16 Z"/><path ${S} d="M12 11 V3"/><path ${S} d="M10 5 L12 3 L14 5"/>`,
    extrude: `<path ${D} d="M4 19 H14 L18 15"/>${box(4, 4, 10, 11, 4)}<path ${S} d="M20 13 V5 M18 7 L20 5 L22 7"/>`,
    cut: `${box(3, 6, 12, 11, 4)}<path ${S} d="M10 8 V4 M8 6 L10 4 L12 6"/><path ${S} stroke-width="2" d="M7 11 L13 11 M7 11 L7 20 M13 11 L13 20"/><path ${D} d="M7 20 H13"/>`,
    revolve: `<path ${D} d="M12 2 V22"/><path ${S} d="M12 5 C18 5 18 10 12 10 M12 14 C19 14 19 20 12 20"/><path ${S} d="M12 5 C6 5 6 10 12 10 M12 14 C5 14 5 20 12 20"/><path ${S} d="M20 3 A8 8 0 0 1 22 8 M20.5 6.5 L22 8 L23.5 6.3"/>`,
    fillet: `<path ${S} d="M4 20 V9 A5 5 0 0 1 9 4 H20"/><path ${D} d="M4 9 V4 H9"/>`,
    chamfer: `<path ${S} d="M4 20 V10 L10 4 H20"/><path ${D} d="M4 10 V4 H10"/>`,
    shell: `<path ${S} d="M4 7 H20 V20 H4 Z"/><path ${S} d="M7 10 H17 V20 M7 10 V20"/>`,
    thread: `<path ${S} d="M5 8 H19 M5 16 H19"/><path ${S} d="M6 8 L8 16 M9 8 L11 16 M12 8 L14 16 M15 8 L17 16"/>`,
    hole: `${box(3, 6, 14, 10, 4)}<ellipse cx="10" cy="7" rx="3" ry="1.3" ${S}/><path ${S} d="M7 7 V13 M13 7 V13"/><ellipse cx="10" cy="13" rx="3" ry="1.3" ${D}/>`,
    pattern: `<circle cx="6" cy="6" r="2.2" ${S}/><circle cx="12" cy="6" r="2.2" ${S}/><circle cx="18" cy="6" r="2.2" ${S}/><circle cx="6" cy="13" r="2.2" ${S}/><circle cx="12" cy="13" r="2.2" ${S}/><circle cx="18" cy="13" r="2.2" ${S}/><circle cx="6" cy="20" r="2.2" ${S}/><circle cx="12" cy="20" r="2.2" ${S}/><circle cx="18" cy="20" r="2.2" ${S}/>`,
    mirror: `<path ${D} d="M12 2 V22"/><path ${S} d="M9 6 L4 10 V18 L9 16 Z"/><path ${S} d="M15 6 L20 10 V18 L15 16 Z"/>`,
    sweep: `<path ${S} d="M3 19 C6 8 12 20 15 9 C16 6 18 5 20 5"/><ellipse cx="4" cy="19" rx="1.6" ry="2.4" ${S}/><ellipse cx="20" cy="5" rx="1.6" ry="2.4" ${S}/><path ${D} d="M3 15 C6 4 12 16 15 5 C16 2.5 18 2 20 2.6"/>`,
    // ---- Part: mesh preparation
    place: `<path ${S} d="M3 20 H21 M3 20 V4"/><path ${D} d="M12 8 L19 8 L19 15 L12 15 Z"/><path ${S} d="M6 13 H12 V19 H6 Z M14 12 L9 15"/><path ${S} d="M9 15 L11.5 15.2 M9 15 L10.2 12.8"/>`,
    import: `${box(5, 9, 10, 9, 4)}<path ${S} d="M12 2 V10 M9 7 L12 10 L15 7"/>`,
    boolean: `<circle cx="9.5" cy="12" r="6" ${S}/><circle cx="14.5" cy="12" r="6" ${S}/><path d="M12 6.8 A6 6 0 0 1 12 17.2 A6 6 0 0 1 12 6.8 Z" fill="currentColor" stroke="none" opacity="0.5"/>`,
    split: `${box(3, 7, 14, 10, 4)}<path ${S} stroke-width="1.8" d="M10 3 V22"/><path ${S} d="M6 4 H14"/>`,
    unify: `<path ${S} d="M3 6 H21 V18 H3 Z"/><path ${D} d="M12 6 V18 M3 12 H21"/><path ${S} d="M9 12 H15 M13 10 L15 12 L13 14 M11 10 L9 12 L11 14"/>`,
    heal: `<path ${S} d="M4 18 L10 6 H20 L14 18 Z"/><path ${S} d="M12 9 V15 M9 12 H15"/>`,
    defeature: `${box(3, 7, 14, 10, 4)}<path ${S} d="M10 10 L14 14 M14 10 L10 14"/>`,
    smooth: `<path ${S} d="M3 15 Q6 9 9 15 T15 15 T21 15"/><path ${D} d="M3 10 L6 7 L9 11 L12 6 L15 10 L18 7 L21 10"/>`,
    replace: `<path ${S} d="M3 17 L8 8 H21 L16 17 Z"/><path ${D} d="M3 13 L8 4 H21 L16 13"/><path ${S} d="M12 2 V6 M10 4 L12 6 L14 4"/>`,
    combine: `<path ${S} d="M3 17 L8 7 H21 L16 17 Z"/><path ${D} d="M9.5 7 L4.5 17 M14.5 7 L9.5 17"/><path ${S} d="M11 12 H14"/>`,
    // ---- Part: surfaces
    surf_extract: `${box(3, 8, 12, 9, 4)}<path ${S} d="M9 6 L13 2 H21 L17 6 Z"/><path ${D} d="M12 6 V8"/>`,
    surf_fit: `<path ${S} d="M3 17 Q8 7 12 12 T21 9"/><path ${S} d="M3 21 Q8 11 12 16 T21 13"/><path ${D} d="M4 17 L6 10 L9 13 L12 8 L15 11 L18 7"/>`,
    surf_sketch: `<path ${S} d="M3 18 Q8 10 12 15 T21 12"/><path ${S} d="M3 11 Q8 3 12 8 T21 5"/><path ${S} d="M3 18 V11 M21 12 V5 M12 15 V8"/>`,
    surf_revolve: `<path ${D} d="M12 2 V22"/><path ${S} d="M12 5 Q20 7 12 10 M12 14 Q22 16 12 20"/><path ${S} d="M12 5 Q4 7 12 10 M12 14 Q2 16 12 20"/>`,
    surf_loft: `<ellipse cx="12" cy="5" rx="4" ry="1.6" ${S}/><ellipse cx="12" cy="19" rx="8" ry="2.4" ${S}/><path ${S} d="M8 5 C7 11 4 13 4 19 M16 5 C17 11 20 13 20 19"/>`,
    surf_fill: `<path ${S} d="M4 8 L9 4 L19 6 L20 15 L12 20 L4 16 Z"/><path ${D} d="M4 8 L12 20 M9 4 L20 15 M19 6 L4 16"/>`,
    surf_fillet: `<path ${S} d="M3 20 H11 A8 8 0 0 0 19 12 V3"/><path ${D} d="M3 15 H11 A3 3 0 0 0 14 12 V3"/>`,
    surf_offset: `<path ${S} d="M3 14 Q8 6 12 11 T21 8"/><path ${S} d="M3 20 Q8 12 12 17 T21 14"/><path ${S} d="M12 11 V17 M10.5 15.5 L12 17 L13.5 15.5"/>`,
    surf_import: `<path ${S} d="M3 16 Q8 8 12 13 T21 10"/><path ${S} d="M12 2 V9 M9 6 L12 9 L15 6"/>`,
    surf_sew: `<path ${S} d="M3 16 Q7 8 11 12"/><path ${S} d="M13 12 Q17 16 21 8"/><path ${S} stroke-width="1.2" d="M9 10 L15 14 M9 14 L15 10"/>`,
    thicken: `<path ${S} d="M3 12 Q8 4 12 9 T21 6"/><path ${S} d="M3 18 Q8 10 12 15 T21 12"/><path ${S} d="M3 12 V18 M21 6 V12"/><path ${S} d="M12 9 V15"/>`,
    surf_cut: `${box(3, 8, 14, 10, 4)}<path ${S} stroke-width="1.8" d="M2 14 Q10 6 22 12"/>`,
    curve_extract: `${box(3, 8, 14, 10, 4)}<path ${S} stroke-width="2.2" d="M3 12 H17 L21 8"/>`,
    curve_section: `<path ${S} d="M3 16 Q8 8 12 13 T21 10"/><path ${S} d="M6 4 L18 20"/><circle cx="10" cy="10.5" r="1.6" ${F}/><circle cx="14.5" cy="15.5" r="1.6" ${F}/>`,
    surf_from_curve: `<path ${S} stroke-width="2" d="M3 19 Q8 11 12 16 T21 13"/><path ${S} d="M3 11 Q8 3 12 8 T21 5"/><path ${D} d="M3 19 V11 M21 13 V5"/>`,
    surf_trim: `<path ${S} d="M3 16 Q8 6 12 11 T21 8"/><path ${D} d="M3 16 V21 M12 11 V21 M3 21 H12"/><path ${S} d="M15 14 L20 20 M20 14 L15 20"/>`,
    surf_extend: `<path ${S} d="M3 16 Q8 6 12 11 T17 10"/><path ${D} d="M17 10 Q19 9.5 22 8"/><path ${S} d="M19 4 L22 8 L18 9"/>`,
    // ---- Sketch tools
    select: `<path ${S} d="M6 3 L18 13 H12 L15 20 L12.5 21 L9.5 14 L5 18 Z"/>`,
    line: `<path ${S} d="M4 20 L20 4"/><circle cx="4" cy="20" r="1.6" ${F}/><circle cx="20" cy="4" r="1.6" ${F}/>`,
    rect: `<rect x="4" y="6" width="16" height="12" ${S}/><circle cx="4" cy="6" r="1.6" ${F}/><circle cx="20" cy="18" r="1.6" ${F}/>`,
    rect3: `<path ${S} d="M3 14 L13 4 L21 12 L11 22 Z"/><circle cx="3" cy="14" r="1.6" ${F}/><circle cx="13" cy="4" r="1.6" ${F}/><circle cx="21" cy="12" r="1.6" ${F}/>`,
    rectc: `<rect x="4" y="6" width="16" height="12" ${S}/><path ${D} d="M4 6 L20 18 M20 6 L4 18"/><circle cx="12" cy="12" r="1.6" ${F}/>`,
    slot: `<path ${S} d="M8 7 H16 A5 5 0 0 1 16 17 H8 A5 5 0 0 1 8 7 Z"/><path ${D} d="M8 12 H16"/><circle cx="8" cy="12" r="1.3" ${F}/><circle cx="16" cy="12" r="1.3" ${F}/>`,
    tarc: `<path ${S} d="M3 18 H11"/><path ${S} d="M11 18 A7 7 0 0 0 18 11"/><circle cx="11" cy="18" r="1.5" ${F}/><circle cx="18" cy="11" r="1.5" ${F}/>`,
    circle3: `<circle cx="12" cy="12" r="8" ${S}/><circle cx="4.5" cy="9.5" r="1.6" ${F}/><circle cx="17" cy="5.8" r="1.6" ${F}/><circle cx="15.5" cy="19.2" r="1.6" ${F}/>`,
    circle: `<circle cx="12" cy="12" r="8" ${S}/><circle cx="12" cy="12" r="1.4" ${F}/><path ${D} d="M12 12 H20"/>`,
    ellipse: `<ellipse cx="12" cy="12" rx="9" ry="5.5" ${S} transform="rotate(-20 12 12)"/><circle cx="12" cy="12" r="1.3" ${F}/>`,
    conic: `<path ${S} d="M3 20 Q12 2 21 20"/><path ${D} d="M3 20 L12 5 L21 20"/><circle cx="3" cy="20" r="1.3" ${F}/><circle cx="21" cy="20" r="1.3" ${F}/><circle cx="12" cy="5" r="1.3" ${S}/>`,
    spline: `<path ${S} d="M3 19 C7 19 7 6 12 6 S17 19 21 5"/><circle cx="3" cy="19" r="1.3" ${S}/><circle cx="12" cy="6" r="1.3" ${S}/><circle cx="21" cy="5" r="1.3" ${S}/>`,
    polygon: `<path ${S} d="M12 3 L20 7.5 L20 16.5 L12 21 L4 16.5 L4 7.5 Z"/>`,
    p3g: `<path ${S} d="M12 3 C16 3 20 6 20 10 C20 14 18 19 14 20 C10 21 5 18 4 14 C3 10 6 5 12 3 Z"/><circle cx="12" cy="12" r="1.2" ${F}/>`,
    arc: `<path ${S} d="M5 18 A9 9 0 0 1 19 10"/><circle cx="12" cy="18" r="1.4" ${F}/><path ${D} d="M12 18 L5 18 M12 18 L19 10"/>`,
    point: `<circle cx="12" cy="12" r="2.2" ${F}/><path ${S} d="M12 4 V8 M12 16 V20 M4 12 H8 M16 12 H20"/>`,
    move: `<path ${S} d="M12 3 V21 M3 12 H21 M9 6 L12 3 L15 6 M9 18 L12 21 L15 18 M6 9 L3 12 L6 15 M18 9 L21 12 L18 15"/>`,
    copy: `<rect x="4" y="4" width="11" height="11" ${S}/><path ${S} d="M9 9 H20 V20 H9 Z"/>`,
    rotate: `<path ${S} d="M5 12 A7 7 0 1 1 8 17.7"/><path ${S} d="M4 9 L5 12 L8 11"/><circle cx="12" cy="12" r="1.4" ${F}/>`,
    offset: `<path ${S} d="M4 18 L10 6 H20"/><path ${D} d="M4 22 L12 10 H20"/>`,
    trim: `<path ${S} d="M4 12 H13"/><path ${D} d="M13 12 H20"/><path ${S} d="M13 4 V20"/><path ${S} d="M15 8 L19 4 M15 16 L19 20"/>`,
    extend: `<path ${S} d="M4 12 H12"/><path ${D} d="M12 12 H19"/><path ${S} d="M19 4 V20"/><path ${S} d="M16 10 L19 12 L16 14"/>`,
    dim: `<path ${S} d="M4 8 V16 M20 8 V16 M4 12 H20"/><path ${S} d="M7 10 L4 12 L7 14 M17 10 L20 12 L17 14"/>`,
    dimh: `<path ${S} d="M4 7 V14 M20 7 V14 M4 11 H20"/><path ${S} d="M7 9 L4 11 L7 13 M17 9 L20 11 L17 13"/><path ${S} d="M9 19 H15"/>`,
    dimv: `<path ${S} d="M7 4 H14 M7 20 H14 M11 4 V20"/><path ${S} d="M9 7 L11 4 L13 7 M9 17 L11 20 L13 17"/><path ${S} d="M19 9 V15"/>`,
    note: `<path ${S} d="M5 5 H19 M12 5 V19 M9 19 H15"/>`,
    leader: `<path ${S} d="M4 18 L11 9 H20"/><path ${S} d="M6 15 L4 18 L7.5 17.5"/>`,
    h: `<path ${S} d="M4 7 V14 M20 7 V14 M4 11 H20"/><path ${S} d="M7 9 L4 11 L7 13 M17 9 L20 11 L17 13"/>`,
    v: `<path ${S} d="M7 4 H14 M7 20 H14 M11 4 V20"/><path ${S} d="M9 7 L11 4 L13 7 M9 17 L11 20 L13 17"/>`,
    a: `<path ${S} d="M4 16 L16 4 M2 13 L7 18 M13 2 L18 7"/><path ${S} d="M7 13 L4 16 L8 17 M13 7 L16 4 L15 8"/>`,
    angle: `<path ${S} d="M4 20 H21 M4 20 L17 5"/><path ${S} d="M13 20 A9 9 0 0 0 10 13.2"/><path ${S} d="M12.6 15.9 L10 13.2 L13.6 13.6"/>`,
    diameter: `<circle cx="12" cy="12" r="7" ${S}/><path ${S} d="M4 20 L20 4"/>`,
    radius: `<path ${S} d="M4 18 A9 9 0 0 1 20 12"/><path ${S} d="M12 18 L18 10"/><circle cx="12" cy="18" r="1.4" ${F}/>`,
    ann_sketch: `<path ${S} d="M4 20 L5 15 L16 4 L20 8 L9 19 Z M14 6 L18 10"/>`,
    // ---- Sketch: constraints (key con_<name>)
    con_coincident: `<path ${S} d="M4 19 L12 12 M20 5 L12 12"/><circle cx="12" cy="12" r="2.6" ${F}/>`,
    con_horizontal: `<path ${S} d="M4 12 H20 M4 9 V15 M20 9 V15"/>`,
    con_vertical: `<path ${S} d="M12 4 V20 M9 4 H15 M9 20 H15"/>`,
    con_parallel: `<path ${S} d="M5 19 L13 5 M11 19 L19 5"/>`,
    con_perpendicular: `<path ${S} d="M4 19 H20 M10 19 V5"/><path ${S} d="M10 15 H14 V19"/>`,
    con_tangent: `<circle cx="12" cy="14" r="6" ${S}/><path ${S} d="M3 8 H21"/><circle cx="12" cy="8" r="1.4" ${F}/>`,
    con_equal: `<path ${S} d="M5 9 H19 M5 15 H19"/>`,
    con_pointon: `<path ${S} d="M4 18 L20 6"/><circle cx="12" cy="12" r="2.4" ${F}/>`,
    con_midpoint: `<path ${S} d="M4 17 L20 7"/><circle cx="12" cy="12" r="2.2" ${F}/><path ${S} d="M4 14 V20 M20 4 V10"/>`,
    con_concentric: `<circle cx="12" cy="12" r="8" ${S}/><circle cx="12" cy="12" r="4" ${S}/><circle cx="12" cy="12" r="1.2" ${F}/>`,
    con_symmetric: `<path ${D} d="M12 3 V21"/><circle cx="6" cy="12" r="2.2" ${F}/><circle cx="18" cy="12" r="2.2" ${F}/>`,
    con_fix: `<path ${S} d="M12 4 V12 M5 12 H19 M7 12 L4 16 M11 12 L8 16 M15 12 L12 16 M19 12 L16 16"/>`,
    detail: `<circle cx="10" cy="10" r="6" ${S}/><path ${S} d="M14.5 14.5 L20 20"/><circle cx="10" cy="10" r="2" ${F}/>`,
    // ---- Analysis
    fa_mesh: `<path ${S} d="M3 20 L12 4 L21 20 Z M7.5 12 H16.5 M12 20 L7.5 12 M12 20 L16.5 12"/>`,
    fa_solve: `<path ${S} d="M7 4 L19 12 L7 20 Z"/>`,
    fa_stop: `<rect x="6" y="6" width="12" height="12" ${S}/>`,
    fa_beam: `<path ${S} d="M4 17 L20 7"/><path ${S} stroke-width="3" d="M6 15.75 L18 8.25"/><circle cx="4" cy="17" r="1.8" ${F}/><circle cx="20" cy="7" r="1.8" ${F}/>`,
    fa_rod: `<path ${S} d="M4 17 L20 7"/><circle cx="4" cy="17" r="1.8" ${F}/><circle cx="20" cy="7" r="1.8" ${F}/>`,
    fa_skbeams: `<path ${D} d="M3 20 H21"/><path ${S} stroke-width="2.6" d="M4 17 L9 7 L15 15 L20 5"/><circle cx="9" cy="7" r="1.4" ${F}/><circle cx="15" cy="15" r="1.4" ${F}/>`,
    fa_pface: `${box(4, 9, 11, 9, 5)}<path fill="currentColor" fill-opacity="0.3" stroke="none" d="M4 14 l5 -5 l11 0 l-5 5 Z"/>`,
    fa_ppts: `<path ${S} d="M4 17 L8 6 L19 8 L20 18 Z"/><circle cx="4" cy="17" r="1.6" ${F}/><circle cx="8" cy="6" r="1.6" ${F}/><circle cx="19" cy="8" r="1.6" ${F}/><circle cx="20" cy="18" r="1.6" ${F}/>`,
    fa_fast: `<path ${S} d="M7 3 H17 V7 H7 Z M10 7 V20 H14 V7 M10 10 L14 11 M10 13 L14 14 M10 16 L14 17"/>`,
    fa_rp: `<path ${S} d="M12 3 L12 21 M3 12 L21 12"/><circle cx="12" cy="12" r="4" ${S}/><path ${S} d="M5 5 L8 8 M19 5 L16 8 M5 19 L8 16 M19 19 L16 16"/>`,
    fa_sup: `<path ${S} d="M12 6 L6 16 H18 Z M4 19 H20 M6 19 L4 21.5 M10 19 L8 21.5 M14 19 L12 21.5 M18 19 L16 21.5"/><circle cx="12" cy="6" r="1.6" ${F}/>`,
    fa_load: `<path ${S} d="M12 3 V17 M7 12 L12 17 L17 12 M5 21 H19"/>`,
    // ---- Explicit
    xp_build: `<path ${S} d="M5 4 H14 L19 9 V20 H5 Z M14 4 V9 H19 M8 13 H16 M8 16.5 H13"/>`,
    xp_starter: `<path ${S} d="M7 4 L15 12 L7 20 Z M18 5 V19"/>`,
    // ---- Assembly
    as_part: `${box(3, 9, 11, 10, 4)}<path ${S} d="M19 2 V8 M16 5 H22"/>`,
    as_delete: `<path ${S} d="M5 7 H19 M9.5 7 V4.5 H14.5 V7 M7 7 L8 20 H16 L17 7 M10.5 10.5 V16.5 M13.5 10.5 V16.5"/>`,
    as_mates: `<path ${S} d="M9 6 H20 M9 12 H20 M9 18 H20"/><circle cx="5" cy="6" r="1.4" ${F}/><circle cx="5" cy="12" r="1.4" ${F}/><circle cx="5" cy="18" r="1.4" ${F}/>`,
    measure: `<path ${S} d="M3 16 L16 3 L21 8 L8 21 Z M7 12 L9 14 M10 9 L12 11 M13 6 L15 8"/>`,
    as_box: `<path ${D} d="M3 5 H17 V15 H3 Z"/><path ${S} d="M13 11 L21 19 M13 11 L13 17.5 M13 11 L19.5 11"/>`,
    as_showall: `<path ${S} d="M2 12 C5 6.5 8.5 4.5 12 4.5 S19 6.5 22 12 C19 17.5 15.5 19.5 12 19.5 S5 17.5 2 12 Z"/><circle cx="12" cy="12" r="3.2" ${S}/>`,
    as_invert: `<path ${S} d="M2 12 C5 6.5 8.5 4.5 12 4.5 S19 6.5 22 12 C19 17.5 15.5 19.5 12 19.5 S5 17.5 2 12 Z"/><path ${F} d="M12 8.8 A3.2 3.2 0 0 1 12 15.2 Z"/><path ${S} d="M12 8.8 A3.2 3.2 0 0 0 12 15.2"/>`,
    as_undo: `<path ${S} d="M9 7 L4 11 L9 15 M4 11 H14 A6 6 0 0 1 14 23"/>`,
    as_redo: `<path ${S} d="M15 7 L20 11 L15 15 M20 11 H10 A6 6 0 0 0 10 23"/>`,
    as_check: `<circle cx="10" cy="10" r="6" ${S}/><path ${S} d="M14.5 14.5 L20 20 M7.5 10 L9.5 12 L13 8"/>`,
    as_solve: `<path ${S} d="M4 13 L9 18 L20 6"/>`,
    mate_coincident: `<path ${S} d="M3 12 H21 M5 12 V5 H15 V12 M9 12 V19 H19 V12"/>`,
    mate_distance: `<path ${S} d="M3 9 H14 V4 H3 Z M8 15 H16 V20 H8 Z M14 9 H21 M16 15 H21 M18.5 9 V15 M17 10.5 L18.5 9 L20 10.5 M17 13.5 L18.5 15 L20 13.5"/>`,
    mate_parallel: `<path ${S} d="M3 8 H21 M3 16 H21"/><path ${S} d="M10 4 L8 8 M16 4 L14 8 M10 20 L12 16 M16 20 L18 16"/>`,
    mate_angle: `<path ${S} d="M4 19 H20 M4 19 L16 6 M11 19 A7 7 0 0 0 8.75 13.86"/>`,
    mate_concentric: `<circle cx="12" cy="12" r="8" ${S}/><circle cx="12" cy="12" r="4.5" ${S}/><path ${D} d="M12 1.5 V22.5 M1.5 12 H22.5"/>`,
    mate_tangent: `<circle cx="12" cy="10" r="6" ${S}/><path ${S} d="M3 16 H21"/><circle cx="12" cy="16" r="1.5" ${F}/>`,
    mate_gear: `<circle cx="8" cy="12" r="4.5" ${S}/><circle cx="17" cy="12" r="3" ${S}/><path ${S} d="M8 5.5 V7.5 M8 16.5 V18.5 M1.5 12 H3.5 M3.4 7.4 L4.8 8.8 M3.4 16.6 L4.8 15.2 M17 7.5 V9 M17 15 V16.5 M20.5 12 H22"/>`,
    mate_point: `<path ${S} d="M12 3 V8.5 M12 15.5 V21 M3 12 H8.5 M15.5 12 H21"/><circle cx="12" cy="12" r="2.6" ${F}/>`,
    balloon: `<circle cx="12" cy="9" r="6" ${S}/><path ${S} d="M9 14 L5 21"/><text x="12" y="12" font-size="8" text-anchor="middle" fill="currentColor" font-family="sans-serif">1</text>`,
  };
  function icon(key) {
    const body = ICONS[key];
    return body ? `<svg class="tb-ico" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">${body}</svg>` : "";
  }
  function apply(scope, attr, keyOf) {
    document.querySelectorAll(scope + " button[" + attr + "]").forEach(b => {
      if (b.querySelector("svg.tb-ico")) return;
      const key = keyOf(b);
      const svg = icon(key);
      if (!svg) return;
      const label = b.textContent.trim();
      b.innerHTML = svg + `<span class="tb-lbl">${label}</span>`;
      b.classList.add("ico-btn");
      if (!b.title) b.title = label;
    });
  }
  function applyAll() {
    apply("#tab-part", "data-add", b => { if (b.dataset.init) { try { const i = JSON.parse(b.dataset.init); if (i.kind === "revolve") return "surf_revolve"; } catch (e) { /* ignore */ } } return b.dataset.add; });
    apply("#tab-sketch", "data-tool", b => b.dataset.tool);
    apply("#tab-sketch", "id", b => ({ "sk-pattern": "pattern" })[b.id] || "");
    apply("#tab-sketch", "data-con", b => "con_" + b.dataset.con);
    apply("#tab-asm", "data-icon", b => b.dataset.icon);
    apply("#tab-part", "data-icon", b => b.dataset.icon);
    apply("#tab-fea", "data-icon", b => b.dataset.icon);
    apply("#tab-xp", "data-icon", b => b.dataset.icon);
    apply("#tab-annotate", "data-tool", b => b.dataset.tool === "sketch" ? "ann_sketch" : b.dataset.tool);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", applyAll); else applyAll();
  window.toolbarIcon = icon;
})();
