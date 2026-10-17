---
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, AskUserQuestion, "Bash(python3 *)"]
tags: [observe]
---

I exported our X-Ray traces to fixtures/traces/xray_batch.json. Our budget is
500 ms per tool call. Where does the time go?
