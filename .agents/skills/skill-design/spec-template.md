# Spec: [Skill Name]

## Objective
What does this skill do and why does it exist? Who is the user? What problem does it solve?

## Skill Type
- **Type:** discipline | technique | pattern | reference
- **Category:** engineering | productivity | misc | personal

## Invocation
- **Invocation:** model-invoked | user-invoked
- If model-invoked: what triggers should fire it?
- If user-invoked: is a router skill needed?

## YAML Frontmatter

```yaml
---
name: skill-name-with-hyphens
description: |-
  First sentence: what the skill does (action-oriented, third-person).
  Use when: [specific trigger conditions — symptoms, task types, phrases].
  Triggers: [activation keywords].
---
```

## Overview
One-two sentences explaining what this skill does and why it matters.

## When to Use
- Bullet list of triggering conditions
- When NOT to use (exclusions)
- Decision flowchart (if non-obvious)

## Core Process / Workflow
The main workflow, broken into numbered steps or phases. Each step ends with a Completion Criterion — a checkable, ideally exhaustive condition.

## Reference & Supporting Files
What goes in SKILL.md vs supporting files:

| Content | Location | Why |
|---------|----------|-----|
| Core steps | SKILL.md | Primary workflow |
| [reference X] | SKILL.md inline | Under 50 lines |
| [reference Y] | supporting-file.md | Over 50 lines |

## Completion Criteria

- [ ] Criterion 1: [checkable condition]
- [ ] Criterion 2: [checkable condition]
- [ ] Criterion 3: [checkable condition]

## Common Rationalizations

| Rationalization | Reality |
|-----------------|---------|
| Excuse agents use to skip steps | Why the excuse is wrong |

## Red Flags

- Behavioral patterns indicating the skill is being violated
- Observable signs during execution

## Verification

After following the skill's process, confirm:

- [ ] Item 1
- [ ] Item 2
- [ ] Item 3

## Boundaries
- Always do: [list]
- Ask first: [list]
- Never do: [list]

## Test Strategy

### Skill Type → Test Method
- **Discipline:** Pressure scenarios (time + sunk cost + exhaustion)
- **Technique:** Application scenarios, variation scenarios
- **Pattern:** Recognition scenarios, counter-examples
- **Reference:** Retrieval scenarios, gap testing

### Key Rationalizations to Bulletproof
- Excuse 1
- Excuse 2

### Baseline Failure (without skill)
What does the agent do wrong without this skill?

## Open Questions
- [Question 1]
- [Question 2]