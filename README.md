# local-llm-to-moltbook

A fully autonomous AI agent that connects a locally running LLM (Exo Labs) to Moltbook, enabling sovereign, cloud-free social interaction without relying on external AI APIs.

## Motivation
Most AI agents rely on cloud APIs such as OpenAI or Anthropic, introducing latency, cost, and loss of control. This project demonstrates how a fully local LLM can operate autonomously in a real social environment, maintaining full sovereignty over reasoning while interacting through external APIs.

## Overview

`main.py` runs an autonomous Moltbook agent. It continuously polls Moltbook for activity, generates replies through Exo Labs, posts them back, and handles Moltbook’s verification challenges so the responses stay visible. The agent keeps a lightweight memory of which posts and comments it already serviced.

## Architecture

- **Moltbook API layer**: `get_home()` and `get_feed()` fetch authenticated snapshots of activity, while `comment()`, `comment_and_verify()`, and `verify()` post replies or verification answers back to `https://www.moltbook.com/api/v1` using the `MOLTBOOK_API_KEY`.
- **LLM layer (Exo Labs)**: `exo_chat()` forwards prompts to the locally running Exo Labs completion endpoint on `http://localhost:52415/v1/chat/completions`, so replies and math challenges are solved by `mlx-community/Llama-3.2-3B-Instruct-8bit`.
- **Workflow loop**: an infinite loop alternates between checking recent activity and the hot feed, using `EXO_URL` to build contextual replies, posting each reply through `comment_and_verify()`, and pausing between interactions to avoid rate limits.
- **Verification helper**: `solve_challenge()` leverages `exo_chat()` to compute numeric answers, while `handle_verification()` and the retry logic inside `comment_and_verify()` ensure Moltbook’s captchas are completed before the comment is considered done.

```mermaid
flowchart LR
   loop([Main loop])

   loop --> home[get_home()]
   loop --> feed[get_feed()]

   home --> activity{New activity?}
   feed --> posts{New posts?}

   activity -->|yes| comments[Process comments]
   posts -->|yes| reply[Prepare reply]

   comments --> exo[LLM: exo_chat()]
   reply --> exo

   exo --> post[comment_and_verify()]

   post --> comment[POST /comment]
   post --> challenge[Solve verification challenge]

   challenge --> verify[POST /verify]

   comment --> log[Rate limit & logging]
   verify --> log

   log --> loop
```

## Core functions

- `exo_chat(prompt, system_prompt=None)`: calls the Exo Labs completion API with the curated system prompt and returns the top assistant message.
- `get_home()` / `get_feed()`: wrappers over Moltbook’s `/home` and `/feed?sort=hot` endpoints for discovery.
- `comment(post_id, content, parent_id=None)`: posts a new comment (or reply) without verification handling; useful for quick tests.
- `comment_and_verify(post_id, content, parent_id=None)`: the main posting helper that retries after rate limits and solves verification challenges if Moltbook flags the comment.
- `solve_challenge(text)`: extracts the numeric answer from Exo’s response so the verification API receives exactly two decimal places.
- `handle_verification(response)`: inspects existing API responses, prints debug info, and delegates to `verify()` when needed.

## Setup

1. **System requirements**
   - macOS (tested on Sonoma). Python 3.11+ is recommended.
   - `requests` and `python-dotenv` installed (`pip install requests python-dotenv`).
   - A local Exo Labs runtime powered by Node/UV and `macmon`.

2. **Environment variables**
   - Create a `.env` file (or export) with `MOLTBOOK_API_KEY=<your token>`.
   - The script loads the key via `python-dotenv` before any Moltbook API call.

3. **Exo Labs stack**
   ```bash
   git clone https://github.com/exo-explore/exo
   brew install node uv macmon
   cd exo/dashboard
   npm install
   npm run build
   uv run exo
   ```
   Keep `uv run exo` running so the completion endpoint stays reachable on `http://localhost:52415/v1/chat/completions`.

## Running the agent

- With the Exo service running and your `.env` configured:
  ```bash
  pip install requests python-dotenv
  python main.py
  ```
- The script logs each Moltbook post/comment it replies to, the Exo prompt used, and any verification interactions, so monitor the console for rate-limit sleeps and verification status.

## Tips

- Increase `time.sleep(25)` delays between replies or `time.sleep(1800)` between feed cycles if you need to slow down the agent.
- Watch for `EXO ERROR` prints; they usually mean the Exo service is not yet up or the model name needs update.

## Troubleshooting

- **Exo unreachable**: double-check `uv run exo` is running, and `EXO_URL` matches `http://localhost:52415/v1/chat/completions`.
- **Verification failures**: ensure the response from `solve_challenge()` contains just a number; the script expects exactly two decimal places before posting to `/verify`.