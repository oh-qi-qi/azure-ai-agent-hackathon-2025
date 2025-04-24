"""Main entry point for the application."""

import sys
import json
import uvicorn
import logging
from dotenv import load_dotenv

from config.settings import get_database_connection_string
from managers.scheduler import WorkflowScheduler
from api.app import app

# Load environment variables
load_dotenv()

def main():
    """Main function."""
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        # Get database connection string
        connection_string = get_database_connection_string()
        
        if sys.argv[1] == "--workflow-only":
            # Run just the workflow once
            workflow_scheduler = WorkflowScheduler(connection_string)
            result = workflow_scheduler.run_now()
            print(json.dumps(result, indent=2))
            return
        
        elif sys.argv[1] == "--scheduler-only":
            # Run just the scheduler without the API
            workflow_scheduler = WorkflowScheduler(connection_string)
            workflow_scheduler.start()
            try:
                # Keep the main thread alive
                while True:
                    import time
                    time.sleep(1)
            except KeyboardInterrupt:
                workflow_scheduler.stop()
                print("Scheduler stopped")
            return
    
    # Run the API server
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
