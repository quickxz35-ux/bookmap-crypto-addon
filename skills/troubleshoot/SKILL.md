---
name: troubleshoot
description: Investigate unexpected chat agent behavior by analyzing direct debug logs in JSONL files. Use when users ask why something happened, why a request was slow, why tools or subagents were used or skipped, or why instructions/skills/agents did not load.
---

# 🛠 Troubleshoot Skill

This skill is for diagnosing why chat agent behavior did not match expectations.

## Purpose

Use this skill when the user wants to understand:
- why a request took too long
- why a tool or subagent was called or skipped
- why instructions, skill files, or agents did not load
- why a model decision or response was unexpected
- why a tool invocation failed or returned an error

## Data Sources

Analyze direct Copilot Chat debug logs from the session directory:
- `debug-logs/<sessionId>/main.jsonl`
- `debug-logs/<sessionId>/system_prompt_*.json`
- `debug-logs/<sessionId>/tools_*.json`
- `debug-logs/<sessionId>/runSubagent-*.jsonl`

Always start with the main session log and follow `child_session_ref` pointers to related files.

## Troubleshooting Workflow

1. Identify the relevant debug session directory and start with the main log.
2. Search for:
   - errors or failures
   - long durations
   - discovery/load failures for instructions, skills, or agents
   - tool calls and subagent invocations
3. Read only the relevant lines around suspicious events.
4. Correlate user intent, model decisions, and tool results.
5. Summarize the root cause with evidence and concrete next steps.

## Key Focus Areas

- **Tool behavior**: Did the model request a tool? Did the tool call succeed or fail?
- **Model latency**: Which step was slow? Was it the model call or a tool execution?
- **Discovery/loading**: Did a customization file fail to load or get skipped?
- **Schema/format mismatches**: Did the agent use the wrong field name, title property, or config key?
- **Authentication/network**: Are there endpoint or credentials failures in the logs?

## Output Style

When answering, keep it concise and evidence-based:
- state what happened and why
- cite the relevant failure or mismatch
- provide direct remediation steps
- avoid internal log structure details unless they are part of the explanation

## When Not to Use

Do not use this skill for general coding, feature implementation, or non-debugging requests. This skill is specifically for analyzing unexpected agent or tool behavior using debug logs.
