import pandas as pd
import io
from typing import Dict, Any, Optional

class CatalogManager:
    """
    Gestiona el catálogo de descripciones de productos y sus posiciones arancelarias.
    Se almacena como {descripcion_normalizada: codigo_arancelario}.
    """
    def __init__(self):
        # Catálogo por defecto (se elimina el hardcoding en excel_generator)
        self.catalog: Dict[str, str] = {
            'blusa para dama': '6206.40.00.00.00',
            'calzado para dama': '6404.19.90.00.00',

        }

    def _normalize_description(self, description: str) -> str:
        """Normaliza la descripción para la búsqueda (minúsculas, sin espacios extra)."""
        if not description:
            return ""
        # Limpia y normaliza (ej. 'Blusa para Dama   ' -> 'blusa para dama')
        return ' '.join(description.lower().strip().split())

    def load_catalog_from_df(self, df: pd.DataFrame, desc_col: str, arancel_col: str):
        """
        Carga el catálogo desde un DataFrame de pandas.
        Los datos cargados sobrescriben o complementan el catálogo existente.
        """
        if df.empty or desc_col not in df.columns or arancel_col not in df.columns:
            print("Advertencia: DataFrame de catálogo inválido o columnas no encontradas.")
            return

        new_entries = {}
        for _, row in df.iterrows():
            desc = str(row[desc_col]) if pd.notna(row[desc_col]) else ""
            arancel = str(row[arancel_col]) if pd.notna(row[arancel_col]) else "PENDIENTE"
            
            # Solo guarda entradas que tienen una descripción y un arancel válido
            if desc and arancel != "PENDIENTE":
                normalized_desc = self._normalize_description(desc)
                new_entries[normalized_desc] = arancel
        
        # Actualiza el catálogo interno
        self.catalog.update(new_entries)
        print(f"INFO: Catálogo cargado. Total de entradas: {len(self.catalog)}")

    def get_arancel_code(self, description_es: str) -> str:
        """
        Busca el código arancelario más probable basado en la descripción traducida.
        Prioriza la coincidencia de subcadenas normalizadas.
        """
        if not description_es:
            return 'PENDIENTE'
        
        normalized_query = self._normalize_description(description_es)
        
        # 1. Búsqueda por coincidencia exacta
        if normalized_query in self.catalog:
            return self.catalog[normalized_query]

        # 2. Búsqueda por subcadena (útil para "blusa para dama, roja" -> "blusa para dama")
        # Se itera sobre las claves del catálogo para ver si están contenidas en la descripción (más amplia)
        for key, code in self.catalog.items():
            if key in normalized_query:
                return code
        
        return 'PENDIENTE'

    def get_all_entries(self) -> Dict[str, str]:
        """Devuelve el catálogo completo (descripción normalizada: código)."""
        return self.catalog