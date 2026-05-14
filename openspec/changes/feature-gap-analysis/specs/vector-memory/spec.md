## ADDED Requirements

### Requirement: SQLite storage backend

The system SHALL store memories in SQLite database with FTS support.

#### Scenario: SQLite database initialization
- **WHEN** memory system initializes
- **THEN** SQLite database is created at `~/.agentcraft/memory.db`

#### Scenario: Memory table schema
- **WHEN** database is created
- **THEN** table `memories` exists with columns: id, name, type, content, embedding, created_at

#### Scenario: FTS index
- **WHEN** database is created
- **THEN** FTS5 virtual table `memories_fts` is created for full-text search

### Requirement: Vector embedding support

The system SHALL generate embeddings for memory content and store in vector index.

#### Scenario: Embedding generation
- **WHEN** memory is saved
- **THEN** embedding is generated from content using configured embedding model

#### Scenario: Vector index
- **WHEN** SQLite database is created
- **THEN** sqlite-vec extension is loaded for vector similarity search

#### Scenario: Similarity search
- **WHEN** user queries memory with text
- **THEN** system returns memories ordered by embedding similarity score

### Requirement: Hybrid search

The system SHALL support hybrid search combining FTS and vector similarity.

#### Scenario: Full-text search only
- **WHEN** user queries with `mode: "fts"`
- **THEN** only FTS search is performed

#### Scenario: Vector search only
- **WHEN** user queries with `mode: "vector"`
- **THEN** only vector similarity search is performed

#### Scenario: Hybrid search
- **WHEN** user queries with `mode: "hybrid"` (default)
- **THEN** results combine FTS and vector search with weighted scoring

### Requirement: Embedding model configuration

The system SHALL support both local and remote embedding models.

#### Scenario: Local embedding model
- **WHEN** configuration specifies `embedding: "local:sentence-transformers"`
- **THEN** embeddings are generated using local model

#### Scenario: Remote embedding API
- **WHEN** configuration specifies `embedding: "openai:text-embedding-3-small"`
- **THEN** embeddings are generated via OpenAI API