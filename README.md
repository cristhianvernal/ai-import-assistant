# AI Import Documentation Assistant

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-App-red.svg)
![AI](https://img.shields.io/badge/AI-Google%20Gemini-orange.svg)

**An intelligent document processing system that automates the extraction, validation, and consolidated reporting of import documentation (Bills of Lading & Commercial Invoices).**

> *Designed to streamline customs operations by reducing manual data entry and minimizing errors through Generative AI.*

---

## Project Overview

This application serves as a comprehensive tool for customs brokers and logistics coordinators. It leverages **Google's Gemini 2.5 Flash** model to perform multimodal extraction (OCR + Text) from complex PDF documents, structuring unstructured data into standardized formats for automatic Excel report generation.

### Key Problems Solved:
*   **Manual Data Entry**: Eliminates hours of typing data from PDFs into Excel.
*   **Complex Validation**: Automatically cross-references data between Bills of Lading (BL) and Invoices.
*   **Cost Calculation**: Automates CIF (Cost, Insurance, Freight) calculations and proportional freight distribution per item.
*   **Standardization**: Converts varied invoice descriptions into standardized Spanish terminology for customs declarations.

## Key Features

*   **Multimodal AI Extraction**:
    *   Processes native PDFs and scanned images.
    *   Intelligently identifies document types (BL vs. Invoice).
    *   Extracts tables, entities (Exporter, Consignee), and financial data.

*   **Human-in-the-Loop (HITL) Validation**:
    *   Interactive UI to review confidence scores.
    *   Side-by-side editing of extracted data before final processing.
    *   Traffic-light system (Green/Yellow/Red) for data quality.

*   **Automated Data Processing**:
    *   **Auto-Translation**: Translates product descriptions from English to Spanish.
    *   **Smart Consolidation**: Merges data from multiple invoices associated with a single BL.
    *   **Logic Engine**: Calculates total weight, package counts, and financial totals automatically.

*   **Excel Generation**:
    *   Programmatically generates `.xlsx` files using `openpyxl`.
    *   Produces "AFORO/DEVA" reports formatted for customs systems.
    *   No legacy dependencies (macros or template files required).

## Technical Architecture

The project is structured for modularity and scalability:

```text
├── src/
│   ├── document_processor.py   # AI Integrations & Optical Character Recognition
│   ├── invoice_generator.py    # Excel Report Generation Logic
│   ├── validation_editor.py    # Streamlit UI Components for Data Editing
│   ├── session_manager.py      # State Management & Persistence
│   ├── error_reporter.py       # Data Quality Analytics
│   └── batch_processor.py      # Bulk Processing Queue
├── app.py                      # Main Streamlit Entry Point
├── requirements.txt            # Project Dependencies
└── README.md                   # Documentation
```

**Tech Stack:** `Python 3.10+`, `Streamlit`, `Google Generative AI SDK`, `Pandas`, `OpenPyXL`, `PDFPlumber`, `PDF2Image`.

## Getting Started

### Prerequisites
*   Python 3.10 or higher.
*   A Google Cloud API Key with access to Gemini models.

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/cristhianvernal/ai-import-assistant.git
    cd ai-import-assistant
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: For Windows, you may need `poppler-utils` installed and added to PATH if using OCR features locally).*

3.  **Configuration:**
    Create a `.env` file in the root directory:
    ```env
    GOOGLE_API_KEY=your_api_key_here
    ```

4.  **Run the application:**
    ```bash
    streamlit run app.py
    ```

## Screenshots

*(Add screenshots of your application here: e.g., The File Upload screen, The Validation Editor, and The Final Excel Output)*

## Disclaimer

This project is a functional prototype developed for portfolio demonstration purposes. While it processes real documents, it is configured with a generic "Sandbox" environment. Sensitive data handling policies should be reviewed before production deployment.

---

*Created by Cristhian Vernal*

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
