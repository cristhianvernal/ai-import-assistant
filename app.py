import streamlit as st
import pandas as pd
import io
import traceback
import re
import os
from dateutil import parser
from dotenv import load_dotenv

load_dotenv()

from typing import Dict, Any, List, Optional, Tuple

# Importaciones de módulos
from src.document_processor import process_documents
from src.excel_generator import create_final_excel_report
from src.catalog_manager import CatalogManager 
from src.invoice_generator import InvoiceGenerator 
from src.session_manager import SessionManager 
from src.excel_templates import ExcelTemplateManager 

# Configuración Inicial de la Página
st.set_page_config(layout="wide", page_title="Asistente de Importaciones IA - Validable")

# Inicializar Gestores de Negocio (solo para referencia si es necesario)
invoice_gen = InvoiceGenerator()

# Funciones Auxiliares para Gestores de Sesión y Detección de Columnas

def normalize_text(text: str) -> str:
    """Normaliza el texto para comparación (minúsculas y sin espacios/puntuación)."""
    if not isinstance(text, str):
        return ""
    # Remover tildes, símbolos, puntuación y convertir a minúsculas para robustez
    text = text.lower()
    text = re.sub(r'[áéíóúüñ]', lambda m: {'á': 'a', 'é': 'a', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u', 'ñ': 'n'}[m.group(0)], text)
    text = re.sub(r'[\s\-_\.,()/#]', '', text) 
    return text

def find_best_column_match(df_columns: List[str], target_keywords: Dict[str, List[str]]) -> Dict[str, Optional[str]]:
    """
    Busca la mejor coincidencia de columna basándose en una lista de palabras clave
    para los campos requeridos, usando normalización.
    """
    column_map = {}
    normalized_df_columns = {col: normalize_text(col) for col in df_columns}
    
    for required_name, keywords in target_keywords.items():
        best_match_col = None
        max_score = 0
        
        normalized_keywords = [normalize_text(k) for k in keywords]
        
        for real_col, normalized_real_col in normalized_df_columns.items():
            current_score = 0
            
            # 1. Búsqueda de coincidencia exacta (normalizada)
            if normalized_real_col == normalize_text(required_name):
                current_score = 100 
            
            # 2. Búsqueda por palabras clave 
            elif current_score < 100:
                for keyword in normalized_keywords:
                    if keyword and keyword in normalized_real_col:
                        current_score += 10 # Puntuación por cada palabra clave encontrada
            
            # 3. Priorizar el match si es mejor
            if current_score > max_score:
                max_score = current_score
                best_match_col = real_col
        
        # Solo acepta el match si se encontró alguna palabra clave (score > 0)
        column_map[required_name] = best_match_col if max_score >= 10 else None
        
    return column_map

def get_catalog_manager() -> CatalogManager:
    """Obtiene o inicializa la instancia de CatalogManager en la sesión."""
    if 'catalog_manager' not in st.session_state:
        st.session_state.catalog_manager = CatalogManager()
    return st.session_state.catalog_manager

def get_session_manager() -> SessionManager:
    """Obtiene o inicializa la instancia de SessionManager en la sesión."""
    if 'session_manager' not in st.session_state:
        try:
            st.session_state.session_manager = SessionManager()
        except ValueError as e:
            st.error(f"Error de configuración de Base de Datos (SessionManager): {e}. Revise su DATABASE_URL.")
            st.session_state.session_manager = None
        except Exception as e:
            st.error(f"Error inicializando SessionManager: {e}")
            st.session_state.session_manager = None
    return st.session_state.session_manager

def get_template_manager() -> ExcelTemplateManager:
    """Obtiene o inicializa la instancia de ExcelTemplateManager en la sesión."""
    if 'template_manager' not in st.session_state:
        st.session_state.template_manager = ExcelTemplateManager()
    return st.session_state.template_manager

def initialize_session_state():
    """Inicializa las variables necesarias en el estado de la sesión."""
    if 'step' not in st.session_state:
        st.session_state.step = "upload"
    
    if 'raw_data' not in st.session_state:
        st.session_state.raw_data = None
    if 'validated_data' not in st.session_state:
        st.session_state.validated_data = None
    if 'excel_output_aforo' not in st.session_state:
        st.session_state.excel_output_aforo = None
    if 'excel_output_custom' not in st.session_state: 
        st.session_state.excel_output_custom = None
    if 'last_report_type' not in st.session_state: 
        st.session_state.last_report_type = None
    if 'invoice_file_names' not in st.session_state:
        st.session_state.invoice_file_names = []
        
    # Inicializa los Managers para que estén disponibles
    get_catalog_manager()
    get_session_manager()
    get_template_manager()
    
    # Limpia el estado de la generación de facturas
    if 'invoice_generation_success' not in st.session_state:
        st.session_state.invoice_generation_success = False

    # Restaurar datos si se cargó una sesión
    if st.session_state.get('loaded_session_data') and st.session_state.step == "upload":
        st.session_state.validated_data = st.session_state.loaded_session_data
        st.session_state.step = "validate" 
        st.session_state.loaded_session_data = None 
    
# Función para cargar valores validados a los widgets (persistencia de estado)
def _load_validated_data_to_widgets_state(data_to_edit: Dict[str, Any]):
    """
    Carga los valores de 'validated_data' al st.session_state con las claves
    exactas que usan los widgets de edición, forzando la persistencia.
    """
    
    bl_data = data_to_edit.get('bl_data', {})
    invoices_data = data_to_edit.get('all_invoices_data', [])
    
    # 1. Cargar claves del BL 
    bl_fields = {
        "edit_bl_num": safe_str(bl_data.get('bl_number')),
        "edit_booking_num": safe_str(bl_data.get('booking_number')),
        "edit_freight_cost": safe_float(bl_data.get('freight_cost')),
        "edit_pol": safe_str(bl_data.get('port_of_loading')),
        "edit_pod": safe_str(bl_data.get('port_of_discharge')),
        "edit_cargo_type": safe_str(bl_data.get('cargo_type')),
        "edit_container_no": safe_str(bl_data.get('container_no')),
        "edit_packages_count": int(safe_float(bl_data.get('packages_count', 0))),
        "edit_gross_weight": safe_float(bl_data.get('gross_weight')),
        # Partes
        "exporter_name_ref": safe_str(bl_data.get('exporter_details', {}).get('name')),
        "exporter_address_edit": safe_str(bl_data.get('exporter_details', {}).get('address')),
        "consignee_name_ref": safe_str(bl_data.get('consignee_details', {}).get('name')),
        "consignee_address_edit": safe_str(bl_data.get('consignee_details', {}).get('address')),
    }

    # Asignar a session_state SOLO si la clave no existe o si el valor es diferente
    # Esto previene el error "StreamlitValueAssignmentNotAllowedError"
    for key, value in bl_fields.items():
        if key not in st.session_state or st.session_state[key] != value:
            st.session_state[key] = value

    # 2. Cargar claves de Facturas (campos de entrada normales)
    for i, inv in enumerate(invoices_data):
        inv_fields = {
            f"incoterm_{i}": safe_str(inv.get('incoterm', 'NOT_FOUND')).upper(),
            f"inv_num_{i}": safe_str(inv.get('invoice_number')),
            f"inv_date_{i}": safe_str(inv.get('invoice_date')),
            f"inv_curr_{i}": safe_str(inv.get('currency')),
            f"total_val_{i}": safe_float(inv.get('total_value')),
        }
        
        for key, value in inv_fields.items():
             if key not in st.session_state or st.session_state[key] != value:
                st.session_state[key] = value
            


def reset_process():
    """Resetea el estado para iniciar un nuevo análisis."""
    st.session_state.step = "upload"
    
    st.session_state.raw_data = None
    st.session_state.validated_data = None
    st.session_state.excel_output_aforo = None
    st.session_state.excel_output_custom = None
    st.session_state.last_report_type = None
    st.session_state.invoice_file_names = []
    st.session_state.catalog_manager = CatalogManager() 
    st.session_state.invoice_generation_success = False
    st.session_state.master_invoice_data = []
    

    if 'widgets_initialized' in st.session_state:
        del st.session_state['widgets_initialized']
    
    # Limpiar las claves de edición explícitas 
    keys_to_delete = [k for k in st.session_state.keys() if isinstance(k, str) and (k.startswith('edit_') or k.startswith('exporter_') or k.startswith('consignee_') or k.startswith('incoterm_') or k.startswith('inv_') or k.startswith('total_val_') or k.startswith('items_editor_') or k.startswith('invoice_df_'))]
    for k in keys_to_delete:
        if k in st.session_state:
            del st.session_state[k]

    st.rerun()

def safe_float(value: Any, default: float = 0.0) -> float:
    """Convierte un valor a float de forma segura, útil para inputs numéricos."""
    try:
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default
        
def safe_str(value: Any, default: str = "") -> str:
    """Convierte un valor a string de forma segura."""
    return str(value) if value is not None else default



def calculate_prorated_freight(validated_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calcula el flete prorrateado para cada ítem basado en su valor FOB.
    Esta función debe ser llamada DESPUÉS de la validación manual y ANTES de generar el reporte.
    """
    # 1. Obtener el costo total del flete desde los datos validados del BL
    total_freight_cost = safe_float(validated_data.get('bl_data', {}).get('freight_cost', 0))
    
    # 2. Iterar sobre cada factura en los datos validados
    for invoice in validated_data.get('all_invoices_data', []):
        # Primero, calcular el valor FOB total de la factura actual.
        # Es crucial usar 'total_value' como el FOB base, asumiendo que las facturas son FOB.
        # Si el incoterm no fuera FOB, se necesitaría una lógica más compleja que no está definida.
        total_fob_invoice = sum(safe_float(item.get('total_price', 0)) for item in invoice.get('items', []))
        
        # Asignar un valor fob_value a cada ítem para referencia futura
        for item in invoice.get('items', []):
            item['fob_value'] = safe_float(item.get('total_price', 0))
            
        # 3. Solo proceder si el FOB total es mayor que cero para evitar división por cero
        if total_fob_invoice > 0:
            # 4. Ahora, calcular y asignar el flete prorrateado para cada ítem en la factura
            for item in invoice.get('items', []):
                item_fob = safe_float(item.get('fob_value', 0))
                
                # La fórmula del prorrateo: (FOB del Ítem / FOB Total de la Factura) * Costo Total del Flete
                prorated_freight = (item_fob / total_fob_invoice) * total_freight_cost
                item['freight_proportional'] = prorated_freight
        else:
            # Si el total FOB es cero, el flete proporcional también es cero para todos los ítems
            for item in invoice.get('items', []):
                item['freight_proportional'] = 0.0

    return validated_data




def _consolidate_data_for_template(validated_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Combina datos del BL y la primera factura para el ExcelTemplateManager.
    """
    if not validated_data or not validated_data.get('bl_data'):
        return []
        
    bl_data = validated_data['bl_data']
    all_invoices = validated_data.get('all_invoices_data', [])
    
    # Tomamos los campos del BL
    base_data = {
        'numero_bl': bl_data.get('bl_number'),
        'valor_flete': bl_data.get('freight_cost'),
        'bultos': bl_data.get('packages_count'),
        'kilos': bl_data.get('gross_weight'),
        'numero_contenedor': bl_data.get('container_no'),
        'exportador': bl_data.get('exporter_details', {}).get('name'),
        'consignatario': bl_data.get('consignee_details', {}).get('name'),
        'archivo': bl_data.get('bl_number', 'Documento Consolidado'),
    }
    
    # Agregamos los campos de la PRIMERA FACTURA para consolidar los datos financieros.
    if all_invoices:
        first_invoice = all_invoices[0]
        invoice_data = {
            'tipo_documento': 'BL_FACTURA',
            'incoterm': first_invoice.get('incoterm'),
            'valor_factura': first_invoice.get('total_value'),
            'moneda': first_invoice.get('currency'),
            # Usar valores de BL para FOB/CIF si no están en la factura, o los totales de factura
            'valor_fob': first_invoice.get('total_value') if first_invoice.get('incoterm') == 'FOB' else None,
            'valor_cif': first_invoice.get('total_value') if first_invoice.get('incoterm') == 'CIF' else None,
        }
        
        # Lógica simple para completar FOB/CIF si solo se extrajo uno de ellos
        freight = safe_float(bl_data.get('freight_cost', 0))
        insurance_rate = 0.015
        
        if invoice_data.get('incoterm') == 'FOB' and invoice_data['valor_fob'] is not None:
             fob = safe_float(invoice_data['valor_fob'])
             invoice_data['valor_cif'] = fob + freight + (fob * insurance_rate)
        elif invoice_data.get('incoterm') == 'CIF' and invoice_data['valor_cif'] is not None:
             cif = safe_float(invoice_data['valor_cif'])
             # Esta es una simplificación, ya que el cálculo real es más complejo
             invoice_data['valor_fob'] = cif / (1 + insurance_rate) - freight # Aproximación
        
        final_doc = {**base_data, **invoice_data}
        return [final_doc]
        
    return []

# Interfaz Principal
def main():
    initialize_session_state()

    st.title("Asistente de Importaciones Inteligente con Validación Total")
    
    # Obtener gestores
    session_manager = get_session_manager()
    template_manager = get_template_manager()
    
    # BARRA LATERAL (Carga de Archivos y Control General)
    with st.sidebar:
        st.image("https://storage.googleapis.com/gweb-cloudblog-publish/images/Gemini_logo_2023.width-1000.format-webp.webp", caption="Impulsado por Gemini", width=150)
        
        st.header("1. Documentos de Importación")
        # Campos de carga
        bl_file = st.file_uploader("Bill of Lading (BL)", type="pdf")
        invoice_files = st.file_uploader("Facturas Comerciales", type="pdf", accept_multiple_files=True)
        
        st.divider()
        
        # Carga del Catálogo Arancelario
        st.header("2. Gestión de Catálogos")
        catalog_file = st.file_uploader(
            "Cargar Catálogo Arancelario (.xlsx, .csv)", 
            type=["xlsx", "csv"], 
            key="catalog_uploader"
        )

        if catalog_file:
            try:
                catalog_manager = get_catalog_manager()
                
                # Cargar el DataFrame
                if catalog_file.name.lower().endswith('.csv'):
                    # Intentar leer CSV con diferentes delimitadores y encodings si falla
                    df_catalog = pd.read_csv(catalog_file, encoding='utf-8')
                else: 
                    # Leer Excel
                    xls = pd.ExcelFile(catalog_file)
                    sheet_names = xls.sheet_names
                    # Priorizar hojas con nombres clave
                    best_sheet_name = next((s for s in sheet_names if any(p in s.upper() for p in ['CATALOGO', 'ARANCEL', 'CLASIFICACION', 'PRODUCTOS'])), sheet_names[0])
                    df_catalog = pd.read_excel(xls, sheet_name=best_sheet_name)
                    
                if not df_catalog.empty:
                    
                    # LÓGICA DE DETECCIÓN INTELIGENTE DE COLUMNAS
                    REQUIRED_FIELDS_KEYWORDS = {
                        'Descripción Producto (Español)': ['descripcion', 'producto', 'articulo', 'item', 'nombre'], 
                        'Posicion_Arancelaria': ['posicion', 'arancel', 'clasificacion', 'codigo', 'partida']
                    }
                    
                    column_mapping = find_best_column_match(df_catalog.columns.tolist(), REQUIRED_FIELDS_KEYWORDS)
                    
                    desc_col_final = column_mapping.get('Descripción Producto (Español)')
                    arancel_col_final = column_mapping.get('Posicion_Arancelaria')

                    if not desc_col_final or not arancel_col_final:
                        # Fallo en la detección
                        st.error(f"""
                            No se pudo identificar automáticamente las columnas requeridas para el catálogo.
                            Asegúrese de que el archivo contenga encabezados con palabras clave como:
                            - **Descripción**: {', '.join(REQUIRED_FIELDS_KEYWORDS['Descripción Producto (Español)'])}
                            - **Arancel**: {', '.join(REQUIRED_FIELDS_KEYWORDS['Posicion_Arancelaria'])}
                            Columnas detectadas: {df_catalog.columns.tolist()}
                        """)
                    else:
                        st.info(f"""
                            Columnas mapeadas exitosamente: 
                            Descripción: '{desc_col_final}' 
                            Arancel: '{arancel_col_final}'
                        """)
                        
                        # Usar los nombres de columna detectados en lugar de los nombres fijos
                        catalog_manager.load_catalog_from_df(
                            df_catalog, 
                            desc_col=desc_col_final, 
                            arancel_col=arancel_col_final
                        )
                        st.success(f"Catálogo cargado/actualizado con {len(catalog_manager.get_all_entries())} entradas.")
                
            except Exception as e:
                st.error(f"Error cargando catálogo: {e}")
                st.code(f"Asegúrese que los archivos CSV/Excel tengan el formato correcto. {traceback.format_exc()}")
        
        st.divider()

        # Botón de reinicio (siempre visible en la barra lateral)
        if st.button("Reiniciar Proceso", use_container_width=True):
            reset_process()

    # Interfaz Principal (Tabs)
    
    # Define las pestañas
    tabs_list = ["1. Extracción y Validación", "2. Generación de Reporte", "3. Generar Factura de Venta", "Gestión de Sesiones"]
    
    # Lógica de forzado de pestaña ELIMINADA (Incompatible)
    if st.session_state.get('invoice_generation_success'):
        tabs_list[2] = "Factura Generada"
    
    # Renderizar las pestañas (CORRECCIÓN CRÍTICA: SOLO PASAR titles_list)
    tab_titles = st.tabs(tabs_list) 
    tab1, tab2, tab3, tab4 = tab_titles # Desempaquetar los contenedores

    
    # Contenido de Pestañas

    # PESTAÑA 1: Extracción y Validación
    with tab1:
        if st.session_state.step == "upload":
            st.subheader("Fase Inicial: Cargar y Analizar")
            st.markdown("Por favor, cargue los archivos **BL** y **Facturas Comerciales** en la barra lateral y haga clic en 'Extraer Datos'.")
            st.divider()
            
            if bl_file and invoice_files:
                if st.button("Extraer Datos para Validación", use_container_width=True, type="primary"):
                    
                    api_key = os.getenv("GOOGLE_API_KEY")
                    if not api_key:
                         api_key = st.secrets.get("GOOGLE_API_KEY")

                    if not api_key or "AQUÍ_VA_TU_CLAVE" in api_key:
                        st.error("Error: Google API Key no configurada. Asegúrese de tener un archivo .env con GOOGLE_API_KEY.", icon="🔑")
                        st.stop()
                    
                    with st.spinner("Analizando documentos con Gemini..."):
                        try:
                            bl_bytes = io.BytesIO(bl_file.getvalue())
                            inv_bytes_list = [io.BytesIO(f.getvalue()) for f in invoice_files]
                            
                            st.session_state.invoice_file_names = [f.name for f in invoice_files]
                            
                            bl_data, invoices_data = process_documents(bl_bytes, inv_bytes_list, api_key)
                            
                            if bl_data.get("error") or (invoices_data and invoices_data[0].get("error")):
                                st.error(f"Error en la IA: {bl_data.get('error') or invoices_data[0].get('error')}")
                            else:
                                st.session_state.raw_data = {'bl_data': bl_data, 'all_invoices_data': invoices_data}
                                # Inicializar validated_data con raw_data
                                st.session_state.validated_data = st.session_state.raw_data
                                st.session_state.step = "validate"
                                st.rerun()
                        except Exception as e:
                            st.error(f"Ocurrió un error crítico: {e}")
                            st.code(traceback.format_exc())
            else:
                st.info("Esperando la carga de archivos. Necesita un BL y al menos una factura.")
        
      
        elif st.session_state.step == "validate":
            st.subheader("Paso 1: Validar y Corregir TODOS los Datos Extraídos")
            st.warning("**Control Total:** Todos los campos son editables. ¡Corrija cualquier error antes de finalizar!.")
            st.divider()
            
            if st.session_state.validated_data:

                if 'widgets_initialized' not in st.session_state:
                    _load_validated_data_to_widgets_state(st.session_state.validated_data)
                    st.session_state.widgets_initialized = True
                
                # La data de partida para la edición es la última data validada
                data_to_edit = st.session_state.validated_data
                bl_data = data_to_edit['bl_data']
                invoices_data = data_to_edit['all_invoices_data']
                invoice_names = st.session_state.invoice_file_names
                
                
                # Sección 1: Datos Generales (BL)
                st.markdown("#### Datos del Bill of Lading (Editable)")
                
                col1, col2, col3 = st.columns(3)
                
                # Edición de BL: USAR st.session_state[KEY] como valor por defecto/inicial
                edited_bl_number = col1.text_input("Número de BL", key="edit_bl_num")
                edited_booking_number = col2.text_input("Número de Booking", key="edit_booking_num")
                
                edited_freight_cost = col3.number_input(
                    "Costo de Flete (USD)", 
                    min_value=0.0,
                    format="%.2f",
                    key="edit_freight_cost"
                )
                
                st.markdown("---")
                
                col4, col5, col6 = st.columns(3)
                edited_port_of_loading = col4.text_input("Puerto de Origen (POL)", key="edit_pol")
                edited_port_of_discharge = col5.text_input("Puerto de Destino (POD)", key="edit_pod")
                edited_cargo_type = col6.text_input("Tipo de Carga (FCL/LCL)", key="edit_cargo_type")

                st.markdown("---")
                
                col7, col8, col9 = st.columns(3)
                edited_container_no = col7.text_input("Nº de Contenedor", key="edit_container_no")
                
                edited_packages_count = col8.number_input(
                    "Bultos Totales", 
                    min_value=0,
                    format="%d",
                    key="edit_packages_count"
                )
                edited_gross_weight = col9.number_input(
                    "Peso Bruto (Kg)", 
                    min_value=0.0,
                    format="%.2f",
                    key="edit_gross_weight"
                )

                st.markdown("---")

                # Fila 4: Partes
                colA, colB = st.columns(2)
                
                colA.markdown("**Exportador (Editable)**")
                edited_exporter_name = colA.text_area("Nombre Exportador", key="exporter_name_ref", height=50)
                edited_exporter_address = colA.text_area("Dirección Exportador", key="exporter_address_edit", height=100)
                
                colB.markdown("**Consignatario (Editable)**")
                edited_consignee_name = colB.text_area("Nombre Consignatario", key="consignee_name_ref", height=50)
                edited_consignee_address = colB.text_area("Dirección Consignatario", key="consignee_address_edit", height=100)
                
                exporter_details = bl_data.get('exporter_details', bl_data.get('exporter', {}))
                consignee_details = bl_data.get('consignee_details', bl_data.get('consignee', {}))

                # FIN DE EDICIÓN DE BL


                st.markdown("---")
                st.markdown("#### Detalles por Factura (Edición de Metadatos e Ítems)")
                
                edited_invoices = []
                # Edición por cada factura
                for i, inv in enumerate(invoices_data):
                    file_name_display = ""
                    if i < len(invoice_names):
                        file_name_display = f" (Archivo: **{invoice_names[i]}**)"
                        
                    st.markdown(f"##### Factura #{i+1}{file_name_display}")
                    
                    colInv1, colInv2, colInv3, colInv4 = st.columns(4)

                    incoterm_options = ["FOB", "CIF", "EXW", "CFR", "DAP", "DDP", "NOT_FOUND"]
                    current_incoterm_val = st.session_state.get(f"incoterm_{i}") # Valor desde session_state
                    if current_incoterm_val not in incoterm_options:
                        incoterm_options.append(current_incoterm_val)
                    
                    edited_incoterm = colInv1.selectbox(
                        "Incoterm (Clave de Cálculo)", 
                        options=incoterm_options,
                        key=f"incoterm_{i}"
                    )
                    
                    edited_invoice_number = colInv2.text_input("Nº de Factura", key=f"inv_num_{i}")
                    edited_invoice_date = colInv3.text_input("Fecha de Emisión", key=f"inv_date_{i}", help="Formato sugerido: YYYY-MM-DD")
                    edited_currency = colInv4.text_input("Moneda", key=f"inv_curr_{i}")

                    edited_total_value = st.number_input(
                        f"Valor Total de la Factura (Moneda: {edited_currency})",
                        min_value=0.0,
                        format="%.2f",
                        key=f"total_val_{i}"
                    )
                    
                    st.markdown("**Tabla de Ítems (Corrija cantidades, precios y descripciones):**")
                    # Tabla de Ítems (Corrija cantidades, precios y descripciones)
                    
                    # Se usa una clave para el widget y otra para nuestro DataFrame en el estado.
                    df_state_key = f"invoice_df_{i}"
                    editor_key = f"items_editor_{i}"

                    # Inicializamos nuestro DataFrame en el estado la primera vez.
                    if df_state_key not in st.session_state:
                        st.session_state[df_state_key] = pd.DataFrame(inv.get('items', []))
                         
                    column_config = {
                        "description": st.column_config.TextColumn("Descripción Original (Edición)", width="large", disabled=True),
                        "description_es": st.column_config.TextColumn("Descripción Traducida (Español)", width="large"),
                        "part_number": st.column_config.TextColumn("Part Number", required=False),
                        "quantity": st.column_config.NumberColumn("Cantidad", format="%d", min_value=0),
                        "unit_price": st.column_config.NumberColumn("Precio Unitario", format="$%.2f", min_value=0.0),
                        "total_price": st.column_config.NumberColumn("Precio Total (Factura)", format="$%.2f", disabled=True), 
                        "description_original": st.column_config.TextColumn("Descripción Original", disabled=True),
                        "fob_value": st.column_config.NumberColumn("FOB (Calculado)", disabled=True),
                        "freight_proportional": st.column_config.NumberColumn("Flete Prorr. (Calculado)", disabled=True),
                        "insurance_calculated": st.column_config.NumberColumn("Seguro (Calculado)", disabled=True),
                        "cif_value_corrected": st.column_config.NumberColumn("CIF (Corregido)", disabled=True),
                    }
                    
                    # Mostramos el editor CON nuestro DataFrame y guardamos el resultado de la edición 
                    # INMEDIATAMENTE de vuelta en nuestro estado. Este es el ciclo correcto.
                    st.session_state[df_state_key] = st.data_editor(
                        st.session_state[df_state_key], 
                        key=editor_key, 
                        num_rows="dynamic",
                        column_config=column_config,
                        use_container_width=True
                    )
                    
                    
                    # Guardamos el resultado de la edición de vuelta en el estado
                    
                    # Actualizar la factura con los datos de los widgets
                    inv['incoterm'] = st.session_state[f"incoterm_{i}"]
                    inv['invoice_number'] = st.session_state[f"inv_num_{i}"]
                    inv['invoice_date'] = st.session_state[f"inv_date_{i}"]
                    inv['currency'] = st.session_state[f"inv_curr_{i}"]
                    inv['total_value'] = st.session_state[f"total_val_{i}"]
                    # Usamos nuestro DataFrame del estado para la consolidación final
                    inv['items'] = st.session_state[df_state_key].to_dict('records')
                    edited_invoices.append(inv)
                    st.markdown("---")

                
                # Consolidar datos validados (Esto se ejecuta en cada rerun, manteniendo la persistencia)
                validated_bl = {
                    'bl_number': st.session_state.edit_bl_num, 'booking_number': st.session_state.edit_booking_num, 
                    'container_no': st.session_state.edit_container_no, 'freight_cost': st.session_state.edit_freight_cost, 
                    'port_of_loading': st.session_state.edit_pol, 'port_of_discharge': st.session_state.edit_pod,
                    'cargo_type': st.session_state.edit_cargo_type, 'packages_count': st.session_state.edit_packages_count, 
                    'gross_weight': st.session_state.edit_gross_weight,
                    'exporter_details': {'name': st.session_state.exporter_name_ref, 'address': st.session_state.exporter_address_edit},
                    'consignee_details': {'name': st.session_state.consignee_name_ref, 'address': st.session_state.consignee_address_edit},
                }
                st.session_state.validated_data = {'bl_data': validated_bl, 'all_invoices_data': edited_invoices}
                
                st.success("Datos Validados. Proceda a la Pestaña '2. Generación de Reporte'.")
                
            else:
                 st.error("No hay datos cargados para validar.")

    with tab2:
        st.subheader("Paso 2: Generación de Reporte")
        if st.session_state.get('validated_data'):
            st.markdown("#### 1. Reporte Adicional (AFORO / DEVA)")
            if st.button("Generar Reporte AFORO/DEVA", key="gen_aforo_deva", type="primary"):
                with st.spinner("Generando Excel AFORO/DEVA..."):
                    
                    # Llamar a la función de prorrateo ANTES de generar el reporte
                    st.session_state.validated_data = calculate_prorated_freight(st.session_state.validated_data)

                    excel_bytes = create_final_excel_report(st.session_state.validated_data['bl_data'], st.session_state.validated_data['all_invoices_data'], get_catalog_manager())
                    st.session_state.excel_output_aforo = excel_bytes
                    st.session_state.last_report_type = "AFORO_DEVA"
            
            if st.session_state.get('excel_output_aforo') and st.session_state.last_report_type == "AFORO_DEVA":
                st.download_button(label="Descargar Reporte AFORO/DEVA", data=st.session_state.excel_output_aforo, file_name=f"Reporte_AFORO_{st.session_state.validated_data['bl_data'].get('bl_number', 'S_N')}.xlsx")
            
            st.markdown("---")
            st.markdown("#### 2. Reportes con Plantillas Avanzadas")
            selected_template_id = template_manager.render_template_selector()
            
            if st.button(f"Generar Reporte con Plantilla", key="gen_custom_report", type="secondary"):

                # Llamar a la función de prorrateo ANTES de generar el reporte
                st.session_state.validated_data = calculate_prorated_freight(st.session_state.validated_data)

                all_processed_data = _consolidate_data_for_template(st.session_state.validated_data)
                if all_processed_data:
                    with st.spinner(f"Generando plantilla..."):
                        excel_bytes_custom = template_manager.create_excel_with_template(all_processed_data, selected_template_id)
                        st.session_state.excel_output_custom = excel_bytes_custom
                        st.session_state.last_report_type = "CUSTOM"
            
            if st.session_state.get('excel_output_custom') and st.session_state.last_report_type == "CUSTOM":
                st.download_button(label="Descargar Reporte Personalizado", data=st.session_state.excel_output_custom, file_name=f"Reporte_Plantilla_{st.session_state.validated_data['bl_data'].get('bl_number', 'S_N')}.xlsx")
        else:
            st.warning("Complete la validación en la Pestaña 1 primero.")

    with tab3:
        if st.session_state.get('invoice_generation_success'):
             invoice_gen.render_invoice_download()
        else:
             invoice_gen.render_invoice_interface()

    with tab4:
        st.header("Gestión de Datos y Sesiones")
        if session_manager:
            if st.session_state.get('validated_data'):
                processed_data_for_session = [st.session_state.raw_data['bl_data'] if st.session_state.raw_data else {}]
                edited_data_for_session = {0: st.session_state.validated_data}
                st.session_state.processed_data = processed_data_for_session 
                st.session_state.edited_data = edited_data_for_session
            session_manager.render_session_manager()
        else:
            st.warning("El gestor de sesiones no está disponible.")

if __name__ == "__main__":
    main()