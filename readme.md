In 3D Slicer get the path to python runtime by doing {import sys; sys.executable} to print the runtime path.

Batch loading for full dataset trees:

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

