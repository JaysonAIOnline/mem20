# Step 13 — Experience Vision & Prototyping

**Type:** human/design (instrument). **Goal:** a north-star experience narrative
and a cheap prototype test plan so 2.0 doesn't ship features nobody adopts.

## Deliverables (templates / drafts)
1. **North-star narrative draft:** "An agent that remembers honestly — recalls
   what really happened, simulates what might, and never confuses the two."
2. **Prototype test plan:** 3 task scenarios (recall a grounded fact; ask a
   counterfactual; spot a contaminated memory) run on a clickable MCP client mock.
3. **Design-system notes:** tool naming consistency, error-message tone, the
   `/ready` probe as a UX "is it safe?" signal.
4. **Success bar for prototype:** ≥ 80% of testers correctly distinguish grounded
   vs simulated recall.

## Engineering input available now
- The engine already separates grounded/simulated at the write path (ADR-0002) —
  the prototype can demonstrate the partition live.
- `tool_calls`/error metrics let the prototype measure task success rates.

## Not executable by agent
Building the mock client and running moderated tests needs design/research.
