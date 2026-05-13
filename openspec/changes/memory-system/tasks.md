## 1. Core Module - Memory Persistence

- [x] 1.1 Create `sessions/memory_persistence.py` with MemoryType enum
- [x] 1.2 Implement MemoryEntry dataclass (name, description, type, content, created_at)
- [x] 1.3 Implement MemoryStore class with save/load/list/delete methods
- [x] 1.4 Implement project path hash function for storage location
- [x] 1.5 Implement MEMORY.md index file generator with 200-line limit

## 2. Memory Extraction

- [x] 2.1 Implement MemoryExtractor class with LLM-based extraction
- [x] 2.2 Add extraction prompts for feedback and project memory types
- [ ] 2.3 Implement session-end extraction hook in gateway.py (deferred - manual trigger via CLI)

## 3. Memory Tools

- [x] 3.1 Create `tools/memory_tools.py` with remember/forget/recall tools
- [x] 3.2 Implement remember tool (explicit save with confirmation)
- [x] 3.3 Implement forget tool (delete with error handling)
- [x] 3.4 Implement recall tool (list all or query specific)

## 4. CLI Integration

- [x] 4.1 Add `/remember <content>` slash command to cli.py
- [x] 4.2 Add `/forget <name>` slash command to cli.py
- [x] 4.3 Add `/recall [name]` slash command to cli.py
- [x] 4.4 Add memory loading at session start (MEMORY.md to context)

## 5. Gateway Integration

- [x] 5.1 Add memory loading in lifespan startup
- [x] 5.2 Add POST /memory/save API endpoint
- [x] 5.3 Add GET /memory/list API endpoint
- [x] 5.4 Add DELETE /memory/{name} API endpoint
- [x] 5.5 Update sessions/__init__.py to export memory persistence module

## 6. Testing

- [x] 6.1 Test memory save/load/delete operations
- [x] 6.2 Test MEMORY.md index generation and truncation
- [x] 6.3 Test memory loading at session start
- [x] 6.4 Test CLI slash commands for memory operations