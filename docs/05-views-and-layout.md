[Contents](../README.md) · [← 4. Title block editor](04-title-block-editor.md) · [6. Drawings →](06-drawings.md)

# 5. Views and layout

| View | Direction |
|---|---|
| Front | Looking along +Y, X to the right, Z up |
| Top | From +Z, placed below the front view |
| Right | From +X, placed left of the front view |
| Section A-A, plane normal X | Cutting plane shown on the front view, viewed in +X (**Reverse**: -X) |
| Section A-A, plane normal Y | Cutting plane shown on the top view, viewed in +Y (**Reverse**: -Y) |
| Section A-A, plane normal Z | Cutting plane shown on the front view, viewed in -Z (**Reverse**: +Z) |
| Isometric | View direction (1, -1, 1) |

Two layouts are evaluated and the one giving the larger scale is used:

```
A:  Right | Front | A-A          B:  Right | Front | A-A | Iso
          | Top   | Iso                    | Top   |     |
```

Line widths follow ISO 128 in `config.json` > `line_widths_mm` (visible 0.5 mm, hidden, chain and hatch 0.25 mm, frame 0.7 mm) and are set in the **Title block editor** window ([section 4](04-title-block-editor.md#4-title-block-editor)).
Hatching is 45 deg at 2.5 mm spacing on paper (`hatch_angle_deg`, `hatch_spacing_mm`).

[Contents](../README.md) · [← 4. Title block editor](04-title-block-editor.md) · [6. Drawings →](06-drawings.md)
