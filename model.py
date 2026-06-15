
import cv2
import mediapipe as mp.   
import time
import numpy as np
import math
import subprocess
import tempfile
import os
import Jetson.GPIO as GPIO
from collections import deque
import json
import requests
from threading import Thread

# Initialize MediaPipe modules
mp_drawing = mp.solutions.drawing_utils
mp_face_mesh = mp.solutions.face_mesh

# ---- Face Mesh ----
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# ✅ NEW: Initialize Haar Cascade for eye detection
eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# ---- Constants ----
EYE_CLOSURE_THRESH = 0.26
MOUTH_OPEN_THRESH = 0.40
DROWSY_TIME_THRESH = 3.5
FACE_NOT_DETECTED_VIBRATE_THRESH = 4.0

# ✅ NEW: Haar Cascade eye detection parameters
EYE_DETECTION_CONFIDENCE = 0.7  # Threshold for considering eyes as detected
CONSECUTIVE_FRAMES_FOR_BLINK = 2  # Frames with no eyes detected to register blink

# --- "ML Model" Weights ---
W_EYE_OPEN = 4
W_MOUTH = 2
W_NECK = 3
W_BLINK = 3
max_raw_score = (W_EYE_OPEN * 1) + (W_MOUTH * 1) + (W_NECK * 2) + (W_BLINK * 1)

# --- Blink Rate Constants ---
BLINK_TIME_WINDOW = 5.0
NORMAL_BLINK_MIN = 1
NORMAL_BLINK_MAX = 3

RATING_LABELS = {
    1:"Fully Distracted",
    2:"Distracted",
    3:"Bit Distracted",
    4:"Attentive",
    5:"Fully Attentive"
}

# ✅ NEW: Flask server configuration
JETSON_ID = "jetson-001"
FLASK_SERVER_URL = "http://YOUR_FLASK_SERVER_IP:5000/stream"  # Update this!
STREAM_INTERVAL = 5.0  # Send data every 5 seconds

neck_text_map = {3: "Straight", 2: "Slight Turn", 1: "Full Turn"}
blink_text_map = {1: "Strained", 2: "Staring", 3: "Normal"}

# ---- GPIO Pin Definitions ----
IN3_PIN = 38
IN4_PIN = 40
IN1_PIN = 35
IN2_PIN = 37

# ---- Helper Functions ----
def euclidean(a,b): return math.sqrt((a[0]-b[0])**2+(a[1]-b[1])**2)

def eye_aspect_ratio(landmarks, left=True):
    if left:
        ids = [33,160,158,133,153,144]
    else:
        ids = [263,387,385,362,380,373]
    pts = [(landmarks[i].x, landmarks[i].y) for i in ids]
    A = euclidean(pts[1], pts[5])
    B = euclidean(pts[2], pts[4])
    C = euclidean(pts[0], pts[3])
    return (A + B) / (2.0 * C)

# ✅ NEW: Haar Cascade-based eye detection for blink counting
def detect_eyes_haar(frame, face_roi=None):
    """
    Detect eyes using Haar Cascade classifier.
    Returns: (eyes_detected_count, eye_closed)
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # If face ROI is provided, use it; otherwise detect face first
    if face_roi is not None:
        x, y, w, h = face_roi
        roi_gray = gray[y:y+h, x:x+w]
    else:
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        if len(faces) == 0:
            return 0, True  # No face detected, assume eyes closed
        x, y, w, h = faces[0]
        roi_gray = gray[y:y+h, x:x+w]
    
    # Detect eyes in the face region
    eyes = eye_cascade.detectMultiScale(roi_gray, 1.1, 5, minSize=(20, 20))
    eyes_count = len(eyes)
    
    # If less than 2 eyes detected, consider eyes as closed
    eye_closed = eyes_count < 2
    
    return eyes_count, eye_closed

def mouth_open_ratio(landmarks):
    top, bottom = landmarks[13], landmarks[14]
    left, right = landmarks[78], landmarks[308]
    vertical = euclidean((top.x, top.y), (bottom.x, bottom.y))
    horizontal = euclidean((left.x, left.y), (right.x, right.y))
    return vertical / horizontal

def get_head_pose(landmarks):
    left_eye_3d = np.array([landmarks[33].x, landmarks[33].y, landmarks[33].z])
    right_eye_3d = np.array([landmarks[263].x, landmarks[263].y, landmarks[263].z])
    nose_3d = np.array([landmarks[1].x, landmarks[1].y, landmarks[1].z])
    face_vec = right_eye_3d - left_eye_3d
    
    yaw = np.degrees(np.arctan2(face_vec[2], face_vec[0])) * 2
    delta_y = landmarks[263].y - landmarks[33].y
    delta_x = landmarks[263].x - landmarks[33].x
    roll = np.degrees(np.arctan2(delta_y, delta_x))
    pitch = np.degrees((nose_3d[2] - (left_eye_3d[2] + right_eye_3d[2]) / 2) * 100)
    
    return yaw, pitch, roll

def say(text):
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()
        subprocess.run(["pico2wave", "-w", tmp_path, text])
        command = f"paplay {tmp_path} && rm {tmp_path}"
        subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"TTS Error: {e}")
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)

def motor_on():
    GPIO.output(IN3_PIN, GPIO.HIGH)
    GPIO.output(IN4_PIN, GPIO.LOW)
    time.sleep(0.25)
    GPIO.output(IN1_PIN, GPIO.HIGH)
    GPIO.output(IN2_PIN, GPIO.LOW)
    print("Motors ON")

def motor_off():
    GPIO.output(IN3_PIN, GPIO.LOW)
    GPIO.output(IN4_PIN, GPIO.LOW)
    GPIO.output(IN1_PIN, GPIO.LOW)
    GPIO.output(IN2_PIN, GPIO.LOW)
    print("Motors OFF")

# ✅ NEW: Function to send data to Flask server
def send_to_flask(data):
    """Send JSON data to Flask server in a separate thread"""
    def _send():
        try:
            response = requests.post(
                FLASK_SERVER_URL,
                json=data,
                timeout=3
            )
            if response.status_code == 200:
                print(f"✓ Data sent successfully at {data['timestamp']}")
            else:
                print(f"✗ Server returned status {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to send data: {e}")
    
    # Run in separate thread to avoid blocking
    Thread(target=_send, daemon=True).start()

# ---- Video Input ----
cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FPS, 60)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if not cap.isOpened():
    print("Error: Could not open video stream from USB camera.")
    exit()

fps = 30.0
print("Processing video from USB Cam | FPS:", fps)

blink_counter = 0
eye_was_open = True
eye_closed_start_time = 0

# ✅ NEW: Variables for Haar Cascade blink detection
eyes_closed_frames = 0  # Counter for consecutive frames with eyes closed
last_eye_state = "open"  # Track previous eye state

rating_buffer = deque(maxlen=2)
blink_timestamps = deque()

frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"Camera resolution: {frame_width} x {frame_height}")

# Caching for frame skipping
frame_counter = 0
cached_final_rating = 5
cached_label = RATING_LABELS[5]
cached_color = (0, 255, 0)
cached_yaw, cached_pitch, cached_roll = 0, 0, 0
cached_mouth_text = "Closed"
cached_eye_text = "Open"
cached_neck_text = neck_text_map[3]
cached_blink_text = blink_text_map[3]
cached_blinks_in_window = 0
cached_neck_direction_text = "N/A"
cached_face_detected = True
cached_is_drowsy = False
cached_mouth_status = "closed"
cached_eye_status = "open"

# ✅ NEW: Streaming state
last_stream_time = 0

try:
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(IN1_PIN, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(IN2_PIN, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(IN3_PIN, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(IN4_PIN, GPIO.OUT, initial=GPIO.LOW)
    print("GPIO pins setup for both motors.")

    last_alert_time = 0
    last_rating = None
    last_face_seen_time = time.time()
    
    INFO_COLOR = (255, 255, 0)

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_counter += 1
        frame = cv2.flip(frame, 1)
        current_time = time.time()

        # --- Processing block runs only every 3rd frame ---
        if frame_counter % 3 == 0:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_result = face_mesh.process(rgb)

            score_mouth = 2
            score_eye_openness = 2
            score_neck = 3
            score_blink_rate = 3
            
            is_drowsy = False
            blinks_in_window = 0
            yaw, pitch, roll = 0, 0, 0
            face_detected = False
            neck_direction_text = "N/A"
            
            processing_time = time.time()

            if face_result.multi_face_landmarks:
                face_detected = True
                last_face_seen_time = processing_time
                landmarks = face_result.multi_face_landmarks[0].landmark
                left_ratio = eye_aspect_ratio(landmarks, True)
                right_ratio = eye_aspect_ratio(landmarks, False)
                avg_eye = (left_ratio + right_ratio) / 2
                mouth_ratio = mouth_open_ratio(landmarks)
                yaw, pitch, roll = get_head_pose(landmarks)

                # ✅ NEW: Haar Cascade eye detection for better blink counting
                # Get face bounding box from MediaPipe for Haar Cascade
                h, w, _ = frame.shape
                x_coords = [landmarks[i].x * w for i in range(len(landmarks))]
                y_coords = [landmarks[i].y * h for i in range(len(landmarks))]
                face_x = int(min(x_coords))
                face_y = int(min(y_coords))
                face_w = int(max(x_coords) - min(x_coords))
                face_h = int(max(y_coords) - min(y_coords))
                face_roi = (face_x, face_y, face_w, face_h)
                
                eyes_count, eye_closed = detect_eyes_haar(frame, face_roi)
                
                # Enhanced blink detection using Haar Cascade
                if eye_closed:
                    eyes_closed_frames += 1
                    score_eye_openness = 1
                    
                    # Register blink when eyes transition from open to closed
                    if last_eye_state == "open" and eyes_closed_frames >= CONSECUTIVE_FRAMES_FOR_BLINK:
                        blink_counter += 1
                        blink_timestamps.append(processing_time)
                        last_eye_state = "closed"
                        print(f"👁️ Blink detected! Total: {blink_counter}")
                    
                    # Check for drowsiness (eyes closed too long)
                    if last_eye_state == "closed":
                        if eye_was_open:
                            eye_closed_start_time = processing_time
                            eye_was_open = False
                        
                        if (processing_time - eye_closed_start_time) > DROWSY_TIME_THRESH:
                            is_drowsy = True
                else:
                    eyes_closed_frames = 0
                    score_eye_openness = 2
                    last_eye_state = "open"
                    eye_was_open = True

                # Mouth
                if mouth_ratio > MOUTH_OPEN_THRESH:
                    score_mouth = 1
                else:
                    score_mouth = 2

                # Neck Turn
                PITCH_STRAIGHT_MIN = -725
                PITCH_STRAIGHT_MAX = -600
                YAW_STRAIGHT_THRESH = 10
                ROLL_STRAIGHT_THRESH = 10
                YAW_TURNED_THRESH = 60
                
                is_straight = (abs(yaw) <= YAW_STRAIGHT_THRESH) and \
                              (abs(roll) <= ROLL_STRAIGHT_THRESH) and \
                              (PITCH_STRAIGHT_MIN <= pitch <= PITCH_STRAIGHT_MAX)
                is_fully_turned = (abs(yaw) > YAW_TURNED_THRESH)
                
                if is_straight:
                    score_neck = 3
                elif is_fully_turned:
                    score_neck = 1
                else:
                    score_neck = 2
                
                if score_neck == 3:
                    neck_direction_text = "Straight"
                else:
                    if abs(yaw) > YAW_STRAIGHT_THRESH:
                        neck_direction_text = "Right" if yaw > YAW_STRAIGHT_THRESH else "Left"
                    elif (pitch < PITCH_STRAIGHT_MIN or pitch > PITCH_STRAIGHT_MAX):
                         neck_direction_text = "Down" if pitch > PITCH_STRAIGHT_MAX else "Up"
                    elif abs(roll) > ROLL_STRAIGHT_THRESH:
                         neck_direction_text = "Tilted"
                    else:
                         neck_direction_text = "Turn"

                # Blink Rate
                while blink_timestamps and processing_time - blink_timestamps[0] > BLINK_TIME_WINDOW:
                    blink_timestamps.popleft()
                blinks_in_window = len(blink_timestamps)
                
                if blinks_in_window < NORMAL_BLINK_MIN:
                    score_blink_rate = 2
                elif blinks_in_window > NORMAL_BLINK_MAX:
                    score_blink_rate = 1
                else:
                    score_blink_rate = 3
            
            else:
                face_detected = False

            # ML Model Rating
            if not face_detected:
                final_rating = 1
            elif is_drowsy:
                final_rating = 1
            else:
                feat_eye_open = 1 if score_eye_openness == 2 else 0
                feat_mouth_closed = 1 if score_mouth == 2 else 0
                feat_neck = score_neck - 1
                feat_blink_normal = 1 if score_blink_rate == 3 else 0

                current_raw = (W_EYE_OPEN * feat_eye_open) + \
                              (W_MOUTH * feat_mouth_closed) + \
                              (W_NECK * feat_neck) + \
                              (W_BLINK * feat_blink_normal)
                
                scaled_rating = (current_raw / max_raw_score) * 4.0
                pre_final_rating = int(round(scaled_rating)) + 1
                final_rating = max(1, min(5, pre_final_rating))

            # Smoothing
            rating_buffer.append(final_rating)
            final_rating = int(round(sum(rating_buffer) / len(rating_buffer)))
            final_rating = max(1, min(5, final_rating))

            # Update cached values
            cached_final_rating = final_rating
            cached_label = RATING_LABELS[final_rating]
            cached_yaw, cached_pitch, cached_roll = yaw, pitch, roll
            cached_mouth_status = "closed" if score_mouth == 2 else "open"
            cached_eye_status = "open" if score_eye_openness == 2 else "closed"
            cached_mouth_text = "Closed (2)" if score_mouth == 2 else "Open (1)"
            cached_eye_text = "Open (2)" if score_eye_openness == 2 else "Closed (1)"
            cached_neck_text = neck_text_map[score_neck]
            cached_blink_text = blink_text_map[score_blink_rate]
            cached_blinks_in_window = blinks_in_window
            cached_neck_direction_text = neck_direction_text
            cached_face_detected = face_detected
            cached_is_drowsy = is_drowsy
        
        # --- Alert + Motor Logic ---
        if not cached_face_detected:
            if (current_time - last_face_seen_time) > FACE_NOT_DETECTED_VIBRATE_THRESH:
                motor_on()
            else:
                motor_off()
            
            if (current_time - last_alert_time) >= 3.0:
                say("face not detected")
                last_alert_time = current_time
            last_rating = 1 
        
        elif cached_is_drowsy:
            motor_on()
            if (current_time - last_alert_time) >= 1.0:
                say("wake up wake up")
                last_alert_time = current_time
            last_rating = 1

        elif cached_final_rating == 1:
            motor_on()
            if (current_time - last_alert_time) >= 1.0:
                say("wake")
                last_alert_time = current_time
            last_rating = 1

        elif cached_final_rating == 2:
            motor_on()
            if (current_time - last_alert_time) >= 3.0:
                say("wakeup")
                last_alert_time = current_time
            last_rating = 2
        
        elif cached_final_rating == 3:
            motor_off()
            if last_rating != 3: 
                say("distracted")
                last_alert_time = current_time
            last_rating = 3

        elif cached_final_rating == 4:
            motor_off()
            if last_rating != 4: 
                say("attentive")
                last_alert_time = current_time
            last_rating = 4
        
        else:
            motor_off()
            if last_rating != 5: 
                say("fully attentive")
                last_alert_time = current_time
            last_rating = 5

        # ✅ NEW: Stream data every 5 seconds
        if (current_time - last_stream_time) >= STREAM_INTERVAL:
            stream_data = {
                "jetson_id": JETSON_ID,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "epoch_time": current_time,
                "attention_score": cached_final_rating,
                "attention_label": cached_label,
                "mouth_status": cached_mouth_status,
                "eye_status": cached_eye_status,
                "neck_position": cached_neck_text,
                "neck_direction": cached_neck_direction_text,
                "blink_rate_status": cached_blink_text,
                "total_blinks": blink_counter,
                "recent_blinks": cached_blinks_in_window,
                "yaw": round(cached_yaw, 2),
                "pitch": round(cached_pitch, 2),
                "roll": round(cached_roll, 2),
                "face_detected": cached_face_detected,
                "is_drowsy": cached_is_drowsy
            }
            send_to_flask(stream_data)
            last_stream_time = current_time

        # Display Info
        cv2.putText(frame, f"ATTENTION: {cached_final_rating} - {cached_label}", (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        
        cv2.putText(frame, f"Yaw:{int(cached_yaw)} Pitch:{int(cached_pitch)} Roll:{int(cached_roll)}", (10, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, INFO_COLOR, 2)
        
        cv2.putText(frame, f"Mouth: {cached_mouth_text}", (10, 110),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, INFO_COLOR, 2)
        cv2.putText(frame, f"Eye: {cached_eye_text}", (10, 140),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, INFO_COLOR, 2)
        cv2.putText(frame, f"Neck: {cached_neck_text}", (10, 170),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, INFO_COLOR, 2)
        cv2.putText(frame, f"Blink Rate: {cached_blink_text}", (10, 200),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, INFO_COLOR, 2)
        cv2.putText(frame, f"Blinks (Total): {blink_counter}", (10, 230),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, INFO_COLOR, 2)
        cv2.putText(frame, f"Blinks (Last {BLINK_TIME_WINDOW}s): {cached_blinks_in_window}", (10, 260),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, INFO_COLOR, 2)
        
        cv2.putText(frame, f"Direction: {cached_neck_direction_text}", (10, 290),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, INFO_COLOR, 2)

        cv2.imshow("MediaPipe 0.8.5 - Video Pipeline", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

finally:
    print("Cleaning up GPIO...")
    GPIO.cleanup()
    cap.release()
    cv2.destroyAllWindows()
    print("Processing complete.")