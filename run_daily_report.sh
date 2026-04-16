#!/bin/bash
# Daily Report Runner Script
# =======================
# This script runs the daily report and logs output

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load environment variables
if [ -f ".env" ]; then
    export $(cat .env | xargs)
else
    echo "Warning: .env file not found!"
fi

# Log file with timestamp
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/report_$(date +%Y%m%d_%H%M%S).log"

echo "Starting daily report at $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Run the report
python3 daily_report.py --output "$LOG_DIR/latest_report.txt" 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "Report completed at $(date)" | tee -a "$LOG_FILE"

# Keep only last 7 days of logs
find "$LOG_DIR" -name "report_*.log" -mtime +7 -delete 2>/dev/null

exit 0