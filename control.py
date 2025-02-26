import os
import sys
import can
import canopen
import threading
import time
import serial.tools.list_ports
from flask import Flask, render_template, request, jsonify
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl
from threading import Thread

# Flask Setup
app = Flask(__name__, template_folder="templates")
socketio = None

# CAN Configuration
NODE_ID = 19  # Actuator Node ID
BITRATE = 500000  # 500 kbps
network = None
node = None
last_move_command = None
@app.route("/")
def index():
    """Load UI with available COM ports."""
    com_ports = [port.device for port in serial.tools.list_ports.comports()]
    return render_template("index.html", com_ports=com_ports)

@app.route("/list_ports")
def list_ports():
    """Returns available COM ports."""
    ports = [port.device for port in serial.tools.list_ports.comports()]
    print(f"Detected COM Ports: {ports}")  # ✅ Debugging output
    return jsonify(ports)




@app.route("/connect", methods=["POST"])
def connect_can():
    """Connects to the CAN network and ensures the actuator is in OPERATIONAL mode."""
    global network, node

    data = request.json
    com_port = data.get("com_port")

    if not com_port:
        return jsonify({"error": "COM port must be selected."}), 400

    try:
        print(f"🔄 Connecting to CAN on {com_port} at 500kbit/s...")

        network = canopen.Network()
        network.connect(bustype="slcan", channel=com_port, bitrate=500000)

        node = network.add_node(19)  # Default Node ID
        print("✔ CAN bus connected.")

        # Perform RESET COMMUNICATION before OPERATIONAL mode
        node.nmt.state = 'RESET COMMUNICATION'
        time.sleep(2)
        node.nmt.state = 'OPERATIONAL'
        print("✔ Actuator set to OPERATIONAL mode.")

        # Add delay before reading SDOs
        time.sleep(2)

        heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)
        heartbeat_thread.start()


        return jsonify({"status": "success", "message": f"Connected to {com_port} and settings applied"}), 200

    except Exception as e:
        print(f"❌ Connection error: {e}")
        return jsonify({"error": str(e)}), 500

def disable_sleep_if_enabled():
    """Checks if the actuator's sleep mode is enabled (1) and disables it (sets to 0), then resets communication."""
    global network, node

    if network is None or node is None:
        print("❌ Cannot check sleep mode: No active CAN connection.")
        return

    try:
        # Read the current sleep setting
        current_sleep_value = node.sdo[0x2013].raw
        print(f"🔍 Current Sleep Mode: {current_sleep_value}")

        if current_sleep_value == 1:
            print("⚠️ Sleep mode is enabled. Disabling it now...")
            node.sdo[0x2013].raw = 0  # Disable sleep mode
            time.sleep(1)  # Allow time for storage

            # Read back to verify
            new_sleep_value = node.sdo[0x2013].raw
            print(f"✔ Sleep mode disabled (New Value: {new_sleep_value})")

            # Confirm the change persisted
            if new_sleep_value == 0:
                print("✅ Sleep mode successfully disabled.")

                # Reset communication to reinitialize the actuator
                print("🔄 Resetting actuator communication to restore responsiveness...")
                node.nmt.state = "RESET COMMUNICATION"
                time.sleep(2)
                node.nmt.state = "OPERATIONAL"
                print("✔ Actuator back to OPERATIONAL mode.")

            else:
                print("⚠️ Warning: Sleep mode change did not persist.")

        else:
            print("✅ Sleep mode is already disabled. No action needed.")

    except Exception as e:
        print(f"❌ Failed to check/disable sleep mode: {e}")
        
@app.route('/move', methods=['POST'])
def move_actuator():
    """Sends a CANopen RPDO command with user-defined position, speed, and acceleration."""
    global network, node, last_move_command

    if network is None or node is None:
        return jsonify({"error": "CAN bus not connected"}), 400

    data = request.json
    direction = data.get("direction")  # "raise" or "lower"
    target_position = int(data.get("target_position", 100))  # Default 100mm for Raise
    target_speed = int(data.get("target_speed", 800))  # Default 80% duty cycle
    acceleration = int(data.get("acceleration", 500))  # Default acceleration

    if direction == "lower":
        target_position = 0  # Ensure Lower always goes to 0mm

    print(f"🔄 Sending {direction.upper()} command: Position={target_position}mm, Speed={target_speed}, Accel={acceleration}")

    try:
        # Convert target position from mm to actuator units (10x for resolution)
        position_value = target_position * 10
        current_limit = 0x007D  # 12.5A (125 decimal)
        movement_profile = acceleration  # Acceleration value
        control_bits = 0x01  # Enable Motion

        # Format data in Little Endian order
        can_data = [
            position_value & 0xFF, (position_value >> 8) & 0xFF,  # Target Position
            current_limit & 0xFF, (current_limit >> 8) & 0xFF,  # Current Limit
            target_speed & 0xFF, (target_speed >> 8) & 0xFF,  # Target Speed
            movement_profile & 0xFF,  # Movement Profile (Acceleration)
            control_bits  # Control Bits (Enable motion)
        ]

        # Save the last command
        last_move_command = can_data

        # Send CAN message
        msg = can.Message(arbitration_id=(0x200 + NODE_ID), data=can_data, is_extended_id=False)
        network.bus.send(msg)

        print(f"✔ Actuator moving {direction} to {target_position}mm at {target_speed} speed with {acceleration} acceleration")

        return jsonify({
            "status": "success",
            "message": f"Actuator moving {direction} to {target_position}mm at {target_speed} speed with {acceleration} acceleration"
        }), 200

    except Exception as e:
        print(f"❌ Movement command failed: {e}")
        return jsonify({"error": str(e)}), 500



# Keep sending the last known command every 4 seconds
def keep_alive():
    global last_move_command, network

    while True:
        if last_move_command:
            try:
                msg = can.Message(arbitration_id=(0x200 + NODE_ID), data=last_move_command, is_extended_id=False)
                network.bus.send(msg)
                print("✔ Sent keep-alive PDO message")
            except Exception as e:
                print(f"❌ Keep-alive error: {e}")
        time.sleep(2)  # Repeat every 4 seconds

# Start keep-alive in a separate thread
keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()


def send_heartbeat():
    """Continuously sends heartbeat messages every 2 seconds."""
    global network, node

    if network is None or node is None:
        print("❌ Cannot start heartbeat: No active CAN connection.")
        return

    try:
        print("🔄 Starting heartbeat messages every 2 seconds...")
        while True:
            msg = can.Message(arbitration_id=0x700 + 19, data=[0x05], is_extended_id=False)
            network.bus.send(msg)
            time.sleep(2)  # Send heartbeat every 2 seconds
    except Exception as e:
        print(f"❌ Heartbeat error: {e}")


@app.route('/can_status', methods=['GET'])
def check_can_status():
    """Checks if the CAN bus is active and reports errors."""
    global network

    if network is None:
        return jsonify({"error": "CAN bus not initialized"}), 400

    try:
        bus_status = network.bus.state  # Get CAN bus state
        return jsonify({"status": "success", "bus_state": str(bus_status)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/read_feedback', methods=['GET'])
def read_feedback():
    """Reads actuator feedback from TPDO messages."""
    global network, node

    if network is None or node is None:
        return jsonify({"error": "CAN bus not connected"}), 400

    try:
        # Listen for actuator feedback
        message = network.bus.recv(timeout=1.0)  # Wait for 1 second
        if message:
            return jsonify({"status": "success", "data": message.data.hex()})
        else:
            return jsonify({"status": "error", "message": "No response from actuator"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# Qt WebView
class CANControlApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.browser = QWebEngineView()
        self.browser.setUrl(QUrl("http://127.0.0.1:5000"))
        layout = QVBoxLayout()
        layout.addWidget(self.browser)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.setWindowTitle("CAN Actuator Control")
        self.resize(1024, 768)

def run_qt():
    app = QApplication(sys.argv)
    window = CANControlApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    Thread(target=lambda: app.run(debug=False, use_reloader=False)).start()
    run_qt()
