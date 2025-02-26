import os
import time
import can
import canopen

# Configuration
USB_CAN_CHANNEL = "COM8"  # Update as needed (Windows COM port or 'can0' on Linux)
BAUDRATE = 500000          # Set baudrate to 500 kbit/s
NODE_ID = 19               # Default CANopen Node ID for Electrak HD

# Set EDS file path (Desktop location)
DESKTOP_PATH = os.path.join(os.path.expanduser("~"), "Desktop")
EDS_FILE_NAME = "Electrak_HD-20200113.eds"
EDS_FILE_PATH = os.path.join(DESKTOP_PATH, EDS_FILE_NAME)

# Check if EDS file exists
if not os.path.exists(EDS_FILE_PATH):
    raise FileNotFoundError(f"EDS file not found at {EDS_FILE_PATH}")

# Initialize CAN bus
print("🔄 Connecting to CAN bus at 500 kbit/s...")
network = canopen.Network()
network.connect(bustype="slcan", channel=USB_CAN_CHANNEL, bitrate=BAUDRATE)
print("✔ CAN bus connected.")

# Send NMT Operational Command
print("🔄 Sending NMT Operational Command...")
network.send_message(0x000, [0x01, NODE_ID])  # Set Node 19 to operational mode
time.sleep(2)  # Allow transition
print("✔ Device set to Operational Mode.")

# Add actuator node with EDS file
print(f"📂 Loading EDS file: {EDS_FILE_NAME}")
node = network.add_node(NODE_ID, EDS_FILE_PATH)

# Function to read and print all SDO parameters
def read_all_sdo_parameters():
    print("\n📋 **Electrak HD CANopen Parameters**\n")
    print(f"{'Index':<10} {'Sub-Index':<12} {'Name':<40} {'Value':<20}")

    for obj_index, obj in node.object_dictionary.items():
        if isinstance(obj, canopen.objectdictionary.Record) or isinstance(obj, canopen.objectdictionary.Array):
            for sub_index, sub_obj in obj.items():
                try:
                    value = node.sdo[obj_index][sub_index].raw
                    print(f"{hex(obj_index):<10} {hex(sub_index):<12} {sub_obj.name:<40} {value:<20}")
                except Exception as e:
                    print(f"{hex(obj_index):<10} {hex(sub_index):<12} {sub_obj.name:<40} ❌ Read Error: {e}")
        else:
            try:
                value = node.sdo[obj_index].raw
                print(f"{hex(obj_index):<10} {'-':<12} {obj.name:<40} {value:<20}")
            except Exception as e:
                print(f"{hex(obj_index):<10} {'-':<12} {obj.name:<40} ❌ Read Error: {e}")

# Read and print all parameters
read_all_sdo_parameters()

# Disconnect
print("\n🔌 Disconnecting from CAN bus.")
network.disconnect()
