---
name: verification
trigger: When the user wants to verify the result of a previous action
freedom: medium
gotchas:
  - Checks file existence, output correctness, side effects
  - Some actions don't leave verifiable traces
  - Time-dependent checks may give false negatives
---

action_id: string — ID of action to verify
Returns: verification_result with {exists: bool, valid: bool, details: str}
Verifies: file created, API call succeeded, expected output present.