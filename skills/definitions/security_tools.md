---
name: security_tools
trigger: When the user asks about security scanning, vulnerability analysis, penetration testing, bug bounty, or cybersecurity
freedom: low
gotchas:
  - Requires target path to exist
  - Large codebases may timeout — use scan_type=quick for fast scan
  - WSL Kali tools must be installed separately for advanced testing
---

Run `cyber.mythos_pipeline.run(target, scan_type)` for full 7-agent analysis:
- RECON → HUNTER → ADVERSARIAL → EXPLOIT → TRIAGE → AI_SECURITY → SUPPLY_CHAIN

Returns: JSON report with CVSS scores, confidence tiers (confirmed/plausible/theoretical), and finding_id for each vulnerability.

Quick modes: scan_type=recon (Phase 1 only), scan_type=secrets (supply chain only)