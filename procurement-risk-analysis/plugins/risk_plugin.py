"""Risk calculation plugin for schedule risk assessment."""

import json
from semantic_kernel.functions.kernel_function_decorator import kernel_function

class RiskCalculationPlugin:
    """A plugin for calculating and categorizing schedule risks."""
    
    @kernel_function(description="Calculates risk percentage")
    def calculate_risk_percentage(self, days_variance: int, days_until_due: int) -> str:
        """Calculates risk percentage based on days variance and time until due date"""
        try:
            if days_until_due <= 0:
                return "100.0"  # Already past due
            
            risk_percent = abs(days_variance / days_until_due * 100)
            #risk_percent = days_variance / days_until_due * 100
            return f"{risk_percent:.2f}"
        except Exception as e:
            return "-1"  # Error indicator
    
    @kernel_function(description="Categorizes risk by percentage")
    def categorize_risk(self, risk_percentage: float) -> str:
        """Categorizes risk based on percentage and returns risk flag and points"""
        try:
            # if risk_percentage < 0:
            #     return json.dumps({"error": "Invalid risk percentage"})
            
            if risk_percentage < 5:
                return json.dumps({
                    "risk_flag": "Low Risk",
                    "risk_points": 1
                })
            elif risk_percentage < 15:
                return json.dumps({
                    "risk_flag": "Medium Risk",
                    "risk_points": 3
                })
            else:
                return json.dumps({
                    "risk_flag": "High Risk",
                    "risk_points": 5
                })
        except Exception as e:
            return json.dumps({"error": str(e)})
