"""Plugins module initialization."""

from .schedule_plugin import EquipmentSchedulePlugin
from .risk_plugin import RiskCalculationPlugin

__all__ = [
    'EquipmentSchedulePlugin',
    'RiskCalculationPlugin'
]
