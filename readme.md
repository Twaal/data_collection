## Finding the 3D Slicer executable path

The wrapper scripts (`run.ps1`, `run_batch.ps1`, `run_export.ps1`) all have a `$SlicerExe` variable that must point to your local `Slicer.exe`. The default value is:

```
C:/Users/theod/AppData/Local/slicer.org/3D Slicer 5.10.0/Slicer.exe
```

**To find the correct path on your machine:**

1. Open **3D Slicer**.
2. Open the Python console (View → Python Console).
3. Run:
   ```python
   import sys; print(sys.executable)
   ```
4. The printed path (e.g. `C:/Users/<you>/AppData/Local/slicer.org/3D Slicer X.Y.Z/bin/PythonSlicer.exe`) shows your Slicer install directory. The `Slicer.exe` you need is one level up from `bin/`, i.e. `C:/Users/<you>/AppData/Local/slicer.org/3D Slicer X.Y.Z/Slicer.exe`.

**Where to update it in the scripts:**

| Script | Variable | Line |
|---|---|---|
| `run.ps1` | `$slicerExe` | 5 |
| `run_batch.ps1` | `$SlicerExe` (param default) | 3 |
| `run_export.ps1` | `$SlicerExe` (param default) | 6 |

You can either edit the default value in each script, or pass the path at invocation:

```powershell
.\run_batch.ps1 -SlicerExe "C:/path/to/your/Slicer.exe" -Root "..."
.\run_export.ps1 -SlicerExe "C:/path/to/your/Slicer.exe" -Scene "..."
```

---

## Batch loading for full dataset trees

```powershell
"C:/Users/theod/AppData/Local/slicer.org/3D Slicer 5.10.0/Slicer.exe" --python-script "C:/Users/theod/Documents/uio/_masteroppgave/data_collection/automated_loading_batch.py" -- --root "C:/Users/theod/Documents/uio/_masteroppgave/data/stroma/ExampleTiles"
```

Optional flags:

- `--output-scene "C:/path/to/output/ExampleTiles-Project.mrb"`
- `--max-tiles-per-case 50`
- `--no-save`

Notes:

- The script assumes each case folder contains one image folder (`HE` by default) and any number of mask class folders (for example `stroma`, `tumor`, `background`, `tumorAnnotation`).
- All tiles in a case are **stacked into a single volume** (one tile per slice). Each case produces one volume node and one segmentation node whose mask data is aligned per-slice to the corresponding tile.
- **Workflow for pathologists:** open the saved scene, scroll through slices with the mouse wheel or slice slider to navigate tiles, toggle segment visibility, and use the Segment Editor to paint/erase on each slice. Save the scene when done.
- The volume node description lists the slice-to-tile mapping (e.g. `Slice 0: CaseName_HE_tile001`).

---

Exporting edited segmentations back to binary mask PNGs:

```powershell
.\run_export.ps1 -Scene "C:/Users/theod/Documents/uio/_masteroppgave/data/_annotations/ExampleTiles-20260215-120000.mrb"
```

Or directly:

```powershell
"C:/Users/theod/AppData/Local/slicer.org/3D Slicer 5.10.0/Slicer.exe" --no-main-window --python-script "C:/Users/theod/Documents/uio/_masteroppgave/data_collection/export_segmentations.py" -- --scene "path/to/scene.mrb" --root "C:/Users/theod/Documents/uio/_masteroppgave/data/stroma/ExampleTiles"
```

Optional flags:

- `--tag "_edited"` — suffix added before the extension (default: `_edited`)
- `--he-folder HE`
- `--ext .png`

Exported masks are saved next to the originals with the tag in the filename:

- Original: `R44-003/stroma/R44-003_stroma_tile001.png`
- Exported: `R44-003/stroma/R44-003_stroma_tile001_edited.png`

Masks are cropped back to original tile dimensions (stacking padding removed) and saved as 0/255 single-channel grayscale PNGs.

