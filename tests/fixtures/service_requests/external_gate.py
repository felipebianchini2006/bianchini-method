from pathlib import Path
import sys

state = Path(".bianchini/.runtime/service-state").read_text().strip()
if state != "up":
    print("external service unavailable")
    sys.exit(1)
print("external service available")
