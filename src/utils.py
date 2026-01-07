import os
import magic
from typing import Dict, Any, Union # Asegura la importación de Union

def validate_file(uploaded_file) -> Dict[str, Any]:
    """Validate uploaded file type and size"""
    # ... (Resto de la función validate_file)
    try:
        # Check file size (max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB
        file_size = len(uploaded_file.getvalue())
        
        if file_size > max_size:
            return {
                'valid': False,
                'error': f'Archivo demasiado grande ({format_file_size(file_size)}). Máximo permitido: 10MB'
            }
        
        # Check file type
        filename = uploaded_file.name.lower()
        allowed_extensions = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp']
        
        if not any(filename.endswith(ext) for ext in allowed_extensions):
            return {
                'valid': False,
                'error': 'Tipo de archivo no permitido. Use: PDF, PNG, JPG, JPEG, TIFF, BMP'
            }
        
        # Determine file type
        if filename.endswith('.pdf'):
            file_type = 'PDF'
        else:
            file_type = 'Imagen'
        
        return {
            'valid': True,
            'type': file_type,
            'size': format_file_size(file_size)
        }
        
    except Exception as e:
        return {
            'valid': False,
            'error': f'Error validando archivo: {str(e)}'
        }

def get_file_type(uploaded_file) -> str:
    """Get file type (pdf or image)"""
    filename = uploaded_file.name.lower()
    if filename.endswith('.pdf'):
        return 'pdf'
    return 'image'

def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

def clean_extracted_value(value: str) -> str:
    """Clean extracted values from OCR"""
    # ... (Resto de la función clean_extracted_value)
    if not value or value in ['No detectado', 'None', 'null']:
        return 'No detectado'
    
    # Remove common OCR artifacts
    cleaned = str(value).strip()
    
    # Remove extra whitespaces
    cleaned = ' '.join(cleaned.split())
    
    return cleaned if cleaned else 'No detectado'

def validate_numeric_field(value: str, field_name: str) -> tuple:
    """Validate numeric fields and return (is_valid, cleaned_value, error_message)"""
    # ... (Resto de la función validate_numeric_field)
    if not value or value == 'No detectado':
        return False, 'No detectado', f'{field_name} no detectado'
    
    try:
        # Remove common currency symbols and formatting
        cleaned = str(value).replace('$', '').replace(',', '').replace('USD', '').strip()
        float(cleaned)
        return True, cleaned, None
    except ValueError:
        return False, value, f'{field_name} no es un valor numérico válido'

def extract_currency_from_value(value: str) -> tuple:
    """Extract currency and numeric value from a string"""
    # ... (Resto de la función extract_currency_from_value)
    if not value or value == 'No detectado':
        return 'No detectado', 'No detectado'
    
    value_str = str(value).upper()
    
    # Common currency patterns
    currencies = ['USD', 'EUR', 'COP', 'PEN', 'MXN', 'CLP', 'ARS']
    detected_currency = 'USD'  # Default
    
    for currency in currencies:
        if currency in value_str:
            detected_currency = currency
            break
    
    # Extract numeric value
    try:
        numeric_value = value_str.replace('$', '').replace(',', '')
        for currency in currencies:
            numeric_value = numeric_value.replace(currency, '')
        numeric_value = numeric_value.strip()
        float(numeric_value)  # Validate it's numeric
        return detected_currency, numeric_value
    except ValueError:
        return detected_currency, 'No detectado'

# FUNCIÓN PARA LA LÓGICA DE FACTURACIÓN (Necesaria)
def safe_numeric(value: Any) -> Union[int, float]:
    """Convierte un valor a int o float (prioriza float si hay decimales) de forma segura, retorna 0 si falla."""
    if value is None:
        return 0.0
    try:
        s = str(value).strip().replace(',', '') # Remover comas de miles
        if '.' in s:
            return float(s)
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return 0.0