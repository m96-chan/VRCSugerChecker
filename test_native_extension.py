#!/usr/bin/env python3
"""
WASAPI Native Extension のテストスクリプト
"""
import sys
import traceback

print("=== WASAPI Native Extension Test ===")
print()

# Step 1: Import test
print("Step 1: Importing module...")
try:
    from src.modules.audio.wasapi_process_loopback_native import ProcessLoopback
    print("OK: Module imported successfully")
except Exception as e:
    print(f"ERROR: Failed to import module: {e}")
    traceback.print_exc()
    sys.exit(1)

print()

# Step 2: Find VRChat process
print("Step 2: Finding VRChat process...")
try:
    import comtypes
    from pycaw.pycaw import AudioUtilities

    comtypes.CoInitialize()
    sessions = AudioUtilities.GetAllSessions()

    vrchat_pid = None
    for session in sessions:
        if session.Process and session.Process.name() == "VRChat.exe":
            vrchat_pid = session.Process.pid
            print(f"OK: VRChat process found (PID: {vrchat_pid})")
            break

    comtypes.CoUninitialize()

    if not vrchat_pid:
        print("WARNING: VRChat process not found. Using fake PID for testing...")
        vrchat_pid = 12345  # テスト用のダミーPID

except Exception as e:
    print(f"ERROR: Failed to find VRChat process: {e}")
    traceback.print_exc()
    print("Using fake PID for testing...")
    vrchat_pid = 12345

print()

# Step 3: Create ProcessLoopback object
print(f"Step 3: Creating ProcessLoopback object (PID: {vrchat_pid})...")
try:
    process_loopback = ProcessLoopback(vrchat_pid)
    print("OK: ProcessLoopback object created")
except Exception as e:
    print(f"ERROR: Failed to create ProcessLoopback: {e}")
    traceback.print_exc()
    sys.exit(1)

print()

# Step 4: Get format
print("Step 4: Getting audio format...")
try:
    format_info = process_loopback.get_format()
    if format_info:
        print(f"OK: Format info: {format_info}")
    else:
        print("WARNING: Format info is None")
except Exception as e:
    print(f"ERROR: Failed to get format: {e}")
    traceback.print_exc()
    sys.exit(1)

print()

# Step 5: Start capture
print("Step 5: Starting capture...")
try:
    process_loopback.start()
    print("OK: Capture started")
except Exception as e:
    print(f"ERROR: Failed to start capture: {e}")
    traceback.print_exc()
    sys.exit(1)

print()

# Step 6: Read data
print("Step 6: Reading data (5 attempts)...")
import time
for i in range(5):
    try:
        data = process_loopback.read()
        if data:
            print(f"  Attempt {i+1}: Got {len(data)} bytes")
        else:
            print(f"  Attempt {i+1}: No data")
        time.sleep(0.1)
    except Exception as e:
        print(f"  Attempt {i+1}: ERROR: {e}")
        traceback.print_exc()

print()

# Step 7: Stop capture
print("Step 7: Stopping capture...")
try:
    process_loopback.stop()
    print("OK: Capture stopped")
except Exception as e:
    print(f"ERROR: Failed to stop capture: {e}")
    traceback.print_exc()

print()
print("=== Test Complete ===")
