# User-run device acceptance

**Status: unverified.** The user owns these checks after implementation. No app
services were started for the audit. The two-pass Build integration is committed as `6c97904`, with correction ordering fixed in `6e21c72`. The affected UI suite
passed 24 tests, lint and build; those checks do not establish real browser/audio/network behavior.

Use your normal service startup and the existing
[private-network configuration](../README.md#private-wi-fi-and-tailscale-access).
Run the checks on the host browser and each intended Wi-Fi/Tailscale device.
Use a short disposable recording and conversation so changes are easy to inspect.

| Check | Acceptance |
|---|---|
| Chat and capture | Send a message, navigate away/back, and reload. Both turns survive; errors preserve an unsent draft. Capture is durable, while new searchable claims appear after Build Memory. |
| Memory inspection | Build the new source, ask for a supported detail, open its evidence and source. The cited source and segment match the displayed assertion. |
| Navigation under delay | Switch between two chats/pages/recordings while requests are pending, including A→B→A. A late response cannot replace the currently selected content or clear a newer draft. |
| Correction dates | Propose a correction containing a relative date. The interpreted date and source/reference appear before saving; cancel preserves the original, and save retains the reviewed interpretation. |
| Shared evidence and manual edits | Open two view items citing the same statement. Edit or move one item, then Build a related source. Its manual text and the other item remain inspectable with their original citations. |
| Identity and page review | Review one occurrence as “no page.” That evidence disappears from the subject's page; independently useful evidence can still support the page. |
| Recording and playback | Make a short microphone recording with the device's recording app, upload it in Engram, and play/seek it. The current Engram flow is upload-based; this does not assume an in-app microphone recorder. Audio requests work from the same UI origin on each network. |
| Transcript admission | Process the clip; review/correct transcript, speakers and meeting time, then finalize. Edits lock during saving. The source is saved before the optional summary; Build Memory makes its claims searchable. |
| Failure and retry | Exercise a recoverable failed request, then retry. Draft edits remain available, errors identify the failed action, and retries do not duplicate an admitted source. Unavailable speaker detection/summary is reported separately from durable source saving. |
| Recording deletion | Delete the disposable recording after inspecting its admitted source. The UI explains that already admitted memory remains; deletion cannot race playback/processing into corrupt storage. Retract the admitted source separately if desired. |

Record device, OS/browser, connection, result and any reproducible failure below.
An unchecked row stays unverified; it is not an implicit pass.

| Device/browser | Connection | Checks passed | Failure or unverified check |
|---|---|---|---|
| | Host | | |
| | Wi-Fi | | |
| | Tailscale | | |

Semantic limitations and benchmark completion are tracked separately in the
[implementation plan](audit_implementation_2026_09_15.md) and the
[current product check](compact_product_result_2026_09_18.md).
