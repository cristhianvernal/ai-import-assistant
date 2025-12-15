import sys
import os
import io

# Add current directory to path
sys.path.append(os.getcwd())

def test_invoice_generator():
    print("Testing InvoiceGenerator...")
    try:
        from src.invoice_generator import InvoiceGenerator
        print("Import successful.")
        
        generator = InvoiceGenerator()
        
        # Test mock products
        products = generator.load_products_from_template()
        if products.empty:
            print("Error: Products DB is empty")
            return
            
        print(f"Products DB loaded: {len(products)} items.")
        
        # Test data generation
        mock_validated = {
            "cliente_preview": "Test Client",
            "rtn_preview": "1234567890",
            "direccion_preview": "Test Address",
            "bl_data": {"bl_number": "BL-TEST-001"}
        }
        mock_selected = {
            "Servicio de Trámite Aduanal": {"quantity": 1, "price": 100.0}
        }
        
        context = generator.generate_invoice_data(mock_validated, mock_selected)
        print(f"Context generated. Total: {context['total_pagar']}")
        
        # Test Excel creation
        excel_bytes = generator.create_invoice_excel(context)
        if isinstance(excel_bytes, io.BytesIO) and excel_bytes.getvalue():
             print("SUCCESS: Excel generated successfully.")
        else:
             print("Error: Excel generation failed to return valid bytes.")

    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_invoice_generator()
