import requests
import time
import json

# The URL of your running Flask application
# (Use 127.0.0.1 or localhost)
APP_URL = "http://127.0.0.1:5001/stream"

# This is a FAKE data packet.
# We set 'attention_score' to 1 to trigger the alert.
test_payload = {
    "jetson_id": "driver-2",
    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    "epoch_time": time.time(),
    "attention_score": 1,  # <-- This is the value that triggers the alert
    "attention_label": "CRITICAL (Test)",
    "eye_status": "Closed",
    "is_drowsy": True,
    "neck_position": "Down",
    "face_detected": True,
    "blink_rate_status": "Low",
    "recent_blinks": 0,
    "yaw": 0,
    "pitch": 0,
    "roll": 0
}

print(f"Sending test alert packet to {APP_URL}...")
print(json.dumps(test_payload, indent=2))

try:
    # Send the data as a POST request with JSON
    response = requests.post(APP_URL, json=test_payload)

    # Print the server's response
    print("\n--- Server Response ---")
    print(f"Status Code: {response.status_code}")
    print(f"Response Body: {response.json()}")

    if response.status_code == 200:
        print("\nSUCCESS: Test packet sent. Check the inbox for:")
        print(f"RECIPIENT_EMAIL = 'b24219@students.iitmandi.ac.in'")
    else:
        print("\nERROR: The server reported an error.")

except requests.exceptions.ConnectionError:
    print(f"\nFATAL ERROR: Could not connect to {APP_URL}")
    print("Please make sure your main Flask app is running.")
except Exception as e:
    print(f"An error occurred: {e}")