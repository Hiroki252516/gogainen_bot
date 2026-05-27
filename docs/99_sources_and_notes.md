# 99. Sources and Notes

## Codex app-server

Official docs state that Codex app-server is the interface Codex uses for rich clients such as the VS Code extension, and exposes authentication, conversation history, approvals, and streamed agent events.

Source:
- https://developers.openai.com/codex/app-server

## Codex authentication

Codex supports Sign in with ChatGPT and API key authentication. This project must use Sign in with ChatGPT, not OpenAI API keys.

Sources:
- https://developers.openai.com/codex/auth
- https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan

## app-server protocol

Codex app-server supports JSON-RPC-like messages over stdio, WebSocket, and Unix sockets. The WebSocket transport is documented as experimental/unsupported; therefore, the implementation must isolate it behind an adapter.

Sources:
- https://developers.openai.com/codex/app-server
- https://developers.openai.com/codex/cli/reference

## Auth flows

Open source app-server README documents:

- `account/read`
- `account/login/start` with `apiKey`, `chatgpt`, and `chatgptDeviceCode`
- `account/login/completed`
- `account/logout`

Source:
- https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md

## Project research notes

The research plan is based on the uploaded decks:

- 5月18日(テーマ変更).pptx
- 5月25日進捗報告.pptx

Key research assumptions:

- Main comparison is not AI vs no AI, but static AI support vs log-adaptive AI support.
- Main metrics are recurrence rate, L0 answer rate, and transfer rate.
- Final misconception taxonomy is M1〜M4.
