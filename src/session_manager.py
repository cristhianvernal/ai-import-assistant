import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from typing import Dict, Any, List, Optional, Tuple
import streamlit as st
from datetime import datetime
import uuid
import traceback 

class SessionManager:
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        if not self.database_url:
            # Lanza ValueError para que app.py pueda manejar la falta de la variable de entorno.
            raise ValueError("DATABASE_URL no está configurada")
        
        # Initialize database tables
        self._initialize_database()
    
    def _get_connection(self):
        """Get database connection"""
        return psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
    
    def _initialize_database(self):
        """Create necessary tables if they don't exist"""

        create_tables_sql = """
        -- Enable UUID extension if not exists
        CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
        
        CREATE TABLE IF NOT EXISTS work_sessions (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            session_name VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_notes TEXT,
            total_documents INTEGER DEFAULT 0,
            documents_with_errors INTEGER DEFAULT 0,
            processing_status VARCHAR(50) DEFAULT 'in_progress',
            session_data JSONB NOT NULL
        );
        
        CREATE TABLE IF NOT EXISTS session_documents (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            session_id UUID REFERENCES work_sessions(id) ON DELETE CASCADE,
            document_index INTEGER NOT NULL,
            filename VARCHAR(500),
            original_data JSONB NOT NULL,
            edited_data JSONB,
            validation_status VARCHAR(50) DEFAULT 'pending',
            error_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON work_sessions(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_session_documents_session_id ON session_documents(session_id);
        """
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(create_tables_sql)
                    conn.commit()
        except Exception as e:
            # Re-raise the exception to properly handle initialization failure
            raise Exception(f"Error inicializando base de datos: {str(e)}")

    
    def save_session(self, 
                    session_name: str,
                    # ADVERTENCIA: Aquí esperamos que processed_data contenga el BL original
                    processed_data: List[Dict[str, Any]], 
                    # ADVERTENCIA: Aquí esperamos que edited_data contenga el BL editado en el índice 0
                    edited_data: Dict[int, Dict[str, Any]], 
                    user_notes: str = "",
                    processing_status: str = "completed") -> str:
        """Save a work session to database"""
        
        try:
            session_id = str(uuid.uuid4())
            
            # Ajuste para el flujo: solo un "documento" (el BL consolidado)
            total_documents = len(processed_data)
            documents_with_errors = 0 
            
            # Asumimos que si hay datos editados, el documento fue "corregido"
            if len(edited_data) > 0:
                documents_with_errors = 0 
            else:
                 # Simplemente un contador de errores si hubiera habido en el BL original
                 documents_with_errors = 1 if processed_data and processed_data[0].get('error') else 0

            # Preparar session metadata
            session_metadata = {
                'total_documents': total_documents,
                'documents_with_errors': documents_with_errors,
                'edited_count': len(edited_data),
                'timestamp': datetime.now().isoformat(),
                'processing_complete': True,
                'validation_mode': len(edited_data) > 0,
                # Clave para saber qué cargar: Si se guardó data consolidada BL/Facturas, lo marcamos.
                'consolidated_flow': True 
            }
            
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Insert main session record
                    cursor.execute("""
                        INSERT INTO work_sessions 
                        (id, session_name, user_notes, total_documents, documents_with_errors, processing_status, session_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        session_id,
                        session_name,
                        user_notes,
                        total_documents,
                        documents_with_errors,
                        processing_status,
                        Json(session_metadata)
                    ))
                    
                    # Insert document records (solo el BL consolidado y su edición)
                    # En el flujo actual de app.py, 'processed_data' = [bl_data_original]
                    # y 'edited_data' = {0: bl_data_validado}
                    for doc_index, doc_data in enumerate(processed_data):
                        filename = doc_data.get('bl_number', f'Documento_{doc_index + 1}')
                        edited_doc_data = edited_data.get(doc_index)
                        
                        error_count = documents_with_errors
                        validation_status = 'edited' if edited_doc_data else 'original'
                        
                        doc_id = str(uuid.uuid4())
                        cursor.execute("""
                            INSERT INTO session_documents 
                            (id, session_id, document_index, filename, original_data, edited_data, validation_status, error_count)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            doc_id,
                            session_id,
                            doc_index,
                            filename,
                            # NOTA IMPORTANTE: original_data no incluye las facturas, pero edited_data
                            # debe contener el bl_data Y la lista de all_invoices_data para cargarlo bien.
                            # Para este flujo específico, solo guardamos el BL y usamos edited_data
                            # para guardar la data completa (BL + Facturas)
                            Json(doc_data), 
                            Json(edited_doc_data) if edited_doc_data else None,
                            validation_status,
                            error_count
                        ))
                    
                    conn.commit()
            
            return session_id
            
        except Exception as e:
            # st.error(f"Error guardando sesión: {str(e)}")
            print(f"Error guardando sesión: {traceback.format_exc()}")
            return ""

    
    def get_saved_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            id,
                            session_name,
                            created_at,
                            updated_at,
                            user_notes,
                            total_documents,
                            documents_with_errors,
                            processing_status,
                            session_data
                        FROM work_sessions 
                        ORDER BY updated_at DESC 
                        LIMIT %s
                    """, (limit,))
                    
                    sessions = []
                    for row in cursor.fetchall():
                        row_dict = dict(row)
                        session_data = row_dict.get('session_data', {}) if isinstance(row_dict.get('session_data'), dict) else {}
                        
                        sessions.append({
                            'id': row_dict['id'],
                            'session_name': row_dict['session_name'],
                            'created_at': row_dict['created_at'],
                            'updated_at': row_dict['updated_at'],
                            'user_notes': row_dict['user_notes'],
                            'total_documents': row_dict['total_documents'],
                            'documents_with_errors': row_dict['documents_with_errors'],
                            'processing_status': row_dict['processing_status'],
                            'metadata': session_data
                        })
                    
                    return sessions
        
        except Exception as e:
            # st.error(f"Error cargando sesiones: {str(e)}")
            print(f"Error cargando sesiones: {traceback.format_exc()}")
            return []
    
    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Carga una sesión. En este flujo, devuelve el diccionario consolidado
        que se guardó en edited_data (el diccionario 'validated_data').
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Get session metadata
                    cursor.execute("""
                        SELECT session_name, user_notes, session_data
                        FROM work_sessions 
                        WHERE id = %s
                    """, (session_id,))
                    
                    session_row = cursor.fetchone()
                    if not session_row:
                        return None
                    
                    # Get session documents
                    # Para el flujo de importaciones, solo esperamos un doc con edited_data
                    cursor.execute("""
                        SELECT edited_data
                        FROM session_documents 
                        WHERE session_id = %s 
                        ORDER BY document_index
                        LIMIT 1
                    """, (session_id,))
                    
                    doc_row = cursor.fetchone()
                    
                    if not doc_row or not doc_row['edited_data']:
                        # Si no hay edited_data, intentamos cargar original_data
                        cursor.execute("""
                            SELECT original_data
                            FROM session_documents 
                            WHERE session_id = %s 
                            ORDER BY document_index
                            LIMIT 1
                        """, (session_id,))
                        doc_row = cursor.fetchone()
                        
                        if not doc_row or not doc_row['original_data']:
                             return None

                        # En este caso, solo cargamos la estructura base del BL
                        bl_data_original = doc_row['original_data'] if isinstance(doc_row['original_data'], dict) else {}
                        return {'bl_data': bl_data_original, 'all_invoices_data': []} # Estructura incompleta

                    # La clave 'edited_data' en este flujo CONTIENE la data consolidada (BL + Facturas)
                    validated_data_structure = doc_row['edited_data'] if isinstance(doc_row['edited_data'], dict) else {}
                    
                    # Session metadata
                    session_row_dict = dict(session_row)
                    session_metadata = {
                        'session_name': session_row_dict['session_name'],
                        'user_notes': session_row_dict['user_notes'],
                        'session_data': session_row_dict.get('session_data', {})
                    }
                    
                    # Devolvemos la estructura validada completa
                    return validated_data_structure
        
        except Exception as e:
            # st.error(f"Error cargando sesión: {str(e)}")
            print(f"Error cargando sesión: {traceback.format_exc()}")
            return None
    
    def delete_session(self, session_id: str) -> bool:

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # ON DELETE CASCADE se encarga de session_documents
                    cursor.execute("DELETE FROM work_sessions WHERE id = %s", (session_id,))
                    conn.commit()
                    return True
        
        except Exception as e:
            # st.error(f"Error eliminando sesión: {str(e)}")
            print(f"Error eliminando sesión: {traceback.format_exc()}")
            return False
    
    def update_session_notes(self, session_id: str, user_notes: str) -> bool:

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE work_sessions 
                        SET user_notes = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (user_notes, session_id))
                    conn.commit()
                    return True
        
        except Exception as e:
            # st.error(f"Error actualizando notas: {str(e)}")
            print(f"Error actualizando notas: {traceback.format_exc()}")
            return False
    
    def get_session_statistics(self) -> Dict[str, Any]:

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Get basic statistics
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total_sessions,
                            SUM(total_documents) as total_documents_processed,
                            SUM(documents_with_errors) as total_documents_with_errors,
                            AVG(total_documents) as avg_documents_per_session,
                            MAX(created_at) as last_session_date
                        FROM work_sessions
                    """)
                    
                    stats = cursor.fetchone()
                    
                    # Get sessions by status
                    cursor.execute("""
                        SELECT processing_status, COUNT(*) as count
                        FROM work_sessions 
                        GROUP BY processing_status
                    """)
                    
                    status_counts = {dict(row)['processing_status']: dict(row)['count'] for row in cursor.fetchall()}
                    
                    # Get recent activity (last 30 days)
                    cursor.execute("""
                        SELECT COUNT(*) as recent_sessions
                        FROM work_sessions 
                        WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
                    """)
                    
                    recent_stats = cursor.fetchone()
                    
                    stats_dict = dict(stats) if stats else {}
                    recent_dict = dict(recent_stats) if recent_stats else {}
                    
                    return {
                        'total_sessions': stats_dict.get('total_sessions', 0) or 0,
                        'total_documents_processed': stats_dict.get('total_documents_processed', 0) or 0,
                        'total_documents_with_errors': stats_dict.get('total_documents_with_errors', 0) or 0,
                        'avg_documents_per_session': float(stats_dict.get('avg_documents_per_session', 0) or 0),
                        'last_session_date': stats_dict.get('last_session_date'),
                        'status_distribution': status_counts,
                        'recent_sessions_30d': recent_dict.get('recent_sessions', 0) or 0
                    }
        
        except Exception as e:
            # st.error(f"Error obteniendo estadísticas: {str(e)}")
            print(f"Error obteniendo estadísticas: {traceback.format_exc()}")
            return {}
    
    def render_session_manager(self):

        st.header("Gestión de Sesiones de Trabajo")
        
        tab1, tab2, tab3 = st.tabs(["Guardar Sesión", "Cargar Sesión", "Estadísticas"])
        
        with tab1:
            self._render_save_session()
        
        with tab2:
            self._render_load_session()
        
        with tab3:
            self._render_session_statistics()
    
    def _render_save_session(self):
        """Render save session interface"""
        st.subheader("Guardar Sesión Actual")
        
        # AJUSTE CRÍTICO: Usar validated_data para guardar, si existe
        if not st.session_state.get('validated_data'):
            st.warning("No hay datos validados para guardar. Realice la Extracción y Validación primero.")
            return
        
        # Prepara la data a guardar: Usamos la estructura de un documento (el BL),
        # y guardamos toda la data validada (BL + Facturas) como edited_data.
        
        # Simulamos que 'processed_data' tiene un único documento (el BL)
        processed_data_to_save = [st.session_state.validated_data['bl_data']]
        # Simulamos que 'edited_data' tiene el BL consolidado + facturas en el índice 0
        edited_data_to_save = {0: st.session_state.validated_data}
        
        st.markdown("""
        Guarde su sesión actual (datos de BL y Facturas validados) para poder continuar trabajando más tarde.
        """)
        
        # Session details form
        col1, col2 = st.columns(2)
        
        with col1:
            session_name = st.text_input(
                "Nombre de la Sesión",
                value=f"Sesión_{st.session_state.validated_data['bl_data'].get('bl_number', 'S_N')}_{datetime.now().strftime('%Y%m%d_%H%M')}",
                help="Nombre descriptivo para identificar esta sesión"
            )
        
        with col2:
            processing_status = st.selectbox(
                "Estado del Procesamiento",
                options=["completed", "in_progress", "review_needed"],
                format_func=lambda x: {
                    "completed": "Completado",
                    "in_progress": "En Progreso", 
                    "review_needed": "Necesita Revisión"
                }[x],
                key="save_status_select"
            )
        
        user_notes = st.text_area(
            "Notas (Opcional)",
            help="Agregue notas sobre esta sesión de trabajo",
            height=100,
            key="save_notes_area"
        )
        
        # Session summary
        st.markdown("### Resumen de la Sesión")
        
        total_docs = 1 # Solo 1 documento consolidado
        edited_docs = 1 # Si estamos en validated_data, se ha editado
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Documentos (BL)", total_docs)
        
        with col2:
            st.metric("Facturas Incluidas", len(st.session_state.validated_data.get('all_invoices_data', [])))
        
        with col3:
            st.metric("Estado", "Validado")
        
        if st.button("Guardar Sesión", type="primary", use_container_width=True):
            if not session_name.strip():
                st.error("Debe ingresar un nombre para la sesión")
                return
            
            with st.spinner("💾 Guardando sesión..."):
                session_id = self.save_session(
                    session_name=session_name.strip(),
                    processed_data=processed_data_to_save,
                    edited_data=edited_data_to_save,
                    user_notes=user_notes,
                    processing_status=processing_status
                )
                
                if session_id:
                    st.success(f"Sesión guardada exitosamente con ID: {session_id[:8]}...")
                    st.session_state.current_session_id = session_id
                else:
                    st.error("Error guardando la sesión")
    
    def _render_load_session(self):

        st.subheader("Cargar Sesión Guardada")
        
        sessions = self.get_saved_sessions()
        
        if not sessions:
            st.info("No hay sesiones guardadas aún. Guarde una sesión para poder cargarla aquí.")
            return
        
        st.markdown("### Sesiones Disponibles")
        
        # Create session cards
        for session in sessions:
            # Corrección del error TypeError: se elimina la llamada a len()
            with st.expander(
                f"{session['session_name']} - {session['metadata'].get('edited_count', 0)} Documento(s) Consolidado(s)",
                expanded=False
            ):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Creada:** {session['created_at'].strftime('%d/%m/%Y %H:%M')}")
                    st.write(f"**Actualizada:** {session['updated_at'].strftime('%d/%m/%Y %H:%M')}")
                    # Ya que el flujo consolida, solo mostramos el total de docs procesados (1)
                    st.write(f"**Total documentos:** {session['total_documents']}")
                    st.write(f"**Documentos con errores:** {session['documents_with_errors']}")
                
                with col2:
                    status_emoji = {
                        'completed': '',
                        'in_progress': '',
                        'review_needed': ''
                    }.get(session['processing_status'], '')
                    st.write(f"**Estado:** {status_emoji} {session['processing_status']}")
                    
                    if session['user_notes']:
                        st.write(f"**Notas:** {session['user_notes']}")
                
                # Action buttons
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button(f"Cargar", key=f"load_{session['id']}", use_container_width=True):
                        self._load_session_action(session['id'])
                
                with col2:
                    if st.button(f"Editar Notas", key=f"edit_{session['id']}", use_container_width=True):
                        st.session_state[f"editing_notes_{session['id']}"] = True
                
                with col3:
                    if st.button(f"Eliminar", key=f"delete_{session['id']}", use_container_width=True):
                        # Nota: La doble confirmación aquí se realiza a través de un simple botón,
                        # pero si se presiona dos veces muy rápido podría eliminar. 
                        # Una solución más robusta sería usar un modal o un pop-up de confirmación.
                        if st.session_state.get(f"confirm_delete_{session['id']}", False):
                             self._delete_session_action(session['id'])
                        else:
                            st.session_state[f"confirm_delete_{session['id']}"] = True
                            st.button(f"Confirmar Eliminación", key=f"confirm_delete_btn_{session['id']}", type="secondary")
    
    def _load_session_action(self, session_id: str):
        """Handle session loading action"""
        with st.spinner("Cargando sesión..."):
            # Ahora load_session devuelve directamente la estructura validated_data
            validated_data_structure = self.load_session(session_id)
            
            if validated_data_structure:
                
                # ACTUALIZACIÓN DE ESTADO PARA EL FLUJO PRINCIPAL
                st.session_state.validated_data = validated_data_structure
                st.session_state.raw_data = validated_data_structure # Para consistencia visual
                st.session_state.processing_complete = True
                st.session_state.step = "validate" # Vuelve al paso de validación para revisión
                st.session_state.current_session_id = session_id
                
                st.success(f"Sesión cargada. Vuelva a la Pestaña '1. Extracción y Validación' para revisar y continuar.")
                st.rerun()
            else:
                st.error("Error cargando la sesión. No se encontraron datos validados.")
    
    def _delete_session_action(self, session_id: str):
        with st.spinner("Eliminando sesión..."):
            if self.delete_session(session_id):
                st.success("Sesión eliminada correctamente")
                st.rerun()
            else:
                st.error("Error eliminando la sesión")
    
    def _render_session_statistics(self):

        st.subheader("Estadísticas de Sesiones")
        
        with st.spinner("Cargando estadísticas..."):
            stats = self.get_session_statistics()
        
        if not stats:
            st.warning("No se pudieron cargar las estadísticas")
            return
        
        # Overall metrics
        st.markdown("### Métricas Generales")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Sesiones", stats['total_sessions'])
        
        with col2:
            st.metric("Documentos Procesados", stats['total_documents_processed'])
        
        with col3:
            st.metric("Documentos con Errores", stats['total_documents_with_errors'])
        
        with col4:
            st.metric("Sesiones Recientes (30d)", stats['recent_sessions_30d'])
        
        # Additional metrics
        col1, col2 = st.columns(2)
        
        with col1:
            if stats['total_documents_processed'] > 0:
                error_rate = (stats['total_documents_with_errors'] / stats['total_documents_processed']) * 100
                st.metric("Tasa de Errores", f"{error_rate:.1f}%")
            else:
                st.metric("Tasa de Errores", "0%")
        
        with col2:
            st.metric("Promedio Docs/Sesión", f"{stats['avg_documents_per_session']:.1f}")
        
        # Status distribution
        if stats['status_distribution']:
            st.markdown("### Distribución por Estado")
            
            status_names = {
                'completed': 'Completado',
                'in_progress': 'En Progreso',
                'review_needed': 'Necesita Revisión'
            }
            
            for status, count in stats['status_distribution'].items():
                display_name = status_names.get(status, status)
                st.write(f"**{display_name}:** {count} sesiones")
        
        # Last session info
        if stats['last_session_date']:
            st.markdown("### Última Actividad")
            st.write(f"**Última sesión:** {stats['last_session_date'].strftime('%d/%m/%Y %H:%M')}")