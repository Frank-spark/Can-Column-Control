### **Document: Explanation of `control3.py`**
This document explains the functionality of `control.py`, a **Flask and PyQt-based application** that controls a **CANopen actuator**. The script manages **CAN communication, actuator movement, and UI interaction**.

---

## **1️⃣ Overview**
This script:
- **Uses Flask** to serve a **web-based UI** for actuator control.
- **Uses PyQt6** to display the UI in a **desktop application**.
- **Manages CANopen communication** with an **Electrak HD actuator**.
- **Sends movement commands** and **monitors actuator feedback**.
- **Includes periodic heartbeat and keep-alive messages** to maintain communication.

---

## **2️⃣ Main Components**
### **🔹 2.1 Flask Web Server**
The script initializes a **Flask web server** that:
- Serves a **web-based UI** (`index.html`).
- Provides **API endpoints** for CAN communication.

#### **Key Flask Routes:**
| Route | Method | Description |
|--------|--------|-------------|
| `/` | GET | Loads the UI with available COM ports |
| `/list_ports` | GET | Returns a list of available COM ports |
| `/connect` | POST | Connects to the CAN bus |
| `/move` | POST | Sends movement commands to the actuator |
| `/disable_sleep` | POST | Disables sleep mode if enabled |
| `/can_status` | GET | Checks CAN bus state |
| `/read_feedback` | GET | Reads actuator feedback |

---

### **🔹 2.2 CAN Bus Communication**
The script **connects to the CAN bus** and **sends movement commands**.

#### **CAN Configuration**
```python
NODE_ID = 19  # Actuator Node ID
BITRATE = 500000  # 500 kbps
network = None
node = None
```
✅ **The actuator uses Node ID `19` and a baud rate of `500 kbit/s`**.

#### **Connecting to CAN Bus**
```python
@app.route("/connect", methods=["POST"])
def connect_can():
    global network, node
    data = request.json
    com_port = data.get("com_port")
    
    try:
        network = canopen.Network()
        network.connect(bustype="slcan", channel=com_port, bitrate=500000)
        node = network.add_node(NODE_ID)

        # Reset communication and set operational mode
        node.nmt.state = 'RESET COMMUNICATION'
        time.sleep(2)
        node.nmt.state = 'OPERATIONAL'
        
        print("✔ Actuator set to OPERATIONAL mode.")

        # Start periodic heartbeat messages
        threading.Thread(target=send_heartbeat, daemon=True).start()

        return jsonify({"status": "success", "message": f"Connected to {com_port}"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```
✅ **Connects to the CAN bus and ensures the actuator is in `OPERATIONAL` mode**.

---

### **🔹 2.3 Disabling Sleep Mode**
Some Electrak HD actuators enter **sleep mode** automatically, stopping movement.  
The script **checks and disables sleep mode (`0x2013`)**.

#### **Function to Disable Sleep Mode**
```python
def disable_sleep_if_enabled():
    global network, node
    if network is None or node is None:
        return

    try:
        current_sleep_value = node.sdo[0x2013].raw
        if current_sleep_value == 1:
            node.sdo[0x2013].raw = 0  # Disable sleep mode
            time.sleep(1)
            node.nmt.state = "RESET COMMUNICATION"
            time.sleep(2)
            node.nmt.state = "OPERATIONAL"
            print("✔ Sleep mode disabled.")
    except Exception as e:
        print(f"❌ Failed to disable sleep mode: {e}")
```
✅ **Only disables sleep if it is enabled (`1`).**  
✅ **Performs a `RESET COMMUNICATION` to reinitialize the actuator.**  

---

### **🔹 2.4 Sending Movement Commands**
The script sends **CANopen RPDO commands** to move the actuator **up (raise)** or **down (lower)**.

#### **Move Command:**
```python
@app.route('/move', methods=['POST'])
def move_actuator():
    global network, node, last_move_command
    if network is None or node is None:
        return jsonify({"error": "CAN bus not connected"}), 400

    data = request.json
    direction = data.get("direction")
    target_position = int(data.get("target_position", 100))
    target_speed = int(data.get("target_speed", 800))
    acceleration = int(data.get("acceleration", 500))

    if direction == "lower":
        target_position = 0  # Lower always moves to 0mm

    print(f"Sending {direction.upper()} command: {target_position}mm at {target_speed} speed.")

    try:
        # Convert target position from mm to actuator units
        position_value = target_position * 10
        current_limit = 0x007D  # 12.5A
        control_bits = 0x01  # Enable Motion

        can_data = [
            position_value & 0xFF, (position_value >> 8) & 0xFF,
            current_limit & 0xFF, (current_limit >> 8) & 0xFF,
            target_speed & 0xFF, (target_speed >> 8) & 0xFF,
            acceleration & 0xFF,
            control_bits
        ]

        last_move_command = can_data
        msg = can.Message(arbitration_id=(0x200 + NODE_ID), data=can_data, is_extended_id=False)
        network.bus.send(msg)

        return jsonify({"status": "success", "message": f"Actuator moving {direction}"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```
✅ **Uses user-defined target position, speed, and acceleration.**  
✅ **Formats data in Little Endian before sending the CAN message.**  
✅ **Saves the last command to allow periodic keep-alive messages.**  

---

### **🔹 2.5 Keep-Alive PDO Messages**
To **prevent the actuator from timing out**, the script resends the **last movement command** every **4 seconds**.

```python
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
        time.sleep(4)
```
✅ **Ensures the actuator stays active by re-sending commands every 4 seconds.**  

---

### **🔹 2.6 Sending Heartbeat Messages**
CANopen devices require **periodic heartbeat messages** to maintain communication.

```python
def send_heartbeat():
    global network, node
    if network is None or node is None:
        return

    try:
        while True:
            msg = can.Message(arbitration_id=0x700 + NODE_ID, data=[0x05], is_extended_id=False)
            network.bus.send(msg)
            time.sleep(2)  # Send every 2 seconds
    except Exception as e:
        print(f"❌ Heartbeat error: {e}")
```
✅ **Prevents the actuator from timing out by sending a heartbeat every 2 seconds.**  

---

### **🔹 2.7 UI Integration with PyQt6**
The script embeds the **Flask UI inside a PyQt6 application**.

```python
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

def run_qt():
    app = QApplication(sys.argv)
    window = CANControlApp()
    window.show()
    sys.exit(app.exec())
```
✅ **Displays the Flask UI inside a desktop app.**  

---

## **3️⃣ Conclusion**
This script **provides a complete CANopen actuator control system** using:
- ✅ **Flask** for the web UI.
- ✅ **PyQt6** for a desktop UI.
- ✅ **CANopen communication** for actuator control.
- ✅ **Periodic heartbeats & keep-alive messages** to maintain connection.

