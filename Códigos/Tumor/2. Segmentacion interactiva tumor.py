import slicer
import vtk
import numpy as np

# =============================================================================
# Segmentación semiautomática de tumor mediante Grow from Seeds en 3D Slicer
# =============================================================================
#
# Objetivo:
#   Este script automatiza una segmentación semiautomática del tumor a partir
#   de semillas colocadas manualmente por el usuario.
#
# Flujo general:
#   1. El usuario coloca puntos/seeds dentro del tumor.
#   2. El usuario coloca puntos/seeds en el fondo o tejido no tumoral.
#   3. El script convierte esas semillas en un labelmap temporal.
#   4. El labelmap se importa como segmentación inicial.
#   5. Se ejecuta el efecto Grow from Seeds de 3D Slicer.
#   6. Se genera una segmentación final con dos segmentos:
#       - Tumor
#       - Background
#
# Uso:
#   Ejecutar este script dentro de 3D Slicer.
#   El programa irá mostrando instrucciones para colocar cada punto.
#
# IMPORTANTE:
#   - El script elimina segmentaciones previas con el mismo nombre.
#   - El resultado se guarda en una segmentación llamada "Tumor_GrowFromSeeds".
#   - El segmento Background se oculta al finalizar.
# =============================================================================


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Nombre del nodo de puntos donde se guardarán las semillas del tumor.
TUMOR_SEED_NODE = "TumorSeeds"

# Nombre del nodo de puntos donde se guardarán las semillas de fondo.
BACKGROUND_SEED_NODE = "BackgroundSeeds"

# Nombre de la segmentación final que se creará en la escena.
SEGMENTATION_NAME = "Tumor_GrowFromSeeds"

# Nombre del labelmap temporal usado para transformar las semillas en segmentos.
TEMP_LABELMAP_NAME = "SeedLabelMap"

# Radio de cada semilla, expresado en milímetros.
# Cada punto colocado por el usuario se convierte en una pequeña esfera.
SEED_RADIUS_MM = 1.5


# Instrucciones que se mostrarán al usuario para colocar las semillas tumorales.
# Se piden varios puntos dentro del tumor para representar diferentes zonas:
# centro, bordes, parte superior e inferior.
TUMOR_INSTRUCTIONS = [
    "Tumor 1/6: CENTRO del tumor — capa CENTRAL",
    "Tumor 2/6: PARTE SUPERIOR del tumor — capa CENTRAL",
    "Tumor 3/6: PARTE INFERIOR del tumor — capa CENTRAL",
    "Tumor 4/6: BORDE LATERAL del tumor — capa CENTRAL",
    "Tumor 5/6: DENTRO del tumor — capa SUPERIOR",
    "Tumor 6/6: DENTRO del tumor — capa INFERIOR",
]


# Instrucciones que se mostrarán al usuario para colocar semillas de fondo.
# Estas semillas indican zonas que NO deben formar parte del tumor.
BACKGROUND_INSTRUCTIONS = [
    "Background 1/6: JUSTO POR ENCIMA del tumor — capa CENTRAL",
    "Background 2/6: JUSTO POR ENCIMA del tumor (otra zona) — capa CENTRAL",
    "Background 3/6: FUERA del tumor (lateral) — capa CENTRAL",
    "Background 4/6: FUERA del tumor (zona cercana) — capa CENTRAL",
    "Background 5/6: FUERA del tumor — capa SUPERIOR",
    "Background 6/6: FUERA del tumor — capa INFERIOR",
]


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def get_first_scalar_volume():
    """
    Obtiene el primer volumen escalar cargado en la escena de 3D Slicer.

    El algoritmo necesita un volumen de referencia, por ejemplo una RM o TC,
    sobre el que se realizará la segmentación.

    Devuelve:
        Primer vtkMRMLScalarVolumeNode encontrado en la escena.

    Lanza:
        RuntimeError si no hay ningún volumen cargado.
    """

    nodes = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")

    if not nodes:
        raise RuntimeError("No hay ningún volumen cargado.")

    return nodes[0]


def remove_if_exists(name):
    """
    Elimina un nodo de la escena si existe.

    Se utiliza para borrar segmentaciones o labelmaps temporales previos
    y evitar conflictos al volver a ejecutar el script.

    Parámetros:
        name: nombre del nodo que se quiere eliminar.
    """

    try:
        node = slicer.util.getNode(name)
        slicer.mrmlScene.RemoveNode(node)
    except Exception:
        # Si el nodo no existe, no se hace nada.
        pass


def get_or_create_fiducial_node(name):
    """
    Obtiene un nodo de puntos fiduciales o lo crea si no existe.

    Los nodos fiduciales se utilizan para almacenar las semillas colocadas
    manualmente por el usuario.

    Parámetros:
        name: nombre del nodo fiducial.

    Devuelve:
        Nodo vtkMRMLMarkupsFiducialNode.
    """

    try:
        node = slicer.util.getNode(name)
    except Exception:
        node = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsFiducialNode",
            name
        )
        node.CreateDefaultDisplayNodes()

    return node


def clear_all_points(node):
    """
    Elimina todos los puntos de un nodo fiducial.

    Esto permite empezar la colocación de semillas desde cero cada vez que
    se ejecuta el script.

    Parámetros:
        node: nodo fiducial del que se eliminarán los puntos.
    """

    node.RemoveAllControlPoints()


def ras_to_ijk(volume_node, ras_point):
    """
    Convierte un punto desde coordenadas RAS a coordenadas IJK.

    En 3D Slicer:
        - RAS corresponde a coordenadas anatómicas/mundo.
        - IJK corresponde a índices de voxel dentro del volumen.

    Esta conversión es necesaria para poder pintar las semillas dentro
    del array volumétrico.

    Parámetros:
        volume_node: volumen de referencia.
        ras_point: coordenadas RAS del punto.

    Devuelve:
        Coordenadas IJK redondeadas como enteros.
    """

    rasToIjk = vtk.vtkMatrix4x4()
    volume_node.GetRASToIJKMatrix(rasToIjk)

    ras_h = [ras_point[0], ras_point[1], ras_point[2], 1.0]
    ijk_h = [0.0, 0.0, 0.0, 0.0]

    rasToIjk.MultiplyPoint(ras_h, ijk_h)

    return np.round(np.array(ijk_h[:3])).astype(int)


def clamp(v, lo, hi):
    """
    Limita un valor dentro de un intervalo.

    Se usa para evitar acceder a posiciones fuera del volumen.

    Parámetros:
        v: valor original.
        lo: límite inferior.
        hi: límite superior.

    Devuelve:
        Valor limitado entre lo y hi.
    """

    return max(lo, min(hi, v))


def draw_sphere(arr_kji, center_ijk, radius_mm, spacing, value):
    """
    Dibuja una esfera dentro de un array volumétrico.

    Cada semilla colocada por el usuario se transforma en una pequeña esfera
    de voxeles. Esto hace que Grow from Seeds tenga una región inicial más
    estable que un único punto aislado.

    Parámetros:
        arr_kji: array del volumen en orden KJI.
        center_ijk: centro de la esfera en coordenadas IJK.
        radius_mm: radio de la esfera en milímetros.
        spacing: tamaño de voxel del volumen.
        value: etiqueta asignada a la esfera.
            1 = Tumor
            2 = Background
    """

    ci, cj, ck = center_ijk
    zmax, ymax, xmax = arr_kji.shape

    # Conversión del radio desde milímetros a número aproximado de voxeles.
    rx = max(1, int(np.ceil(radius_mm / spacing[0])))
    ry = max(1, int(np.ceil(radius_mm / spacing[1])))
    rz = max(1, int(np.ceil(radius_mm / spacing[2])))

    # Definición del cubo que contiene la esfera.
    i0 = clamp(ci - rx, 0, xmax - 1)
    i1 = clamp(ci + rx, 0, xmax - 1)
    j0 = clamp(cj - ry, 0, ymax - 1)
    j1 = clamp(cj + ry, 0, ymax - 1)
    k0 = clamp(ck - rz, 0, zmax - 1)
    k1 = clamp(ck + rz, 0, zmax - 1)

    # Recorrido de los voxeles dentro del cubo.
    # Solo se rellenan los que caen dentro de la esfera.
    for k in range(k0, k1 + 1):
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                dx = (i - ci) * spacing[0]
                dy = (j - cj) * spacing[1]
                dz = (k - ck) * spacing[2]

                if dx * dx + dy * dy + dz * dz <= radius_mm * radius_mm:
                    arr_kji[k, j, i] = value


def create_segmentation_from_seedmap(volume_node, seedmap_array, seg_name):
    """
    Crea una segmentación inicial a partir del mapa de semillas.

    El mapa de semillas se guarda primero como un labelmap temporal.
    Después se importa a un nodo de segmentación de Slicer.

    Parámetros:
        volume_node: volumen de referencia.
        seedmap_array: array con las etiquetas de semillas.
        seg_name: nombre de la segmentación que se creará.

    Devuelve:
        Nodo de segmentación creado.
    """

    # Crear un labelmap temporal con la misma geometría que el volumen original.
    label_node = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLLabelMapVolumeNode",
        TEMP_LABELMAP_NAME
    )

    slicer.modules.volumes.logic().CreateLabelVolumeFromVolume(
        slicer.mrmlScene,
        label_node,
        volume_node
    )

    # Actualizar el labelmap con el array de semillas.
    slicer.util.updateVolumeFromArray(
        label_node,
        seedmap_array.astype(np.uint8)
    )

    # Crear nodo de segmentación final.
    seg_node = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLSegmentationNode",
        seg_name
    )

    seg_node.CreateDefaultDisplayNodes()
    seg_node.SetReferenceImageGeometryParameterFromVolumeNode(volume_node)

    # Importar el labelmap como segmentos.
    slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
        label_node,
        seg_node
    )

    # Renombrar y colorear los segmentos generados.
    # La etiqueta 1 corresponde al tumor y la etiqueta 2 al fondo.
    seg = seg_node.GetSegmentation()

    for i in range(seg.GetNumberOfSegments()):
        seg_id = seg.GetNthSegmentID(i)
        segment = seg.GetSegment(seg_id)
        name = segment.GetName()

        if "1" in name:
            segment.SetName("Tumor")
            segment.SetColor(1.0, 0.0, 0.0)  # rojo
        elif "2" in name:
            segment.SetName("Background")
            segment.SetColor(0.0, 1.0, 0.0)  # verde

    # Eliminar el labelmap temporal, ya que su contenido se importó a la segmentación.
    slicer.mrmlScene.RemoveNode(label_node)

    return seg_node


def run_grow_from_seeds(volume_node, seg_node):
    """
    Ejecuta el efecto Grow from Seeds sobre la segmentación inicial.

    Grow from Seeds utiliza las regiones iniciales de tumor y fondo para
    expandir la segmentación en función de la intensidad y continuidad de
    la imagen.

    Parámetros:
        volume_node: volumen de referencia.
        seg_node: segmentación inicial con semillas de tumor y fondo.

    Devuelve:
        Nodo de segmentación resultante tras aplicar Grow from Seeds.
    """

    # Crear un Segment Editor temporal.
    editor_widget = slicer.qMRMLSegmentEditorWidget()
    editor_widget.setMRMLScene(slicer.mrmlScene)

    editor_node = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLSegmentEditorNode"
    )

    editor_widget.setMRMLSegmentEditorNode(editor_node)
    editor_widget.setSegmentationNode(seg_node)
    editor_widget.setSourceVolumeNode(volume_node)

    # Activar el efecto Grow from Seeds.
    editor_widget.setActiveEffectByName("Grow from seeds")
    effect = editor_widget.activeEffect()

    if effect is None:
        raise RuntimeError("No se pudo activar Grow from seeds.")

    # Generar previsualización y aplicar resultado.
    effect.self().onPreview()
    effect.self().onApply()

    return seg_node


def get_points_ras(markup_node):
    """
    Extrae todos los puntos de un nodo fiducial en coordenadas RAS.

    Parámetros:
        markup_node: nodo vtkMRMLMarkupsFiducialNode.

    Devuelve:
        Lista de puntos en coordenadas RAS.
    """

    pts = []
    n = markup_node.GetNumberOfControlPoints()

    for i in range(n):
        p = [0.0, 0.0, 0.0]
        markup_node.GetNthControlPointPositionWorld(i, p)
        pts.append(np.array(p, dtype=float))

    return pts


# =============================================================================
# CLASE INTERACTIVA PARA GUIAR LA COLOCACIÓN DE SEMILLAS
# =============================================================================

class SeedPlacementGuide:
    """
    Clase que controla el flujo interactivo de colocación de semillas.

    La clase guía al usuario en dos fases:
        1. Colocación de semillas dentro del tumor.
        2. Colocación de semillas en el fondo.

    Al completar ambas fases, se ejecuta automáticamente Grow from Seeds.
    """

    def __init__(self):
        """
        Inicializa la guía interactiva.

        Se obtiene el volumen, se crean o reutilizan los nodos de puntos,
        se limpian datos previos y se inicia la fase de semillas tumorales.
        """

        # Obtener volumen de referencia.
        self.volume_node = get_first_scalar_volume()

        # Crear u obtener nodos de semillas.
        self.tumor_node = get_or_create_fiducial_node(TUMOR_SEED_NODE)
        self.bg_node = get_or_create_fiducial_node(BACKGROUND_SEED_NODE)

        # Limpiar puntos previos para iniciar una nueva segmentación.
        clear_all_points(self.tumor_node)
        clear_all_points(self.bg_node)

        # Eliminar resultados anteriores con los mismos nombres.
        remove_if_exists(SEGMENTATION_NAME)
        remove_if_exists(TEMP_LABELMAP_NAME)

        # Estado interno de la guía.
        self.phase = "tumor"
        self.tumor_index = 0
        self.bg_index = 0

        # Observers para detectar cuándo el usuario añade un punto.
        self.tumor_observer = None
        self.bg_observer = None

        # Configurar visualización e iniciar primera fase.
        self.setup_display()
        self.start_tumor_phase()

    def setup_display(self):
        """
        Define los colores de visualización de los puntos de semillas.

        Tumor:
            rojo

        Background:
            verde
        """

        self.tumor_node.GetDisplayNode().SetColor(1, 0, 0)
        self.bg_node.GetDisplayNode().SetColor(0, 1, 0)

    def show_message(self, text):
        """
        Muestra un mensaje al usuario.

        El mensaje aparece en una ventana emergente de Slicer y también
        se imprime en la consola.

        Parámetros:
            text: texto que se mostrará.
        """

        slicer.util.infoDisplay(text, "Guía de semillas")
        print(text)

    def activate_place_mode(self):
        """
        Activa el modo de colocación de puntos en 3D Slicer.

        Esto permite que el usuario haga clic directamente sobre la imagen
        para colocar las semillas.
        """

        interactionNode = slicer.app.applicationLogic().GetInteractionNode()
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()

        selectionNode.SetReferenceActivePlaceNodeClassName(
            "vtkMRMLMarkupsFiducialNode"
        )

        interactionNode.SetCurrentInteractionMode(interactionNode.Place)

        # Mantiene activo el modo de colocación para poder añadir varios puntos.
        try:
            interactionNode.SetPlaceModePersistence(1)
        except Exception:
            pass

    def set_active_list(self, node):
        """
        Define en qué nodo se guardarán los puntos colocados.

        Parámetros:
            node: nodo fiducial activo.
        """

        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        selectionNode.SetActivePlaceNodeID(node.GetID())

    def start_tumor_phase(self):
        """
        Inicia la fase de colocación de semillas tumorales.

        Se activa el nodo TumorSeeds y se añade un observer para detectar
        cada nuevo punto colocado.
        """

        self.cleanup_observers()
        self.phase = "tumor"

        self.set_active_list(self.tumor_node)

        self.tumor_observer = self.tumor_node.AddObserver(
            slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
            self.on_tumor_point_added
        )

        self.prompt_next()

    def start_bg_phase(self):
        """
        Inicia la fase de colocación de semillas de fondo.

        Se activa el nodo BackgroundSeeds y se añade un observer para detectar
        cada nuevo punto colocado.
        """

        self.cleanup_observers()
        self.phase = "background"

        self.set_active_list(self.bg_node)

        self.bg_observer = self.bg_node.AddObserver(
            slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
            self.on_bg_point_added
        )

        self.prompt_next()

    def prompt_next(self):
        """
        Muestra la siguiente instrucción al usuario.

        Según la fase actual, indica dónde debe colocarse la siguiente semilla.
        Cuando se completan todas las semillas tumorales, pasa a fondo.
        Cuando se completan todas las semillas de fondo, ejecuta la segmentación.
        """

        if self.phase == "tumor":
            if self.tumor_index < len(TUMOR_INSTRUCTIONS):
                self.show_message(TUMOR_INSTRUCTIONS[self.tumor_index])
                self.activate_place_mode()
            else:
                self.start_bg_phase()

        elif self.phase == "background":
            if self.bg_index < len(BACKGROUND_INSTRUCTIONS):
                self.show_message(BACKGROUND_INSTRUCTIONS[self.bg_index])
                self.activate_place_mode()
            else:
                self.finish()

    def on_tumor_point_added(self, caller, event):
        """
        Función llamada automáticamente cuando se añade una semilla tumoral.
        """

        self.tumor_index += 1
        self.prompt_next()

    def on_bg_point_added(self, caller, event):
        """
        Función llamada automáticamente cuando se añade una semilla de fondo.
        """

        self.bg_index += 1
        self.prompt_next()

    def finish(self):
        """
        Finaliza la colocación de semillas y lanza la segmentación.
        """

        self.cleanup_observers()
        self.show_message("Semillas completadas. Ejecutando Grow from Seeds...")
        self.run_segmentation()

    def run_segmentation(self):
        """
        Construye el mapa de semillas y ejecuta Grow from Seeds.

        Pasos:
            1. Obtener el array del volumen.
            2. Crear un seedmap vacío.
            3. Convertir los puntos RAS a IJK.
            4. Dibujar esferas de semillas en el seedmap.
            5. Crear una segmentación inicial.
            6. Ejecutar Grow from Seeds.
            7. Ocultar el segmento Background.
        """

        spacing = self.volume_node.GetSpacing()
        arr = slicer.util.arrayFromVolume(self.volume_node)

        # Crear un mapa de semillas vacío con las mismas dimensiones que el volumen.
        seedmap = np.zeros_like(arr, dtype=np.uint8)

        # Obtener puntos de tumor y fondo en coordenadas RAS.
        tumor_points_ras = get_points_ras(self.tumor_node)
        bg_points_ras = get_points_ras(self.bg_node)

        # Dibujar semillas tumorales con valor 1.
        for p in tumor_points_ras:
            ijk = ras_to_ijk(self.volume_node, p)
            draw_sphere(seedmap, ijk, SEED_RADIUS_MM, spacing, value=1)

        # Dibujar semillas de fondo con valor 2.
        for p in bg_points_ras:
            ijk = ras_to_ijk(self.volume_node, p)
            draw_sphere(seedmap, ijk, SEED_RADIUS_MM, spacing, value=2)

        # Crear la segmentación inicial a partir del labelmap de semillas.
        seg_node = create_segmentation_from_seedmap(
            self.volume_node,
            seedmap,
            SEGMENTATION_NAME
        )

        # Ejecutar Grow from Seeds sobre la segmentación inicial.
        run_grow_from_seeds(self.volume_node, seg_node)

        # Ocultar el segmento Background para visualizar solo el tumor.
        display_node = seg_node.GetDisplayNode()
        seg = seg_node.GetSegmentation()

        for i in range(seg.GetNumberOfSegments()):
            seg_id = seg.GetNthSegmentID(i)
            name = seg.GetSegment(seg_id).GetName().lower()

            if "background" in name:
                display_node.SetSegmentVisibility(seg_id, False)

        print("Segmentación completada")

    def cleanup_observers(self):
        """
        Elimina los observers activos.

        Esto evita que se acumulen eventos duplicados si se reinicia el script
        o si se cambia de fase.
        """

        if self.tumor_observer:
            self.tumor_node.RemoveObserver(self.tumor_observer)
            self.tumor_observer = None

        if self.bg_observer:
            self.bg_node.RemoveObserver(self.bg_observer)
            self.bg_observer = None


# =============================================================================
# EJECUCIÓN DEL SCRIPT
# =============================================================================

# Al crear una instancia de SeedPlacementGuide se inicia automáticamente
# la guía interactiva para colocar semillas.
guide = SeedPlacementGuide()