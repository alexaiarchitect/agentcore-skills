---
max_turns: 16
allowed_tools: [Read, Glob, Grep, Skill, AskUserQuestion, Write, Edit, "Bash(python3 *)"]
tags: [gateway, dry-run]
---

Put an AgentCore Gateway in front of our existing Lambda MCP server, with our
Cognito users. Show me exactly what you would write first — don't write
anything yet.
