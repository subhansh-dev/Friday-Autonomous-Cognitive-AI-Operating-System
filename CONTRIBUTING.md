# Contributing to F.R.I.D.A.Y.

Thanks for your interest in contributing! Here's how to get started.

## Getting Started

```bash
git clone https://github.com/subhansh-dev/Friday.git
cd Friday
pip install -r requirements.txt
python main.py
```

## How to Contribute

### Reporting Bugs
- Open an issue with a clear description
- Include steps to reproduce
- Mention your OS, Python version, and relevant hardware (webcam, mic, etc.)

### Suggesting Features
- Open an issue with the `enhancement` label
- Describe the use case, not just the feature

### Code Contributions

1. **Fork** the repo
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes**
4. **Test** — make sure `python main.py` still works
5. **Commit** with a clear message:
   ```bash
   git commit -m "Add: brief description of what you did"
   ```
6. **Push** and open a **Pull Request**

## Code Style

- Python 3.11+ compatible
- Follow existing code patterns in the file you're editing
- Docstrings on public classes and methods
- Keep functions focused — one job per function
- No hardcoded API keys or secrets

## Project Structure

| Directory | Purpose |
|-----------|---------|
| `brain/` | Cognitive systems (memory, reasoning, learning) |
| `actions/` | Tool actions (56 tools) |
| `cyber/` | Security toolkit |
| `skills/` | Skill engine and definitions |
| `agent/` | Task execution system |
| `agents/` | Expert agent personas |
| `security/` | Permission and audit |
| `gesture_music_system/` | Gesture control |

## Security

- **Never** commit API keys, tokens, or credentials
- Security tool contributions must follow the confirmation protocol
- See `SECURITY.md` for the full security policy

## Questions?

Open an issue or reach out on [Discord](https://discord.com/invite/clawd).

---

<p align="center">
  <sub>Every contribution makes F.R.I.D.A.Y. better. Thanks!</sub>
</p>
