# document_processor.py

import pdfplumber
import re
import json
from typing import List, Dict, Any, Tuple, BinaryIO
import google.generativeai as genai
from PIL import Image
import pdf2image
import io

def get_text_from_pdf_multimodal(pdf_file: BinaryIO, prompt: str, api_key: str) -> Dict[str, Any]:
    text = ""
    pdf_file.seek(0)
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            
            text = "\n".join(page.extract_text(x_tolerance=2, layout=True) or "" for page in pdf.pages)
    except Exception:
        text = ""

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    generation_config = genai.GenerationConfig(
        temperature=0.1
    )

    if text and len(text.strip()) > 150:
        print("INFO: Documento procesado como PDF de texto.")
        full_prompt = f"{prompt}\n\n--- INICIO DEL TEXTO DEL DOCUMENTO ---\n{text}\n--- FIN DEL TEXTO DEL DOCUMENTO ---"
        try:
            response = model.generate_content(full_prompt, generation_config=generation_config)
            return clean_json_response(response.text)
        except Exception as e:
            print(f"Error en la API de Gemini (modo texto): {e}")
            return {"error": str(e)}

    else:
        print("INFO: No se encontró texto. Procesando documento como imagen (OCR).")
        pdf_file.seek(0)
        try:
            # pdf2image.convert_from_bytes puede consumir mucha memoria. Considerar solo las primeras 5 páginas.
            images = pdf2image.convert_from_bytes(pdf_file.read(), first_page=1, last_page=5)
            content = [prompt] + images
            response = model.generate_content(content, generation_config=generation_config)
            return clean_json_response(response.text)
        except Exception as e:
            print(f"Error procesando el PDF como imagen con Gemini: {e}")
            return {"error": str(e)}

def clean_json_response(response_text: str) -> Dict[str, Any]:
    match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
    if not match:
        match = re.search(r'(\{.*?\})', response_text, re.DOTALL)
    
    if match:
        json_str = match.group(1)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Error decodificando JSON: {e}\nString con problemas:\n{json_str}")
            return {"error": "JSON mal formado en la respuesta de la IA."}
    else:
        print(f"Error: No se encontró JSON en la respuesta.\nRespuesta recibida:\n{response_text}")
        return {"error": f"La IA no devolvió un JSON. Respuesta recibida: {response_text[:500]}..."}


# NUEVA FUNCIÓN: Traducción de texto
def translate_text(text: str, api_key: str) -> str:
    """Uses Gemini to translate a string from English to Spanish."""
    if not text or text.lower() in ('no detectado', 's/m', 'por definir', 'null'):
        return text
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    # Prompt específico para asegurar solo la traducción
    prompt = f"Traduce el siguiente texto de descripción de producto al español. Devuelve SOLO la traducción: '{text}'"
    
    try:
        response = model.generate_content(prompt)
        # Limpieza simple de la respuesta
        return response.text.strip().replace('*', '').replace('"', '')
    except Exception as e:
        print(f"Error en la API de Gemini durante la traducción: {e}")
        return f"ERROR_TRADUCCION: {text}"

# LÓGICA DE CONSOLIDACIÓN MEJORADA
def _consolidate_party_info(info_bl: Dict, info_invoice: Dict) -> Dict:
    """Consolida la información del exportador/consignatario priorizando la más detallada."""
    
    bl_address = str(info_bl.get('address', '')).strip()
    inv_address = str(info_invoice.get('address', '')).strip()
    
    final_info = {
        # Priorizar el nombre de la Factura si es más específico
        "name": info_invoice.get('name') or info_bl.get('name') or "No detectado",
        
        # Priorizar la dirección más larga
        "address": inv_address if len(inv_address) > len(bl_address) else bl_address or "No detectado",
        
        # Priorizar el teléfono de la Factura (asumiendo que es la fuente más reciente)
        "phone": info_invoice.get('phone') or info_bl.get('phone') or "No detectado",
    }
    return final_info

def process_documents(bl_file: BinaryIO, invoice_files: List[BinaryIO], api_key: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    
    # Prompt del BL (Añadiendo Dirección y Teléfono explícitamente)
    bl_prompt = f"""
    **Tarea:** Extraer **todos** los datos clave de un Bill of Lading (BL) para un reporte de importación.
    **Rol:** Eres un API de extracción de datos. Tu única función es devolver un objeto JSON.
    **Reglas Estrictas:**
    1. Tu respuesta debe ser **EXCLUSIVAMENTE** un objeto JSON válido.
    2. **NO** incluyas texto explicativo, introducciones, resúmenes ni formato markdown.
    3. Envuelve el JSON en un bloque de código: ```json ... ```.
    4. Si un campo no se encuentra en el documento, usa `null` como valor.
    5. Los valores numéricos (freight_cost, packages_count, gross_weight, gross_measurement) deben ser números (int o float), no cadenas.
    6. Para 'exporter' y 'consignee', extrae el **nombre completo**, la **dirección postal completa** y el **número de teléfono** si está presente.

    **Formato de Salida JSON Requerido:**
    ```json
    {{
        "bl_number": "...",
        "booking_number": "...",
        "container_no": "...",
        "vessel_voyage": "...",
        "port_of_loading": "...",
        "port_of_discharge": "...",
        "place_of_delivery": "...",
        "date_laden_on_board": "...",
        "cargo_type": "...",
        "freight_cost": 0.00,
        "packages_count": 0,
        "gross_weight": 0.00,
        "gross_measurement": 0.00,
        "exporter": {{ "name": "...", "address": "...", "phone": "..." }},
        "consignee": {{ "name": "...", "address": "...", "phone": "..." }}
    }}
    ```
    """

    # Prompt de Factura (Sin cambios, solo se asegura la estructura)
    invoice_prompt = f"""
    **Tarea:** Extraer **todos** los datos clave y la tabla de ítems de una Factura Comercial para un reporte de importación.
    **Rol:** Eres un API de extracción de datos. Tu única función es devolver un objeto JSON.
    **Reglas Estrictas:**
    1. Tu respuesta debe ser **EXCLUSIVAMENTE** un objeto JSON válido.
    2. **NO** incluyas texto explicativo, introducciones, resúmenes ni formato markdown.
    3. Envuelve el JSON en un bloque de código: ```json ... ```.
    4. **INCOTERM:** Busca con alta prioridad el INCOTERM (FOB, CIF). Si no lo encuentras, establece su valor como "NOT_FOUND".
    5. **MONEDA:** Extrae el código de moneda (USD, EUR, etc.).
    6. **ITEMS:** El campo "description" debe ser una consolidación legible de la descripción del producto, el estilo y el color. Los números deben ser extraídos como números (int/float).

    **Formato de Salida JSON Requerido:**
    ```json
    {{
        "invoice_number": "...",
        "invoice_date": "...",
        "incoterm": "...",
        "currency": "...",
        "total_value": 0.00,
        "shipping_cost_invoice": 0.00,
        "exporter": {{ "name": "...", "address": "...", "phone": "..." }},
        "items": [
            {{
                "part_number": "...",
                "description": "...", 
                "quantity": 0,
                "unit_price": 0.00,
                "total_price": 0.00
            }}
        ]
    }}
    ```
    """

    print("Procesando Bill of Lading...")
    bl_data = get_text_from_pdf_multimodal(bl_file, bl_prompt, api_key)
    
    if bl_data.get("error"):
        return bl_data, []

    all_invoices_data = []
    for i, invoice_file in enumerate(invoice_files):
        print(f"Procesando Factura {i+1}...")
        invoice_data = get_text_from_pdf_multimodal(invoice_file, invoice_prompt, api_key)
        
        if invoice_data.get("error"):
            all_invoices_data.append(invoice_data)
            continue
            
        # Agregamos los detalles del Exportador y Consignatario (del BL) a la factura para la consolidación
        exporter_info = _consolidate_party_info(bl_data.get('exporter', {}), invoice_data.get('exporter', {}))
        consignee_info = bl_data.get('consignee', {})
        invoice_data['exporter_details'] = exporter_info
        invoice_data['consignee_details'] = consignee_info
        all_invoices_data.append(invoice_data)

    # Solo proceder con los cálculos si se pudo extraer data de al menos una factura
    if not all_invoices_data or any(inv.get("error") for inv in all_invoices_data):
        return bl_data, all_invoices_data
        
    # Paso 1.5: Traducción Automática de Ítems
    for invoice_data in all_invoices_data:
        items_list = invoice_data.get('items', [])
        
        for item in items_list:
            original_description = item.get('description', '')
            
            # 1. Almacenar la descripción original
            item['description_original'] = original_description
            
            # 2. Realizar la traducción automática
            translated_description = translate_text(original_description, api_key)
            item['description_es'] = translated_description
            
            # Usar la traducción como descripción principal (con fallback)
            if not translated_description.startswith('ERROR_TRADUCCION') and translated_description:
                 item['description'] = translated_description 
            else:
                 item['description'] = original_description


    # Lógica de Cálculo de CIF / Prorrateo (Regla: FOB + Flete BL + 1.5% Seguro)
    freight_cost_bl = float(bl_data.get('freight_cost', 0.0) or 0.0)
    
    # Calcular el valor total FOB de la mercancía (para prorrateo)
    total_fob_shipment = sum(
        float(item.get('total_price', 0)) 
        for inv in all_invoices_data
        for item in inv.get('items', []) if inv.get('items')
    )

    if total_fob_shipment == 0:
        total_fob_shipment = sum(
            float(item.get('quantity', 0)) * float(item.get('unit_price', 0))
            for inv in all_invoices_data
            for item in inv.get('items', []) if inv.get('items')
        )
        
    # Aplicar Prorrateo e Impuestos
    for invoice_data in all_invoices_data:
        items_list = invoice_data.get('items', [])
        if not items_list:
            continue
        
        # Valor total de la mercancía para esta factura (usando el valor extraído/editado)
        total_value_invoice = float(invoice_data.get('total_value', 0.0) or 0.0)

        for item in items_list:
            # Calcular el valor FOB del ítem (Cantidad * Precio Unitario)
            fob_value_item = float(item.get('total_price', 0.0) or (float(item.get('quantity', 0)) * float(item.get('unit_price', 0))))
            
            # Cálculo de Seguros: 1.5% sobre el valor FOB del ítem
            insurance_item = fob_value_item * 0.015
            
            # Cálculo del Flete Proporcional (usando el FLETE TOTAL DEL BL)
            item_proportion = (fob_value_item / total_fob_shipment) if total_fob_shipment > 0 else 0
            freight_item = freight_cost_bl * item_proportion
            
            # Cálculo del CIF Corregido (para el reporte AFORO/DEVA)
            cif_value_corrected = fob_value_item + freight_item + insurance_item
            
            # Guardar los valores de cálculo
            item['fob_value'] = fob_value_item
            item['freight_proportional'] = freight_item
            item['insurance_calculated'] = insurance_item
            item['cif_value_corrected'] = cif_value_corrected
            
            
    # Asignar los detalles consolidados de las partes al BL para facilitar la manipulación en Streamlit
    bl_data['exporter_details'] = _consolidate_party_info(bl_data.get('exporter', {}), all_invoices_data[0].get('exporter', {})) if all_invoices_data and not all_invoices_data[0].get("error") else bl_data.get('exporter', {})
    bl_data['consignee_details'] = bl_data.get('consignee', {})
            
    return bl_data, all_invoices_data