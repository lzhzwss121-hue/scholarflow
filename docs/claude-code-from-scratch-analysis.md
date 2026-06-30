# Claude Code From Scratch Analysis

Reference repository: `Windy3f3f3f3f/claude-code-from-scratch`

Reference commit reviewed: `5e67477 fix(agent): move auto-compact to turn boundary`

## What The Project Implements Well

The project is a compact teaching implementation of a Claude Code style coding agent. Its strongest design choices are not tied to coding only; they are general agent product patterns that ScholarFlow can reuse.

## Agent Loop

The core loop follows a clear pattern:

```text
user request
  -> model response stream
  -> detect tool calls
  -> check permission
  -> execute safe tools early or in parallel
  -> persist large results
  -> feed tool results back
  -> repeat until no more tools
```

For ScholarFlow, the useful lesson is that research workflows should expose the loop, not hide it. Users should see when the agent is retrieving papers, reading paper cards, writing memory, generating a summary, or waiting for confirmation.

## Frontend / UI Lessons

The repository is mostly CLI-based, but `src/ui.ts` has a useful interaction model:

- Tool calls are shown with an icon and a short summary.
- Long tool outputs are truncated in the visible UI.
- File edits receive a specialized diff-like display.
- Plan approval is shown as a bounded review block with explicit options.
- Sub-agent work is visually bracketed with start/end markers.
- Token and cost usage are surfaced after each run.

ScholarFlow should adapt this into web UI cards:

- Tool Timeline should show recognizable icons and concise summaries.
- Direction Review and Paper Memory should show artifacts and memory hits as first-class execution evidence.
- The dashboard should show agent runtime state: plan mode, memory recall, context handling, and artifact persistence.

## Memory Design

The memory system uses a lightweight index plus semantic selection:

```text
memory files
  -> MEMORY.md manifest
  -> model selects relevant memories
  -> selected memories are injected into the next turn
```

ScholarFlow has already adapted the core idea into `Paper Memory Bank`:

```text
paper cards
  -> paper_memories
  -> direction_memories
  -> retrieve 3-8 related memories
  -> answer from retrieved evidence
```

The next upgrade should replace keyword ranking with embedding/vector retrieval while preserving the current structured memory schema.

## Context Management

The project has a 4-layer context strategy:

- Budget large tool results.
- Snip stale or duplicate tool results.
- Microcompact old results after idle time.
- Auto-compact near context-window limits.

ScholarFlow should not push all 30 papers into a model prompt. The equivalent design is:

- Store every paper card as structured memory.
- Store every round summary as an artifact.
- Store direction memory as a cumulative snapshot.
- Retrieve only the 3-8 most relevant paper memories for a follow-up question.

## Permission And Plan Mode

The plan mode design is useful because it separates analysis from action:

- read-only exploration
- plan writing
- user approval
- execution mode

ScholarFlow already has Research Plan Mode, but it should make the approval state more visible in the UI and keep destructive or external actions behind explicit confirmation in later phases.

## Borrowed Into ScholarFlow Now

This review directly informs the following ScholarFlow changes:

- Add an Agent Runtime panel to the dashboard.
- Make tool timeline entries more readable with tool-specific icons.
- Surface memory recall and context strategy as explicit runtime signals.

## Future Borrowing Candidates

- Streaming progress events for long direction-review runs.
- A true approval gate before external API spending or bulk PDF downloads.
- Sub-agent style workers for retrieval, paper reading, novelty checking, and experiment planning.
- Context compaction artifacts for long research projects.
- Tool-result persistence for large PDF parses and benchmark logs.
