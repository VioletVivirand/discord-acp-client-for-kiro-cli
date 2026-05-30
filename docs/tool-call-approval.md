# Tool-call approval gating — design notes

Status: **not implemented** (future improvement #3). Read this before starting work.

## Current behavior

The bot does **not** gate tools and has no Approve/Deny UI.

- `agent_session.py` `_initialize()` advertises empty `clientCapabilities: {}`.
- No handler is registered for the ACP `session/request_permission` request
  (`JsonRpcClient.on_request` exists in `acp_client.py` but is currently unused).
- `session/update` `tool_call` / `tool_call_update` notifications are only *displayed*
  (`render.py`), never gated.
- Consequence: tools the agent treats as pre-allowed run automatically; anything that
  required interactive approval would hit the unhandled-request path in
  `_handle_request` and get a `-32601 "Method not found"` error (a denial/failure, not
  an approval).

So today, the agent config (`KIRO_AGENT`, set via `kiro-cli agent create`) is the only
control over what tools the bot can use.

## Feasibility: achievable

The ACP spec supports this directly — see
https://agentclientprotocol.com/protocol/tool-calls#requesting-permission

The agent sends `session/request_permission`:

```json
{
  "jsonrpc": "2.0", "id": 5, "method": "session/request_permission",
  "params": {
    "sessionId": "...",
    "toolCall": { "toolCallId": "call_001" },
    "options": [
      { "optionId": "allow-once", "name": "Allow once", "kind": "allow_once" },
      { "optionId": "reject-once", "name": "Reject", "kind": "reject_once" }
    ]
  }
}
```

Client replies with the user's choice:

```json
{ "jsonrpc": "2.0", "id": 5, "result": { "outcome": { "outcome": "selected", "optionId": "allow-once" } } }
```

Option kinds: `allow_once`, `allow_always`, `reject_once`, `reject_always`.
If the turn is cancelled, the client MUST respond with `{ "outcome": { "outcome": "cancelled" } }`.

## Implementation sketch

1. Register `client.on_request("session/request_permission", handler)`.
2. In the handler, post a Discord message with buttons built from the request's `options`
   (map each `optionId`/`name`/`kind` to a button; reuse the pattern in `ui.py`).
3. Await the button click; return `{"outcome": {"outcome": "selected", "optionId": ...}}`,
   or `{"outcome": {"outcome": "cancelled"}}` if the prompt turn was cancelled.
4. Likely advertise the relevant client capability in `_initialize()`.

No architectural blocker — the JSON-RPC transport already supports incoming requests.

## Open question to verify first

Whether `kiro-cli acp` actually emits `session/request_permission` (vs. resolving
everything silently from agent config). The protocol allows it and the bot would be
ready, but if Kiro never sends it, the buttons won't trigger. Test this before building
the UI.
