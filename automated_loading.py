import os

try:
    import slicer
except ImportError as error:
    raise RuntimeError(
        "3D Slicer Python API is not available in this interpreter.\n"
        "Run this script with the 3D Slicer executable, for example:\n"
        '"C:\\path\\to\\Slicer.exe" --python-script "automated_loading.py"'
    ) from error

imagePath = r"C:\Users\theod\Documents\uio\masteroppgave\data\Stroma\ExampleTiles\R44-003\HE\R44-003_HE_0002_X=45482_Y=17340.png"
maskPath = r"C:\Users\theod\Documents\uio\masteroppgave\data\Stroma\ExampleTiles\R44-003\stroma\R44-003_stroma_0002_X=45482_Y=17340.png"

if not hasattr(slicer, "util"):
    raise RuntimeError(
        "This script requires the 3D Slicer Python runtime. "
        "Do not run it with a regular Python interpreter.\n"
        "Run it like:\n"
        '"C:\\path\\to\\Slicer.exe" --python-script "automated_loading.py"'
    )

if not os.path.isfile(imagePath):
    raise FileNotFoundError(f"Image file not found: {imagePath}")

if not os.path.isfile(maskPath):
    raise FileNotFoundError(f"Mask file not found: {maskPath}")

# Load RGB image
imageNode = slicer.util.loadVolume(imagePath)

# Load mask as labelmap
maskNode = slicer.util.loadLabelVolume(maskPath)

# Create segmentation
segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
segmentationNode.CreateDefaultDisplayNodes()

# Import labelmap into segmentation
slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
    maskNode, segmentationNode
)

# Set reference geometry from image
segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(imageNode)

# Show segmentation in slice views with visible 2D overlay
segmentationNode.SetDisplayVisibility(True)
displayNode = segmentationNode.GetDisplayNode()
displayNode.SetVisibility2D(True)
displayNode.SetAllSegmentsVisibility2D(True)
displayNode.SetOpacity2DFill(0.4)
displayNode.SetOpacity2DOutline(1.0)

# Ensure slice viewers show the RGB image in the background and refresh view
slicer.util.setSliceViewerLayers(background=imageNode)
slicer.util.resetSliceViews()

# Clean up the temporary labelmap if you want
# slicer.mrmlScene.RemoveNode(maskNode)

print("Ready for editing")