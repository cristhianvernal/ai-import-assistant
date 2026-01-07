import sys
import os
import io
import json
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path to import from src
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.document_processor import process_documents
from src.excel_generator import create_final_excel_report
from src.catalog_manager import CatalogManager

app = FastAPI()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for now (adjust for production)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Import Assistant API"}

@app.post("/api/process")
async def process_files(
    bl_file: UploadFile = File(...),
    invoice_files: List[UploadFile] = File(...),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    
    # Use environment variable if header is not provided
    api_key = x_api_key or os.getenv("GOOGLE_API_KEY")
    
    if not api_key:
        raise HTTPException(status_code=400, detail="Google API Key is required (X-API-Key header or valid .env)")

    try:
        # Read files into BytesIO
        bl_bytes = io.BytesIO(await bl_file.read())
        inv_bytes_list = []
        for inv in invoice_files:
            inv_bytes_list.append(io.BytesIO(await inv.read()))
            
        # Process documents
        bl_data, invoices_data = process_documents(bl_bytes, inv_bytes_list, api_key)
        
        if bl_data.get("error"):
             raise HTTPException(status_code=500, detail=f"AI Error: {bl_data.get('error')}")

        return {
            "bl_data": bl_data,
            "invoices_data": invoices_data
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class GenerateReportRequest(BaseModel):
    bl_data: Dict[str, Any]
    invoices_data: List[Dict[str, Any]]
    catalog: Optional[Dict[str, Any]] = None # Optional initial catalog entries

@app.post("/api/generate-excel")
async def generate_excel(request: GenerateReportRequest):
    try:
        # Initialize catalog manager
        catalog_manager = CatalogManager()
        
        # If catalog entries provided in request, update catalog
        # Warning: CatalogManager expects {desc: code}
        if request.catalog:
            # Assuming simple dict for now, logic might need adjustment based on CatalogManager internals
            # CatalogManager.catalog is a Dict[str, str]
            catalog_manager.catalog.update(request.catalog) 
            
        # Use existing logic to generate excel
        # calculate_prorated_freight logic should ideally be here or in frontend. 
        # For this minimal port, we assume data is already validated/calculated or we add that logic here.
        # But `create_final_excel_report` just takes data. 
        # The frontend should likely handle the prorating display and send final values.
        
        excel_io = create_final_excel_report(request.bl_data, request.invoices_data, catalog_manager)
        
        # Return file
        headers = {
            'Content-Disposition': f'attachment; filename="Reporte_Importacion.xlsx"'
        }
        return StreamingResponse(
            iter([excel_io.getvalue()]), 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
            headers=headers
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/catalog/parse")
async def parse_catalog(file: UploadFile = File(...)):
    """Parses an uploaded Excel/CSV catalog file and returns items."""
    try:
        content = await file.read()
        import pandas as pd
        
        df = pd.DataFrame()
        if file.filename.endswith('.csv'):
             df = pd.read_csv(io.BytesIO(content))
        else:
             df = pd.read_excel(io.BytesIO(content))
             
        if df.empty:
            return {"entries": {}}

        # Simple logic to find columns (reused from app.py logic simplified)
        # For API, we might want to return columns to let user map them, or try auto-detect.
        # Let's try auto-detect simply here or return raw data?
        # Returning normalized entries seems best for "loading".
        
        manager = CatalogManager()
        # We need to reuse the `find_best_column_match` or similar logic. 
        # Since that was in app.py (UI layer), we might need to duplicate it or move it to utils.
        # For now, let's just return a success message or the raw columns to be mapped by frontend.
        
        return {
            "filename": file.filename,
            "columns": df.columns.tolist(),
            "preview": df.head(5).to_dict(orient='records')
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
