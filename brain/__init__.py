# brain package — Friday's neural memory system

# Global Workspace (Thalamus) — unified consciousness
try:
    from brain.global_workspace import get_global_workspace, GlobalWorkspace, WorkspaceParticipant
    from brain.workspace_events import EventType as WsEventType, WorkspaceEvent
    from brain.workspace_context import inject_workspace_context, generate_workspace_context
except ImportError:
    pass

# Self-Modification Engine — safe codebase analysis and evolution tracking
try:
    from brain.self_modifier import get_self_modifier, SelfModifier
except ImportError:
    pass
