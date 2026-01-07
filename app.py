import streamlit as st
import pandas as pd
import io
import traceback
import re
import os
from dateutil import parser
from dotenv import load_dotenv

load_dotenv(override=True)

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
            print(f"Error inicializando SessionManager: {e}")
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

# Función para inyectar CSS personalizado
def local_css():
    st.markdown("""
    <style>
        /* Tipografía Global */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }
        
        /* Contenedores Principales - Fondo neutro para soportar Dark/Light */
        .stApp {
            /* Dejar que Streamlit maneje el fondo global */
        }
        
        /* Encabezados - Usar colores de tema o neutros */
        h1, h2, h3 {
            font-family: 'Inter', sans-serif !important;
        }
        
        h1 {
            font-weight: 700 !important;
            padding-bottom: 0.5rem;
            margin-bottom: 2rem;
            border-bottom: 2px solid rgba(128, 128, 128, 0.2);
        }
        
        h2 {
            font-weight: 600 !important;
            margin-top: 1.5rem;
        }

        h3 {
            font-weight: 600 !important;
            border-left: 4px solid #3b82f6; 
            padding-left: 10px;
        }

        /* Estilo de Tarjetas para Secciones - Glassmorphism sutil */
        .stContainer {
            background-color: rgba(128, 128, 128, 0.05); /* Muy sutil, funciona en dark y light */
            padding: 2rem;
            border-radius: 10px;
            border: 1px solid rgba(128, 128, 128, 0.2);
            margin-bottom: 1.5rem;
        }

        /* Input Fields styling - Mejorar bordes */
        .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div {
            border-radius: 6px;
        }

        /* Botones Primarios */
        .stButton>button[kind="primary"] {
            background-color: #2563eb;
            color: white;
            border-radius: 8px;
            border: none;
            transition: all 0.3s ease;
        }
        
        .stButton>button[kind="primary"]:hover {
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4);
            transform: translateY(-1px);
        }

        /* Tabs styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            border-radius: 8px;
            padding: 4px;
        }

        .stTabs [data-baseweb="tab"] {
            height: 48px;
            white-space: pre-wrap;
            border-radius: 6px;
            font-weight: 500;
        }

        /* Mensajes de Alerta */
        .stSuccess, .stInfo, .stWarning, .stError {
            border-radius: 8px;
            padding: 1rem;
            border: 1px solid rgba(128, 128, 128, 0.2);
        }
        
        /* Ajuste para el texto dentro de los contenedores blancos que rompían el dark mode */
        /* Eliminamos selectores específicos de color de texto para heredar del tema */

    </style>
    """, unsafe_allow_html=True)

# Interfaz Principal
def main():
    initialize_session_state()
    local_css() # Inyectar estilos


    # Layout de Título Principal con Icono
    col_header, col_logo = st.columns([4, 1])
    with col_header:
        st.title("Asistente de Importaciones")
        st.markdown("**Validación Inteligente & Generación de Reportes**")
    
    # Obtener gestores
    session_manager = get_session_manager()
    template_manager = get_template_manager()
    
    # BARRA LATERAL (Carga de Archivos y Control General)
    with st.sidebar:
        st.markdown("""
            <div style='text-align: center; padding-bottom: 20px;'>
                 <h2 style='font-weight: 800; border:none; margin:0;'>PANEL DE CONTROL</h2>
            </div>
        """, unsafe_allow_html=True)
        # st.image("...", ...) # Placeholder si se quiere logo
        
        with st.expander("Carga de Documentos", expanded=True):
            st.markdown("Cargue los archivos PDF originales aquí.")
            # Campos de carga
            bl_file = st.file_uploader("Bill of Lading (BL)", type="pdf", help="Arrastre el archivo BL aquí")
            invoice_files = st.file_uploader("Facturas Comerciales", type="pdf", accept_multiple_files=True, help="Puede seleccionar múltiples facturas")
        
        st.write("") # Espacio
        
        with st.expander("Catálogo Arancelario", expanded=False):
            # Carga del Catálogo Arancelario
            catalog_file = st.file_uploader(
                "Actualizar Catálogo (.xlsx, .csv)", 
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

        st.markdown(
            "<div style='position: fixed; bottom: 20px; width: 100%; text-align: center; color: #cbd5e1; font-size: 0.8rem;'>Powered by Gemini AI</div>", 
            unsafe_allow_html=True
        )

    # Interfaz Principal (Tabs)
    
    # Define las pestañas
    tabs_list = ["Validación de Datos", "Generación de Reportes", "Facturación", "Sesiones"]
    
    # Lógica de forzado de pestaña ELIMINADA (Incompatible)
    if st.session_state.get('invoice_generation_success'):
        tabs_list[2] = "Factura Lista"
    
    # Renderizar las pestañas (CORRECCIÓN CRÍTICA: SOLO PASAR titles_list)
    tab_titles = st.tabs(tabs_list) 
    tab1, tab2, tab3, tab4 = tab_titles # Desempaquetar los contenedores

    
    # Contenido de Pestañas

    # PESTAÑA 1: Extracción y Validación
    with tab1:
        st.write("") # Spacer
        if st.session_state.step == "upload":
            # EMPTY STATE - Diseño profesional
            with st.container():
                st.markdown("""
                <div class="stContainer" style="text-align: center; margin-top: 20px;">
                    <h3 style="border:none;">Bienvenido al Asistente de Importaciones</h3>
                    <p style="font-size: 1.1rem; opacity: 0.8;">Para comenzar, cargue sus documentos PDF desde el panel lateral izquierdo.</p>
                </div>
                """, unsafe_allow_html=True)

            if bl_file and invoice_files:
                col_action_1, col_action_2, col_action_3 = st.columns([1,2,1])
                with col_action_2:
                    st.write("")
                    if st.button("Iniciar Extracción con IA", use_container_width=True, type="primary"):
                        
                        api_key = os.getenv("GOOGLE_API_KEY")
                        if not api_key:
                             api_key = st.secrets.get("GOOGLE_API_KEY")

                        if not api_key or "AQUÍ_VA_TU_CLAVE" in api_key:
                            st.error("Error: Google API Key no configurada. Asegúrese de tener un archivo .env con GOOGLE_API_KEY.")
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
            
            # Header de sección
            col_msg, col_status = st.columns([3, 1])
            with col_msg:
                st.info("Tips: Edite los campos directamente. Los cálculos se actualizarán automáticamente al generar el reporte.")
            with col_status:
                st.write("") # Spacer

            
            if st.session_state.validated_data:

                if 'widgets_initialized' not in st.session_state:
                    _load_validated_data_to_widgets_state(st.session_state.validated_data)
                    st.session_state.widgets_initialized = True
                
                # ...
                data_to_edit = st.session_state.validated_data
                bl_data = data_to_edit['bl_data']
                invoices_data = data_to_edit['all_invoices_data']
                invoice_names = st.session_state.invoice_file_names
                
                
                # --- CARD: DATOS DEL BL ---
                with st.container():
                     st.markdown('<div class="stContainer">', unsafe_allow_html=True)
                     st.subheader("Datos del Bill of Lading (BL)")
                     
                     col1, col2, col3 = st.columns(3)
                     
                     with col1:
                         st.markdown("**Identificación**")
                         edited_bl_number = st.text_input("Número de BL", key="edit_bl_num")
                         edited_booking_number = st.text_input("Número de Booking", key="edit_booking_num")
                     
                     with col2:
                         st.markdown("**Ruta y Carga**")
                         c2a, c2b = st.columns(2)
                         with c2a:
                            edited_pol = st.text_input("Origen (POL)", key="edit_pol")
                         with c2b:
                            edited_pod = st.text_input("Destino (POD)", key="edit_pod")
                         edited_cargo_type = st.text_input("Tipo Carga", key="edit_cargo_type")

                     with col3:
                         st.markdown("**Valores Financieros**")
                         edited_freight_cost = st.number_input(
                            "Costo Flete (USD)", 
                            min_value=0.0,
                            format="%.2f",
                            key="edit_freight_cost"
                        )
                     
                     st.markdown("---")
                     
                     col4, col5, col6 = st.columns(3)
                     with col4:
                        edited_container_no = st.text_input("Nº de Contenedor", key="edit_container_no")
                     with col5:
                        edited_packages_count = st.number_input("Bultos Totales", min_value=0, format="%d", key="edit_packages_count")
                     with col6:
                        edited_gross_weight = st.number_input("Peso Bruto (Kg)", min_value=0.0, format="%.2f", key="edit_gross_weight")

                     st.markdown("---")

                     # Fila 4: Partes
                     colA, colB = st.columns(2)
                     
                     with colA:
                         st.markdown("**Exportador**")
                         edited_exporter_name = st.text_area("Nombre", key="exporter_name_ref", height=68, label_visibility="collapsed", placeholder="Nombre Exportador")
                         edited_exporter_address = st.text_area("Dirección", key="exporter_address_edit", height=80, label_visibility="collapsed", placeholder="Dirección Exportador")
                     
                     with colB:
                         st.markdown("**Consignatario**")
                         edited_consignee_name = st.text_area("Nombre", key="consignee_name_ref", height=68, label_visibility="collapsed", placeholder="Nombre Consignatario")
                         edited_consignee_address = st.text_area("Dirección", key="consignee_address_edit", height=80, label_visibility="collapsed", placeholder="Dirección Consignatario")
                     
                     st.markdown('</div>', unsafe_allow_html=True)
                
                # FIN DE EDICIÓN DE BL


                st.write("") # Spacer

                # --- CARD: FACTURAS ---
                st.subheader("Detalles por Factura")
                
                edited_invoices = []
                # Edición por cada factura
                for i, inv in enumerate(invoices_data):
                    file_name_display = ""
                    if i < len(invoice_names):
                        file_name_display = f" - {invoice_names[i]}"
                    
                    with st.expander(f"Factura #{i+1}{file_name_display}", expanded=True):
                        
                        colInv1, colInv2, colInv3, colInv4 = st.columns(4)

                        incoterm_options = ["FOB", "CIF", "EXW", "CFR", "DAP", "DDP", "NOT_FOUND"]
                        current_incoterm_val = st.session_state.get(f"incoterm_{i}") # Valor desde session_state
                        if current_incoterm_val not in incoterm_options:
                            incoterm_options.append(current_incoterm_val)
                        
                        with colInv1:
                            edited_incoterm = st.selectbox("Incoterm", options=incoterm_options, key=f"incoterm_{i}")
                        with colInv2:
                            edited_invoice_number = st.text_input("Nº de Factura", key=f"inv_num_{i}")
                        with colInv3:
                            edited_invoice_date = st.text_input("Fecha", key=f"inv_date_{i}", help="YYYY-MM-DD")
                        with colInv4:
                            edited_currency = st.text_input("Moneda", key=f"inv_curr_{i}")
                        
                        # Use metrics for Total Value for better visualization
                        st.markdown("---")
                        c_val, c_editor = st.columns([1, 4])
                        
                        with c_val:
                            st.caption("Valor Total Declarado")
                            edited_total_value = st.number_input(
                                "Total",
                                min_value=0.0,
                                format="%.2f",
                                key=f"total_val_{i}",
                                label_visibility="collapsed"
                            )
                        
                        with c_editor:
                            st.caption(f"Detalle de Ítems ({inv.get('currency', 'USD')})")
                            
                            # Se usa una clave para el widget y otra para nuestro DataFrame en el estado.
                            df_state_key = f"invoice_df_{i}"
                            editor_key = f"items_editor_{i}"

                            # Inicializamos nuestro DataFrame en el estado la primera vez.
                            if df_state_key not in st.session_state:
                                st.session_state[df_state_key] = pd.DataFrame(inv.get('items', []))
                                
                            column_config = {
                                "description": st.column_config.TextColumn("Descripción Original", width="medium", disabled=True),
                                "description_es": st.column_config.TextColumn("Descripción (ES) - Editable", width="medium"),
                                "part_number": st.column_config.TextColumn("PN", required=False, width="small"),
                                "quantity": st.column_config.NumberColumn("Cant.", format="%d", min_value=0, width="small"),
                                "unit_price": st.column_config.NumberColumn("P. Unit", format="$%.2f", min_value=0.0, width="small"),
                                "total_price": st.column_config.NumberColumn("Total", format="$%.2f", disabled=True, width="small"), 
                                "description_original": st.column_config.TextColumn("Desc. Orig", disabled=True),
                                "fob_value": st.column_config.NumberColumn("FOB", disabled=True),
                                "freight_proportional": st.column_config.NumberColumn("Flete Prorr.", disabled=True),
                                "insurance_calculated": st.column_config.NumberColumn("Seguro", disabled=True),
                                "cif_value_corrected": st.column_config.NumberColumn("CIF", disabled=True),
                            }
                            
                            # Mostramos el editor CON nuestro DataFrame y guardamos el resultado de la edición 
                            # INMEDIATAMENTE de vuelta en nuestro estado. Este es el ciclo correcto.
                            st.session_state[df_state_key] = st.data_editor(
                                st.session_state[df_state_key], 
                                key=editor_key, 
                                num_rows="dynamic",
                                column_config=column_config,
                                use_container_width=True,
                                height=200
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
                
                st.success("Datos sincronizados. Validado.")
                
            else:
                 st.error("No hay datos cargados para validar.")

    with tab2:
        st.write("")
        if st.session_state.get('validated_data'):
            
            col_rep_1, col_rep_2 = st.columns(2)
            
            with col_rep_1:
                with st.container():
                    st.markdown('<div class="stContainer">', unsafe_allow_html=True)
                    st.subheader("Reporte Estándar")
                    st.markdown("Genera el reporte **AFORO/DEVA** completo con todas las pestañas reglamentarias.")
                    
                    if st.button("Generar Excel AFORO/DEVA", key="gen_aforo_deva", type="primary", use_container_width=True):
                        with st.spinner("Compilando reporte maestro..."):
                            
                            # Llamar a la función de prorrateo ANTES de generar el reporte
                            st.session_state.validated_data = calculate_prorated_freight(st.session_state.validated_data)

                            excel_bytes = create_final_excel_report(st.session_state.validated_data['bl_data'], st.session_state.validated_data['all_invoices_data'], get_catalog_manager())
                            st.session_state.excel_output_aforo = excel_bytes
                            st.session_state.last_report_type = "AFORO_DEVA"
                    
                    if st.session_state.get('excel_output_aforo') and st.session_state.last_report_type == "AFORO_DEVA":
                        st.write("")
                        st.download_button(
                            label="Descargar Resultado", 
                            data=st.session_state.excel_output_aforo, 
                            file_name=f"Reporte_AFORO_{st.session_state.validated_data['bl_data'].get('bl_number', 'S_N')}.xlsx",
                            use_container_width=True
                        )
                    st.markdown('</div>', unsafe_allow_html=True)
            
            with col_rep_2:
                with st.container():
                     st.markdown('<div class="stContainer">', unsafe_allow_html=True)
                     st.subheader("Reporte Personalizado")
                     st.markdown("Utilice plantillas predefinidas para salidas específicas.")
                     
                     selected_template_id = template_manager.render_template_selector()
                     st.write("")
                     if st.button(f"Generar desde Plantilla", key="gen_custom_report", type="secondary", use_container_width=True):

                        # Llamar a la función de prorrateo ANTES de generar el reporte
                        st.session_state.validated_data = calculate_prorated_freight(st.session_state.validated_data)

                        all_processed_data = _consolidate_data_for_template(st.session_state.validated_data)
                        if all_processed_data:
                            with st.spinner(f"Aplicando plantilla..."):
                                excel_bytes_custom = template_manager.create_excel_with_template(all_processed_data, selected_template_id)
                                st.session_state.excel_output_custom = excel_bytes_custom
                                st.session_state.last_report_type = "CUSTOM"
                    
                     if st.session_state.get('excel_output_custom') and st.session_state.last_report_type == "CUSTOM":
                        st.write("")
                        st.download_button(
                            label="Descargar Plantilla", 
                            data=st.session_state.excel_output_custom, 
                            file_name=f"Reporte_Plantilla_{st.session_state.validated_data['bl_data'].get('bl_number', 'S_N')}.xlsx",
                            use_container_width=True
                        )
                     st.markdown('</div>', unsafe_allow_html=True)

        else:
            st.warning("Primero complete la validación en la pestaña anterior.")

    with tab3:
        st.write("")
        if st.session_state.get('invoice_generation_success'):
             invoice_gen.render_invoice_download()
        else:
             with st.container():
                # Wrapper para el generador de facturas para darle estilo si es necesario
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