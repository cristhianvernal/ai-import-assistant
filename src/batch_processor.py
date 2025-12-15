import streamlit as st
import asyncio
import threading
import time
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
import queue
from .document_processor import DocumentProcessor
import concurrent.futures
from dataclasses import dataclass, field
import uuid

@dataclass
class BatchJob:
    id: str
    name: str
    files: List[Any]  
    total_files: int
    processed_files: int
    failed_files: int
    status: str  
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    results: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    progress_percentage: float = 0.0
    cancel_event: Optional[threading.Event] = field(default_factory=threading.Event)

class BatchProcessor:
    def __init__(self):
        self.doc_processor = DocumentProcessor()
        self.active_jobs: Dict[str, BatchJob] = {}
        self.job_queue = queue.Queue()
        self.max_concurrent_jobs = 2  # Limit concurrent processing
        self.max_workers = 4  # Thread pool size for individual documents
        
        
        if 'batch_jobs' not in st.session_state:
            st.session_state.batch_jobs = {}
        if 'batch_processing_active' not in st.session_state:
            st.session_state.batch_processing_active = False
    
    def create_batch_job(self, job_name: str, files: List[Any]) -> str:
        """Create a new batch processing job"""
        job_id = str(uuid.uuid4())
        
        job = BatchJob(
            id=job_id,
            name=job_name,
            files=files,
            total_files=len(files),
            processed_files=0,
            failed_files=0,
            status='pending',
            results=[],
            errors=[]
        )
        
        self.active_jobs[job_id] = job
        st.session_state.batch_jobs[job_id] = job
        
        return job_id
    
    def process_batch_sync(self, job_id: str, progress_callback: Optional[Callable] = None) -> BatchJob:
        """Process batch job synchronously with progress updates"""
        if job_id not in self.active_jobs:
            raise ValueError(f"Job {job_id} not found")
        
        job = self.active_jobs[job_id]
        job.status = 'running'
        job.start_time = datetime.now()
        
        # Update session state
        st.session_state.batch_jobs[job_id] = job
        
        try:
           
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                
                future_to_file = {}
                for i, file in enumerate(job.files):
                    future = executor.submit(self._process_single_file, file, i)
                    future_to_file[future] = (file, i)
                
                # Collect results as they complete
                for future in concurrent.futures.as_completed(future_to_file):
                    file, file_index = future_to_file[future]
                    
                    try:
                        result = future.result()
                        if result.get('success', False):
                            job.results.append(result['data'])
                            job.processed_files += 1
                        else:
                            job.errors.append({
                                'file_index': file_index,
                                'filename': file.name,
                                'error': result.get('error', 'Unknown error')
                            })
                            job.failed_files += 1
                    
                    except Exception as e:
                        job.errors.append({
                            'file_index': file_index,
                            'filename': file.name,
                            'error': str(e)
                        })
                        job.failed_files += 1
                    
                    # Update progress
                    completed = job.processed_files + job.failed_files
                    job.progress_percentage = (completed / job.total_files) * 100
                    
                    # Update session state
                    st.session_state.batch_jobs[job_id] = job
                    
                    # Call progress callback if provided
                    if progress_callback:
                        progress_callback(job)
            
            # Job completed
            job.status = 'completed'
            job.end_time = datetime.now()
            
        except Exception as e:
            job.status = 'failed'
            job.end_time = datetime.now()
            job.errors.append({
                'file_index': -1,
                'filename': 'batch_processing',
                'error': f"Batch processing failed: {str(e)}"
            })
        
        # Final update to session state
        st.session_state.batch_jobs[job_id] = job
        self.active_jobs[job_id] = job
        
        return job
    
    def _process_single_file(self, file, file_index: int) -> Dict[str, Any]:
        """Process a single file and return result"""
        try:
            # Validate file
            from .utils import validate_file, get_file_type
            
            validation_result = validate_file(file)
            if not validation_result.get('valid', False):
                return {
                    'success': False,
                    'error': validation_result.get('error', 'Archivo no válido o tipo no soportado')
                }
            
            # Get file type
            file_type = get_file_type(file)
            
            # Process the document
            result = self.doc_processor.process_document(file)
            
            if result:
                # Add metadata
                result['archivo'] = file.name
                result['indice_archivo'] = file_index
                result['tipo_archivo'] = file_type
                result['fecha_procesamiento'] = datetime.now().isoformat()
                result['metodo_procesamiento'] = result.get('metodo_procesamiento', 'desconocido')
                
                return {
                    'success': True,
                    'data': result
                }
            else:
                return {
                    'success': False,
                    'error': 'No se pudo procesar el documento'
                }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_job_status(self, job_id: str) -> Optional[BatchJob]:
        """Get current status of a batch job"""
        return st.session_state.batch_jobs.get(job_id)
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running batch job"""
        if job_id in self.active_jobs:
            job = self.active_jobs[job_id]
            if job.status == 'running':
                # Signal cancellation
                if job.cancel_event:
                    job.cancel_event.set()
                job.status = 'cancelled'
                job.end_time = datetime.now()
                st.session_state.batch_jobs[job_id] = job
                return True
        return False
    
    def get_all_jobs(self) -> List[BatchJob]:
        """Get all batch jobs"""
        return list(st.session_state.batch_jobs.values())
    
    def delete_job(self, job_id: str) -> bool:
        """Delete a batch job"""
        if job_id in st.session_state.batch_jobs:
            del st.session_state.batch_jobs[job_id]
        if job_id in self.active_jobs:
            del self.active_jobs[job_id]
        return True
    
    def render_batch_interface(self):
        """Render the batch processing interface"""
        st.header("Procesamiento por Lotes")
        
        tab1, tab2, tab3 = st.tabs(["Nuevo Lote", "Jobs Activos", "Estadísticas"])
        
        with tab1:
            self._render_new_batch()
        
        with tab2:
            self._render_active_jobs()
        
        with tab3:
            self._render_batch_statistics()
    
    def _render_new_batch(self):
        """Render new batch creation interface"""
        st.subheader("Crear Nuevo Lote de Procesamiento")
        
        st.markdown("""
        El procesamiento por lotes le permite cargar múltiples documentos y procesarlos automáticamente.
        Ideal para grandes volúmenes de documentos BL y facturas.
        """)
        
        # Job configuration
        col1, col2 = st.columns(2)
        
        with col1:
            job_name = st.text_input(
                "Nombre del Lote",
                value=f"Lote_{datetime.now().strftime('%Y%m%d_%H%M')}",
                help="Nombre descriptivo para identificar este lote"
            )
        
        with col2:
            processing_mode = st.selectbox(
                "Modo de Procesamiento",
                options=["parallel", "sequential"],
                format_func=lambda x: {
                    "parallel": "Paralelo (Más rápido)",
                    "sequential": "Secuencial (Más estable)"
                }[x],
                help="Paralelo: más rápido pero consume más recursos. Secuencial: más lento pero más estable."
            )
        
        # File upload
        st.markdown("### Seleccionar Archivos")
        
        uploaded_files = st.file_uploader(
            "Seleccione múltiples documentos (PDF o imágenes)",
            type=['pdf', 'jpg', 'jpeg', 'png', 'tiff', 'bmp'],
            accept_multiple_files=True,
            help="Puede seleccionar hasta 50 archivos a la vez"
        )
        
        if uploaded_files:
            # File summary
            st.markdown("### Resumen de Archivos")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Archivos", len(uploaded_files))
            
            with col2:
                total_size = sum(file.size for file in uploaded_files) / (1024 * 1024)  # MB
                st.metric("Tamaño Total", f"{total_size:.1f} MB")
            
            with col3:
                # Estimate processing time (rough estimate: 10-30 seconds per document)
                est_time_min = len(uploaded_files) * 10 / 60  # Optimistic
                est_time_max = len(uploaded_files) * 30 / 60  # Conservative
                st.metric("Tiempo Estimado", f"{est_time_min:.0f}-{est_time_max:.0f} min")
            
            # File list preview
            if st.checkbox("Mostrar lista de archivos", value=False):
                st.markdown("**Archivos seleccionados:**")
                for i, file in enumerate(uploaded_files[:10], 1):  # Show first 10
                    st.write(f"{i}. {file.name} ({file.size / 1024:.1f} KB)")
                
                if len(uploaded_files) > 10:
                    st.write(f"... y {len(uploaded_files) - 10} archivos más")
            
            # Processing options
            st.markdown("### Opciones de Procesamiento")
            
            col1, col2 = st.columns(2)
            
            with col1:
                auto_validation = st.checkbox(
                    "Validación automática", 
                    value=True,
                    help="Aplicar validación automática a todos los documentos procesados"
                )
            
            with col2:
                save_session = st.checkbox(
                    "Guardar sesión automáticamente",
                    value=True,
                    help="Guardar automáticamente los resultados como una sesión de trabajo"
                )
            
            # Start processing button
            if st.button("Iniciar Procesamiento por Lotes", type="primary", use_container_width=True):
                if not job_name.strip():
                    st.error("Debe ingresar un nombre para el lote")
                    return
                
                if len(uploaded_files) > 50:
                    st.error("Máximo 50 archivos por lote")
                    return
                
                # Create batch job
                with st.spinner("Creando lote de procesamiento..."):
                    job_id = self.create_batch_job(job_name.strip(), uploaded_files)
                    st.session_state.current_batch_job = job_id
                    st.session_state.batch_processing_active = True
                    # Store processing options
                    st.session_state.batch_auto_validation = auto_validation
                    st.session_state.batch_save_session = save_session
                
                st.success(f"Lote creado: {job_name}")
                st.info("El procesamiento comenzará automáticamente...")
                st.rerun()
        
        else:
            st.info("📁 Seleccione archivos para comenzar el procesamiento por lotes")
    
    def _render_active_jobs(self):
        """Render active jobs monitoring interface"""
        st.subheader("Monitoreo de Jobs Activos")
        
        # Auto-refresh option
        auto_refresh = st.checkbox("Actualización automática (cada 5 segundos)", value=True)
        
        if auto_refresh:
            # Auto-refresh placeholder
            refresh_placeholder = st.empty()
            time.sleep(5)
            st.rerun()
        
        # Current batch job processing
        if st.session_state.get('batch_processing_active', False) and st.session_state.get('current_batch_job'):
            self._render_current_job_progress()
        
        # All jobs list
        jobs = self.get_all_jobs()
        
        if not jobs:
            st.info("No hay jobs de procesamiento por lotes")
            return
        
        # Jobs summary
        st.markdown("### Resumen de Jobs")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_jobs = len(jobs)
            st.metric("Total Jobs", total_jobs)
        
        with col2:
            completed_jobs = len([j for j in jobs if j.status == 'completed'])
            st.metric("Completados", completed_jobs)
        
        with col3:
            running_jobs = len([j for j in jobs if j.status == 'running'])
            st.metric("En Ejecución", running_jobs)
        
        with col4:
            failed_jobs = len([j for j in jobs if j.status == 'failed'])
            st.metric("Fallidos", failed_jobs)
        
        # Jobs list
        st.markdown("### Lista de Jobs")
        
        for job in sorted(jobs, key=lambda x: x.start_time or datetime.min, reverse=True):
            self._render_job_card(job)
    
    def _render_current_job_progress(self):
        """Render progress for the currently running job"""
        job_id = st.session_state.current_batch_job
        job = self.get_job_status(job_id)
        
        if not job:
            st.session_state.batch_processing_active = False
            return
        
        st.markdown("### Job Actual en Procesamiento")
        
        # Progress display
        progress_container = st.container()
        
        with progress_container:
            # Job info
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Nombre:** {job.name}")
                st.write(f"**Estado:** {self._get_status_emoji(job.status)} {job.status.title()}")
            
            with col2:
                if job.start_time:
                    elapsed = datetime.now() - job.start_time
                    st.write(f"**Tiempo transcurrido:** {str(elapsed).split('.')[0]}")
                st.write(f"**Progreso:** {job.processed_files + job.failed_files}/{job.total_files}")
            
            # Progress bar
            progress_percentage = job.progress_percentage / 100 if job.total_files > 0 else 0
            st.progress(progress_percentage)
            
            # Detailed metrics
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Procesados", job.processed_files)
            
            with col2:
                st.metric("Fallidos", job.failed_files)
            
            with col3:
                remaining = job.total_files - (job.processed_files + job.failed_files)
                st.metric("Pendientes", remaining)
        
        # Check if processing should start or continue
        if job.status == 'pending':
            # Start processing
            self._start_batch_processing(job_id)
        
        elif job.status in ['completed', 'failed', 'cancelled']:
            # Processing finished
            st.session_state.batch_processing_active = False
            
            if job.status == 'completed':
                st.success(f"Lote '{job.name}' completado exitosamente!")
                
                # Load results into main session
                if st.button("Cargar Resultados en Sesión Principal", use_container_width=True):
                    st.session_state.processed_data = job.results
                    st.session_state.processing_complete = True
                    st.session_state.edited_data = {}
                    st.session_state.validation_mode = False
                    st.success("Resultados cargados en la sesión principal")
                    st.rerun()
            
            elif job.status == 'failed':
                st.error(f"Lote '{job.name}' falló durante el procesamiento")
            
            elif job.status == 'cancelled':
                st.warning(f"Lote '{job.name}' fue cancelado")
    
    def _start_batch_processing(self, job_id: str):
        """Start batch processing for a job"""
        if job_id not in self.active_jobs:
            return
        
        # Create a progress placeholder
        progress_placeholder = st.empty()
        
        def progress_callback(job: BatchJob):
            with progress_placeholder.container():
                st.write(f"Procesando archivo {job.processed_files + job.failed_files + 1} de {job.total_files}...")
        
        # Process batch in a separate thread to avoid blocking UI
        try:
            # For simplicity, we'll process synchronously but update UI
            self.process_batch_sync(job_id, progress_callback)
            
        except Exception as e:
            st.error(f"Error en procesamiento por lotes: {str(e)}")
            job = self.active_jobs[job_id]
            job.status = 'failed'
            job.end_time = datetime.now()
            st.session_state.batch_jobs[job_id] = job
    
    def _render_job_card(self, job: BatchJob):
        """Render a job card"""
        status_emoji = self._get_status_emoji(job.status)
        
        with st.expander(f"{status_emoji} {job.name} - {job.status.title()}", expanded=False):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**ID:** {job.id[:8]}...")
                st.write(f"**Total archivos:** {job.total_files}")
                st.write(f"**Procesados exitosamente:** {job.processed_files}")
                st.write(f"**Fallidos:** {job.failed_files}")
            
            with col2:
                if job.start_time:
                    st.write(f"**Iniciado:** {job.start_time.strftime('%d/%m/%Y %H:%M:%S')}")
                if job.end_time:
                    st.write(f"**Terminado:** {job.end_time.strftime('%d/%m/%Y %H:%M:%S')}")
                    duration = job.end_time - job.start_time
                    st.write(f"**Duración:** {str(duration).split('.')[0]}")
                
                if job.total_files > 0:
                    success_rate = (job.processed_files / job.total_files) * 100
                    st.write(f"**Tasa de éxito:** {success_rate:.1f}%")
            
            # Progress bar
            if job.total_files > 0:
                progress = (job.processed_files + job.failed_files) / job.total_files
                st.progress(progress)
            
            # Action buttons
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if job.status == 'completed' and job.results:
                    if st.button(f"Cargar Resultados", key=f"load_{job.id}", use_container_width=True):
                        st.session_state.processed_data = job.results
                        st.session_state.processing_complete = True
                        st.session_state.edited_data = {}
                        st.session_state.validation_mode = False
                        st.success("✅ Resultados cargados")
                        st.rerun()
            
            with col2:
                if job.status == 'running':
                    if st.button(f"Cancelar", key=f"cancel_{job.id}", use_container_width=True):
                        self.cancel_job(job.id)
                        st.rerun()
            
            with col3:
                if job.status in ['completed', 'failed', 'cancelled']:
                    if st.button(f"Eliminar", key=f"delete_{job.id}", use_container_width=True):
                        self.delete_job(job.id)
                        st.rerun()
            
            # Show errors if any
            if job.errors:
                st.markdown("**Errores:**")
                for error in job.errors[:5]:  # Show first 5 errors
                    st.write(f"• {error['filename']}: {error['error']}")
                
                if len(job.errors) > 5:
                    st.write(f"... y {len(job.errors) - 5} errores más")
    
    def _render_batch_statistics(self):
        """Render batch processing statistics"""
        st.subheader("Estadísticas de Procesamiento por Lotes")
        
        jobs = self.get_all_jobs()
        
        if not jobs:
            st.info("No hay estadísticas disponibles. Procese algunos lotes primero.")
            return
        
        # Overall statistics
        st.markdown("### Estadísticas Generales")
        
        col1, col2, col3, col4 = st.columns(4)
        
        total_files_processed = sum(job.processed_files for job in jobs)
        total_files_failed = sum(job.failed_files for job in jobs)
        total_files = sum(job.total_files for job in jobs)
        
        with col1:
            st.metric("Total Files Procesados", total_files_processed)
        
        with col2:
            st.metric("Total Files Fallidos", total_files_failed)
        
        with col3:
            success_rate = (total_files_processed / total_files * 100) if total_files > 0 else 0
            st.metric("Tasa de Éxito Global", f"{success_rate:.1f}%")
        
        with col4:
            avg_files_per_job = total_files / len(jobs) if jobs else 0
            st.metric("Promedio Files/Job", f"{avg_files_per_job:.1f}")
        
        # Job status distribution
        st.markdown("### Distribución por Estado")
        
        status_counts = {}
        for job in jobs:
            status_counts[job.status] = status_counts.get(job.status, 0) + 1
        
        for status, count in status_counts.items():
            emoji = self._get_status_emoji(status)
            st.write(f"**{emoji} {status.title()}:** {count} jobs")
        
        # Performance metrics
        completed_jobs = [job for job in jobs if job.status == 'completed' and job.start_time and job.end_time]
        
        if completed_jobs:
            st.markdown("### Métricas de Rendimiento")
            
            # Calculate average processing time per file
            total_duration = sum((job.end_time - job.start_time).total_seconds() for job in completed_jobs)
            total_processed = sum(job.processed_files for job in completed_jobs)
            
            if total_processed > 0:
                avg_time_per_file = total_duration / total_processed
                st.write(f"**Tiempo promedio por archivo:** {avg_time_per_file:.1f} segundos")
            
            # Job duration statistics
            durations = [(job.end_time - job.start_time).total_seconds() / 60 for job in completed_jobs]
            avg_duration = sum(durations) / len(durations)
            st.write(f"**Duración promedio por job:** {avg_duration:.1f} minutos")
    
    def _get_status_emoji(self, status: str) -> str:
        """Get emoji for job status"""
        emoji_map = {
            'pending': '',
            'running': '',
            'completed': '',
            'failed': '',
            'cancelled': ''
        }
        return emoji_map.get(status, '')