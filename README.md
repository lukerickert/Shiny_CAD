# SHINYCAD

Local web application that creates ISO drawings from STEP files.
Each drawing has an ISO 5457 frame, an ISO 7200 title block, first-angle Front / Top / Right views, section A-A through the part centre and an isometric view.
Dimensions, notes and ISO 286 tolerances are added interactively.
Output is PDF, DXF, SVG and FCStd (FreeCAD document with a TechDraw page).
The **Sketches** pane of the **Drawings** tab creates 2D sketches on a blank sheet and edits DXF files, with geometric constraints and driving dimensions. Images are placed under a sketch as a reference, scaled from a measured distance and corrected for lens distortion and perspective. The same editor sketches on a view or on the sheet of a model drawing.
The **Part** tab creates 3D parts from sketches with extrude, cut and revolve features.
The **Analysis** tab runs linear static analyses of assemblies and parts with CalculiX: solid bodies, plates, beams, rods and preloaded fasteners. Modal (natural frequencies) and linear buckling analyses are available for solid bodies, plates and rods.
The **Explicit** tab builds and runs OpenCourant explicit analyses (ORC\*\*3 core) from the ShinyCAD geometry or a PrePoMax .inp, locally or on a Linux server, and shows the results.
Projection and hidden-line removal use OpenCascade through build123d.

## Quick start (Windows)

1. Install Python 3.10 to 3.14 (64-bit) from python.org with the py launcher.
2. Extract the zip file to a folder with a short path, for example `C:\SHINYCAD`.
3. Double-click `start.bat`. The first start installs the packages (approximately 500 MB); the browser opens `http://localhost:8765`.

Details and troubleshooting: [1. Installation](docs/01-installation.md), `INSTALL.txt`.

## Documentation

| Page | Sections |
|---|---|
| [1. Installation (Windows)](docs/01-installation.md) | [1.1 Solvers](docs/01-installation.md#11-solvers) |
| [2. Files](docs/02-files.md) | [2.1 Projects](docs/02-files.md#21-projects), [2.2 Publishing to GitHub](docs/02-files.md#22-publishing-to-github) |
| [3. Use](docs/03-use.md) | [3.1 Options](docs/03-use.md#31-options) |
| [4. Title block editor](docs/04-title-block-editor.md) | - |
| [5. Views and layout](docs/05-views-and-layout.md) | - |
| [6. Drawings](docs/06-drawings.md) | [6.1 Threads and holes reference](docs/06-drawings.md#61-threads-and-holes-reference), [6.2 Detail views](docs/06-drawings.md#62-detail-views), [6.3 Sketches on drawings](docs/06-drawings.md#63-sketches-on-drawings) |
| [7. DXF](docs/07-dxf.md) | - |
| [8. FCStd](docs/08-fcstd.md) | - |
| [9. Sketch](docs/09-sketch.md) | [9.1 Files](docs/09-sketch.md#91-files), [9.2 Drawing and modify tools](docs/09-sketch.md#92-drawing-and-modify-tools), [9.3 Constraints](docs/09-sketch.md#93-constraints), [9.4 Dimensions and notes](docs/09-sketch.md#94-dimensions-and-notes), [9.5 Images](docs/09-sketch.md#95-images) |
| [10. Part](docs/10-part.md) | [10.1 Tree](docs/10-part.md#101-tree), [10.2 Selection in the view](docs/10-part.md#102-selection-in-the-view), [10.3 Command bar](docs/10-part.md#103-command-bar), [10.4 Features](docs/10-part.md#104-features), [10.5 Configurations](docs/10-part.md#105-configurations), [10.6 3D view](docs/10-part.md#106-3d-view), [10.7 Files](docs/10-part.md#107-files), [10.8 Mesh preparation: import, partition, clean-up](docs/10-part.md#108-mesh-preparation-import-partition-clean-up), [10.9 Surfaces](docs/10-part.md#109-surfaces), [10.10 FEA mesh export](docs/10-part.md#1010-fea-mesh-export), [10.11 Measure](docs/10-part.md#1011-measure), [10.12 STL import](docs/10-part.md#1012-stl-import) |
| [11. Assembly](docs/11-assembly.md) | [11.1 Mates](docs/11-assembly.md#111-mates), [11.2 Mate check](docs/11-assembly.md#112-mate-check) |
| [12. Analysis](docs/12-analysis.md) | [12.1 Solver](docs/12-analysis.md#121-solver), [12.2 Controls](docs/12-analysis.md#122-controls), [12.3 Model](docs/12-analysis.md#123-model), [12.4 Members](docs/12-analysis.md#124-members), [12.5 Plates](docs/12-analysis.md#125-plates), [12.6 Fasteners](docs/12-analysis.md#126-fasteners), [12.7 Supports](docs/12-analysis.md#127-supports), [12.8 Loads](docs/12-analysis.md#128-loads), [12.9 Results](docs/12-analysis.md#129-results), [12.10 Modal and buckling analysis](docs/12-analysis.md#1210-modal-and-buckling-analysis) |
| [13. Explicit](docs/13-explicit.md) | [13.1 Executables and settings of this PC](docs/13-explicit.md#131-executables-and-settings-of-this-pc), [13.2 Documents and folders](docs/13-explicit.md#132-documents-and-folders), [13.3 Model](docs/13-explicit.md#133-model), [13.4 Runs](docs/13-explicit.md#134-runs), [13.5 Build](docs/13-explicit.md#135-build), [13.6 Solve](docs/13-explicit.md#136-solve), [13.7 Results](docs/13-explicit.md#137-results), [13.8 Console](docs/13-explicit.md#138-console) |
| [14. Tests](docs/14-tests.md) | - |
| [15. Limitations](docs/15-limitations.md) | - |
