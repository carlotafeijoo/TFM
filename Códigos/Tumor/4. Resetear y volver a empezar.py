import slicer
# Importa el módulo principal de 3D Slicer para acceder a la escena y nodos

# Lista de nodos que queremos eliminar
for name in ["TumorSeeds", "BackgroundSeeds", "Tumor_GrowFromSeeds", "SeedLabelMap"]:
    
    try:
        # Intenta buscar el nodo por nombre en la escena
        node = slicer.util.getNode(name)
        
        # Si existe, lo elimina de la escena
        slicer.mrmlScene.RemoveNode(node)
        
        # Imprime en consola que lo ha borrado
        print("Borrado:", name)
    
    except Exception:
        # Si el nodo no existe (por ejemplo ya estaba borrado),
        # no hace nada y continúa sin error
        pass


# Obtener el nodo de interacción (controla cómo interactúas con la imagen)
interactionNode = slicer.app.applicationLogic().GetInteractionNode()

# Cambiar el modo a "ViewTransform"
# Esto desactiva el modo de colocar puntos (Place mode)
# y vuelve al modo normal de navegación (mover, zoom, etc.)
interactionNode.SetCurrentInteractionMode(interactionNode.ViewTransform)

# Mensaje final en consola
print("Limpieza completa hecha.")