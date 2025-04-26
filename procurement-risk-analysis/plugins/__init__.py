"""Plugins module initialization."""

from .schedule_plugin import EquipmentSchedulePlugin
from .risk_plugin import RiskCalculationPlugin
from .thinking_logger_plugin import ThinkingLoggerPlugin
from .context_aware_logger import ContextAwareThinkingLoggerPlugin
<<<<<<< Updated upstream
=======
from .enhanced_thinking_logger import EnhancedThinkingLoggerPlugin
from .event_log_plugin import EventLogPlugin
>>>>>>> Stashed changes

__all__ = [
    'EquipmentSchedulePlugin',
    'RiskCalculationPlugin',
    'ThinkingLoggerPlugin',
<<<<<<< Updated upstream
    'ContextAwareThinkingLoggerPlugin'
=======
    'ContextAwareThinkingLoggerPlugin',
    'EnhancedThinkingLoggerPlugin',
    'EventLogPlugin'
>>>>>>> Stashed changes
]