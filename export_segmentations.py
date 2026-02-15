"""
Export edited segmentations from a saved 3D Slicer scene back to individual
binary-mask PNGs, placed alongside the original masks with a configurable
filename tag so originals are never overwritten.

Run with the 3D Slicer executable:
  "C:/path/to/Slicer.exe" --no-main-window --python-script export_segmentations.py -- \
      --scene "C:/path/to/_annotations/ExampleTiles-20260215.mrb" \
      --root  "C:/path/to/ExampleTiles"

Each case's segmentation node is unstacked slice-by-slice.  The slice-to-tile
mapping stored in the volume description (written by automated_loading_batch.py)
is used to reconstruct original filenames.  Each segment (class) is exported as
a 0/255 single-channel grayscale PNG cropped to the original tile dimensions.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

try:
    import SimpleITK as sitk
except ImportError:
    sitk = None

try:
    import slicer
    import vtk
except ImportError as error:
    raise RuntimeError(
        "3D Slicer Python API is not available in this interpreter.\n"
        "Run this script with the 3D Slicer executable, for example:\n"
        '"C:\\path\\to\\Slicer.exe" --no-main-window --python-script '
        '"export_segmentations.py" -- --scene "scene.mrb" --root "ExampleTiles"'
    ) from error

if not hasattr(slicer, "util"):
    raise RuntimeError(
        "This script requires the 3D Slicer Python runtime. "
        "Do not run it with a regular Python interpreter."
    )


# ---------------------------------------------------------------------------
#  CLI
# ---------------------------------------------------------------------------


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=(
            "Export edited segmentations from a saved 3D Slicer scene back to "
            "individual binary-mask PNGs alongside the originals."
        ),
    )
    parser.add_argument(
        "--scene",
        required=True,
        help="Path to the saved .mrb or .mrml scene file.",
    )
    parser.add_argument(
        "--root",
        required=True,
        help="Root data folder (same --root used when loading).",
    )
    parser.add_argument(
        "--tag",
        default="_edited",
        help="Tag appended to exported filenames before the extension (default: _edited).",
    )
    parser.add_argument(
        "--he-folder",
        default="HE",
        help="Name of the image folder inside each case (default: HE).",
    )
    parser.add_argument(
        "--ext",
        default=".png",
        help="Image / mask file extension (default: .png).",
    )
    parser.add_argument(
        "--keep-vtk-warnings",
        action="store_true",
        help="Keep VTK warning output enabled.",
    )
    args, _ = parser.parse_known_args(argv)
    return args


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------


def read_image_dimensions(file_path):
    """Return (height, width) of an image file by reading only its header."""
    if sitk is not None:
        reader = sitk.ImageFileReader()
        reader.SetFileName(str(file_path))
        reader.ReadImageInformation()
        size = reader.GetSize()  # (width, height, …)
        return size[1], size[0]

    # Fallback: load through Slicer (heavier)
    node = slicer.util.loadVolume(str(file_path))
    if not node:
        return None, None
    arr = slicer.util.arrayFromVolume(node)
    h, w = arr.shape[-2], arr.shape[-1]
    slicer.mrmlScene.RemoveNode(node)
    return h, w


def save_binary_png(array_2d, output_path):
    """Save a 2-D uint8 array as a single-channel grayscale PNG."""
    if sitk is not None:
        img = sitk.GetImageFromArray(array_2d.astype(np.uint8))
        sitk.WriteImage(img, str(output_path))
        return

    # Fallback: create a temporary label-map node and save via Slicer
    label_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode", "tmp_export")
    expanded = array_2d[np.newaxis, :, :]  # Slicer expects (Z, H, W)
    slicer.util.updateVolumeFromArray(label_node, expanded)
    slicer.util.saveNode(label_node, str(output_path))
    slicer.mrmlScene.RemoveNode(label_node)


def parse_tile_mapping(description):
    """Parse the volume node Description written by automated_loading_batch.py.

    Returns a list of tile stem names, one per slice index.
    Example line:  'Slice 0: R44-003_HE_tile001'  →  'R44-003_HE_tile001'
    """
    tile_names = []
    for line in (description or "").strip().splitlines():
        line = line.strip()
        if not line.startswith("Slice "):
            continue
        parts = line.split(": ", 1)
        if len(parts) == 2:
            tile_names.append(parts[1].strip())
    return tile_names


# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------


def main(argv):
    args = parse_args(argv)

    if not args.keep_vtk_warnings and hasattr(vtk.vtkObject, "GlobalWarningDisplayOff"):
        vtk.vtkObject.GlobalWarningDisplayOff()

    scene_path = Path(args.scene)
    root_path = Path(args.root)
    ext = args.ext if args.ext.startswith(".") else f".{args.ext}"
    tag = args.tag

    if not scene_path.is_file():
        raise FileNotFoundError(f"Scene file not found: {scene_path}")
    if not root_path.is_dir():
        raise FileNotFoundError(f"Root folder not found: {root_path}")

    # -- Load the scene ----------------------------------------------------
    print(f"Loading scene: {scene_path}")
    slicer.util.loadScene(str(scene_path))
    print("Scene loaded.")

    # -- Find all segmentation nodes ---------------------------------------
    seg_nodes = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
    if not seg_nodes:
        print("[WARN] No segmentation nodes found in scene.  Nothing to export.")
        return

    total_exported = 0

    for seg_node in seg_nodes:
        seg_name = seg_node.GetName()

        # Derive case name:  "<case>_Segmentation" → "<case>"
        suffix_tag = "_Segmentation"
        if seg_name.endswith(suffix_tag):
            case_name = seg_name[: -len(suffix_tag)]
        else:
            case_name = seg_name
            print(f"[WARN] Segmentation '{seg_name}' does not follow expected naming; using as case name.")

        # Find the matching HE volume
        vol_name = f"{case_name}_HE"
        vol_node = None
        for cls in ("vtkMRMLVectorVolumeNode", "vtkMRMLScalarVolumeNode"):
            for v in slicer.util.getNodesByClass(cls):
                if v.GetName() == vol_name:
                    vol_node = v
                    break
            if vol_node:
                break

        if not vol_node:
            print(f"[WARN] No volume '{vol_name}' found for segmentation '{seg_name}'; skipping.")
            continue

        # Tile mapping from volume description
        tile_names = parse_tile_mapping(vol_node.GetDescription())
        if not tile_names:
            print(f"[WARN] Volume '{vol_name}' has no slice-to-tile mapping in its description; skipping.")
            continue

        image_prefix = f"{case_name}_{args.he_folder}_"
        he_dir = root_path / case_name / args.he_folder

        # Pre-read original tile dimensions for cropping
        tile_dims = {}  # slice_idx → (height, width)
        for slice_idx, tile_stem in enumerate(tile_names):
            tile_suffix = tile_stem[len(image_prefix) :]  # e.g. "tile001"
            he_path = he_dir / f"{image_prefix}{tile_suffix}{ext}"
            if he_path.is_file():
                h, w = read_image_dimensions(he_path)
                if h is not None:
                    tile_dims[slice_idx] = (h, w)

        # Iterate over segments (classes)
        segmentation = seg_node.GetSegmentation()
        seg_ids = vtk.vtkStringArray()
        segmentation.GetSegmentIDs(seg_ids)

        for seg_i in range(seg_ids.GetNumberOfValues()):
            segment_id = seg_ids.GetValue(seg_i)
            segment = segmentation.GetSegment(segment_id)
            if not segment:
                continue
            class_name = segment.GetName()

            # Export this single segment as a labelmap aligned to the volume
            ids_to_export = vtk.vtkStringArray()
            ids_to_export.InsertNextValue(segment_id)

            label_node = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLLabelMapVolumeNode", f"tmp_{class_name}"
            )
            slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(
                seg_node, ids_to_export, label_node, vol_node
            )
            mask_3d = slicer.util.arrayFromVolume(label_node).copy()  # (Z, H, W)
            slicer.mrmlScene.RemoveNode(label_node)

            class_dir = root_path / case_name / class_name
            class_dir.mkdir(parents=True, exist_ok=True)

            for slice_idx, tile_stem in enumerate(tile_names):
                if slice_idx >= mask_3d.shape[0]:
                    break

                tile_suffix = tile_stem[len(image_prefix) :]
                output_name = f"{case_name}_{class_name}_{tile_suffix}{tag}{ext}"
                output_path = class_dir / output_name

                slice_mask = mask_3d[slice_idx]

                # Crop to original tile size if available (remove stacking padding)
                if slice_idx in tile_dims:
                    orig_h, orig_w = tile_dims[slice_idx]
                    slice_mask = slice_mask[:orig_h, :orig_w]

                # Convert to 0 / 255 binary mask
                binary = ((slice_mask > 0).astype(np.uint8)) * 255

                save_binary_png(binary, output_path)
                total_exported += 1

            print(
                f"[OK] Case {case_name}, class '{class_name}': "
                f"exported {len(tile_names)} mask(s) with tag '{tag}'"
            )

    print(f"\nDone.  Exported {total_exported} mask file(s) total.")
    print("Originals are untouched — exported files have the " f"'{tag}' tag in their filename.")


if __name__ == "__main__":
    main(sys.argv[1:])
