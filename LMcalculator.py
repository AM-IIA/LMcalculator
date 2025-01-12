# LMcalculator
#PyGIS method for Landscape Metrics computation (QGIS environment compliant)

from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingParameterString
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterNumber
from qgis.core import QgsProcessingParameterVectorDestination
from qgis.core import QgsProcessingParameterRasterDestination
from qgis.core import QgsProcessingParameterFolderDestination
from qgis.core import QgsProcessingParameterFeatureSink
from qgis.core import QgsCoordinateReferenceSystem
import processing
import os

class LMCalculator(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        # Parameter: Classified Raster Input
        self.addParameter(QgsProcessingParameterRasterLayer('RasterInput', 'Classified Raster Input', defaultValue=None))

        # Parameter: Class Value
        self.addParameter(QgsProcessingParameterString('ClassValue', 'Class Value to Extract (e.g., 1)', defaultValue='1'))

        # Parameter: Folder for Outputs
        self.addParameter(QgsProcessingParameterFolderDestination('OutputFolder', 'Output Folder', defaultValue=None))

        # Parameter: Grid Spacing
        self.addParameter(QgsProcessingParameterNumber('HSpacing', 'Grid Spacing (meters)', type=QgsProcessingParameterNumber.Integer, defaultValue=300))

        # Outputs
        self.addParameter(QgsProcessingParameterVectorDestination('MetricsTable', 'Metrics Table Output', type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        feedback = QgsProcessingMultiStepFeedback(14, model_feedback)
        results = {}
        output_folder = parameters['OutputFolder']
        temporary_folder = os.path.join(output_folder, "Temporary_outputs")
        os.makedirs(temporary_folder, exist_ok=True)


        raster_input = self.parameterAsRasterLayer(parameters, 'RasterInput', context)
        class_value = parameters['ClassValue']
        h_spacing = parameters['HSpacing']

        # Step 1: Extract class-specific area raster (Raster Calculator)
        feedback.setCurrentStep(0)
        if feedback.isCanceled():
            return {}

        class_area_output_path = os.path.join(temporary_folder, "class_area.tif")
        alg_params = {
            'CELLSIZE': 0,
            'CRS': raster_input.crs(),
            'EXPRESSION': f'"{raster_input.name()}@1"={class_value}',
            'LAYERS': raster_input,
            'OUTPUT': class_area_output_path
        }
        class_area_output = processing.run('qgis:rastercalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Step 2: Label Landscape Patches
        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        labelled_patches_output_path = os.path.join(temporary_folder, "labelled_patches.tif")
        alg_params = {
            'LAND': class_area_output['OUTPUT'],
            'LC_CLASS': 1,
            'OUTPUT_RASTER': labelled_patches_output_path
        }
        labelled_patches_output = processing.run('lecos:labellandscape', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Step 3: Vectorize labelled raster
        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        vector_patch_output_path = os.path.join(temporary_folder, "vector_patches.shp")
        alg_params = {
            'BAND': 1,
            'EIGHT_CONNECTEDNESS': True,
            'FIELD': 'patch_id',
            'INPUT': labelled_patches_output['OUTPUT_RASTER'],
            'OUTPUT': vector_patch_output_path
        }
        vector_patch_output = processing.run('gdal:polygonize', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Step 4: Extract by attribute
        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        extracted_patches_path = os.path.join(temporary_folder, "extracted_patches.shp")
        alg_params = {
            'FIELD': 'patch_id',
            'INPUT': vector_patch_output['OUTPUT'],
            'OPERATOR': 1,  # ≠
            'VALUE': '0',
            'OUTPUT': extracted_patches_path
        }
        extracted_patches_output = processing.run('native:extractbyattribute', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Step 5: Fix invalid geometries
        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        fixed_vector_patch_output_path = os.path.join(temporary_folder, "fixed_vector_patches.shp")
        alg_params = {
            'INPUT': extracted_patches_output['OUTPUT'],
            'OUTPUT': fixed_vector_patch_output_path
        }
        fixed_vector_patch_output = processing.run('native:fixgeometries', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Step 6: Create grid
        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        grid_output_path = os.path.join(temporary_folder, "grid.shp")
        alg_params = {
            'CRS': raster_input.crs(),
            'EXTENT': fixed_vector_patch_output['OUTPUT'],
            'HOVERLAY': 0,
            'HSPACING': h_spacing,
            'TYPE': 2,  # Rectangle (Polygon)
            'VOVERLAY': 0,
            'VSPACING': h_spacing,
            'OUTPUT': grid_output_path
        }
        grid_output = processing.run('native:creategrid', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Step 7: Intersection of grid and vector patches
        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        intersection_output_path = os.path.join(temporary_folder, "grid_patch_intersection.shp")
        alg_params = {
            'INPUT': grid_output['OUTPUT'],
            'OVERLAY': fixed_vector_patch_output['OUTPUT'],
            'OUTPUT': intersection_output_path
        }
        intersection_output = processing.run('native:intersection', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Step 8: Field calculator area
        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

        field_area_output_path = os.path.join(temporary_folder, "field_area.shp")
        alg_params = {
            'FIELD_LENGTH': 8,
            'FIELD_NAME': 'surface',
            'FIELD_PRECISION': 2,
            'FIELD_TYPE': 0,  # Float
            'FORMULA': '$area',
            'INPUT': intersection_output['OUTPUT'],
            'OUTPUT': field_area_output_path
        }
        field_area_output = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Step 9: Field calculator perimeter
        feedback.setCurrentStep(8)
        if feedback.isCanceled():
            return {}

        field_perimeter_output_path = os.path.join(temporary_folder, "field_perimeter.shp")
        alg_params = {
            'FIELD_LENGTH': 9,
            'FIELD_NAME': 'perimeter',
            'FIELD_PRECISION': 2,
            'FIELD_TYPE': 0,  # Float
            'FORMULA': '$perimeter',
            'INPUT': field_area_output['OUTPUT'],
            'OUTPUT': field_perimeter_output_path
        }
        field_perimeter_output = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Step 10: Field calculator number of patches
        feedback.setCurrentStep(9)
        if feedback.isCanceled():
            return {}

        field_patch_count_output_path = os.path.join(temporary_folder, "field_patch_count.shp")
        alg_params = {
            'FIELD_LENGTH':11,
            'FIELD_NAME': 'patch_count',
            'FIELD_PRECISION': 0,
            'FIELD_TYPE': 1,  # Integer
            'FORMULA':'count_distinct(\"patch_id\",group_by:=\"id\")',
            'INPUT': os.path.join(temporary_folder, "field_perimeter.shp"),#field_perimeter_output['OUTPUT'],
            'OUTPUT': field_patch_count_output_path
        }
        field_patch_count_output = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        
        
        # Step 11: Aggregate metrics
        feedback.setCurrentStep(10)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'AGGREGATES': [
                {'aggregate': 'first_value','delimiter': ',','input': '\"id\"','length': 20,'name': 'id','precision': 0,'type': 2},
                {'aggregate': 'first_value','delimiter': ',','input': '\"left\"','length': 23,'name': 'left','precision': 15,'type': 2},
                {'aggregate': 'first_value','delimiter': ',','input': '\"top\"','length': 23,'name': 'top','precision': 15,'type': 2},
                {'aggregate': 'first_value','delimiter': ',','input': '\"right\"','length': 23,'name': 'right','precision': 15,'type': 2},
                {'aggregate': 'first_value','delimiter': ',','input': '\"bottom\"','length': 23,'name': 'bottom','precision': 15,'type': 2},
                {'aggregate': 'first_value','delimiter': ',','input': '\"patch_id\"','length': 20,'name': 'first_patch_id','precision': 0,'type': 2},
                {'aggregate': 'last_value','delimiter': ',','input': '\"patch_id\"','length': 20,'name': 'last_patch_id','precision': 0,'type': 2},
                {'aggregate': 'sum','delimiter': ',','input': '\"surface\"','length': 8,'name': 'surface','precision': 2,'type': 2},
                {'aggregate': 'sum','delimiter': ',','input': '\"perimeter\"','length': 9,'name': 'perimeter','precision': 2,'type': 2},
                {'aggregate': 'first_value','delimiter': ',','input': '\"patch_coun\"', 'length': 11, 'name': 'patch_count', 'precision': 0, 'type': 2}
            ],
            'GROUP_BY': 'id',
            'INPUT': field_patch_count_output['OUTPUT'],
            'OUTPUT': parameters['MetricsTable']
        }
        aggregate_output = processing.run('native:aggregate', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        results['MetricsTable'] = aggregate_output['OUTPUT']

        return results

    def name(self):
        return 'lm_calculator'

    def displayName(self):
        return 'LM Calculator'

    def group(self):
        return 'Custom Plugins'

    def groupId(self):
        return 'custom_plugins'

    def createInstance(self):
        return LMCalculator()
