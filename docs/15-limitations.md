[Contents](../README.md) · [← 14. Tests](14-tests.md)

# 15. Limitations

- Input is STEP only.
- Dimensions and notes are not written to the FCStd file.
- Dimensions in the DXF are lines and text, not DIMENSION entities.
- One section view per drawing.
- Sketch: arcs from three points cannot be drawn. Dimensions on a curve (radius of an ellipse, length of a spline) are not available; dimensions between curve points are. Imported splines and ellipses are polylines (**Convert to arc** / **spline** / **conic** in **Properties**, or **Convert N polyline(s)** in **Check**).
- Sketch: constraints are not written to the DXF file. The sketch file (**Save**) keeps them.
- Sketch: hatching is not imported or drawn.
- Sketch images: not exported to DXF or PDF. The lens model has one radial coefficient k1 with the distortion centre at the image centre.
- Part: fillet and chamfer are equal-distance on edges only; no draft. Loft is a surface feature (**Loft surface**).
- Assembly: mates use planar and cylindrical faces, straight and circular edges, vertices and the reference planes and axes of the components. Gear mates measure rotations within half a turn of the reference position.
- Cosmetic threads and hole callouts come from the **Hole** feature of parts; threads of imported STEP files and of assembly drawings are not drawn. Holes copied by a **Pattern** or a **Mirror** carry the thread and the callout of the source hole, and the callout count includes the copies.
- FEA mesh: structured hexahedra need block cells (6 faces with 4 edges each); no swept meshing of non-block cells, no contact or boundary condition definitions.
- Analysis: linear static only; no contact (touching bodies are bonded or not connected), no shell elements. Modal and buckling analyses: solid bodies, plates and rods only. U1 beams: no shear deformation; torsional stiffness G (I11 + I22), exact for ROUND and PIPE only. Body plates are prismatic parts and plate items are flat; both have one element layer.
- Explicit: the ShinyCAD geometry gives solid elements only (no shells); shell models come from the deck generator or an external .inp. The deck generator models a flat rectangular panel with beams along x and y, one material and no rigid bodies (impactors come from an external .inp; the rigid floor applies). Supports hold displacements of face nodes; loads other than the driver, gravity and the rigid floor come from the .inp. The results view reads legacy VTK files of anim_to_vtk.
- Projection time depends on the number of B-spline faces (approximately 10 s to 30 s per part for a 7 MB STEP part with 234 faces on a 2-core machine). Views are computed in parallel on machines with more than 2 cores.

[Contents](../README.md) · [← 14. Tests](14-tests.md)
