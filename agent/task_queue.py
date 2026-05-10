# -*- coding: utf-8 -*-
"""
task_queue.py — FRIDAY Agent Task Queue
Priority queue with concurrent execution, cancellation, and progress tracking.
"""
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any, Optional, List, Dict


class TaskStatus(Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    LOW    = 3
    NORMAL = 2
    HIGH   = 1


@dataclass(order=True)
class Task:
    priority:   int
    created_at: float = field(compare=False)
    task_id:    str   = field(compare=False)
    goal:       str   = field(compare=False)
    status:     TaskStatus = field(compare=False, default=TaskStatus.PENDING)
    result:     Any        = field(compare=False, default=None)
    error:      str        = field(compare=False, default="")
    progress:   str        = field(compare=False, default="")       # [#1]
    speak:      Any        = field(compare=False, default=None)
    on_complete: Any       = field(compare=False, default=None)
    on_progress: Any       = field(compare=False, default=None)     # [#2]
    cancel_flag: threading.Event = field(compare=False,
                                          default_factory=threading.Event)
    started_at:  float = field(compare=False, default=0.0)          # [#3]
    finished_at: float = field(compare=False, default=0.0)          # [#3]


class TaskQueue:
    def __init__(self, max_concurrent: int = 1):
        self._queue:          List[Task]         = []
        self._lock:           threading.Lock     = threading.Lock()
        self._condition:      threading.Condition = threading.Condition(self._lock)
        self._tasks:          Dict[str, Task]    = {}
        self._running:        bool               = False
        self._worker_thread:  Optional[threading.Thread] = None
        self._max_concurrent  = max_concurrent
        self._active_count    = 0
        self._executor        = None

        # Metrics [#4]
        self._total_submitted  = 0
        self._total_completed  = 0
        self._total_failed     = 0
        self._total_cancelled  = 0

    def _get_executor(self):
        if self._executor is None:
            from agent.executor import AgentExecutor
            self._executor = AgentExecutor()
        return self._executor

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="AgentTaskQueue",
        )
        self._worker_thread.start()
        print("[TaskQueue] ✅ Started")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        # Cancel all pending tasks [#5]
        with self._lock:
            for task in self._queue:
                if task.status == TaskStatus.PENDING:
                    task.cancel_flag.set()
                    task.status = TaskStatus.CANCELLED
        with self._condition:
            self._condition.notify_all()
        print("[TaskQueue] 🔴 Stopped")

    # ── Submit ────────────────────────────────────────────────────────

    def submit(
        self,
        goal:        str,
        priority:    TaskPriority = TaskPriority.NORMAL,
        speak:       Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,  # [#2]
    ) -> str:
        task_id = str(uuid.uuid4())[:8]
        task = Task(
            priority    = priority.value,
            created_at  = time.time(),
            task_id     = task_id,
            goal        = goal,
            speak       = speak,
            on_complete = on_complete,
            on_progress = on_progress,
        )

        with self._condition:
            self._queue.append(task)
            self._queue.sort(key=lambda t: (t.priority, t.created_at))
            self._tasks[task_id] = task
            self._total_submitted += 1
            self._condition.notify()

        print(f"[TaskQueue] 📥 Task queued: [{task_id}] {goal[:60]}")
        return task_id

    # ── Query ─────────────────────────────────────────────────────────

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED,
                               TaskStatus.CANCELLED):
                return False

            task.cancel_flag.set()
            task.status = TaskStatus.CANCELLED
            self._total_cancelled += 1

            # Remove from queue if still pending [#6]
            if task in self._queue:
                try:
                    self._queue.remove(task)
                except ValueError:
                    pass

            print(f"[TaskQueue] 🚫 Task cancelled: [{task_id}]")
            return True

    def get_status(self, task_id: str) -> Optional[dict]:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            elapsed = 0.0
            if task.started_at > 0:
                end = task.finished_at if task.finished_at > 0 else time.time()
                elapsed = round(end - task.started_at, 1)
            return {
                "task_id":     task.task_id,
                "goal":        task.goal,
                "status":      task.status.value,
                "result":      task.result,
                "error":       task.error,
                "progress":    task.progress,       # [#1]
                "elapsed":     elapsed,             # [#3]
                "priority":    task.priority,
            }

    def get_all_statuses(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "task_id":  t.task_id,
                    "goal":     t.goal[:50],
                    "status":   t.status.value,
                    "progress": t.progress,  # [#1]
                }
                for t in self._tasks.values()
            ]

    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._queue
                       if t.status == TaskStatus.PENDING)

    def active_count(self) -> int:  # [#7]
        with self._lock:
            return self._active_count

    def get_metrics(self) -> dict:  # [#4]
        with self._lock:
            return {
                "submitted":  self._total_submitted,
                "completed":  self._total_completed,
                "failed":     self._total_failed,
                "cancelled":  self._total_cancelled,
                "active":     self._active_count,
                "pending":    sum(1 for t in self._queue
                                  if t.status == TaskStatus.PENDING),
            }

    def cleanup_completed(self, max_age: float = 3600) -> int:  # [#8]
        """Remove completed/failed tasks older than max_age seconds."""
        now = time.time()
        removed = 0
        with self._lock:
            stale = [
                tid for tid, t in self._tasks.items()
                if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED,
                                TaskStatus.CANCELLED)
                and t.finished_at > 0
                and (now - t.finished_at) > max_age
            ]
            for tid in stale:
                del self._tasks[tid]
                removed += 1
        if removed:
            print(f"[TaskQueue] 🧹 Cleaned up {removed} old tasks")
        return removed

    # ── Worker ────────────────────────────────────────────────────────

    def _worker_loop(self) -> None:
        while self._running:
            task = None

            with self._condition:
                # [#9] Wait with timeout to avoid missed notifications
                while self._running and not self._next_task():
                    self._condition.wait(timeout=2.0)
                if not self._running:
                    break
                task = self._next_task()
                if task:
                    task.status = TaskStatus.RUNNING
                    task.started_at = time.time()
                    self._active_count += 1
                    try:
                        self._queue.remove(task)
                    except ValueError:
                        pass

            if task:
                # [#10] Run directly if max_concurrent is 1
                # (avoids thread-per-task overhead for single-worker)
                if self._max_concurrent <= 1:
                    self._run_task(task)
                else:
                    threading.Thread(
                        target=self._run_task,
                        args=(task,),
                        daemon=True,
                        name=f"AgentTask-{task.task_id}",
                    ).start()

    def _next_task(self) -> Optional[Task]:
        if self._active_count >= self._max_concurrent:
            return None
        for task in self._queue:
            if (task.status == TaskStatus.PENDING
                    and not task.cancel_flag.is_set()):
                return task
        return None

    # ── Task execution ────────────────────────────────────────────────

    def _run_task(self, task: Task) -> None:
        print(f"[TaskQueue] ▶️ Running: [{task.task_id}] "
              f"{task.goal[:60]}")

        # Progress callback wrapper [#2]
        def _on_step_start(step_num, tool, desc):
            task.progress = f"Step {step_num}: {desc[:40]}"
            if task.on_progress:
                try:
                    task.on_progress(task.task_id, "step_start",
                                     task.progress)
                except Exception:
                    pass

        def _on_step_done(step_num, status, result):
            task.progress = f"Step {step_num}: {status}"
            if task.on_progress:
                try:
                    task.on_progress(task.task_id, "step_done",
                                     f"{status}: {result[:60]}")
                except Exception:
                    pass

        try:
            executor = self._get_executor()
            result = executor.execute(
                goal          = task.goal,
                speak         = task.speak,
                cancel_flag   = task.cancel_flag,
                on_step_start = _on_step_start,
                on_step_done  = _on_step_done,
            )

            with self._lock:
                task.finished_at = time.time()
                if task.cancel_flag.is_set():
                    task.status = TaskStatus.CANCELLED
                    self._total_cancelled += 1
                else:
                    task.status = TaskStatus.COMPLETED
                    task.result = result
                    self._total_completed += 1
                task.progress = "Done"
                self._active_count -= 1

            if task.on_complete and not task.cancel_flag.is_set():
                try:
                    task.on_complete(task.task_id, result)
                except Exception as e:
                    print(f"[TaskQueue] ⚠️ on_complete callback "
                          f"error: {e}")

            elapsed = task.finished_at - task.started_at
            print(f"[TaskQueue] ✅ Completed: [{task.task_id}] "
                  f"in {elapsed:.1f}s")

        except Exception as e:
            with self._lock:
                task.finished_at = time.time()
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.progress = f"Failed: {str(e)[:40]}"
                self._active_count -= 1
                self._total_failed += 1

            print(f"[TaskQueue] ❌ Failed: [{task.task_id}] {e}")

        finally:
            # [#11] Always notify — even on crash
            with self._condition:
                self._condition.notify()


# ── Singleton ─────────────────────────────────────────────────────────

_queue: Optional[TaskQueue] = None
_queue_started = False
_queue_lock    = threading.Lock()


def get_queue() -> TaskQueue:
    global _queue, _queue_started
    with _queue_lock:
        if _queue is None:
            _queue = TaskQueue()
        if not _queue_started:
            _queue.start()
            _queue_started = True
    return _queue
