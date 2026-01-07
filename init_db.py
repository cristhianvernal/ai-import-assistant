import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("Error: DATABASE_URL not found in .env file.")
    exit(1)

print(f"Connecting to database: {DATABASE_URL.split('@')[-1]}") # Print host only for privacy

SQL_SCRIPT = """
-- 1. Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. Create 'work_sessions' table
CREATE TABLE IF NOT EXISTS work_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    user_notes TEXT,
    total_documents INTEGER DEFAULT 0,
    documents_with_errors INTEGER DEFAULT 0,
    processing_status VARCHAR(50) DEFAULT 'in_progress',
    session_data JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- 3. Create 'session_documents' table
CREATE TABLE IF NOT EXISTS session_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES work_sessions(id) ON DELETE CASCADE,
    document_index INTEGER NOT NULL,
    filename VARCHAR(500),
    original_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    edited_data JSONB,
    validation_status VARCHAR(50) DEFAULT 'pending',
    error_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 4. Create Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON work_sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_documents_session_id ON session_documents(session_id);

-- Optional: Triggers
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_work_sessions_modtime ON work_sessions;
CREATE TRIGGER update_work_sessions_modtime
    BEFORE UPDATE ON work_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_session_documents_modtime ON session_documents;
CREATE TRIGGER update_session_documents_modtime
    BEFORE UPDATE ON session_documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
"""

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    print("Executing SQL script...")
    cur.execute(SQL_SCRIPT)
    conn.commit()
    cur.close()
    conn.close()
    print("Success: Database tables created successfully.")
except Exception as e:
    print(f"Error executing script: {e}")
    exit(1)
