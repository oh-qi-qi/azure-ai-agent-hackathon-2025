"""Scheduler for automated workflow."""

import asyncio
import threading
import time
from datetime import datetime, timedelta

class WorkflowScheduler:
    """Schedules and runs the automated workflow."""
    
    def __init__(self, connection_string):
        self.connection_string = connection_string
        from managers.workflow_manager import AutomatedWorkflowManager
        self.workflow_manager = AutomatedWorkflowManager(connection_string)
        self.running = False
        self.scheduler_thread = None
    
    def start(self):
        """Starts the scheduler."""
        if self.running:
            return False
        
        self.running = True
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        return True
    
    def stop(self):
        """Stops the scheduler."""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=1)
        return True
    
    def _scheduler_loop(self):
        """The main scheduler loop."""
        while self.running:
            now = datetime.now()
            scheduled_time = datetime(now.year, now.month, now.day, 7, 0, 0)
            
            # If current time is past 7am, schedule for tomorrow
            if now > scheduled_time:
                scheduled_time += timedelta(days=1)
            
            # Calculate seconds until scheduled time
            wait_seconds = (scheduled_time - now).total_seconds()
            print(f"Next workflow scheduled at {scheduled_time}, waiting {wait_seconds} seconds")
            
            # Wait until scheduled time or until stopped
            wait_interval = 60  # Check every minute if we should stop
            while wait_seconds > 0 and self.running:
                time.sleep(min(wait_interval, wait_seconds))
                wait_seconds -= wait_interval
                if not self.running:
                    return
            
            # Run the workflow if still running
            if self.running:
                print("Starting scheduled workflow")
                asyncio.run(self.workflow_manager.run_workflow())
    
    def run_now(self):
        """Runs the workflow immediately."""
        return asyncio.run(self.workflow_manager.run_workflow())
