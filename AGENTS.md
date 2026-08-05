# Agent Guidance

- Prefer fixing the intended mechanism over adding fallback paths. 
- When changing existing features, do not add backwards compatibility unless explicitly asked.
- When performing test driven development, prefer solutions that are generalizable and serve the end goal of the project, instead of overfitting to the test.
- Check with the user if goals are not clear - ensure that you are aligned with the user's goals and vision before implementing anything.
- Do not run or kill server processes / scripts yourself unless explicitly asked. The user will run these in another shell to view output for debugging.
