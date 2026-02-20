import argparse
import colorsys
import hashlib
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

try:
    import slicer
    import vtk
except ImportError as error:
    raise RuntimeError(
        "3D Slicer Python API is not available in this interpreter.\n"
        "Run this script with the 3D Slicer executable, for example:\n"
        '"C:\\path\\to\\Slicer.exe" --python-script "automated_loading_batch.py" -- --root "C:\\path\\to\\ExampleTiles"'
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
            "Load a full tile dataset tree into 3D Slicer as editable segmentations. "
            "Each case is stacked into a single volume where every slice is one tile. "
            "Scroll through slices to navigate tiles; segmentations are linked per-slice."
        ),
    )
    parser.add_argument(
        "--root",
        required=True,
        help="Root folder containing case folders (e.g. ExampleTiles).",
    )
    parser.add_argument(
        "--he-folder",
        default="HE",
        help="Name of image folder inside each case (default: HE).",
    )
    parser.add_argument(
        "--ext",
        default=".png",
        help="Image/mask extension to use (default: .png).",
    )
    parser.add_argument(
        "--output-scene",
        default=None,
        help="Optional output .mrb/.mrml scene path. Defaults to ../_annotations/<root>-<timestamp>.mrb",
    )
    parser.add_argument(
        "--max-tiles-per-case",
        type=int,
        default=None,
        help="Optional limit for number of tiles loaded per case.",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not save scene automatically after loading.",
    )
    parser.add_argument(
        "--show-segments-by-default",
        action="store_true",
        help="Show segment overlays immediately after loading (default is hidden to keep HE clearly visible).",
    )
    parser.add_argument(
        "--keep-vtk-warnings",
        action="store_true",
        help="Keep VTK warning output enabled.",
    )
    args, _ = parser.parse_known_args(argv)
    return args


# ---------------------------------------------------------------------------
#  Subject-hierarchy helpers
# ---------------------------------------------------------------------------


def get_segment_ids(segmentation):
    ids = vtk.vtkStringArray()
    segmentation.GetSegmentIDs(ids)
    return {ids.GetValue(i) for i in range(ids.GetNumberOfValues())}


def ensure_folder_item(sh_node, parent_item_id, folder_name):
    if sh_node is None or parent_item_id is None:
        return None

    if hasattr(sh_node, "GetItemChildren"):
        child_ids = vtk.vtkIdList()
        sh_node.GetItemChildren(parent_item_id, child_ids, False)
        for i in range(child_ids.GetNumberOfIds()):
            child_id = child_ids.GetId(i)
            if sh_node.GetItemName(child_id) == folder_name:
                return child_id
    elif hasattr(sh_node, "GetNumberOfItemChildren") and hasattr(
        sh_node, "GetItemChild"
    ):
        child_count = sh_node.GetNumberOfItemChildren(parent_item_id)
        for i in range(child_count):
            child_id = sh_node.GetItemChild(parent_item_id, i)
            if sh_node.GetItemName(child_id) == folder_name:
                return child_id

    return sh_node.CreateFolderItem(parent_item_id, folder_name)


# ---------------------------------------------------------------------------
#  Mask / colour helpers
# ---------------------------------------------------------------------------


def build_mask_index(case_dir, case_name, class_name, ext):
    class_dir = case_dir / class_name
    prefix = f"{case_name}_{class_name}_"
    mask_index = {}
    for file_path in sorted(class_dir.glob(f"*{ext}")):
        name = file_path.name
        if not name.startswith(prefix):
            continue
        suffix = name[len(prefix) :]
        mask_index[suffix] = str(file_path)
    return mask_index


def class_color_rgb(class_name):
    normalized = (class_name or "").strip().lower()
    predefined = {
        "background": (0.45, 0.45, 0.45),
        "stroma": (0.95, 0.75, 0.20),
        "tumor": (0.85, 0.20, 0.20),
        "tumorannotation": (0.60, 0.25, 0.85),
    }
    if normalized in predefined:
        return predefined[normalized]

    digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()
    hue = int(digest[:8], 16) / 0xFFFFFFFF
    saturation = 0.90
    value = 0.90
    return colorsys.hsv_to_rgb(hue, saturation, value)


def binarize_mask_array(mask_array):
    """Convert a raw mask array (possibly multi-channel) to a binary 2-D uint8 array."""
    collapsed = mask_array
    if mask_array.ndim == 3:
        if mask_array.shape[-1] == 4:
            alpha = mask_array[..., 3]
            if np.any(alpha == 0) and np.any(alpha > 0):
                collapsed = alpha
            else:
                collapsed = np.max(mask_array[..., :3], axis=-1)
        else:
            collapsed = np.max(mask_array, axis=-1)

    # Always treat 255 as class, 0 as background
    # If mask is not 0/255, threshold at 128
    if collapsed.dtype != np.uint8:
        collapsed = collapsed.astype(np.uint8)
    return (collapsed == 255).astype(np.uint8)


# ---------------------------------------------------------------------------
#  Array I/O  -- load individual tiles via Slicer, return numpy arrays
# ---------------------------------------------------------------------------


def load_tile_image_array(file_path):
    """Load an image tile via Slicer I/O, extract the numpy array, remove the temp node."""
    node = slicer.util.loadVolume(str(file_path))
    if not node:
        return None
    arr = slicer.util.arrayFromVolume(node).copy()
    slicer.mrmlScene.RemoveNode(node)
    # Slicer wraps 2-D images in a singleton Z dimension -- squeeze it out
    if arr.ndim >= 3 and arr.shape[0] == 1:
        arr = arr[0]
    return arr


def load_mask_as_binary(file_path):
    """Load a mask file via Slicer, binarize, return as 2-D uint8 array."""
    node = slicer.util.loadLabelVolume(str(file_path))
    if not node:
        return None
    arr = slicer.util.arrayFromVolume(node).copy()
    slicer.mrmlScene.RemoveNode(node)
    if arr.ndim >= 3 and arr.shape[0] == 1:
        arr = arr[0]
    return binarize_mask_array(arr)


# ---------------------------------------------------------------------------
#  Stacking helpers
# ---------------------------------------------------------------------------


def pad_array_to_shape(arr, target_h, target_w):
    """Pad a 2-D or 3-D (H, W, C) array to *target_h x target_w* with zeros."""
    h, w = arr.shape[0], arr.shape[1]
    pad_h, pad_w = max(0, target_h - h), max(0, target_w - w)
    if pad_h == 0 and pad_w == 0:
        return arr
    if arr.ndim == 3:
        pad_width = [(0, pad_h), (0, pad_w), (0, 0)]
    else:
        pad_width = [(0, pad_h), (0, pad_w)]
    return np.pad(arr, pad_width, mode="constant", constant_values=0)


def stack_tile_arrays(arrays):
    """Stack a list of 2-D / 3-D arrays along a new first axis, padding to common size."""
    if not arrays:
        return None
    max_h = max(a.shape[0] for a in arrays)
    max_w = max(a.shape[1] for a in arrays)
    padded = [pad_array_to_shape(a, max_h, max_w) for a in arrays]
    return np.stack(padded, axis=0)


# ---------------------------------------------------------------------------
#  Display helpers
# ---------------------------------------------------------------------------


def build_default_output_path(root_path):
    annotations_dir = root_path.parent / "_annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return annotations_dir / f"{root_path.name}-{stamp}.mrb"


def configure_segmentation_display_2d(display_node):
    if not display_node:
        return
    display_node.SetVisibility2D(True)
    if hasattr(display_node, "SetAllSegmentsVisibility2D"):
        display_node.SetAllSegmentsVisibility2D(True)
    else:
        display_node.SetAllSegmentsVisibility(True)
    display_node.SetOpacity2DFill(0.65)
    display_node.SetOpacity2DOutline(1.0)


def set_segments_visibility(segmentation_node, visible, hide_names=None):
    if not segmentation_node:
        return

    display_node = segmentation_node.GetDisplayNode()
    segmentation = segmentation_node.GetSegmentation()
    if not display_node or not segmentation:
        return

    ids = vtk.vtkStringArray()
    segmentation.GetSegmentIDs(ids)
    names_lower = {name.lower() for name in (hide_names or set())}
    for i in range(ids.GetNumberOfValues()):
        segment_id = ids.GetValue(i)
        segment = segmentation.GetSegment(segment_id)
        if not segment:
            continue
        should_hide = segment.GetName().lower() in names_lower
        if should_hide:
            display_node.SetSegmentVisibility(segment_id, False)
        else:
            display_node.SetSegmentVisibility(segment_id, visible)


def show_volume_in_slice_views(volume_node):
    """Set *volume_node* as the only background in every slice viewer."""
    if volume_node is None:
        return

    slicer.util.setSliceViewerLayers(
        background=volume_node,
        foreground=None,
        label=None,
        foregroundOpacity=0.0,
        labelOpacity=0.0,
    )

    for comp_node in slicer.util.getNodesByClass("vtkMRMLSliceCompositeNode"):
        comp_node.SetForegroundVolumeID(None)
        comp_node.SetLabelVolumeID(None)
        comp_node.SetForegroundOpacity(0.0)
        comp_node.SetLabelOpacity(0.0)


# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------


def main(argv):
    args = parse_args(argv)

    if not args.keep_vtk_warnings and hasattr(vtk.vtkObject, "GlobalWarningDisplayOff"):
        vtk.vtkObject.GlobalWarningDisplayOff()

    root_path = Path(args.root)

    if not root_path.is_dir():
        raise FileNotFoundError(f"Root folder not found: {root_path}")

    ext = args.ext if args.ext.startswith(".") else f".{args.ext}"
    case_dirs = [
        entry
        for entry in sorted(root_path.iterdir())
        if entry.is_dir() and (entry / args.he_folder).is_dir()
    ]

    if not case_dirs:
        raise RuntimeError(
            f"No case folders found under {root_path}. "
            f"Expected subfolders containing '{args.he_folder}'."
        )

    sh_node = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(
        slicer.mrmlScene
    )
    scene_root_item = sh_node.GetSceneItemID() if sh_node else None
    project_folder = (
        ensure_folder_item(sh_node, scene_root_item, root_path.name)
        if sh_node and scene_root_item is not None
        else None
    )

    first_volume_node = None
    loaded_case_count = 0
    loaded_tile_count = 0

    for case_dir in case_dirs:
        case_name = case_dir.name
        he_dir = case_dir / args.he_folder

        class_dirs = [
            d.name
            for d in sorted(case_dir.iterdir())
            if d.is_dir()
            and d.name != args.he_folder
            and not d.name.startswith("_")
        ]

        image_prefix = f"{case_name}_{args.he_folder}_"
        he_files = [
            path
            for path in sorted(he_dir.glob(f"*{ext}"))
            if path.name.startswith(image_prefix)
        ]

        if not he_files:
            print(f"[WARN] No image tiles found for case '{case_name}' in {he_dir}")
            continue

        if args.max_tiles_per_case is not None:
            he_files = he_files[: args.max_tiles_per_case]

        case_item = (
            ensure_folder_item(sh_node, project_folder, case_name)
            if sh_node and project_folder is not None
            else None
        )

        class_mask_index = {
            class_name: build_mask_index(case_dir, case_name, class_name, ext)
            for class_name in class_dirs
        }

        # -- Phase 1: load every tile + its masks as numpy arrays ----------
        tile_image_arrays = []
        tile_mask_arrays = {cn: [] for cn in class_dirs}
        tile_names = []

        for image_file in he_files:
            suffix = image_file.name[len(image_prefix) :]

            img_arr = load_tile_image_array(image_file)
            if img_arr is None:
                print(f"[WARN] Failed to load image tile: {image_file}")
                continue

            tile_image_arrays.append(img_arr)
            tile_names.append(image_file.stem)

            for class_name in class_dirs:
                mask_path = class_mask_index[class_name].get(suffix)
                if mask_path:
                    mask_arr = load_mask_as_binary(mask_path)
                    if mask_arr is not None:
                        tile_mask_arrays[class_name].append(mask_arr)
                    else:
                        tile_mask_arrays[class_name].append(
                            np.zeros(img_arr.shape[:2], dtype=np.uint8)
                        )
                else:
                    tile_mask_arrays[class_name].append(
                        np.zeros(img_arr.shape[:2], dtype=np.uint8)
                    )

        if not tile_image_arrays:
            continue

        # -- Phase 2: stack tiles into a 3-D (+ channel) volume ------------
        stacked_image = stack_tile_arrays(tile_image_arrays)  # (Z,H,W) or (Z,H,W,C)
        is_vector = stacked_image.ndim == 4
        node_class = (
            "vtkMRMLVectorVolumeNode" if is_vector else "vtkMRMLScalarVolumeNode"
        )
        volume_node = slicer.util.addVolumeFromArray(
            stacked_image, name=f"{case_name}_HE", nodeClassName=node_class
        )
        volume_node.CreateDefaultDisplayNodes()

        # Store a human-readable slice-to-tile mapping in the node description
        mapping = "\n".join(
            f"Slice {i}: {name}" for i, name in enumerate(tile_names)
        )
        volume_node.SetDescription(mapping)

        if first_volume_node is None:
            first_volume_node = volume_node

        # -- Phase 3: one segmentation for the whole case ------------------
        segmentation_node = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode"
        )
        segmentation_node.SetName(f"{case_name}_Segmentation")
        segmentation_node.CreateDefaultDisplayNodes()
        segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(
            volume_node
        )

        ijk_to_ras = vtk.vtkMatrix4x4()
        volume_node.GetIJKToRASMatrix(ijk_to_ras)

        imported_classes = 0
        for class_name in class_dirs:
            stacked_mask = stack_tile_arrays(tile_mask_arrays[class_name])
            if stacked_mask is None or not np.any(stacked_mask):
                continue

            # Create a temporary labelmap with the same geometry as the HE volume
            label_node = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLLabelMapVolumeNode", f"temp_{class_name}"
            )
            slicer.util.updateVolumeFromArray(label_node, stacked_mask)
            label_node.SetIJKToRASMatrix(ijk_to_ras)

            segmentation = segmentation_node.GetSegmentation()
            before_ids = get_segment_ids(segmentation)
            slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
                label_node, segmentation_node
            )
            after_ids = get_segment_ids(segmentation)
            new_ids = sorted(after_ids - before_ids)

            if new_ids:
                for segment_id in new_ids:
                    segment = segmentation.GetSegment(segment_id)
                    if segment:
                        segment.SetName(class_name)
                        segment.SetColor(*class_color_rgb(class_name))
                imported_classes += 1

            slicer.mrmlScene.RemoveNode(label_node)

        display_node = segmentation_node.GetDisplayNode()
        configure_segmentation_display_2d(display_node)
        set_segments_visibility(
            segmentation_node,
            visible=args.show_segments_by_default,
            hide_names={"background"},
        )

        # -- Phase 4: organise in subject hierarchy ------------------------
        if sh_node and case_item is not None:
            vol_item = sh_node.GetItemByDataNode(volume_node)
            seg_item = sh_node.GetItemByDataNode(segmentation_node)
            if vol_item:
                sh_node.SetItemParent(vol_item, case_item)
            if seg_item:
                sh_node.SetItemParent(seg_item, case_item)

        loaded_tile_count += len(tile_names)
        loaded_case_count += 1
        print(
            f"[OK] Case {case_name}: stacked {len(tile_names)} tile(s) as slices, "
            f"classes: {', '.join(class_dirs) if class_dirs else 'none'}"
        )

    # -- Set up initial view -----------------------------------------------
    if first_volume_node is not None:
        show_volume_in_slice_views(first_volume_node)
        slicer.util.resetSliceViews()

    summary = (
        f"Loaded {loaded_tile_count} tile(s) across {loaded_case_count} case(s)."
    )
    nav_hint = (
        "Navigate tiles by scrolling through slices (mouse-wheel / slice slider). "
        "Each slice is one tile; segmentation overlays are linked per-slice."
    )

    if args.no_save:
        print(f"{summary} Scene not saved (--no-save).")
        print(nav_hint)
        return

    output_scene = (
        Path(args.output_scene)
        if args.output_scene
        else build_default_output_path(root_path)
    )
    output_scene.parent.mkdir(parents=True, exist_ok=True)
    saved = slicer.util.saveScene(str(output_scene))

    if not saved:
        raise RuntimeError(f"Failed to save scene to: {output_scene}")

    print(summary)
    print(f"Scene saved to: {output_scene}")
    print(nav_hint)


if __name__ == "__main__":
    main(sys.argv[1:])
