import os

try:
    import slicer
except ImportError as error:
    raise RuntimeError(
        "3D Slicer Python API is not available in this interpreter.\n"
        "Run this script with the 3D Slicer executable, for example:\n"
        '"C:\\path\\to\\Slicer.exe" --python-script "automated_loading.py"'
    ) from error

imagePath = r"C:\Users\theod\Documents\uio\_masteroppgave\data\Stroma\ExampleTiles\R44-003\HE\R44-003_HE_0002_X=45482_Y=17340.png"
maskPath_stroma = r"C:\Users\theod\Documents\uio\_masteroppgave\data\Stroma\ExampleTiles\R44-003\stroma\R44-003_stroma_0002_X=45482_Y=17340.png"
maskPath_background = r"C:\Users\theod\Documents\uio\_masteroppgave\data\Stroma\ExampleTiles\R44-003\background\R44-003_background_0002_X=45482_Y=17340.png"

if not hasattr(slicer, "util"):
    raise RuntimeError(
        "This script requires the 3D Slicer Python runtime. "
        "Do not run it with a regular Python interpreter.\n"
        "Run it like:\n"
        '"C:\\path\\to\\Slicer.exe" --python-script "automated_loading.py"'
    )

if not os.path.isfile(imagePath):
    raise FileNotFoundError(f"Image file not found: {imagePath}")

if not os.path.isfile(maskPath_stroma):
    raise FileNotFoundError(f"Stroma mask file not found: {maskPath_stroma}")

if not os.path.isfile(maskPath_background):
    raise FileNotFoundError(f"Background mask file not found: {maskPath_background}")

# Load RGB image
imageNode = slicer.util.loadVolume(imagePath)

# Load mask as labelmap
maskNode_stroma = slicer.util.loadLabelVolume(maskPath_stroma)
maskNode_background = slicer.util.loadLabelVolume(maskPath_background)

# Create segmentation
segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
segmentationNode.CreateDefaultDisplayNodes()

# Import labelmap into segmentation
slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
    maskNode_stroma, segmentationNode
)
slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
    maskNode_background, segmentationNode
)

# Set reference geometry from image
segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(imageNode)

# Show segmentation in slice views with visible 2D overlay
segmentationNode.SetDisplayVisibility(True)
displayNode = segmentationNode.GetDisplayNode()
displayNode.SetVisibility2D(True)
if hasattr(displayNode, "SetAllSegmentsVisibility2D"):
    displayNode.SetAllSegmentsVisibility2D(True)
else:
    displayNode.SetAllSegmentsVisibility(True)
displayNode.SetOpacity2DFill(0.4)
displayNode.SetOpacity2DOutline(1.0)

# Ensure slice viewers show the RGB image in the background and refresh view
slicer.util.setSliceViewerLayers(background=imageNode)
slicer.util.resetSliceViews()

# Clean up the temporary labelmap if you want
# slicer.mrmlScene.RemoveNode(maskNode_stroma)
# slicer.mrmlScene.RemoveNode(maskNode_background)

print("Ready for editing")