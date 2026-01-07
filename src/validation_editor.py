import streamlit as st
import pandas as pd
from typing import Dict, Any, List, Optional
from datetime import datetime
import re

class ValidationEditor:
    def __init__(self):
        self._current_doc_index = 0
        self.field_definitions = {
            'numero_bl': {
                'name': 'Número de BL',
                'type': 'text',
                'required': True,
                'pattern': r'^[A-Z0-9\-]+$',
                'description': 'Formato: Letras mayúsculas, números y guiones'
            },
            'exportador': {
                'name': 'Exportador',
                'type': 'text', 
                'required': True,
                'min_length': 2,
                'description': 'Nombre completo del exportador'
            },
            'consignatario': {
                'name': 'Consignatario',
                'type': 'text',
                'required': True, 
                'min_length': 2,
                'description': 'Nombre completo del consignatario'
            },
            'valor_flete': {
                'name': 'Valor del Flete',
                'type': 'currency',
                'required': False,
                'min_value': 0,
                'description': 'Valor numérico del flete'
            },
            'bultos': {
                'name': 'Bultos',
                'type': 'integer',
                'required': False,
                'min_value': 1,
                'description': 'Número de bultos/paquetes'
            },
            'kilos': {
                'name': 'Kilos',
                'type': 'decimal',
                'required': False,
                'min_value': 0.1,
                'description': 'Peso en kilogramos'
            },
            'numero_contenedor': {
                'name': 'Número de Contenedor',
                'type': 'text',
                'required': False,
                'pattern': r'^[A-Z]{4}[0-9]{7}$',
                'description': 'Formato: 4 letras + 7 números (ej: ABCD1234567)'
            },
            'incoterm': {
                'name': 'INCOTERM',
                'type': 'select',
                'required': True,
                'options': ['FOB', 'CIF', 'EXW', 'CFR', 'DAP', 'DDP'],
                'description': 'Término de comercio internacional'
            },
            'valor_factura': {
                'name': 'Valor Factura',
                'type': 'currency',
                'required': False,
                'min_value': 0,
                'description': 'Valor total de la factura'
            },
            'valor_fob': {
                'name': 'Valor FOB',
                'type': 'currency',
                'required': False,
                'min_value': 0,
                'description': 'Valor Free On Board'
            },
            'valor_cif': {
                'name': 'Valor CIF',
                'type': 'currency',
                'required': False,
                'min_value': 0,
                'description': 'Valor Cost, Insurance and Freight'
            },
            'moneda': {
                'name': 'Moneda',
                'type': 'select',
                'required': False,
                'options': ['USD', 'EUR', 'COP', 'PEN', 'MXN', 'CLP', 'ARS'],
                'description': 'Moneda de los valores'
            }
        }
    
    def validate_field(self, field_name: str, value: Any) -> Dict[str, Any]:
        """Validate a single field and return validation result"""
        if field_name not in self.field_definitions:
            return {'valid': True, 'value': value, 'messages': []}
        
        field_def = self.field_definitions[field_name]
        messages = []
        is_valid = True
        processed_value = value
        
        # Handle empty/None values
        if not value or str(value).strip() in ['', 'No detectado', 'None', 'null']:
            if field_def.get('required', False):
                is_valid = False
                messages.append(f"Campo obligatorio: {field_def['name']}")
            return {'valid': is_valid, 'value': 'No detectado', 'messages': messages}
        
        # Convert to string for processing
        str_value = str(value).strip()
        
        # Type-specific validation
        if field_def['type'] == 'text':
            processed_value = str_value
            if 'min_length' in field_def and len(str_value) < field_def['min_length']:
                is_valid = False
                messages.append(f"Mínimo {field_def['min_length']} caracteres")
            
            if 'pattern' in field_def:
                if not re.match(field_def['pattern'], str_value):
                    is_valid = False
                    messages.append(f"Formato inválido: {field_def['description']}")
        
        elif field_def['type'] == 'integer':
            try:
                processed_value = self._parse_number(str_value, int)
                if 'min_value' in field_def and processed_value < field_def['min_value']:
                    is_valid = False
                    messages.append(f"Valor mínimo: {field_def['min_value']}")
            except (ValueError, TypeError):
                is_valid = False
                messages.append("Debe ser un número entero")
                processed_value = str_value
        
        elif field_def['type'] == 'decimal':
            try:
                processed_value = self._parse_number(str_value, float)
                if 'min_value' in field_def and processed_value < field_def['min_value']:
                    is_valid = False
                    messages.append(f"Valor mínimo: {field_def['min_value']}")
            except (ValueError, TypeError):
                is_valid = False
                messages.append("Debe ser un número decimal")
                processed_value = str_value
        
        elif field_def['type'] == 'currency':
            try:
                processed_value = self._parse_number(str_value, float)
                if 'min_value' in field_def and processed_value < field_def['min_value']:
                    is_valid = False
                    messages.append(f"Valor mínimo: {field_def['min_value']}")
            except (ValueError, TypeError):
                is_valid = False
                messages.append("Debe ser un valor monetario válido")
                processed_value = str_value
        
        elif field_def['type'] == 'select':
            if str_value not in field_def['options']:
                is_valid = False
                messages.append(f"Debe seleccionar una opción válida: {', '.join(field_def['options'])}")
        
        return {'valid': is_valid, 'value': processed_value, 'messages': messages}
    
    def validate_document(self, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate all fields in a document"""
        validation_results = {}
        all_valid = True
        
        for field_name in self.field_definitions.keys():
            value = document_data.get(field_name, 'No detectado')
            result = self.validate_field(field_name, value)
            validation_results[field_name] = result
            if not result['valid']:
                all_valid = False
        
        return {
            'valid': all_valid,
            'fields': validation_results,
            'summary': self._get_validation_summary(validation_results)
        }
    
    def _get_validation_summary(self, validation_results: Dict[str, Dict]) -> Dict[str, Any]:
        """Generate validation summary"""
        total_fields = len(validation_results)
        valid_fields = sum(1 for r in validation_results.values() if r['valid'])
        invalid_fields = total_fields - valid_fields
        
        error_messages = []
        warning_messages = []
        
        for field_name, result in validation_results.items():
            if not result['valid']:
                field_display_name = self.field_definitions[field_name]['name']
                for message in result['messages']:
                    error_messages.append(f"{field_display_name}: {message}")
        
        return {
            'total_fields': total_fields,
            'valid_fields': valid_fields,
            'invalid_fields': invalid_fields,
            'completion_rate': (valid_fields / total_fields) * 100,
            'error_messages': error_messages,
            'warning_messages': warning_messages
        }
    
    def render_document_editor(self, document_data: Dict[str, Any], doc_index: int) -> Optional[Dict[str, Any]]:
        """Render the document editing interface"""
        self._current_doc_index = doc_index
        st.subheader(f"Editar Documento {doc_index + 1}: {document_data.get('archivo', 'Sin nombre')}")
        
        # Validate current data
        validation = self.validate_document(document_data)
        
        # Show validation summary
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Campos Válidos", f"{validation['summary']['valid_fields']}/{validation['summary']['total_fields']}")
        with col2:
            st.metric("Completitud", f"{validation['summary']['completion_rate']:.1f}%")
        with col3:
            if validation['valid']:
                st.success("Validación Completa")
            else:
                st.error(f"{validation['summary']['invalid_fields']} errores")
        
        # Show errors if any
        if validation['summary']['error_messages']:
            with st.expander("Errores de Validación", expanded=True):
                for error in validation['summary']['error_messages']:
                    st.error(f"• {error}")
        
        # Create editing form
        with st.form(f"edit_document_{doc_index}"):
            edited_data = {}
            
            # Group fields by category
            st.markdown("### Información del BL")
            col1, col2 = st.columns(2)
            
            with col1:
                edited_data['numero_bl'] = self._render_field_input('numero_bl', document_data, validation['fields'])
                edited_data['exportador'] = self._render_field_input('exportador', document_data, validation['fields'])
                edited_data['consignatario'] = self._render_field_input('consignatario', document_data, validation['fields'])
                edited_data['valor_flete'] = self._render_field_input('valor_flete', document_data, validation['fields'])
            
            with col2:
                edited_data['bultos'] = self._render_field_input('bultos', document_data, validation['fields'])
                edited_data['kilos'] = self._render_field_input('kilos', document_data, validation['fields'])
                edited_data['numero_contenedor'] = self._render_field_input('numero_contenedor', document_data, validation['fields'])
            
            
            st.markdown("### Información Financiera")
            col3, col4 = st.columns(2)
            
            with col3:
                edited_data['incoterm'] = self._render_field_input('incoterm', document_data, validation['fields'])
                edited_data['valor_factura'] = self._render_field_input('valor_factura', document_data, validation['fields'])
                edited_data['moneda'] = self._render_field_input('moneda', document_data, validation['fields'])
            
            with col4:
                edited_data['valor_fob'] = self._render_field_input('valor_fob', document_data, validation['fields'])
                edited_data['valor_cif'] = self._render_field_input('valor_cif', document_data, validation['fields'])
            
            # Action buttons
            col_save, col_reset, col_auto = st.columns(3)
            
            with col_save:
                save_clicked = st.form_submit_button("Guardar Cambios", type="primary", use_container_width=True)
            
            with col_reset:
                reset_clicked = st.form_submit_button("Restaurar Original", use_container_width=True)
            
            with col_auto:
                auto_fix_clicked = st.form_submit_button("Corrección Automática", use_container_width=True)
            
            if save_clicked:
                # Copy original data and update with edits
                updated_data = document_data.copy()
                updated_data.update(edited_data)
                
                # Recalculate CIF if needed
                updated_data = self._recalculate_cif(updated_data)
                
                return updated_data
            
            elif reset_clicked:
                # Clear edited data and widget state for this document
                if hasattr(st.session_state, 'edited_data') and doc_index in st.session_state.edited_data:
                    del st.session_state.edited_data[doc_index]
                
                # Clear widget state for this document
                widget_prefix = f"edit_{doc_index}_"
                keys_to_delete = [k for k in st.session_state.keys() if isinstance(k, str) and k.startswith(widget_prefix)]
                for k in keys_to_delete:
                    del st.session_state[k]
                
                st.rerun()
            
            elif auto_fix_clicked:
                # Apply automatic fixes
                auto_fixed_data = self._apply_auto_fixes(document_data)
                return auto_fixed_data
        
        return None
    
    def _get_current_doc_index(self) -> int:
        """Get current document index for unique widget keys"""
        return getattr(self, '_current_doc_index', 0)
    
    def _parse_number(self, value: Any, number_type: type) -> float:
        """Safely parse numeric values from various formats"""
        if not value or str(value).strip() in ['', 'No detectado', 'None', 'null']:
            return 0.0 if number_type == float else 0
        
        try:
            # Convert to string and clean
            str_value = str(value).strip()
            
            # Remove currency symbols and common characters
            cleaned = re.sub(r'[^\d.,\-]', '', str_value)
            
            # Handle different decimal separators and thousand separators
            # Check if it's likely a European format (comma as decimal separator)
            if ',' in cleaned and '.' in cleaned:
                # Both present - assume dot is thousand separator
                cleaned = cleaned.replace('.', '').replace(',', '.')
            elif ',' in cleaned and cleaned.count(',') == 1 and len(cleaned.split(',')[1]) <= 2:
                # Single comma likely decimal separator
                cleaned = cleaned.replace(',', '.')
            elif '.' in cleaned and cleaned.count('.') == 1:
                # Single dot - already correct
                pass
            else:
                # Remove all separators except last one
                if ',' in cleaned:
                    parts = cleaned.split(',')
                    if len(parts[-1]) <= 2:  # Last part looks like decimal
                        cleaned = ''.join(parts[:-1]) + '.' + parts[-1]
                    else:
                        cleaned = cleaned.replace(',', '')
            
            # Convert to number
            result = number_type(cleaned)
            return result
            
        except (ValueError, TypeError):
            return 0.0 if number_type == float else 0
    
    def _render_field_input(self, field_name: str, document_data: Dict[str, Any], validation_fields: Dict[str, Any]):
        """Render input field for a specific field"""
        field_def = self.field_definitions[field_name]
        current_value = document_data.get(field_name, 'No detectado')
        validation_result = validation_fields.get(field_name, {'valid': True, 'messages': []})
        
        # Create label with validation status
        label = field_def['name']
        if field_def.get('required', False):
            label += " *"
        
        
        if not validation_result['valid']:
            label = f"ERROR: {label}"
        elif current_value != 'No detectado':
            label = f"{label}"
        
        # Render appropriate input type
        if field_def['type'] == 'select':
            options = ['No detectado'] + field_def['options']
            index = 0
            if current_value in options:
                index = options.index(current_value)
            
            return st.selectbox(
                label,
                options=options,
                index=index,
                help=field_def['description'],
                key=f"edit_{self._get_current_doc_index()}_{field_name}"
            )
        
        elif field_def['type'] in ['currency', 'decimal']:
            numeric_value = self._parse_number(current_value, float)
            min_val = field_def.get('min_value', 0.0)
            default_value = max(min_val, numeric_value) if numeric_value >= 0 else min_val
            return st.number_input(
                label,
                value=default_value,
                min_value=min_val,
                step=0.01,
                help=field_def['description'],
                key=f"edit_{self._get_current_doc_index()}_{field_name}"
            )
        
        elif field_def['type'] == 'integer':
            numeric_value = self._parse_number(current_value, int)
            min_val = int(field_def.get('min_value', 0))
            default_value = max(min_val, numeric_value) if numeric_value >= 0 else min_val
            return st.number_input(
                label,
                value=default_value,
                min_value=min_val,
                step=1,
                help=field_def['description'],
                key=f"edit_{self._get_current_doc_index()}_{field_name}"
            )
        
        else:  # text
            return st.text_input(
                label,
                value=current_value if current_value != 'No detectado' else '',
                help=field_def['description'],
                key=f"edit_{self._get_current_doc_index()}_{field_name}"
            )
    
    def _recalculate_cif(self, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """Recalculate CIF value if INCOTERM is FOB"""
        try:
            if document_data.get('incoterm') == 'FOB' and document_data.get('valor_fob'):
                fob_value = self._parse_number(document_data['valor_fob'], float)
                if fob_value > 0:
                    cif_value = fob_value * 1.15  # 15% additional for freight and insurance
                    document_data['valor_cif'] = f"{cif_value:.2f}"
                    document_data['conversion_fob_cif'] = True
        except (ValueError, TypeError):
            pass
        
        return document_data
    
    def _apply_auto_fixes(self, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply automatic fixes to common issues"""
        fixed_data = document_data.copy()
        
        # Fix BL number format
        if fixed_data.get('numero_bl') and fixed_data['numero_bl'] != 'No detectado':
            fixed_data['numero_bl'] = fixed_data['numero_bl'].upper().strip()
        
        # Fix container number format
        if fixed_data.get('numero_contenedor') and fixed_data['numero_contenedor'] != 'No detectado':
            container = re.sub(r'[^A-Z0-9]', '', fixed_data['numero_contenedor'].upper())
            if len(container) == 11:
                fixed_data['numero_contenedor'] = container
        
        # Standardize INCOTERM
        if fixed_data.get('incoterm') and fixed_data['incoterm'] != 'No detectado':
            incoterm = fixed_data['incoterm'].upper().strip()
            if incoterm in ['FOB', 'CIF', 'EXW', 'CFR', 'DAP', 'DDP']:
                fixed_data['incoterm'] = incoterm
        
        # Fix numeric values using safe parsing
        for field in ['valor_flete', 'valor_factura', 'valor_fob', 'valor_cif']:
            if fixed_data.get(field) and fixed_data[field] != 'No detectado':
                parsed_value = self._parse_number(fixed_data[field], float)
                if parsed_value > 0:
                    fixed_data[field] = parsed_value
        
        # Recalculate CIF
        fixed_data = self._recalculate_cif(fixed_data)
        
        return fixed_data
    
    def get_validation_report(self, processed_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate comprehensive validation report"""
        total_docs = len(processed_data)
        valid_docs = 0
        field_completeness = {}
        common_errors = {}
        
        for doc in processed_data:
            validation = self.validate_document(doc)
            if validation['valid']:
                valid_docs += 1
            
            # Track field completeness
            for field_name, result in validation['fields'].items():
                if field_name not in field_completeness:
                    field_completeness[field_name] = {'total': 0, 'valid': 0, 'detected': 0}
                
                field_completeness[field_name]['total'] += 1
                if result['valid']:
                    field_completeness[field_name]['valid'] += 1
                if result['value'] != 'No detectado':
                    field_completeness[field_name]['detected'] += 1
            
            # Track common errors
            for error in validation['summary']['error_messages']:
                if error not in common_errors:
                    common_errors[error] = 0
                common_errors[error] += 1
        
        return {
            'total_documents': total_docs,
            'valid_documents': valid_docs,
            'document_validity_rate': (valid_docs / total_docs * 100) if total_docs > 0 else 0,
            'field_completeness': field_completeness,
            'common_errors': dict(sorted(common_errors.items(), key=lambda x: x[1], reverse=True)),
            'generated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }