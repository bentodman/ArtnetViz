import psutil
import time
import os
import sys
import datetime

pid = int(sys.argv[1])
log_file = sys.argv[2]
interval = 1.0  # seconds

with open(log_file, 'w') as f:
    f.write("Timestamp,Memory (MB)\n")
    
    while True:
        try:
            process = psutil.Process(pid)
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            
            print(f"{timestamp}: Memory usage: {memory_mb:.2f} MB")
            f.write(f"{timestamp},{memory_mb:.2f}\n")
            f.flush()
            
            time.sleep(interval)
        except psutil.NoSuchProcess:
            print("Application has terminated.")
            break
        except KeyboardInterrupt:
            print("Monitoring stopped.")
            break
