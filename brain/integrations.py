# -*- coding: utf-8 -*-
"""
integrations.py — FRIDAY System Integrations
Optional dependency management, data analysis, charting, scheduling,
web scraping, system monitoring, and extension status reporting.
"""
import sys
import json
import time
import csv
import io
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Any, Dict, List


def _get_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _get_base_dir()


# ─────────────────────────────────────────────────────────────────
# SMART IMPORTS — gracefully handle optional dependencies
# ─────────────────────────────────────────────────────────────────

_HAVE_LANGCHAIN = False
try:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    from langchain.chains import LLMChain
    from langchain.memory import ConversationBufferMemory
    _HAVE_LANGCHAIN = True
except ImportError:
    pass

_HAVE_LANGGRAPH = False
try:
    from langgraph.graph import StateGraph, END
    _HAVE_LANGGRAPH = True
except ImportError:
    pass

_HAVE_FASTAPI = False
try:
    from fastapi import FastAPI, HTTPException
    import uvicorn
    _HAVE_FASTAPI = True
except ImportError:
    pass

_HAVE_OPENAI = False
try:
    import openai
    _HAVE_OPENAI = True
except ImportError:
    pass

_HAVE_POLARS = False
try:
    import polars as pl
    _HAVE_POLARS = True
except ImportError:
    pass

_HAVE_APSCHEDULER = False
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    _HAVE_APSCHEDULER = True
except ImportError:
    pass

_HAVE_MCP = False
try:
    import mcp
    _HAVE_MCP = True
except ImportError:
    pass

_HAVE_RICH = False
_RICH_CONSOLE = None
try:
    from rich.console import Console
    from rich.table import Table
    from rich.markdown import Markdown
    from rich.panel import Panel
    _HAVE_RICH = True
    _RICH_CONSOLE = Console()
except ImportError:
    pass

_HAVE_BS4 = False
try:
    from bs4 import BeautifulSoup
    _HAVE_BS4 = True
except ImportError:
    pass

_HAVE_HF = False
try:
    from huggingface_hub import HfApi, hf_hub_download
    _HAVE_HF = True
except ImportError:
    pass

_HAVE_MPL = False
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    _HAVE_MPL = True
except ImportError:
    pass

_HAVE_TIKTOKEN = False
try:
    import tiktoken
    _HAVE_TIKTOKEN = True
except ImportError:
    pass

_HAVE_REDIS = False
try:
    import redis
    _HAVE_REDIS = True
except ImportError:
    pass

_HAVE_TQDM = False
try:
    from tqdm import tqdm
    _HAVE_TQDM = True
except ImportError:
    pass

_HAVE_REQUESTS = False
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    _HAVE_REQUESTS = True
except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────
# 1. BROWSER + SCRAPER — BeautifulSoup + requests integration
# ─────────────────────────────────────────────────────────────────

def scrape_webpage(url: str) -> str:
    """Fetch and extract readable text content from a URL."""
    if not _HAVE_REQUESTS:
        return "Requests library not installed."
    try:
        session = requests.Session()
        retries = Retry(total=2, backoff_factor=0.5,
                        status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        resp = session.get(url, timeout=15, headers={
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36')
        })
        resp.raise_for_status()
        if _HAVE_BS4:
            soup = BeautifulSoup(resp.text, 'html.parser')  # [#1]
            for tag in soup(['script', 'style', 'nav', 'footer',
                             'header', 'aside']):
                tag.decompose()
            text = soup.get_text(separator='\n', strip=True)
            lines = [l for l in text.split('\n') if len(l.strip()) > 30]
            return '\n'.join(lines[:80])[:4000]
        return resp.text[:4000]
    except Exception as e:
        return f"Scrape failed: {e}"


# ─────────────────────────────────────────────────────────────────
# 2. DATA ANALYSIS — Polars CSV/JSON analysis
# ─────────────────────────────────────────────────────────────────

def analyze_data(filepath: str, max_rows: int = 50) -> str:
    """Analyze a CSV or JSON file and return summary statistics."""
    if not _HAVE_POLARS:
        return "Polars library not installed."
    try:
        p = Path(filepath).expanduser().resolve()  # [#2]
        if not p.exists():
            return f"File not found: {filepath}"

        if p.suffix.lower() == '.csv':
            df = pl.read_csv(str(p))
        elif p.suffix.lower() == '.json':
            df = pl.read_json(str(p))
        else:
            return f"Unsupported format: {p.suffix}. Use .csv or .json"

        lines = [
            f"Dataset: {p.name}",
            f"Rows: {df.height}, Columns: {df.width}",
            f"Columns: {', '.join(df.columns)}",
        ]

        # Numeric summary [#3]
        try:
            num_cols = [c for c, dt in zip(df.columns, df.dtypes)
                        if dt.is_numeric()]
        except Exception:
            num_cols = []
        if num_cols:
            lines.append("\nNumeric summary:")
            for col_name in num_cols[:5]:
                try:
                    col = df[col_name]
                    lines.append(
                        f"  {col_name}: "
                        f"mean={col.mean():.2f}, "
                        f"min={col.min()}, "
                        f"max={col.max()}, "
                        f"null={col.null_count()}")
                except Exception:
                    pass

        # Sample rows
        lines.append(f"\nFirst {min(max_rows, df.height)} rows:")
        lines.append(str(df.head(max_rows)))

        return '\n'.join(lines)[:5000]
    except Exception as e:
        return f"Analysis failed: {e}"


def query_data(filepath: str, query: str) -> str:
    """Query a CSV/JSON file using filter expressions."""
    if not _HAVE_POLARS:
        return "Polars not installed."
    try:
        p = Path(filepath).expanduser().resolve()  # [#2]
        if not p.exists():
            return f"File not found: {filepath}"
        if p.suffix.lower() == '.csv':
            df = pl.read_csv(str(p))
        elif p.suffix.lower() == '.json':
            df = pl.read_json(str(p))
        else:
            return f"Unsupported: {p.suffix}"

        # [#4] Safer query parsing — handle >= and <= too
        for op in ('>=', '<=', '==', '!=', '>', '<'):
            if op in query:
                parts = query.split(op, 1)  # split on first occurrence only
                col = parts[0].strip()
                val_str = parts[1].strip().strip("'\"")
                if col not in df.columns:
                    return f"Column '{col}' not found. Available: {', '.join(df.columns)}"

                try:
                    val = float(val_str)
                except ValueError:
                    val = val_str  # keep as string

                if op == '==':
                    result = df.filter(pl.col(col) == val)
                elif op == '!=':
                    result = df.filter(pl.col(col) != val)
                elif op == '>':
                    result = df.filter(pl.col(col) > val)
                elif op == '>=':
                    result = df.filter(pl.col(col) >= val)
                elif op == '<':
                    result = df.filter(pl.col(col) < val)
                elif op == '<=':
                    result = df.filter(pl.col(col) <= val)
                else:
                    result = df

                if result.height == 0:
                    return f"No results matching: {query}"
                return str(result.head(50))

        return str(df.head(20))
    except Exception as e:
        return f"Query failed: {e}"


# ─────────────────────────────────────────────────────────────────
# 3. CHART GENERATION — Matplotlib
# ─────────────────────────────────────────────────────────────────

def generate_chart(
    data_json: str,
    chart_type: str = "line",
    title: str = "Chart",
    x_label: str = "X",
    y_label: str = "Y",
    save_path: Optional[str] = None,
) -> str:
    """Generate a chart from JSON data and save it as an image."""
    if not _HAVE_MPL:
        return "Matplotlib not installed."
    try:
        data = json.loads(data_json) if isinstance(data_json, str) else data_json

        fig, ax = plt.subplots(figsize=(10, 6))  # [#5] use ax for cleaner control

        if chart_type == "line":
            series_list = data if isinstance(data, list) else [data]
            for series in series_list:
                if isinstance(series, dict):
                    x = list(series.get('x', series.get('labels', [])))
                    y = list(series.get('y', series.get('values', [])))
                    label = series.get('label', '')
                    ax.plot(x, y, marker='o', label=label or None)
            if any(s.get('label') for s in series_list if isinstance(s, dict)):
                ax.legend()

        elif chart_type == "bar":
            if isinstance(data, dict):
                ax.bar(data.get('labels', []), data.get('values', []))
            elif isinstance(data, list):
                for d in data:
                    ax.bar(d.get('labels', []), d.get('values', []),
                           label=d.get('label', ''))
                ax.legend()

        elif chart_type == "pie":
            if isinstance(data, dict):
                ax.pie(data.get('values', []),
                       labels=data.get('labels', []),
                       autopct='%1.1f%%')
                ax.set_aspect('equal')  # [#6] pie charts need equal aspect

        elif chart_type == "scatter":
            if isinstance(data, dict):
                ax.scatter(data.get('x', []), data.get('y', []))
        else:
            plt.close(fig)
            return f"Unknown chart type: {chart_type}. Use line|bar|pie|scatter"

        ax.set_title(title)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        if save_path:
            p = Path(save_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(str(p), dpi=150)
            plt.close(fig)
            return f"Chart saved to {save_path}"

        temp = Path.home() / '.friday_chart.png'
        fig.savefig(str(temp), dpi=150)
        plt.close(fig)
        return f"Chart saved to {temp}"
    except Exception as e:
        plt.close('all')  # [#7] close leaked figures on error
        return f"Chart generation failed: {e}"


# ─────────────────────────────────────────────────────────────────
# 4. TEXT PROCESSING — tiktoken token counting
# ─────────────────────────────────────────────────────────────────

def count_tokens(text: str, model: str = "gpt-4") -> dict:
    """Count tokens in text using tiktoken."""
    if not _HAVE_TIKTOKEN:
        return {"tokens": len(text.split()), "method": "word_estimate"}
    try:
        enc = tiktoken.encoding_for_model(model)
        tokens = enc.encode(text)
        return {
            "tokens": len(tokens),
            "model": model,
            "method": "tiktoken",
            "characters": len(text),
            "words": len(text.split()),
        }
    except Exception:
        # [#8] Fallback to cl100k_base if model-specific encoding fails
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            tokens = enc.encode(text)
            return {
                "tokens": len(tokens),
                "model": f"{model} (fallback: cl100k_base)",
                "method": "tiktoken_fallback",
                "characters": len(text),
                "words": len(text.split()),
            }
        except Exception:
            return {"tokens": len(text.split()), "method": "word_estimate"}


# ─────────────────────────────────────────────────────────────────
# 5. ADVANCED SCHEDULER — APScheduler
# ─────────────────────────────────────────────────────────────────

_APSCHEDULER: Optional[Any] = None
_APSCHEDULER_JOBS: Dict[str, str] = {}

if _HAVE_APSCHEDULER:
    try:
        _APSCHEDULER = BackgroundScheduler()
        _APSCHEDULER.start()
    except Exception as e:
        print(f"[Integrations] ⚠️ APScheduler failed to start: {e}")
        _HAVE_APSCHEDULER = False


def schedule_advanced(
    job_id: str,
    action: str,
    schedule_type: str,
    **kwargs,
) -> str:
    """Schedule a task using APScheduler."""
    if not _HAVE_APSCHEDULER or _APSCHEDULER is None:
        return "APScheduler not installed."

    try:
        from agent.task_queue import get_queue

        def _task_wrapper():
            try:
                q = get_queue()
                q.submit(goal=action)
            except Exception as e:
                print(f"[Scheduler] ❌ Job {job_id} failed: {e}")

        if schedule_type == "once":
            trigger = DateTrigger(run_date=kwargs.get('run_date'))
        elif schedule_type == "interval":
            trigger = IntervalTrigger(
                hours=int(kwargs.get('hours', 0)),
                minutes=int(kwargs.get('minutes', 0)),
                seconds=int(kwargs.get('seconds', 0)),
            )
        elif schedule_type == "cron":
            trigger = CronTrigger(
                hour=kwargs.get('hour'),
                minute=kwargs.get('minute'),
                day_of_week=kwargs.get('day_of_week'),
            )
        else:
            return f"Unknown schedule type: {schedule_type}"

        _APSCHEDULER.add_job(_task_wrapper, trigger,
                             id=job_id, replace_existing=True)
        _APSCHEDULER_JOBS[job_id] = action
        return f"Scheduled '{job_id}' as {schedule_type}: {kwargs}"
    except Exception as e:
        return f"Schedule failed: {e}"


def list_scheduled_jobs() -> str:
    """List all APScheduler jobs."""
    if not _HAVE_APSCHEDULER or _APSCHEDULER is None:
        return "APScheduler not available."
    jobs = _APSCHEDULER.get_jobs()
    if not jobs:
        return "No scheduled jobs."
    return "\n".join(
        f"  [{j.id}] next run: {j.next_run_time}" for j in jobs[:20])


def remove_scheduled_job(job_id: str) -> str:
    """Remove a scheduled job."""
    if not _HAVE_APSCHEDULER or _APSCHEDULER is None:
        return "APScheduler not available."
    try:
        _APSCHEDULER.remove_job(job_id)
        _APSCHEDULER_JOBS.pop(job_id, None)
        return f"Removed job: {job_id}"
    except Exception as e:
        return f"Remove failed: {e}"


# ─────────────────────────────────────────────────────────────────
# 6. RICH CONSOLE — formatted output
# ─────────────────────────────────────────────────────────────────

def rich_format(
    title: str,
    content: Any,
    format_type: str = "table",
) -> str:
    """Format data using Rich for display."""
    if not _HAVE_RICH or _RICH_CONSOLE is None:
        if isinstance(content, list):
            return "\n".join(
                " | ".join(f"{k}={v}" for k, v in item.items())
                for item in content[:20]
            )
        elif isinstance(content, dict):
            return "\n".join(f"{k}: {v}" for k, v in content.items())
        return str(content)[:2000]

    try:
        buf = io.StringIO()
        console = Console(file=buf, width=100)

        if format_type == "table" and isinstance(content, list):
            if not content:
                return "(empty)"
            table = Table(title=title)
            for key in content[0]:
                table.add_column(str(key), style="cyan")
            for item in content[:20]:
                table.add_row(*[str(v)[:40] for v in item.values()])
            console.print(table)
        elif format_type == "panel":
            if isinstance(content, dict):
                text = "\n".join(
                    f"[bold]{k}:[/bold] {v}" for k, v in content.items())
            else:
                text = str(content)
            console.print(Panel(text, title=title))
        elif format_type == "markdown":
            console.print(Markdown(str(content)))
        else:
            console.print(str(content))

        return buf.getvalue()
    except Exception:
        return str(content)[:2000]


# ─────────────────────────────────────────────────────────────────
# 7. HUGGING FACE — model listing and info
# ─────────────────────────────────────────────────────────────────

def hf_search(query: str, limit: int = 5) -> str:
    """Search HuggingFace models."""
    if not _HAVE_HF:
        return "HuggingFace Hub not installed."
    try:
        api = HfApi()
        models = list(api.list_models(search=query, limit=limit))  # [#9]
        if not models:
            return f"No models found for '{query}'."
        lines = [f"Top {len(models)} models for '{query}':"]
        for m in models:
            downloads = getattr(m, 'downloads', 0) or 0  # [#10]
            model_id = getattr(m, 'modelId',
                       getattr(m, 'id', str(m)))          # [#10]
            lines.append(f"  - {model_id} (downloads: {downloads:,})")
        return "\n".join(lines)
    except Exception as e:
        return f"HF search failed: {e}"


# ─────────────────────────────────────────────────────────────────
# 8. SYSTEM METRICS — Rich dashboard
# ─────────────────────────────────────────────────────────────────

def get_system_dashboard() -> str:
    """Get a formatted system metrics dashboard."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')  # [#11] works on Linux; fix for Windows
        try:
            disk = psutil.disk_usage('C:\\')  # [#11] try Windows first
        except Exception:
            pass

        stats = {
            "CPU Usage": f"{cpu}%",
            "Memory": (f"{mem.percent}% "
                       f"({mem.used // (1024**3)}GB / "
                       f"{mem.total // (1024**3)}GB)"),
            "Disk": (f"{disk.percent}% "
                     f"({disk.used // (1024**3)}GB / "
                     f"{disk.total // (1024**3)}GB)"),
            "Processes": len(psutil.pids()),
        }

        if _HAVE_RICH and _RICH_CONSOLE:
            return rich_format("System Dashboard", stats, format_type="panel")
        else:
            return "\n".join(f"{k}: {v}" for k, v in stats.items())
    except ImportError:
        return "psutil not installed."
    except Exception as e:
        return f"Dashboard failed: {e}"


# ─────────────────────────────────────────────────────────────────
# 9. FILE WATCHER — recent file changes
# ─────────────────────────────────────────────────────────────────

def watch_directory(path: str, patterns: Optional[List[str]] = None) -> str:
    """Watch a directory for recently modified files."""
    try:
        p = Path(path).expanduser().resolve()  # [#2]
        if not p.is_dir():
            return f"Not a directory: {path}"

        cutoff = time.time() - 3600
        recent = []
        for f in p.iterdir():
            if f.is_file():
                mtime = f.stat().st_mtime
                if mtime > cutoff:
                    age_mins = int((time.time() - mtime) / 60)
                    if patterns:
                        if any(f.name.endswith(pat.lstrip('*'))
                               for pat in patterns):
                            recent.append(
                                f"  {f.name} ({age_mins}m ago)")
                    else:
                        recent.append(
                            f"  {f.name} ({age_mins}m ago)")

        if not recent:
            return f"No files modified in {path} in the last hour."
        return "Recently modified:\n" + "\n".join(recent[:20])
    except Exception as e:
        return f"Watch error: {e}"


# ─────────────────────────────────────────────────────────────────
# 10. SYSTEM INFO — Windows integration
# ─────────────────────────────────────────────────────────────────

def get_windows_system_info() -> str:
    """Get detailed Windows system information."""
    try:
        import platform as _platform
        info = {
            "System": _platform.system(),
            "Version": _platform.version(),
            "Processor": _platform.processor(),
            "Machine": _platform.machine(),
            "Python": _platform.python_version(),
        }

        # Windows registry for product name
        if sys.platform == 'win32':  # [#12]
            try:
                import winreg
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
                ) as key:
                    product = winreg.QueryValueEx(key, "ProductName")[0]
                    info["Windows"] = product
            except Exception:
                pass

        return "\n".join(f"{k}: {v}" for k, v in info.items())
    except Exception as e:
        return f"System info failed: {e}"


# ─────────────────────────────────────────────────────────────────
# 11. WEB RESEARCH — enhanced search with scraping
# ─────────────────────────────────────────────────────────────────

def deep_research(topic: str, depth: int = 1) -> str:
    """Research a topic: search + scrape + summarize."""
    try:
        from actions.web_search import web_search
        search_results = web_search(parameters={"query": topic}, player=None)

        lines = [
            f"Deep Research: {topic}",
            "=" * 40,
            "",
            "Search Results:",
            str(search_results)[:1000],  # [#13]
        ]

        if depth > 0 and _HAVE_REQUESTS:
            lines.append("\nNote: Deep scraping available — "
                         "use web_research tool for full page content.")

        return "\n".join(lines)[:4000]
    except Exception as e:
        return f"Research failed: {e}"


# ─────────────────────────────────────────────────────────────────
# STATUS REPORT — what's available
# ─────────────────────────────────────────────────────────────────

def get_available_extensions() -> List[str]:
    """Return list of available advanced features."""
    available = []
    checks = [
        ("Web Scraping (BS4)",               _HAVE_BS4),
        ("Data Analysis (Polars)",           _HAVE_POLARS),
        ("Charts (Matplotlib)",              _HAVE_MPL),
        ("Token Counter (tiktoken)",         _HAVE_TIKTOKEN),
        ("Advanced Scheduler (APScheduler)", _HAVE_APSCHEDULER),
        ("Rich Console Output",              _HAVE_RICH),
        ("HuggingFace Hub",                  _HAVE_HF),
        ("AI Pipelines (LangChain)",         _HAVE_LANGCHAIN),
        ("AI Workflows (LangGraph)",         _HAVE_LANGGRAPH),
        ("FastAPI Server",                   _HAVE_FASTAPI),
        ("OpenAI Provider",                  _HAVE_OPENAI),
        ("MCP Protocol",                     _HAVE_MCP),
        ("Redis Cache",                      _HAVE_REDIS),
    ]
    for name, installed in checks:
        available.append(f"  {'[x]' if installed else '[ ]'} {name}")
    return available


def integration_status() -> str:
    """Get full integration status report."""
    lines = ["Advanced Module Integration Status:", "-" * 35]
    lines.extend(get_available_extensions())
    return "\n".join(lines)
