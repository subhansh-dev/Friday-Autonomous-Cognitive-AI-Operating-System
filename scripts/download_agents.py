# -*- coding: utf-8 -*-
"""
download_agents.py — Download agency-agents markdown files from GitHub
Fetches specialized AI agent personality definitions from
https://github.com/msitarzewski/agency-agents into friday/agents/
"""
import os
import sys
import urllib.request
import time

BASE_URL = "https://raw.githubusercontent.com/msitarzewski/agency-agents/main"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AGENTS_DIR = os.path.join(SCRIPT_DIR, "..", "agents")

# Agent definitions: (category, filename, local_name)
AGENTS = [
    # Engineering (19)
    ("engineering", "engineering-ai-engineer.md",                    "ai_engineer.md"),
    ("engineering", "engineering-backend-architect.md",              "backend_architect.md"),
    ("engineering", "engineering-code-reviewer.md",                  "code_reviewer.md"),
    ("engineering", "engineering-codebase-onboarding-engineer.md",   "codebase_onboarding_engineer.md"),
    ("engineering", "engineering-data-engineer.md",                  "data_engineer.md"),
    ("engineering", "engineering-database-optimizer.md",             "database_optimizer.md"),
    ("engineering", "engineering-devops-automator.md",               "devops_automator.md"),
    ("engineering", "engineering-frontend-developer.md",             "frontend_developer.md"),
    ("engineering", "engineering-git-workflow-master.md",            "git_workflow_master.md"),
    ("engineering", "engineering-incident-response-commander.md",    "incident_response_commander.md"),
    ("engineering", "engineering-mobile-app-builder.md",             "mobile_app_builder.md"),
    ("engineering", "engineering-rapid-prototyper.md",               "rapid_prototyper.md"),
    ("engineering", "engineering-security-engineer.md",              "security_engineer.md"),
    ("engineering", "engineering-senior-developer.md",               "senior_developer.md"),
    ("engineering", "engineering-software-architect.md",             "software_architect.md"),
    ("engineering", "engineering-sre.md",                            "sre.md"),
    ("engineering", "engineering-technical-writer.md",               "technical_writer.md"),
    ("engineering", "engineering-threat-detection-engineer.md",      "threat_detection_engineer.md"),
    ("engineering", "engineering-voice-ai-integration-engineer.md",  "voice_ai_integration_engineer.md"),
    # Testing (5)
    ("testing", "testing-accessibility-auditor.md",                  "accessibility_auditor.md"),
    ("testing", "testing-api-tester.md",                             "api_tester.md"),
    ("testing", "testing-performance-benchmarker.md",                "performance_benchmarker.md"),
    ("testing", "testing-test-results-analyzer.md",                  "test_results_analyzer.md"),
    ("testing", "testing-workflow-optimizer.md",                     "workflow_optimizer.md"),
    # Specialized (4)
    ("specialized", "compliance-auditor.md",                         "compliance_auditor.md"),
    ("specialized", "specialized-document-generator.md",             "document_generator.md"),
    ("specialized", "language-translator.md",                        "language_translator.md"),
    ("specialized", "specialized-workflow-architect.md",             "workflow_architect.md"),
    # Design (2)
    ("design", "design-ui-designer.md",                              "ui_designer.md"),
    ("design", "design-ux-architect.md",                             "ux_architect.md"),
]


def download_agents(force=False):
    downloaded = 0
    skipped = 0
    failed = 0

    for category, remote_name, local_name in AGENTS:
        cat_dir = os.path.join(AGENTS_DIR, category)
        os.makedirs(cat_dir, exist_ok=True)

        local_path = os.path.join(cat_dir, local_name)

        if os.path.exists(local_path) and not force:
            skipped += 1
            continue

        url = f"{BASE_URL}/{category}/{remote_name}"
        try:
            print(f"  Downloading {category}/{local_name}...", end=" ", flush=True)
            req = urllib.request.Request(url, headers={"User-Agent": "Friday-Agent-Downloader/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read().decode("utf-8")
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(content)
            print("OK")
            downloaded += 1
            time.sleep(0.2)  # rate limit courtesy
        except Exception as e:
            print(f"FAILED: {e}")
            failed += 1

    print(f"\nDone: {downloaded} downloaded, {skipped} skipped, {failed} failed")
    return downloaded, skipped, failed


if __name__ == "__main__":
    force = "--force" in sys.argv
    print(f"Downloading agency-agents to {AGENTS_DIR}\n")
    download_agents(force=force)
