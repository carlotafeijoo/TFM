# Borrar TODOS los markups de puntos
markups = slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")
for n in list(markups):
    print("Borrando markup:", n.GetName())
    slicer.mrmlScene.RemoveNode(n)

# Borrar también posibles segmentaciones/máscaras creadas antes
for className in ["vtkMRMLSegmentationNode", "vtkMRMLLabelMapVolumeNode"]:
    nodes = slicer.util.getNodesByClass(className)
    for n in list(nodes):
        name = n.GetName()
        if "Tumor" in name or "Mask" in name or "Seg" in name:
            print("Borrando:", name)
            slicer.mrmlScene.RemoveNode(n)

# Desactivar modo Place
interactionNode = slicer.app.applicationLogic().GetInteractionNode()
interactionNode.SetCurrentInteractionMode(interactionNode.ViewTransform)

print("Limpieza completa hecha.")