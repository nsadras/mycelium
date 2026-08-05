# Agent Guidance

- Prefer fixing the intended mechanism over adding fallback paths. 
- When changing existing features, do not add backwards compatibility unless explicitly asked.
- When performing test driven development, prefer solutions that are generalizable and serve the end goal of the project, instead of overfitting to the test.
- Check with the user if goals are not clear - ensure that you are aligned with the user's goals and vision before implementing anything.
- Do not run or kill server processes / scripts yourself unless explicitly asked. The user will run these in another shell to view output for debugging.

## Host Ollama access

- The host Ollama server at `http://localhost:11434` may be unreachable from the filesystem/network sandbox even when it is running normally.
- Do not conclude that Ollama is down from a sandboxed connection failure. Verify it with a read-only `/api/tags` request using sandbox/network escalation.
- Run Ollama-dependent tests and benchmarks with the same escalation so they can reach the host loopback interface. Do not start another Ollama process, change the configured URL, or use a fallback model to work around sandbox isolation.
