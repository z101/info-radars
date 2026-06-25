---
name: skill-design
description: |-
  Designs skill specifications before creating or modifying skills.
  Use when starting a new skill, improving an existing one, or needing a
  structured specification for a skill. Triggers: "design a skill",
  "write a spec for this skill", "create a new skill", "improve/refactor
  this skill", "skill blueprint", "skill specification".
---

# Skill Design

## Overview

Write a structured specification before touching any skill code. The spec defines what the skill does, who invokes it, what steps it follows, and how we'll know it works. A skill without a spec is guessing.

Two modes, detected automatically:

- **Greenfield** (no SKILL.md exists) — full 5-phase cycle: Setup → Probe → Spec → Quality → Test
- **Iteration** (SKILL.md exists) — delta mode: read existing, diff analysis, iteration spec

## Mode Selection

Check if the target skill directory already contains a SKILL.md:

```
Target: .agents/skills/<skill-name>/SKILL.md
  ├── Does NOT exist → Greenfield mode
  └── Exists → Iteration mode
```

---

## Greenfield Mode

### Phase 0: Setup

Determine the skill's foundations before any writing.

**0a. Skill Type** — one question at a time:

1. **Discipline** — enforces rules agents skip under pressure. Needs rationalization tables, red flags, bulletproofing.
2. **Technique** — concrete method with steps. Needs clear completion criteria.
3. **Pattern** — mental model, way of thinking. Needs recognition scenarios.
4. **Reference** — API docs, syntax guides. Needs quick-reference tables.

**0b. Invocation Type** — see `GLOSSARY.md` (Context Load, Cognitive Load):

- *Model-invoked*: agent fires it autonomously. Pay Context Load (description in every turn).
- *User-invoked*: only human can fire it. Pay Cognitive Load (human must remember it).

Ask: "Could the agent usefully reach for this autonomously?" If yes, model-invoked. If only by hand, user-invoked.

If user-invoked skills multiply past what a human can remember, consider a Router Skill.

**0c. Naming & Description** (SDO — Skill Discovery Optimization):

- Name: `kebab-case`, gerund form preferred (`processing-pdfs`, `designing-skills`)
- Description: *triggering conditions only* — NEVER summarize the workflow. Start with "Use when..."
- Max 1024 chars; keep under 500 if possible
- Third person, concrete triggers

Lead with your recommendation for each decision, then ask for confirmation.

---

### Phase 1: Probe

Interview the user about the skill they want to build.

**Pattern: grilling-style, one question at a time.**

Walk down each branch of the decision tree, resolving dependencies one-by-one. For each question:

1. State what you understand so far
2. Ask ONE question
3. Provide your recommended answer
4. Wait for feedback before continuing

**Question areas (do NOT ask all at once — each is separate):**

- Who is the user of this skill? (developer, non-technical, yourself?)
- What problem does it solve? (What does the agent do wrong without it?)
- What's the core workflow? (2-3 sentence sketch)
- What's the minimum scope? (What's IN, what's OUT explicitly)
- Are there similar skills already? (check `.agents/skills/` for overlaps)
- What should trigger it? (phrases, symptoms, task types)
- What should it NOT do? (boundaries)

**Divergent phase (expand):**

After the core is clear, generate 2-3 approach variations using these lenses:
- **Simplification:** What's the version that's 10x simpler?
- **Inversion:** What if we inverted the flow?
- **Audience shift:** What if this were for a different class of user?

Then converge: which approach fits best and why?

**Record assumptions explicitly before writing:**

```
ASSUMPTIONS I'M MAKING:
1. [Assumption 1]
2. [Assumption 2]
→ Correct me now or I'll proceed with these.
```

---

### Phase 2: Spec

Write the specification document using `spec-template.md` in this skill's directory.

**2a. YAML Frontmatter**

Write name and description first. The description is the most critical line — it's the only thing the agent sees before deciding to load the skill.

```yaml
---
name: skill-name-with-hyphens
description: |-
  What the skill does (third person). Use when: [trigger conditions].
  Triggers: [keywords that surface during tasks].
---
```

**2b. Structure Sections**

Use the `spec-template.md` as a starting point, but adapt sections to the skill's type:

- **Discipline skills** need: Core Process (steps), Common Rationalizations, Red Flags, Verification
- **Technique skills** need: Core Process (steps), Examples, Quick Reference
- **Pattern skills** need: Overview (the mental model), When to Apply, Before/After examples
- **Reference skills** need: Quick Reference table, Implementation details, Common Mistakes

**2c. Information Hierarchy**

Analyse what goes in SKILL.md vs supporting files:

| In SKILL.md (primary) | In supporting file (disclosed) |
|----------------------|-------------------------------|
| Steps the agent follows in order | API reference >100 lines |
| Completion criteria | Long examples |
| Rationalization table | Glossary definitions |
| Red Flags | Scripts/tools |

Rule: inline what every branch needs; disclose behind a context pointer what only some branches use.

**2d. Completion Criteria & Verification**

Every step must end with a checkable completion criterion. Every verification item requires evidence (test output, build result, output check).

**2e. Rationalizations & Red Flags**

For discipline skills, every skip-worthy step needs a counter in the rationalization table. Red flags are observable signs of violation.

**Save the spec** to `docs/skills-specs/<skill-name>-spec.md`.

---

### Phase 3: Quality

Run the checks from `review-checklist.md` in this skill's directory. The checklist covers:

1. Placeholder scan — no TBD, TODO, "fill in details"
2. Internal consistency — sections don't contradict each other
3. Scope check — focused on one subsystem
4. Ambiguity check — requirements unambiguous
5. YAGNI — no over-engineering
6. No-Op test — every line changes behavior vs default
7. Leading word audit — compact concept anchoring behavior
8. Duplication check — Single Source of Truth
9. Progressive disclosure — SKILL.md under ~500 lines
10. Rationalization completeness — every skip covered

Fix issues inline. No need to re-review — just fix and move on.

**User review gate:**

After your self-review passes, show the spec to the user:

> "Spec written and saved to `<path>`. Please review it and let me know if you want to make any changes before we proceed to the test strategy."

Wait for the user. If changes requested — apply and re-run checks. Only proceed when approved.

**Optional DDD (Doubt-Driven Development) for critical decisions:**

For high-stakes decisions (invocation type, architecture), offer:

1. CLAIM — state the decision in 2-3 lines
2. EXTRACT — smallest reviewable unit (artifact + contract, not your reasoning)
3. DOUBT — invoke fresh-context adversarial reviewer ("find what is wrong, do NOT validate")
4. RECONCILE — classify findings (contract misread / actionable / trade-off / noise)
5. STOP — trivial findings, 3 cycles, or user override

---

### Phase 4: Test Strategy

Map the skill type to the right test method:

| Skill Type | Test Method |
|------------|------------|
| Discipline | Pressure scenarios (time + sunk cost + exhaustion), academic questions |
| Technique | Application scenarios, variation scenarios, missing-information tests |
| Pattern | Recognition scenarios, counter-examples |
| Reference | Retrieval scenarios, gap testing |

**Baseline first:**

The user must see what the agent does WITHOUT the skill before writing it:

> Before creating this skill, run a pressure scenario WITHOUT the skill and document the agent's behavior. What rationalizations does it use? What does it do wrong? This is the RED phase — watch it fail.

**Rationalization table from testing:**

Every excuse the test agent uses goes in the rationalization table of the spec.

**Micro-testing wording:**

For behavior-shaping guidance (prohibitions, recipes), test 5+ reps against a no-guidance control before committing to wording.

---

### Phase 5 (Optional): README

If the user wants a human-readable README for the skill:

- Extract name, description, overview from the spec
- Add usage instructions and prerequisites
- Save as `.agents/skills/<skill-name>/README.md`

Only generate on explicit user request. In Iteration mode, skip — README should already exist.

---

## Iteration Mode

Triggered when target SKILL.md already exists.

### Phase 0a: Read

Read the existing SKILL.md and all supporting files in the skill directory.

### Phase 0b: Diff Analysis

Analyse what the spec needs to cover:

| Category | Meaning | Example |
|----------|---------|---------|
| **Keep** | Works, no changes | Existing steps, accurate descriptions |
| **Modify** | Exists but insufficient | Weak description, missing rationalization |
| **Add** | New requirement | New trigger phrases, new steps |
| **Remove** | Obsolete or harmful | Deprecated instructions, stale references |

### Phase 1-2: Iteration Spec

Same Probe and Spec process as Greenfield, but:
- Probe focuses on *what changed*, not full requirements
- Spec is a *delta document* — only the changes section, plus updated YAML frontmatter if description changed
- Include migration notes: backward compatibility, what existing users of the skill should expect

### Phase 3-4: Same as Greenfield

Quality checks and test strategy against the delta.

---

## Common Rationalizations

| Rationalization | Reality |
|----------------|---------|
| "This skill is too simple for a spec" | Simple skills don't need *long* specs, but they still need acceptance criteria. A 3-line spec is fine. |
| "I'll write the spec after I code it" | That's documentation, not specification. The spec's value is in forcing clarity *before* writing the skill. |
| "The spec will slow down creating the skill" | A 15-minute spec prevents hours of rework on a skill that doesn't solve the right problem. |
| "I know what this skill should do" | Even clear ideas have implicit assumptions. The spec surfaces them. |
| "This is just a small change to an existing skill" | Small changes with no spec drift into incoherent skills over time. Delta spec takes 5 minutes. |
| "I'll add the description later" | The description is the single most important line. If it's not right, agents won't find the skill. |

## Red Flags

- Starting to write SKILL.md without a written spec
- Generating a description that summarizes the workflow (SDO violation)
- Not surfacing assumptions before writing
- Skipping the user review gate
- Treating "TBD" as acceptable in a spec
- Not distinguishing model-invoked from user-invoked
- Same spec template for discipline and reference skills
- Using "should", "probably", "seems to" in completion criteria

## Verification

- [ ] Mode correctly detected (greenfield vs iteration)
- [ ] Skill type identified (discipline/technique/pattern/reference)
- [ ] Invocation type decided (model-invoked vs user-invoked)
- [ ] User confirmed at least one decision before proceeding
- [ ] Spec covers all relevant sections per skill type
- [ ] Description is SDO-optimized (triggers only, no workflow summary)
- [ ] Every skip-worthy step has a rationalization counter
- [ ] Quality checklist passed
- [ ] User reviewed and approved the spec
- [ ] Spec saved to `docs/skills-specs/<name>-spec.md`