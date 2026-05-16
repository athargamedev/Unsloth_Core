# Onyx 10X Workflow Assistant Plan

## Onyx Documentation Insights (APIs we can leverage)

### Chat API (/chat/send-chat-message)
- Send messages with persona_id (agent) selection
- Streaming and non-streaming responses
- LLM override (model, temperature, etc.)
- File attachments
- Internal search filters (document sets, tags, metadata)
- Tool integration
- Multi-turn conversations

### Agents API (/persona - CRUD)
- System prompt + task prompt + starter messages
- Document set assignment for scoping knowledge
- Tool assignment (code execution, web search, etc.)
- LLM model provider/version override
- Recency bias, relevance filtering
- User/group access control

### Ingestion API (/onyx-api/ingestion)
- Document with sections, metadata, source
- Document sets for categorization
- cc_pair_id for connector association
- Async indexing

### Search API (/api/admin/search or /api/search)
- Document set filtering
- Metadata/tag filtering
- Query expansion control

### Onyx Built-in Tools
1. internal_search (ID=1)
2. generate_image (ID=2)
3. web_search (ID=3)
4. open_url (ID=7)
5. read_file (ID=9)
6. python/code_interpreter (ID=6)
7. coding_agent (ID=11)

---

## Current Unsloth_Core Onyx Integration
- OnyxClient: Only supports search + health
- onyx_index_repo.py: Basic ingestion, only repo files
- Default technique = "onyx" for NPC dataset generation
- Workflow Assistant uses "docs" technique (not onyx)
- admin search mode (to avoid LLM timeout)

## Current Workflow Assistant
- Uses "docs" technique with static corpus manifest
- 16 source documents
- ~58 examples total
- Manual rule-based answer generation
- No Onyx RAG grounding
- Runs as a fine-tuned model (not interactive Onyx agent)

---

# The 10x Improvement Opportunities

## 1. Switch to Onyx RAG-based dataset generation
Instead of static manifest extraction, use Onyx retrieval to ground answers in real indexed content.

## 2. Create a dedicated Onyx Agent
Create an "Unsloth_Core WorkflowAssistant" agent in Onyx with:
- The system prompt from the workflow assistant spec
- Document sets scoped to repo docs
- Tools: internal_search, code_interpreter (maybe), search

## 3. Upgrade OnyxClient to full API client
Add Chat API, Agents API, full Ingestion API, Document Set management

## 4. Set up automated indexing
- Index all checked-in docs into Onyx
- CI/CD for doc updates
- Document sets per subject/NPC

## 5. Interactive Onyx-powered assistant
Use the Onyx Chat API to make an interactive assistant that can:
- Answer questions in real-time using RAG
- Execute code for validation/testing
- Query the repo knowledge base

## 6. Multi-turn conversational dataset generation
Use Onyx as a RAG engine for generating better training data - ask multi-turn questions, use actual retrieval results.

## 7. Feedback loop integration with Onyx
When the feedback loop identifies weak areas, use Onyx to find and index relevant docs, then regenerate.