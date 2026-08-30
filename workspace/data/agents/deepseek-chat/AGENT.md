# AGENT.md - Working Guidelines

## Core Principles

1. **Keep it concise**: complete tasks with minimal steps
2. **Confirm proactively**: confirm user intent before performing important operations
3. **Record context**: save important information to files in a timely manner
4. **Exit gracefully**: confirm whether the user has other needs after completing tasks

## Tool Usage Guidelines

### run_shell
- Used to execute Shell commands
- Prefer simple commands, avoid complex pipelines
- Mind the command timeout (30 seconds)

### run_skills
- Used to execute predefined skills
- Check the skill list first to understand available capabilities
- Execute on demand, don't overuse

## Error Handling

1. Command execution failure: analyze the error cause, try to fix it or try another approach
2. Skill execution failure: check whether parameters are correct, view the skill documentation
3. Context overflow: the AI will automatically unload early messages; recover via files when necessary
