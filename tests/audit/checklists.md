# Reference checklists for the SHINYCAD audit

Used by the `shinycad-audit` skill in the per-tab review. Each list names the functions of the reference program for
that tab. The review marks each item as present, partial (with the limit) or missing in SHINYCAD, from the code and
`docs/`, not from this file. Items already listed in `docs/15-limitations.md` are reported as known limits.

## Drawings tab (reference: FreeCAD TechDraw, Solid Edge Draft)

- Views: front, top, right, back, bottom, left, isometric; auxiliary view from a face; projection angle first and third
- Section views: single plane, offset (stepped), aligned, half; more than one per sheet; section arrows and labels
- Detail views: circle and rectangle, scale, label
- Broken views; partial views; view alignment and view-to-view spacing; view scale per view
- Hidden lines on and off per view; centre lines and centre marks for holes and cylinders; tangent edges
- Dimensions: linear, aligned, angular, radius, diameter, ordinate, chain, baseline, chamfer, arc length; tolerances
  (ISO 286 fit, +/- limits, general tolerance note); dimension text override and prefix/suffix; units and decimals
- Annotations: notes with leaders, surface finish symbols, welding symbols, geometric tolerance frames (GD&T), datums,
  balloons with a parts list (BOM) for assemblies, revision table
- Threads: cosmetic threads in all views, hole callouts (ISO 128), counterbore and countersink symbols
- Sheet: ISO 5457 sizes A0 to A4, title block ISO 7200, multi-sheet drawings, sheet-to-sheet references
- Output: PDF, DXF (with DIMENSION entities and layers), SVG, FCStd; print scale

## Sketches (reference: Solid Edge sketcher, FreeCAD Sketcher)

- Entities: line, polyline, rectangle (corner, centre, 3-point), circle (centre, 3-point), arc (centre, 3-point,
  tangent), ellipse, elliptical arc, spline (through points, by poles), conic, point, slot, polygon, text
- Modify: trim, extend, split, offset, fillet, chamfer, mirror, rotate, move, copy, scale, array (linear, circular),
  stretch, convert entity type
- Constraints: coincident, horizontal, vertical, parallel, perpendicular, tangent, equal, symmetric, concentric,
  collinear, fixed/lock, midpoint, point on curve, distance, horizontal/vertical distance, angle, radius, diameter;
  driving and reference dimensions; over-constrained and conflicting detection with a fix; degrees of freedom shown
- Snapping: endpoints, midpoints, centres, intersections, grid, tangent, perpendicular, polar angles; construction
  geometry; layers; selection filters
- Reference: project edges of the solid into the sketch (Include/Project geometry), external references, images
- Files: DXF import and export with layers and blocks, DWG, SVG, PDF

## Part tab (reference: Solid Edge ordered modelling, FreeCAD Part Design)

- Tree: sketches, planes, axes, points, features, bodies, surfaces; reorder, suppress, rollback (edit at an earlier
  state), rename, feature failure shown in the tree; configurations
- Sketch-based: extrude (blind, through all, to face, to next, symmetric, draft angle, thin wall), cut, revolve,
  sweep (path and guide), loft (sections and guides), helix, rib, boss/thread, hole (simple, counterbore, countersink,
  tapped, with standard tables)
- Dress-up: fillet (constant, variable, face), chamfer (distance, distance-angle, two distances), draft, shell,
  thicken, split by plane or surface
- Transform: pattern (linear, circular, along curve, fill), mirror (feature and body), move/rotate body, scale
- Boolean: union, subtract, intersect between bodies; multi-body parts; body copy
- Reference geometry: planes (offset, angle, through 3 points, tangent, midplane), axes, points, coordinate systems
- Surfaces: extrude, revolve, loft, sweep, bounded (BlueSurf), offset, trim, extend, stitch, replace face, delete face,
  thicken; region-based trim; surface to solid
- Selection: faces, edges, vertices, bodies by click, box, filters; hidden-line toggle; section at the sketch plane;
  shaded model underlay in sketches; measure (distance, angle, radius, area, volume, mass properties)
- Import: STEP, STL, IGES; repair (healing, sewing); export STEP, STL, 3MF
- Mesh preparation: partition (plane, flat edge, extend face, offset face), merge faces, remove features
  (fillets, holes), defeature, virtual topology; FEA mesh export (hex and tet, element sizes, sets per face)
- Parameters: variable table, equations between dimensions, feature dimensions edited in the view (keyboard-first)

## Assembly tab (reference: Solid Edge Assembly, FreeCAD Assembly)

- Insert part with placement; multiple occurrences; sub-assemblies; replace component; reload after part edit
- Mates: coincident (plane, axis, point), distance, angle, parallel, perpendicular, tangent, concentric, insert
  (axial + planar), gear, rack and pinion, cam, slot, symmetry, fixed; mate check and conflict report; degrees of
  freedom per component; drag with mates; explode view
- Interference check; mass and centre of gravity; measure between components
- Patterns of components; mirror component; configurations and suppressed components
- Drawings from assemblies: balloons, BOM; export STEP (with assembly structure)

## Analysis tab (reference: PrePoMax, CalculiX, Solid Edge Simulation)

- Geometry: solid, shell (mid-surface or surface body), beam, rod, plate by points; import .inp, .step, .stl;
  parts placed and mated; surface parts imported and placed (typed, two-point move, drag, mates)
- Mesh: tet (first and second order), hex (structured and swept), shell quad and tri, beam; local sizes on faces and
  edges; mesh quality report; renumbering; node and element sets by selection and by geometry
- Materials: elastic, plastic (tabular, bilinear), hyperelastic, thermal; orthotropic; library and user entries;
  per-body assignment; sections (solid, shell with thickness and offset, beam profiles)
- Supports: fixed, pinned, per DOF, displacement, symmetry, cylindrical/spherical, remote (reference point),
  spring; edge boundary conditions on shells (fixed, pinned, DOF, prescribed, symmetry)
- Loads: force, pressure, gravity, centrifugal, moment, remote force, line load, edge line load on shells, thermal,
  preloaded fasteners; load cases and steps; amplitudes
- Contact: surface-to-surface, node-to-surface, tie, friction, contact search between parts
- Steps: static, nonlinear static with increments, modal (frequencies), buckling, implicit and explicit dynamics,
  thermal; multiple steps; restart
- Results: displacement, stress (von Mises, principal, components), strain, reaction forces, contact pressure,
  mode shapes, buckling factors; deformed scale; probes; section cuts; history curves; report; export to ParaView
- Batch mode; solver settings (threads, path); job monitor with cancel

## Explicit (OpenCourant) (reference: ORC3 workspace, Radioss workflow)

- Runs: dated numbered run folders, settings report, clean, open folder, run history
- Model: from ShinyCAD geometry or PrePoMax .inp; part list; initial state; deck check; mesh view of the .inp
- Build: materials (elastic, plastic Johnson-Cook, failure), contacts (TYPE7, TYPE19, TYPE24; global tie, scoped
  pairs), time step control, output requests, rivet section, concentrated mass from primitives
- Solve: local (starter + engine), remote Linux server over SSH (queue, status, kill), environment switch, monitor
- Results: frames and fields, energy curves, time histories, probes, PNG and CSV export, ParaView scripts
- Tools: user scripts list and launch; console

## CAM tab (reference: FreeCAD CAM workbench)

See `docs/16-cam.md` section 16.11 for the correspondence table kept by the program. Items to check beyond it:

- Job: stock (box, cylinder, from part with offsets, from STEP), multiple setups with carried stock, fixtures (G54 to
  G59), machine limits and rapid rates, job template export and apply, coolant modes
- Tool bits: end mill, ball end, bull nose, chamfer, V-bit, drill, tap, thread mill, dovetail, T-slot, custom
  profile; tool library files; tool controller (feeds, speeds, spindle direction); feeds and speeds calculator
- Operations: Face, Pocket Shape, Profile (inside/outside, open edges), Drilling (peck, dwell, chip break, retract
  modes), Helix, Slot, Engrave, Deburr, Vcarve, Adaptive, 3D Pocket, 3D Surface, Waterline, Thread milling, Probe,
  Custom (G-code block), Pocket (legacy), Shape (legacy)
- Dressups: Tag (holding tabs), Ramp entry, Lead in/out, Dogbone, Boundary, Dragknife, Axis map, Z-correct
- Supplemental: Copy, Array, Comment, Stop, Fixture, Tool controller as operation
- Simulation: stock cut by the tool with progressive removal, gouge check, playback with speed and position;
  sanity check; path inspector (G-code line to path segment); machining time and tool change count
- Post: Estlcam, generic, grbl, LinuxCNC, Mach3; one file per setup; tool change handling; post-processor options
  (line numbers, comments, precision, units)
