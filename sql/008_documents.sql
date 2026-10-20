-- Document chunks for retrieval (RAG). Needs the pgvector extension, which the
-- pgvector/pgvector:pg16 image provides.
create extension if not exists vector;

create table if not exists doc_chunks (
    id          bigserial primary key,
    source      text not null,       -- file name or URL of the document
    title       text not null,
    page        integer,             -- null for sources without pages
    chunk_index integer not null,    -- position of the chunk in its source
    content     text not null,
    embedding   vector(384) not null,
    unique (source, chunk_index)
);

-- Approximate nearest-neighbour index for cosine distance (the <=> operator).
create index if not exists doc_chunks_embedding_idx
    on doc_chunks using hnsw (embedding vector_cosine_ops);
