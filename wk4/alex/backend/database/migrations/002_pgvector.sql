CREATE TABLE IF NOT EXISTS research_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(128) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    embedding vector NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_documents_tenant
    ON research_documents (tenant_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE research_documents TO alex_app;
