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

## Current Boundary

The v0.1.0 preview does not provide authentication, cloud hosting, paid workspaces, or lab multi-user collaboration. Do not deploy it as a shared service without adding authentication, access control, rate limits, logging review, and a data retention policy.
