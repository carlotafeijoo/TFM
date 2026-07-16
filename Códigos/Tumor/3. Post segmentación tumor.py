import slicer

# =============================================================================
# Postprocesado del segmento tumoral final en 3D Slicer
# =============================================================================
#
# Objetivo:
#   Aplicar un postprocesado automático sobre el segmento tumoral "Tumor_Final"
#   para mejorar su continuidad y suavizar su superficie antes de la
#   reconstrucción 3D/exportación STL.
#
# El procesamiento incluye:
#   1. Interpolación entre cortes con Fill between slices.
#   2. Eliminación de pequeñas islas desconectadas.
#   3. Cierre morfológico para rellenar huecos.
#   4. Suavizado gaussiano.
#   5. Suavizado final mediante filtro de mediana.
#
# IMPORTANTE:
#   - Este script modifica directamente el segmento "Tumor_Final".
#   - No crea una copia automática.
#   - Conviene guardar la escena antes de ejecutarlo.
#   - No procesa Bone ni Background.
# =============================================================================


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Nombre del nodo de segmentación donde se encuentra el segmento tumoral.
# Debe coincidir con el nombre visible en el panel de segmentaciones de Slicer.
SEGMENTATION_NAME = "Tumor_GrowFromSeeds"

# Nombre del segmento que se va a postprocesar.
SEGMENT_NAME = "Tumor_Final"

# Activa el efecto Fill between slices.
# Este efecto interpola/rellena entre cortes y ayuda a reducir artefactos
# tipo rayas o "código de barras" entre slices.
USE_FILL_BETWEEN_SLICES = True

# Parámetros de postprocesado para el tumor.
# Se utilizan valores relativamente fuertes porque el tumor suele necesitar
# mayor regularización que el hueso.
CLOSING_KERNEL_MM_1 = 5.0   # Primer cierre morfológico: rellena huecos grandes.
CLOSING_KERNEL_MM_2 = 3.0   # Segundo cierre: refina discontinuidades menores.
GAUSSIAN_KERNEL_MM = 1.5    # Suavizado gaussiano para una superficie más continua.
MEDIAN_KERNEL_MM = 2.0      # Suavizado final de bordes.

# Si está activado, se conserva solo la isla principal del tumor.
# Esto elimina fragmentos pequeños desconectados.
# Si el tumor tuviera varias regiones separadas que se quieren conservar,
# este valor debería ponerse en False.
USE_KEEP_LARGEST_ISLAND = True


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def get_segment_id_by_name(seg_node, target_name):
    """
    Busca el identificador interno de un segmento a partir de su nombre visible.

    En 3D Slicer, cada segmento tiene:
        - un nombre visible para el usuario, por ejemplo "Tumor_Final"
        - un ID interno utilizado por la API de Slicer

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

    # Crear un widget temporal del Segment Editor
    editor_widget = slicer.qMRMLSegmentEditorWidget()
    editor_widget.setMRMLScene(slicer.mrmlScene)

    # Crear un nodo temporal para guardar la configuración del Segment Editor
    editor_node = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLSegmentEditorNode"
    )
    editor_widget.setMRMLSegmentEditorNode(editor_node)

    # Asociar la segmentación y el volumen de referencia al editor
    editor_widget.setSegmentationNode(seg_node)
    editor_widget.setSourceVolumeNode(volume_node)

    # Evitar que las operaciones sobrescriban otros segmentos.
    # El objetivo es modificar únicamente el segmento seleccionado.
    editor_node.SetOverwriteMode(
        slicer.vtkMRMLSegmentEditorNode.OverwriteNone
    )

    return editor_widget, editor_node


def apply_fill_between_slices(editor_widget, segment_id):
    """
    Aplica el efecto Fill between slices.

    Este efecto interpola/rellena la segmentación entre cortes consecutivos.
    Es útil cuando el modelo 3D presenta un aspecto en bandas o "código de
    barras" debido a diferencias entre slices.

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

    # Generar previsualización de la interpolación
    effect.self().onPreview()

    # Aplicar definitivamente el resultado
    effect.self().onApply()


def apply_islands_keep_largest(editor_widget, segment_id):
    """
    Aplica el efecto Islands con la operación Keep largest island.

    Este paso elimina regiones pequeñas desconectadas y conserva únicamente
    la masa principal del tumor.

    Parámetros:
        editor_widget: Segment Editor temporal.
        segment_id: ID interno del segmento que se quiere procesar.
    """

    editor_widget.setCurrentSegmentID(segment_id)
    editor_widget.setActiveEffectByName("Islands")
    effect = editor_widget.activeEffect()

    if effect is None:
        raise RuntimeError("No se pudo activar Islands.")

    # Conservar solo la isla de mayor tamaño
    effect.setParameter("Operation", "KEEP_LARGEST_ISLAND")
    effect.self().onApply()


def apply_smoothing(editor_widget, segment_id, method, kernel_mm):
    """
    Aplica un suavizado al segmento seleccionado.

    Métodos utilizados:
        - MORPHOLOGICAL_CLOSING:
            Cierra huecos y discontinuidades en la segmentación.
        - GAUSSIAN:
            Suaviza la superficie de forma continua.
        - MEDIAN:
            Reduce irregularidades locales en los bordes.

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

    # Aplicar el efecto
    effect.self().onApply()


def postprocess_tumor(seg_node, volume_node):
    """
    Ejecuta el postprocesado completo del segmento tumoral.

    Secuencia aplicada:
        1. Fill between slices.
        2. Islands - Keep largest island.
        3. Morphological closing 5.0 mm.
        4. Morphological closing 3.0 mm.
        5. Gaussian smoothing 1.5 mm.
        6. Median smoothing 2.0 mm.

    Parámetros:
        seg_node: nodo de segmentación que contiene el segmento Tumor_Final.
        volume_node: volumen de referencia cargado en Slicer.
    """

    # Buscar el ID interno del segmento Tumor_Final
    tumor_id = get_segment_id_by_name(seg_node, SEGMENT_NAME)

    if tumor_id is None:
        raise RuntimeError(
            f"No se encontró el segmento '{SEGMENT_NAME}'."
        )

    # Crear un Segment Editor temporal
    editor_widget, editor_node = create_editor(seg_node, volume_node)

    try:
        # Seleccionar únicamente el segmento Tumor_Final
        editor_widget.setCurrentSegmentID(tumor_id)

        # ---------------------------------------------------------------------
        # 1) Interpolación entre cortes
        # ---------------------------------------------------------------------
        # Reduce el efecto de rayas o bandas entre slices.
        if USE_FILL_BETWEEN_SLICES:
            apply_fill_between_slices(editor_widget, tumor_id)

        # ---------------------------------------------------------------------
        # 2) Conservación de la masa principal
        # ---------------------------------------------------------------------
        # Elimina pequeñas islas desconectadas y mantiene el componente principal.
        if USE_KEEP_LARGEST_ISLAND:
            apply_islands_keep_largest(editor_widget, tumor_id)

        # ---------------------------------------------------------------------
        # 3) Primer cierre morfológico
        # ---------------------------------------------------------------------
        # Rellena huecos grandes y mejora la continuidad del tumor.
        apply_smoothing(
            editor_widget,
            tumor_id,
            "MORPHOLOGICAL_CLOSING",
            CLOSING_KERNEL_MM_1
        )

        # ---------------------------------------------------------------------
        # 4) Segundo cierre morfológico
        # ---------------------------------------------------------------------
        # Refina el resultado anterior y cierra discontinuidades menores.
        apply_smoothing(
            editor_widget,
            tumor_id,
            "MORPHOLOGICAL_CLOSING",
            CLOSING_KERNEL_MM_2
        )

        # ---------------------------------------------------------------------
        # 5) Suavizado gaussiano
        # ---------------------------------------------------------------------
        # Regulariza la superficie del tumor de forma continua.
        apply_smoothing(
            editor_widget,
            tumor_id,
            "GAUSSIAN",
            GAUSSIAN_KERNEL_MM
        )

        # ---------------------------------------------------------------------
        # 6) Suavizado final con mediana
        # ---------------------------------------------------------------------
        # Reduce irregularidades locales en los bordes del segmento.
        apply_smoothing(
            editor_widget,
            tumor_id,
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

# Ejecutar el postprocesado del segmento Tumor_Final
postprocess_tumor(seg_node, volume_node)

# Mensajes finales de control
print("Postprocesado aplicado SOLO al segmento Tumor_Final.")
print("No se ha procesado Bone.")
print("No se ha procesado Background.")