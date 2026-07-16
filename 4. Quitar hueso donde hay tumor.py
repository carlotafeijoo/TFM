import slicer

# =============================================================================
# Priorización del tumor sobre el hueso en 3D Slicer
# =============================================================================
#
# Objetivo:
#   Aplicar una operación lógica entre dos segmentos:
#
#       Bone = Bone - Tumor
#
#   Esto significa que, en las zonas donde coinciden el segmento óseo "Bone"
#   y el segmento tumoral "Tumor", se elimina la parte correspondiente del hueso
#   y se conserva el tumor.
#
# Utilidad:
#   Este paso permite evitar solapamientos entre la reconstrucción ósea y la
#   reconstrucción tumoral antes de generar modelos 3D o exportar archivos STL.
#
# IMPORTANTE:
#   - El segmento "Bone" sí se modifica.
#   - El segmento "Tumor" NO se modifica.
#   - El script no suaviza ni interpola; solo realiza una resta lógica.
#   - Bone y Tumor deben estar dentro del mismo nodo de segmentación.
# =============================================================================


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Si se quiere aplicar la operación solo a una segmentación concreta,
# se debe escribir aquí su nombre.
#
# Ejemplo:
# ONLY_SEGMENTATION_NAME = "Tumor_GrowFromSeeds"
#
# Si se deja en None, el script recorre todas las segmentaciones de la escena
# y aplica la operación únicamente en aquellas que contengan los segmentos
# llamados "Bone" y "Tumor".
ONLY_SEGMENTATION_NAME = None

# Nombre del segmento óseo que se va a modificar.
# Este segmento será recortado en las zonas donde coincida con el tumor.
BONE_SEGMENT_NAME = "Bone"

# Nombre del segmento tumoral que se usará como máscara de resta.
# Este segmento tiene prioridad y NO se modifica.
TUMOR_SEGMENT_NAME = "Tumor"


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def get_segment_id_by_name(seg_node, target_name):
    """
    Busca el identificador interno de un segmento a partir de su nombre visible.

    En 3D Slicer, cada segmento tiene:
        - un nombre visible para el usuario, por ejemplo "Bone" o "Tumor"
        - un ID interno usado por la API de Slicer

    Esta función recorre todos los segmentos de un nodo de segmentación y
    devuelve el ID interno del segmento cuyo nombre coincide con target_name.

    Parámetros:
        seg_node: nodo de segmentación de Slicer.
        target_name: nombre visible del segmento que se quiere buscar.

    Devuelve:
        ID interno del segmento si existe.
        None si no se encuentra.
    """

    seg = seg_node.GetSegmentation()

    for i in range(seg.GetNumberOfSegments()):
        seg_id = seg.GetNthSegmentID(i)
        name = seg.GetSegment(seg_id).GetName()

        if name.lower() == target_name.lower():
            return seg_id

    return None


def get_source_volume():
    """
    Obtiene el volumen de referencia cargado en la escena.

    El Segment Editor necesita un volumen de referencia para aplicar efectos
    correctamente. En este caso se utiliza el primer volumen escalar encontrado
    en la escena.

    Devuelve:
        El primer vtkMRMLScalarVolumeNode encontrado.

    Lanza error:
        Si no hay ningún volumen cargado en Slicer.
    """

    volume_nodes = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")

    if not volume_nodes:
        raise RuntimeError("No hay ningún volumen cargado.")

    return volume_nodes[0]


def subtract_tumor_from_bone(seg_node, volume_node):
    """
    Aplica la operación lógica:

        Bone = Bone - Tumor

    Es decir:
        - Bone es el segmento activo y será modificado.
        - Tumor se usa como segmento modificador o máscara de resta.
        - En las zonas donde Bone y Tumor se solapan, se elimina Bone.
        - Tumor permanece intacto.

    Parámetros:
        seg_node: nodo de segmentación que contiene Bone y Tumor.
        volume_node: volumen de referencia asociado a la segmentación.

    Devuelve:
        True si la operación se ha aplicado correctamente.
        False si la segmentación no contenía Bone o Tumor.
    """

    # Buscar el ID interno del segmento Bone
    bone_id = get_segment_id_by_name(seg_node, BONE_SEGMENT_NAME)

    # Buscar el ID interno del segmento Tumor
    tumor_id = get_segment_id_by_name(seg_node, TUMOR_SEGMENT_NAME)

    # Si no existe Bone, esta segmentación se omite
    if bone_id is None:
        print(f"Saltado '{seg_node.GetName()}': no tiene segmento Bone.")
        return False

    # Si no existe Tumor, esta segmentación se omite
    if tumor_id is None:
        print(f"Saltado '{seg_node.GetName()}': no tiene segmento Tumor.")
        return False

    print(f"Procesando: {seg_node.GetName()}")
    print("Operación: Bone = Bone - Tumor")

    # -------------------------------------------------------------------------
    # Crear un Segment Editor temporal
    # -------------------------------------------------------------------------
    # Esto permite aplicar efectos de Segment Editor mediante código,
    # como si se hiciera manualmente desde la interfaz de Slicer.
    editor_widget = slicer.qMRMLSegmentEditorWidget()
    editor_widget.setMRMLScene(slicer.mrmlScene)

    editor_node = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLSegmentEditorNode"
    )

    editor_widget.setMRMLSegmentEditorNode(editor_node)

    # Asociar la segmentación y el volumen de referencia al editor
    editor_widget.setSegmentationNode(seg_node)
    editor_widget.setSourceVolumeNode(volume_node)

    # -------------------------------------------------------------------------
    # Seleccionar el segmento que se va a modificar
    # -------------------------------------------------------------------------
    # MUY IMPORTANTE:
    # El segmento activo es Bone, porque Bone es el que queremos recortar.
    # Tumor se usará solo como máscara de resta y no se modificará.
    editor_widget.setCurrentSegmentID(bone_id)

    # Evitar que la operación sobrescriba otros segmentos de la segmentación.
    editor_node.SetOverwriteMode(
        slicer.vtkMRMLSegmentEditorNode.OverwriteNone
    )

    # -------------------------------------------------------------------------
    # Activar el efecto Logical operators
    # -------------------------------------------------------------------------
    # Este efecto permite realizar operaciones lógicas entre segmentos:
    # unión, intersección, resta, etc.
    editor_widget.setActiveEffectByName("Logical operators")
    effect = editor_widget.activeEffect()

    if effect is None:
        slicer.mrmlScene.RemoveNode(editor_node)
        raise RuntimeError("No se pudo activar 'Logical operators'.")

    # -------------------------------------------------------------------------
    # Configurar la operación de resta
    # -------------------------------------------------------------------------
    # Operation = SUBTRACT:
    #   resta el segmento indicado en ModifierSegmentID al segmento activo.
    #
    # Segmento activo:
    #   Bone
    #
    # Segmento modificador:
    #   Tumor
    #
    # Resultado:
    #   Bone = Bone - Tumor
    effect.setParameter("Operation", "SUBTRACT")
    effect.setParameter("ModifierSegmentID", tumor_id)

    # Aplicar la operación
    effect.self().onApply()

    # Eliminar el nodo temporal del Segment Editor para limpiar la escena
    slicer.mrmlScene.RemoveNode(editor_node)

    print("Hecho: donde había Tumor + Bone, se ha eliminado Bone.")
    print("Tumor no se ha modificado.")

    return True


# =============================================================================
# EJECUCIÓN DEL SCRIPT
# =============================================================================

# Obtener el volumen de referencia cargado en la escena
volume_node = get_source_volume()

# Contador de segmentaciones procesadas correctamente
processed = 0

# -------------------------------------------------------------------------
# Caso 1: aplicar solo a una segmentación concreta
# -------------------------------------------------------------------------
if ONLY_SEGMENTATION_NAME:
    seg_node = slicer.util.getNode(ONLY_SEGMENTATION_NAME)

    if subtract_tumor_from_bone(seg_node, volume_node):
        processed += 1

# -------------------------------------------------------------------------
# Caso 2: aplicar a todas las segmentaciones de la escena
# -------------------------------------------------------------------------
else:
    seg_nodes = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")

    for seg_node in seg_nodes:
        if subtract_tumor_from_bone(seg_node, volume_node):
            processed += 1


# =============================================================================
# MENSAJE FINAL
# =============================================================================

print("========================================")
print(f"Proceso terminado. Segmentaciones procesadas: {processed}")
print("Resultado final: Tumor tiene prioridad sobre Bone.")
print("Operación aplicada: Bone = Bone - Tumor")
print("========================================")