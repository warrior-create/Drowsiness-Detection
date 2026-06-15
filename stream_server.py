from flask import Flask, request, jsonify, render_template_string
import redis
import json
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from threading import Thread, Lock
import time
from collections import Counter

app = Flask(__name__)

REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0
DATA_RETENTION_HOURS = 24

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

SENDER_EMAIL = "b24225@students.iitmandi.ac.in"
SENDER_PASSWORD = "vamcwrsjpsfjlzhq"
RECIPIENT_EMAIL = "b24160@students.iitmandi.ac.in"

ALERT_THRESHOLD = 2
ALERT_COOLDOWN = 15

redis_client = redis.Redis(
    host=REDIS_HOST,

    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True
)

alert_state = {}
alert_lock = Lock()

def store_data_in_redis(data):
    try:
        jetson_id = data.get('jetson_id', 'unknown')
        epoch_time = data.get('epoch_time', time.time())
        key = f"data:{jetson_id}:{epoch_time}"
        redis_client.setex(key, timedelta(hours=DATA_RETENTION_HOURS), json.dumps(data))
        redis_client.zadd(f"timeline:{jetson_id}", {key: epoch_time})
        redis_client.expire(f"timeline:{jetson_id}", timedelta(hours=DATA_RETENTION_HOURS))
        return True
    except Exception as e:
        print(f"Redis storage error: {e}")
        return False

def get_recent_data(jetson_id, hours=1):
    try:
        current_time = time.time()
        start_time = current_time - (hours * 3600)
        keys = redis_client.zrangebyscore(f"timeline:{jetson_id}", start_time, current_time)
        data_list = []
        for key in keys:
            data_str = redis_client.get(key)
            if data_str:
                data_list.append(json.loads(data_str))
        data_list.sort(key=lambda x: x.get('epoch_time', 0))
        return data_list
    except Exception as e:
        print(f"Redis retrieval error: {e}")
        return []

def send_alert_email(jetson_id, attention_score, data):
    try:
        # --- 1. Extract Location Data ---
        lat = data.get('latitude', 'N/A')
        lon = data.get('longitude', 'N/A')

        # --- 2. Generate Maps Link ---
        maps_section = ""
        if lat != 'N/A' and lon != 'N/A':
            maps_link = f"https://www.google.com/maps?q={lat},{lon}"
            maps_section = f"""
            <div style="margin-top: 20px; border-top: 1px solid #eee; padding-top: 15px;">
                <a href="{maps_link}" style="background-color: #1e40af; color: white; padding: 12px 20px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                    📍 View Location on Google Maps
                </a>
            </div>
            """

        subject = f"CRITICAL: Driver Attention Alert - {jetson_id}"
        
        # --- 3. Updated HTML Body ---
        body = f"""
        <html>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; background-color: #f1f5f9; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                
                <div style="background: #dc2626; color: white; padding: 24px; text-align: center;">
                    <h2 style="margin: 0; font-size: 24px; letter-spacing: 1px;">DRIVER SAFETY ALERT</h2>
                    <p style="margin: 5px 0 0 0; opacity: 0.9;">Immediate Attention Required</p>
                </div>

                <div style="padding: 30px;">
                    
                    <div style="text-align: center; margin-bottom: 25px; background: #fef2f2; padding: 15px; border-radius: 8px; border: 1px solid #fecaca;">
                        <p style="margin: 0; color: #7f1d1d; font-size: 14px; text-transform: uppercase; font-weight: bold;">Attention Score</p>
                        <div style="font-size: 36px; font-weight: 800; color: #dc2626; margin: 5px 0;">{attention_score}/5</div>
                        <div style="color: #991b1b; font-weight: 600;">{data.get('attention_label', 'N/A')}</div>
                    </div>

                    <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                        <tr>
                            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; color: #64748b;">Vehicle ID</td>
                            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #0f172a;">{jetson_id}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; color: #64748b;">Time</td>
                            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #0f172a;">{data.get('timestamp', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; color: #64748b;">Eye Status</td>
                            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #0f172a;">{data.get('eye_status', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; color: #64748b;">Drowsiness</td>
                            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; font-weight: 700; color: {'#dc2626' if data.get('is_drowsy', False) else '#16a34a'};">
                                {'DETECTED' if data.get('is_drowsy', False) else 'None'}
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; color: #64748b;">GPS Coordinates</td>
                            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; font-family: monospace; color: #0f172a;">
                                {lat}, {lon}
                            </td>
                        </tr>
                    </table>

                    {maps_section}

                </div>

                <div style="background: #f8fafc; padding: 15px; text-align: center; border-top: 1px solid #e2e8f0;">
                    <p style="margin: 0; font-size: 12px; color: #94a3b8;">
                        Sent automatically by Driver Safety Monitoring System<br>
                        Logged at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECIPIENT_EMAIL
        html_part = MIMEText(body, 'html')
        msg.attach(html_part)
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

def check_and_send_alert(data):
    jetson_id = data.get('jetson_id', 'unknown')
    attention_score = data.get('attention_score', 5)
    if attention_score < ALERT_THRESHOLD:
        with alert_lock:
            current_time = time.time()
            last_alert_time = alert_state.get(jetson_id, 0)
            if current_time - last_alert_time >= ALERT_COOLDOWN:
                Thread(target=send_alert_email, args=(jetson_id, attention_score, data), daemon=True).start()
                alert_state[jetson_id] = current_time

@app.route('/stream', methods=['POST'])
def receive_stream():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data received"}), 400
        if store_data_in_redis(data):
            check_and_send_alert(data)
            return jsonify({
                "status": "success",
                "message": "Data received and stored",
                "jetson_id": data.get('jetson_id'),
                "timestamp": data.get('timestamp')
            }), 200
        else:
            return jsonify({"error": "Failed to store data"}), 500
    except Exception as e:
        print(f"Error processing stream: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/data/<jetson_id>')
def get_data_api(jetson_id):
    hours = request.args.get('hours', default=1, type=int)
    data = get_recent_data(jetson_id, hours)
    return jsonify(data)

@app.route('/api/devices')
def get_devices():
    try:
        keys = redis_client.keys("timeline:*")
        devices = [key.replace("timeline:", "") for key in keys]
        return jsonify({"devices": devices})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route('/dashboard/<jetson_id>')
def device_dashboard(jetson_id):
    return render_template_string(DEVICE_DASHBOARD_HTML, jetson_id=jetson_id)

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Driver Safety Monitoring System</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        primary: '#1e40af',
                        secondary: '#64748b',
                    }
                }
            }
        }
    </script>
</head>
<body class="bg-slate-50">
    <nav class="bg-white border-b border-slate-200">
        <div class="max-w-7xl mx-auto px-6 py-4">
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-4">
                    <div class="w-12 h-12 bg-blue-600 rounded-lg flex items-center justify-center">
                        <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path>
                        </svg>
                    </div>
                    <div>
                        <h1 class="text-xl font-bold text-slate-900">Driver Safety Monitor</h1>
                        <p class="text-sm text-slate-600">Real-time Fleet Management</p>
                    </div>
                </div>
                <div class="flex items-center space-x-2 px-4 py-2 bg-green-50 border border-green-200 rounded-lg">
                    <div class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                    <span class="text-sm font-semibold text-green-700">System Active</span>
                </div>
            </div>
        </div>
    </nav>

    <main class="max-w-7xl mx-auto px-6 py-8">
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
            <div class="bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl p-6 border border-blue-200">
                <div class="w-16 h-16 bg-blue-600 rounded-xl flex items-center justify-center mb-4">
                    <svg class="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                    </svg>
                </div>
                <h3 class="text-lg font-bold text-slate-900 mb-2">Eye Tracking</h3>
                <p class="text-sm text-slate-700">Real-time monitoring of eye movements, blink patterns, and gaze direction to detect driver attention levels</p>
            </div>

            <div class="bg-gradient-to-br from-purple-50 to-purple-100 rounded-xl p-6 border border-purple-200">
                <div class="w-16 h-16 bg-purple-600 rounded-xl flex items-center justify-center mb-4">
                    <svg class="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                </div>
                <h3 class="text-lg font-bold text-slate-900 mb-2">Drowsiness Detection</h3>
                <p class="text-sm text-slate-700">Advanced algorithms analyze facial features and behavior patterns to identify signs of driver fatigue</p>
            </div>

            <div class="bg-gradient-to-br from-green-50 to-green-100 rounded-xl p-6 border border-green-200">
                <div class="w-16 h-16 bg-green-600 rounded-xl flex items-center justify-center mb-4">
                    <svg class="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                </div>
                <h3 class="text-lg font-bold text-slate-900 mb-2">Head Pose Analysis</h3>
                <p class="text-sm text-slate-700">Track head orientation and position to ensure drivers maintain proper focus on the road ahead</p>
            </div>
        </div>

        <div class="mb-8">
            <h2 class="text-2xl font-bold text-slate-900 mb-2">Active Vehicle Fleet</h2>
            <p class="text-slate-600">Monitor driver attention and safety metrics in real-time</p>
        </div>

        <div id="vehicles" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <div class="col-span-full flex justify-center items-center py-12">
                <div class="text-center">
                    <div class="w-12 h-12 border-4 border-slate-300 border-t-blue-600 rounded-full animate-spin mx-auto mb-4"></div>
                    <p class="text-slate-600">Loading vehicle data...</p>
                </div>
            </div>
        </div>
    </main>

    <script>
        function loadDevices() {
            fetch('/api/devices')
                .then(response => response.json())
                .then(data => {
                    const container = document.getElementById('vehicles');
                    if (data.devices.length === 0) {
                        container.innerHTML = '<div class="col-span-full text-center py-12"><p class="text-slate-600">No vehicles currently active</p></div>';
                        return;
                    }
                    container.innerHTML = '';
                    data.devices.forEach(device => {
                        const card = document.createElement('div');
                        card.className = 'bg-white rounded-xl border border-slate-200 p-6 hover:shadow-lg transition-all cursor-pointer hover:border-blue-500';
                        card.onclick = () => window.location.href = `/dashboard/${device}`;
                        card.innerHTML = `
                            <div class="flex items-start justify-between mb-4">
                                <div class="w-14 h-14 bg-gradient-to-br from-blue-500 to-blue-600 rounded-lg flex items-center justify-center">
                                    <svg class="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path>
                                    </svg>
                                </div>
                                <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">Active</span>
                            </div>
                            <h3 class="text-lg font-bold text-slate-900 mb-2">${device}</h3>
                            <div class="space-y-2 pt-4 border-t border-slate-100">
                                <div class="flex justify-between text-sm">
                                    <span class="text-slate-600">Status</span>
                                    <span class="font-medium text-slate-900">Monitoring</span>
                                </div>
                                <div class="flex justify-between text-sm">
                                    <span class="text-slate-600">Last Update</span>
                                    <span class="font-medium text-slate-900">Live</span>
                                </div>
                            </div>
                        `;
                        container.appendChild(card);
                    });
                })
                .catch(error => {
                    console.error('Error loading devices:', error);
                    document.getElementById('vehicles').innerHTML = '<div class="col-span-full text-center py-12"><p class="text-red-600">Error loading vehicle data</p></div>';
                });
        }
        loadDevices();
        setInterval(loadDevices, 5000);
    </script>
</body>
</html>
'''

DEVICE_DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ jetson_id }} - Driver Monitor</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body class="bg-slate-50">
    <nav class="bg-white border-b border-slate-200">
        <div class="max-w-[1600px] mx-auto px-6 py-4">
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-4">
                    <a href="/" class="inline-flex items-center px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors">
                        <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"></path>
                        </svg>
                        Back to Fleet
                    </a>
                    <div>
                        <h1 class="text-xl font-bold text-slate-900">{{ jetson_id }}</h1>
                        <p class="text-sm text-slate-600" id="lastUpdate">Live Monitoring</p>
                    </div>
                </div>
                <div class="flex items-center space-x-2 px-4 py-2 bg-green-50 border border-green-200 rounded-lg">
                    <div class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                    <span class="text-sm font-semibold text-green-700">Active Monitoring</span>
                </div>
            </div>
        </div>
    </nav>

    <main class="max-w-[1600px] mx-auto px-6 py-6">
        <div id="alertBanner" class="hidden mb-6 bg-red-50 border-l-4 border-red-500 p-4 rounded-lg">
            <div class="flex items-center">
                <svg class="w-6 h-6 text-red-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                </svg>
                <div>
                    <h3 class="text-sm font-bold text-red-800">Critical Attention Alert</h3>
                    <p class="text-sm text-red-700 mt-1">Driver attention level is critically low. Immediate action required.</p>
                </div>
            </div>
        </div>

        <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-4 mb-6">
            <div class="bg-white rounded-lg border border-slate-200 p-4">
                <p class="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Current Attention</p>
                <p class="text-2xl font-bold text-slate-900" id="currentAttention">-</p>
            </div>
            <div class="bg-white rounded-lg border border-slate-200 p-4">
                <p class="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">10s Average</p>
                <p class="text-2xl font-bold text-slate-900" id="avgAttention">-</p>
            </div>
            <div class="bg-white rounded-lg border border-slate-200 p-4">
                <p class="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">10s Mode</p>
                <p class="text-2xl font-bold text-slate-900" id="modeAttention">-</p>
            </div>
            <div class="bg-white rounded-lg border border-slate-200 p-4">
                <p class="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Eye Status</p>
                <p class="text-lg font-bold text-slate-900" id="eyeStatus">-</p>
            </div>
            <div class="bg-white rounded-lg border border-slate-200 p-4">
                <p class="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Drowsiness</p>
                <p class="text-lg font-bold text-slate-900" id="drowsyStatus">-</p>
            </div>
            <div class="bg-white rounded-lg border border-slate-200 p-4">
                <p class="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Blink Rate</p>
                <p class="text-lg font-bold text-slate-900" id="blinkRate">-</p>
            </div>
            <div class="bg-white rounded-lg border border-slate-200 p-4">
                <p class="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Head Position</p>
                <p class="text-lg font-bold text-slate-900" id="neckPosition">-</p>
            </div>
            <div class="bg-white rounded-lg border border-slate-200 p-4">
                <p class="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Face Detection</p>
                <p class="text-lg font-bold text-slate-900" id="faceDetected">-</p>
            </div>
        </div>

        <div class="bg-white rounded-lg border border-slate-200 p-6 mb-6">
            <div class="flex flex-wrap items-center justify-between gap-4 mb-6">
                <h2 class="text-lg font-bold text-slate-900">Attention Score Analysis</h2>
                <div class="flex flex-wrap items-center gap-3">
                    <div class="flex items-center gap-2">
                        <label class="text-sm font-medium text-slate-700">Time Range</label>
                        <select id="timeRange" class="px-3 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500">
                            <option value="5">Last 5 Minutes</option>
                            <option value="15">Last 15 Minutes</option>
                            <option value="30">Last 30 Minutes</option>
                            <option value="60" selected>Last 1 Hour</option>
                            <option value="180">Last 3 Hours</option>
                            <option value="360">Last 6 Hours</option>
                            <option value="720">Last 12 Hours</option>
                            <option value="1440">Last 24 Hours</option>
                        </select>
                    </div>
                    <div class="flex items-center gap-2">
                        <label class="text-sm font-medium text-slate-700">Interval</label>
                        <select id="groupBy" class="px-3 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500">
                            <option value="1">1 Minute</option>
                            <option value="5" selected>5 Minutes</option>
                            <option value="10">10 Minutes</option>
                            <option value="15">15 Minutes</option>
                            <option value="30">30 Minutes</option>
                            <option value="60">1 Hour</option>
                        </select>
                    </div>
                </div>
            </div>
            <div class="h-80">
                <canvas id="barChart"></canvas>
            </div>
        </div>

        <div class="bg-white rounded-lg border border-slate-200 p-6 mb-6">
            <h2 class="text-lg font-bold text-slate-900 mb-6">Real-time Attention Monitoring</h2>
            <div class="h-80">
                <canvas id="attentionChart"></canvas>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div class="bg-white rounded-lg border border-slate-200 p-6">
                <h2 class="text-lg font-bold text-slate-900 mb-6">Blink Analysis</h2>
                <div class="h-80">
                    <canvas id="blinkChart"></canvas>
                </div>
            </div>
            <div class="bg-white rounded-lg border border-slate-200 p-6">
                <h2 class="text-lg font-bold text-slate-900 mb-6">Head Orientation</h2>
                <div class="h-80">
                    <canvas id="orientationChart"></canvas>
                </div>
            </div>
        </div>
    </main>

    <script>
        const jetsonId = "{{ jetson_id }}";
        let attentionChart, blinkChart, orientationChart, barChart;
        let allData = [];

        function initCharts() {
            Chart.defaults.color = '#64748b';
            Chart.defaults.borderColor = '#e2e8f0';
            
            const barCtx = document.getElementById('barChart').getContext('2d');
            barChart = new Chart(barCtx, {
                type: 'bar',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Average Attention Score',
                        data: [],
                        backgroundColor: [],
                        borderRadius: 4,
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: '#1e293b',
                            padding: 12,
                            titleColor: '#f8fafc',
                            bodyColor: '#e2e8f0',
                            borderColor: '#334155',
                            borderWidth: 1,
                            callbacks: {
                                label: function(context) {
                                    return `Score: ${context.parsed.y.toFixed(2)}/5`;
                                }
                            }
                        }
                    },
                    scales: {
                        y: { 
                            min: 0, 
                            max: 5,
                            grid: { color: '#f1f5f9' },
                            ticks: { stepSize: 1 }
                        },
                        x: { grid: { display: false } }
                    }
                }
            });

            const attentionCtx = document.getElementById('attentionChart').getContext('2d');
            attentionChart = new Chart(attentionCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Attention Score',
                        data: [],
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        tension: 0.4,
                        fill: true,
                        borderWidth: 2,
                        pointRadius: 0,
                        pointHoverRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: '#1e293b',
                            padding: 12,
                            borderColor: '#334155',
                            borderWidth: 1
                        }
                    },
                    scales: {
                        y: { 
                            min: 0, 
                            max: 5,
                            grid: { color: '#f1f5f9' },
                            ticks: { stepSize: 1 }
                        },
                        x: { grid: { display: false } }
                    }
                }
            });

            const blinkCtx = document.getElementById('blinkChart').getContext('2d');
            blinkChart = new Chart(blinkCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Blinks (5s window)',
                        data: [],
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        tension: 0.4,
                        fill: true,
                        borderWidth: 2,
                        pointRadius: 0,
                        pointHoverRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: '#1e293b',
                            padding: 12,
                            borderColor: '#334155',
                            borderWidth: 1
                        }
                    },
                    scales: {
                        y: { 
                            beginAtZero: true,
                            grid: { color: '#f1f5f9' }
                        },
                        x: { grid: { display: false } }
                    }
                }
            });

            const orientationCtx = document.getElementById('orientationChart').getContext('2d');
            orientationChart = new Chart(orientationCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Yaw',
                            data: [],
                            borderColor: '#ef4444',
                            backgroundColor: 'transparent',
                            tension: 0.4,
                            borderWidth: 2,
                            pointRadius: 0
                        },
                        {
                            label: 'Pitch',
                            data: [],
                            borderColor: '#3b82f6',
                            backgroundColor: 'transparent',
                            tension: 0.4,
                            borderWidth: 2,
                            pointRadius: 0
                        },
                        {
                            label: 'Roll',
                            data: [],
                            borderColor: '#f59e0b',
                            backgroundColor: 'transparent',
                            tension: 0.4,
                            borderWidth: 2,
                            pointRadius: 0
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { 
                            display: true,
                            position: 'top'
                        },
                        tooltip: {
                            backgroundColor: '#1e293b',
                            padding: 12,
                            borderColor: '#334155',
                            borderWidth: 1
                        }
                    },
                    scales: {
                        y: { 
                            min: -90, 
                            max: 90,
                            grid: { color: '#f1f5f9' }
                        },
                        x: { grid: { display: false } }
                    }
                }
            });
        }

        function getColorForScore(value) {
            if (value >= 4.5) return '#10b981';
            if (value >= 3.5) return '#22c55e';
            if (value >= 2.5) return '#eab308';
            if (value >= 1.5) return '#f59e0b';
            return '#ef4444';
        }

        function updateBarChart() {
            const rangeMinutes = parseInt(document.getElementById('timeRange').value);
            const intervalMinutes = parseInt(document.getElementById('groupBy').value);
            
            if (allData.length === 0) return;
            
            const now = allData[allData.length - 1].epoch_time;
            const startTime = now - (rangeMinutes * 60);
            const filteredData = allData.filter(d => d.epoch_time >= startTime && d.epoch_time <= now);
            
            if (filteredData.length === 0) {
                barChart.data.labels = [];
                barChart.data.datasets[0].data = [];
                barChart.data.datasets[0].backgroundColor = [];
                barChart.update();
                return;
            }
            
            const groups = {};
            filteredData.forEach(d => {
                const timeFromStart = d.epoch_time - startTime;
                const intervalIndex = Math.floor(timeFromStart / (intervalMinutes * 60));
                const intervalStart = startTime + (intervalIndex * intervalMinutes * 60);
                if (!groups[intervalStart]) {
                    groups[intervalStart] = [];
                }
                groups[intervalStart].push(d.attention_score);
            });
            
            const labels = [];
            const averages = [];
            const backgroundColors = [];
            const sortedKeys = Object.keys(groups).sort((a, b) => parseFloat(a) - parseFloat(b));
            
            sortedKeys.forEach(key => {
                const scores = groups[key];
                const avg = scores.reduce((sum, s) => sum + s, 0) / scores.length;
                const date = new Date(parseFloat(key) * 1000);
                const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                labels.push(timeStr);
                averages.push(avg);
                backgroundColors.push(getColorForScore(avg));
            });
            
            barChart.data.labels = labels;
            barChart.data.datasets[0].data = averages;
            barChart.data.datasets[0].backgroundColor = backgroundColors;
            barChart.update();
        }

        function calculateMode(arr) {
            if (arr.length === 0) return null;
            const frequency = {};
            let maxFreq = 0;
            let mode = arr[0];
            arr.forEach(val => {
                frequency[val] = (frequency[val] || 0) + 1;
                if (frequency[val] > maxFreq) {
                    maxFreq = frequency[val];
                    mode = val;
                }
            });
            return mode;
        }

        function getAttentionColor(score) {
            if (score >= 4.5) return 'text-green-600';
            if (score >= 3.5) return 'text-green-500';
            if (score >= 2.5) return 'text-yellow-500';
            if (score >= 1.5) return 'text-orange-500';
            return 'text-red-600';
        }

        function updateDashboard() {
            fetch(`/api/data/${jetsonId}?hours=24`)
                .then(response => response.json())
                .then(data => {
                    if (data.length === 0) return;
                    
                    allData = data;
                    const latest = data[data.length - 1];
                    
                    const alertBanner = document.getElementById('alertBanner');
                    if (latest.attention_score < 2) {
                        alertBanner.classList.remove('hidden');
                    } else {
                        alertBanner.classList.add('hidden');
                    }
                    
                    const currentEl = document.getElementById('currentAttention');
                    currentEl.textContent = `${latest.attention_score}/5`;
                    currentEl.className = `text-2xl font-bold ${getAttentionColor(latest.attention_score)}`;
                    
                    const tenSecondsAgo = latest.epoch_time - 10;
                    const recentData = data.filter(d => d.epoch_time >= tenSecondsAgo);
                    
                    if (recentData.length > 0) {
                        const avgScore = (recentData.reduce((sum, d) => sum + d.attention_score, 0) / recentData.length).toFixed(2);
                        const avgEl = document.getElementById('avgAttention');
                        avgEl.textContent = avgScore;
                        avgEl.className = `text-2xl font-bold ${getAttentionColor(parseFloat(avgScore))}`;
                        
                        const scores = recentData.map(d => d.attention_score);
                        const modeScore = calculateMode(scores);
                        const modeEl = document.getElementById('modeAttention');
                        modeEl.textContent = `${modeScore}/5`;
                        modeEl.className = `text-2xl font-bold ${getAttentionColor(modeScore)}`;
                    }
                    
                    document.getElementById('eyeStatus').textContent = latest.eye_status || '-';
                    
                    const drowsyEl = document.getElementById('drowsyStatus');
                    drowsyEl.textContent = latest.is_drowsy ? 'YES' : 'No';
                    drowsyEl.className = latest.is_drowsy ? 'text-lg font-bold text-red-600' : 'text-lg font-bold text-green-600';
                    
                    document.getElementById('blinkRate').textContent = latest.blink_rate_status || '-';
                    document.getElementById('neckPosition').textContent = latest.neck_position || '-';
                    document.getElementById('faceDetected').textContent = latest.face_detected ? 'Yes' : 'No';
                    document.getElementById('lastUpdate').textContent = `Last update: ${latest.timestamp}`;

                    updateBarChart();

                    const oneHourAgo = latest.epoch_time - 3600;
                    const hourData = data.filter(d => d.epoch_time >= oneHourAgo);
                    
                    const times = hourData.map(d => new Date(d.timestamp).toLocaleTimeString());
                    const attentionScores = hourData.map(d => d.attention_score);
                    const blinks = hourData.map(d => d.recent_blinks);
                    const yaw = hourData.map(d => d.yaw);
                    const pitch = hourData.map(d => d.pitch);
                    const roll = hourData.map(d => d.roll);

                    attentionChart.data.labels = times;
                    attentionChart.data.datasets[0].data = attentionScores;
                    attentionChart.update();

                    blinkChart.data.labels = times;
                    blinkChart.data.datasets[0].data = blinks;
                    blinkChart.update();

                    orientationChart.data.labels = times;
                    orientationChart.data.datasets[0].data = yaw;
                    orientationChart.data.datasets[1].data = pitch;
                    orientationChart.data.datasets[2].data = roll;
                    orientationChart.update();
                })
                .catch(error => console.error('Error updating dashboard:', error));
        }

        document.getElementById('timeRange').addEventListener('change', updateBarChart);
        document.getElementById('groupBy').addEventListener('change', updateBarChart);

        initCharts();
        updateDashboard();
        setInterval(updateDashboard, 5000);
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    print("=" * 60)
    print("DRIVER SAFETY MONITORING SYSTEM")
    print("=" * 60)
    print(f"Redis Server: {REDIS_HOST}:{REDIS_PORT}")
    print(f"Alert Threshold: Attention Score < {ALERT_THRESHOLD}")
    print(f"Email Alerts: {'Enabled' if SENDER_EMAIL != 'your_email@gmail.com' else 'DISABLED'}")
    print(f"Web Dashboard: http://0.0.0.0:5001")
    print("=" * 60)
    print("System Ready")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5001, debug=True)