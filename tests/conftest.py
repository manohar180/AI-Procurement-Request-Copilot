import os

# Ensure unit tests execute deterministically offline without remote API dependencies
os.environ["COPILOT_MODE"] = "offline"
