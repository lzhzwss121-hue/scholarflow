# Security Policy

ScholarFlow is currently a local-first research workflow agent. It may process private papers, unpublished research ideas, experiment notes, local databases, logs, and API credentials. Treat all local workspace contents as sensitive.

## Supported Versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

## Reporting A Vulnerability

Please open a private security advisory on GitHub if the issue involves secrets, local data exposure, unsafe file handling, dependency compromise, or unintended external data transfer.

For non-sensitive bugs, use the public bug report template.

## Data Handling Expectations

- Do not commit API keys, `.env` files, local SQLite databases, logs, PDFs, vector stores, private notes, or generated user artifacts.
- Do not upload unpublished papers, private lab materials, transcripts, or application documents as examples.
- External API integrations must preserve source URLs and warnings so users can audit where data came from.
- Future model-provider integrations should make external data transfer explicit and configurable.
- Parsed paper text is stored locally as traceable chunks in the configured ScholarFlow SQLite database. The original uploaded PDF is not persisted, but deleting the PDF file does not delete already indexed chunks; call `DELETE /projects/{project_id}/papers/{paper_id}/rag-index` or remove the local database when the derived text must be erased.
- RAG phase 2 defaults to `SCHOLARFLOW_RAG_EMBEDDING_PROVIDER=local`, which computes deterministic hash embeddings on the same machine. If an operator explicitly selects `openrouter`, the selected paper chunks and each retrieval query are sent to the configured OpenRouter endpoint. Review the provider's retention policy, access controls, billing, and the sensitivity of the papers before enabling it.
- Embedding vectors are derived local data and remain in SQLite until their paper index, project, or database is deleted. Rebuilding an index replaces the old chunk vectors.

## Current Boundary

The v0.1.0 preview does not provide authentication, cloud hosting, paid workspaces, or lab multi-user collaboration. RAG index and chunk endpoints expose locally stored paper text to any client that can reach the API. Do not deploy it as a shared service without adding authentication, access control, rate limits, logging review, and a data retention policy.
