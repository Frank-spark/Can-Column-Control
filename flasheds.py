import os
import time
import can
import canopen

# Configuration
USB_CAN_CHANNEL = "COM8"  # Update based on Windows COM port
BAUDRATE = 500000          # Set baudrate to 500 kbit/s
NODE_ID = 19               # Default CANopen Node ID for Electrak HD
NEW_SLEEP_VALUE = 0        # Set to 0 to disable sleep mode (1 = Enable, 0 = Disable)
NEW_ENABLE_VALUE = 1
NEW_SPEED_VALUE = 200      # Default Speed (200 out of 1000 max)

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

# Function to write and verify a parameter
def write_sdo_parameter(index, value):
    try:
        print(f"🚀 Writing {hex(index)} = {value}...")
        node.sdo[index].raw = value  # Write the new value
        time.sleep(0.5)  # Allow time for the device to process
        read_back_value = node.sdo[index].raw  # Read back value
        print(f"✔ Read back {hex(index)}: {read_back_value}")

        if read_back_value == value:
            print(f"✅ Successfully updated {hex(index)} to {value}")
        else:
            print(f"⚠️ Warning: {hex(index)} value mismatch! Expected {value}, but read {read_back_value}")

    except canopen.sdo.exceptions.SdoAbortedError as e:
        print(f"❌ Failed to write {hex(index)}: {e}")

# Step 1: Write Parameters
write_sdo_parameter(0x2013, NEW_SLEEP_VALUE)  # Disable sleep
write_sdo_parameter(0x2104, NEW_ENABLE_VALUE)  # Enable motion
write_sdo_parameter(0x2102, NEW_SPEED_VALUE)  # Set default speed

# Step 2: Store Configuration Persistently
try:
    print("💾 Saving parameters persistently...")
    node.sdo[0x1010][1].raw = b"save"  # "save" command in ASCII
    time.sleep(1)  # Allow time for storage
    print("✔ Configuration stored persistently.")
except Exception as e:
    print(f"❌ Failed to store parameters persistently: {e}")

# Step 3: Read Back to Verify After Storage
print("🔄 Re-reading settings to confirm persistence...")
try:
    sleep_value_after_save = node.sdo[0x2013].raw
    speed_value_after_save = node.sdo[0x2102].raw

    print(f"✔ Enable Sleep (0x2013) after save: {sleep_value_after_save}")
    print(f"✔ Target Speed (0x2102) after save: {speed_value_after_save}")

    if sleep_value_after_save == NEW_SLEEP_VALUE:
        print("✅ Enable Sleep parameter successfully updated and saved!")
    else:
        print("⚠️ Warning: Enable Sleep value did not persist after saving!")

    if speed_value_after_save == NEW_SPEED_VALUE:
        print("✅ Default Speed parameter successfully updated and saved!")
    else:
        print("⚠️ Warning: Default Speed value did not persist after saving!")

except Exception as e:
    print(f"❌ Failed to read parameters after save: {e}")

# Disconnect
print("🔌 Disconnecting from CAN bus.")
network.disconnect()
