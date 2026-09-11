# Lantern

## Overview

Lantern is Maya's private local desktop application for searchable meeting memory. `[f-lantern-purpose · chat-01-s01, meeting-02-s01]`

## Objective

- Evaluate correction effort and whether every memory can be traced to transcript evidence. `[f-pilot-metrics · meeting-02-s04]`

## Current Status

- The desktop prototype supports speaker-name correction and links memories to transcript segments. `[f-prototype-status · meeting-05-s02]`
- The September 28 pilot build is ready for Priya's three teams. `[f-pilot-readiness · meeting-06-s02]`

## Requirements & Constraints

- Meetings may contain sensitive client information. `[f-lantern-privacy · chat-01-s03]`
- Audio and transcripts remain on the laptop unless explicitly exported; cloud transcription is rejected. `[f-lantern-local-only · chat-02-s01, meeting-03-s03]`
- Speaker-name correction is required for the pilot. `[f-speaker-correction · meeting-01-s03, meeting-01-s04]`
- Participants must confirm consent before every recording; the consent gate is a release blocker. `[f-consent-gate · chat-03-s03, meeting-05-s03, meeting-05-s04]`

## Decisions

- Build a desktop application, not a browser extension. `[f-lantern-form · chat-01-s03]`
- Use a local WhisperX pipeline for the pilot. `[f-whisperx-decision · chat-02-s03, meeting-03-s02]`

## Next Steps & Deadlines

- Run the first pilot on September 28, 2026; it moved because recruitment required more time. `[f-pilot-date-current · chat-05-s01]`
- After the pilot, decide whether transcript embeddings can remain fully inspectable. `[f-embedding-question · meeting-06-s03]`

## People & Organizations

- [[you|Maya]] owns the desktop prototype and consent flow. `[f-maya-lantern-role · meeting-01-s02]`
- [[priya-raman|Priya Raman]] owns pilot recruitment and evaluation. `[f-priya-role · meeting-01-s01, meeting-02-s03, chat-05-s02]`
- [[luis-ortega|Luis Ortega]] owns the local transcription pipeline and WhisperX packaging. `[f-luis-role · meeting-02-s02]`

## Timeline

- September 10, 2026 — Working-prototype review. `[f-prototype-review · meeting-01-s05]`
- September 22, 2026 — Initial pilot target; superseded by September 28. `[f-pilot-date-old · meeting-02-s06]`
- September 18, 2026 — Maya fixed and closed LANTERN-42, which had allowed recording without consent when reopening recent meetings. `[f-consent-bug · tool-03-s01, meeting-06-s01]`

## Research & References

- WhisperX became the leading candidate because it supports local alignment and diarization, pending a benchmark. `[f-whisperx-research · tool-01-s01, chat-03-s02]`
- The benchmark ran faster than real time on Maya's laptop and produced usable speaker labels after correction. `[f-whisperx-benchmark · meeting-03-s01]`
