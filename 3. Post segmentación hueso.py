import slicer

# =============================================================================
# Postprocesado del segmento óseo en 3D Slicer
# =============================================================================
#
# Objetivo:
#   Aplicar un postprocesado automático sobre el segmento óseo "Bone" para:
#       1. Reducir el efecto de rayas o "código de barras" entre cortes.
#       2. Eliminar fragmentos pequeños desconectados.
#       3. Cerrar pequeños huecos en la segmentación.
#       4. Suavizar la superficie final del modelo.
#
# Este script está pensado para ejecutarse dentro de la consola Python de
# 3D Slicer o desde el módulo Scripting.
#
# IMPORTANTE:
#   - Modifica directamente el segmento "Bone".
#   - No crea una copia automática.
#   - Conviene guardar la escena antes de ejecutarlo.
#   - No procesa el segmento "Tumor".
# =============================================================================


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Nombre del nodo de segmentación donde se encuentra el segmento óseo.
# Debe coincidir exactamente con el nombre visible en el panel Data/Segment Editor.
SEGMENTATION_NAME = "Tumor_GrowFromSeeds"

# Nombre del segmento óseo que se quiere postprocesar.
BONE_SEGMENT_NAME = "Bone"

# Activa el efecto "Fill between slices".
# Este paso interpola entre cortes y ayuda a reducir el efecto de rayas
# o "código de barras" que puede aparecer cuando la segmentación queda
# desalineada entre frames/slices.
USE_FILL_BETWEEN_SLICES = True

# Parámetros de suavizado para hueso.
# Se utilizan valores suaves para evitar deformar demasiado la geometría ósea.
CLOSING_KERNEL_MM_1 = 2.0   # Primer cierre morfológico: cierra pequeños huecos.
CLOSING_KERNEL_MM_2 = 1.0   # Segundo cierre más suave: refina la superficie.
MEDIAN_KERNEL_MM = 1.0      # Suavizado final mediante filtro de mediana.


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def get_segment_id_by_name(seg_node, target_name):
    """
    Busca el identificador interno de un segmento a partir de su nombre visible.

    En 3D Slicer, cada segmento tiene:
        - un nombre visible para el usuario, por ejemplo "Bone"
        - un ID interno usado por la API de Slicer

    Esta función recorre todos los segmentos de una segmentación y devuelve
    el ID interno del segmento cuyo nombre coincide con target_name.

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
        segment_name = seg.GetSegment(seg_id).GetName()

        if segment_name.lower() == target_name.lower():
            return seg_id

    return None


def create_editor(seg_node, volume_node):
    """
    Crea un Segment Editor temporal para aplicar efectos mediante código.

    Es equivalente a utilizar manualmente el módulo Segment Editor de Slicer,
    pero automatizado desde Python.

    Parámetros:
        seg_node: nodo de segmentación sobre el que se aplicarán los efectos.
        volume_node: volumen de referencia asociado a la segmentación.

    Devuelve:
        editor_widget: widget temporal del Segment Editor.
        editor_node: nodo temporal de configuración del Segment Editor.
    """

    # Crear widget temporal del Segment Editor
    editor_widget = slicer.qMRMLSegmentEditorWidget()
    editor_widget.setMRMLScene(slicer.mrmlScene)

    # Crear nodo temporal para guardar la configuración del Segment Editor
    editor_node = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLSegmentEditorNode"
    )
    editor_widget.setMRMLSegmentEditorNode(editor_node)

    # Asociar la segmentación y el volumen de referencia al editor
    editor_widget.setSegmentationNode(seg_node)
    editor_widget.setSourceVolumeNode(volume_node)

    # Evita que las operaciones sobrescriban otros segmentos.
    # El objetivo es modificar únicamente el segmento seleccionado.
    editor_node.SetOverwriteMode(
        slicer.vtkMRMLSegmentEditorNode.OverwriteNone
    )

    return editor_widget, editor_node


def apply_fill_between_slices(editor_widget, segment_id):
    """
    Aplica el efecto "Fill between slices".

    Este efecto interpola/rellena la segmentación entre cortes. Es especialmente
    útil cuando el modelo 3D presenta un aspecto en bandas o "código de barras",
    debido a diferencias entre slices consecutivos.

    Parámetros:
        editor_widget: Segment Editor temporal.
        segment_id: ID interno del segmento que se quiere procesar.
    """

    # Seleccionar el segmento que se va a modificar
    editor_widget.setCurrentSegmentID(segment_id)

    # Activar el efecto Fill between slices
    editor_widget.setActiveEffectByName("Fill between slices")
    effect = editor_widget.activeEffect()

    if effect is None:
        raise RuntimeError("No se pudo activar Fill between slices.")

    # Generar una previsualización de la interpolación
    effect.self().onPreview()

    # Aplicar definitivamente el resultado
    effect.self().onApply()


def apply_islands_keep_largest(editor_widget, segment_id):
    """
    Aplica el efecto Islands con la operación Keep largest island.

    Este paso elimina pequeñas regiones desconectadas y conserva únicamente
    la isla principal del segmento óseo.

    Parámetros:
        editor_widget: Segment Editor temporal.
        segment_id: ID interno del segmento que se quiere procesar.
    """

    editor_widget.setCurrentSegmentID(segment_id)
    editor_widget.setActiveEffectByName("Islands")
    effect = editor_widget.activeEffect()

    if effect is None:
        raise RuntimeError("No se pudo activar Islands.")

    # Mantener únicamente la isla de mayor tamaño
    effect.setParameter("Operation", "KEEP_LARGEST_ISLAND")
    effect.self().onApply()


def apply_smoothing(editor_widget, segment_id, method, kernel_mm):
    """
    Aplica un suavizado al segmento seleccionado.

    Métodos utilizados en este script:
        - MORPHOLOGICAL_CLOSING:
            Cierra pequeños huecos y discontinuidades.
        - MEDIAN:
            Suaviza bordes reduciendo irregularidades locales.

    Parámetros:
        editor_widget: Segment Editor temporal.
        segment_id: ID interno del segmento que se quiere suavizar.
        method: método de suavizado de Slicer.
        kernel_mm: tamaño del kernel en milímetros.
    """

    editor_widget.setCurrentSegmentID(segment_id)
    editor_widget.setActiveEffectByName("Smoothing")
    effect = editor_widget.activeEffect()

    if effect is None:
        raise RuntimeError("No se pudo activar Smoothing.")

    # Definir el método de suavizado y el tamaño del kernel
    effect.setParameter("SmoothingMethod", method)
    effect.setParameter("KernelSizeMm", str(kernel_mm))

    # Aplicar el suavizado
    effect.self().onApply()


def postprocess_bone(seg_node, volume_node):
    """
    Ejecuta el postprocesado completo del segmento óseo.

    Secuencia aplicada:
        1. Fill between slices, para reducir rayas entre cortes.
        2. Islands - Keep largest island, para eliminar fragmentos pequeños.
        3. Morphological closing 2.0 mm.
        4. Morphological closing 1.0 mm.
        5. Median smoothing 1.0 mm.

    Parámetros:
        seg_node: nodo de segmentación que contiene el segmento Bone.
        volume_node: volumen de referencia cargado en Slicer.
    """

    # Buscar el ID interno del segmento Bone
    bone_id = get_segment_id_by_name(seg_node, BONE_SEGMENT_NAME)

    if bone_id is None:
        raise RuntimeError(
            f"No se encontró el segmento '{BONE_SEGMENT_NAME}'."
        )

    # Crear un Segment Editor temporal
    editor_widget, editor_node = create_editor(seg_node, volume_node)

    try:
        # Seleccionar únicamente el segmento Bone
        editor_widget.setCurrentSegmentID(bone_id)

        # ---------------------------------------------------------------------
        # 1) Interpolación entre cortes
        # ---------------------------------------------------------------------
        # Corrige parcialmente el aspecto de rayas o "código de barras" que
        # puede aparecer cuando la segmentación no es continua entre slices.
        if USE_FILL_BETWEEN_SLICES:
            apply_fill_between_slices(editor_widget, bone_id)

        # ---------------------------------------------------------------------
        # 2) Conservación de la isla principal
        # ---------------------------------------------------------------------
        # Elimina componentes pequeños desconectados de la estructura principal.
        apply_islands_keep_largest(editor_widget, bone_id)

        # ---------------------------------------------------------------------
        # 3) Primer cierre morfológico
        # ---------------------------------------------------------------------
        # Cierra pequeños huecos en la segmentación del hueso.
        apply_smoothing(
            editor_widget,
            bone_id,
            "MORPHOLOGICAL_CLOSING",
            CLOSING_KERNEL_MM_1
        )

        # ---------------------------------------------------------------------
        # 4) Segundo cierre morfológico más suave
        # ---------------------------------------------------------------------
        # Refina el resultado del cierre anterior.
        apply_smoothing(
            editor_widget,
            bone_id,
            "MORPHOLOGICAL_CLOSING",
            CLOSING_KERNEL_MM_2
        )

        # ---------------------------------------------------------------------
        # 5) Suavizado final con mediana
        # ---------------------------------------------------------------------
        # Reduce irregularidades locales de la superficie.
        apply_smoothing(
            editor_widget,
            bone_id,
            "MEDIAN",
            MEDIAN_KERNEL_MM
        )

    finally:
        # Eliminar el nodo temporal del Segment Editor para limpiar la escena.
        slicer.mrmlScene.RemoveNode(editor_node)


# =============================================================================
# EJECUCIÓN DEL SCRIPT
# =============================================================================

# Obtener el nodo de segmentación por su nombre
seg_node = slicer.util.getNode(SEGMENTATION_NAME)

# Obtener el volumen de referencia cargado en la escena
volume_nodes = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")

if not volume_nodes:
    raise RuntimeError("No hay ningún volumen cargado.")

# Se utiliza el primer volumen escalar encontrado en la escena
volume_node = volume_nodes[0]

# Ejecutar el postprocesado del segmento Bone
postprocess_bone(seg_node, volume_node)

# Mensajes finales de control
print("Postprocesado aplicado SOLO al segmento Bone.")
print("Se ha añadido Fill between slices para reducir el efecto de código de barras.")
print("No se ha procesado el segmento Tumor.")