from scapy.all import sniff, Dot11, Dot11ProbeReq, RadioTap
from gpiozero import LED, Buzzer
from os import system
import time, datetime, threading

# Run python script as sudo!

green = LED(18)
yellow = LED(15)
red = LED(14)
buzzer = Buzzer(23)

green.off()
yellow.off()
red.off()
buzzer.off()

interface = "wlan0"
det_treshold = -70
mac_timeout = 10

devices = {}

severity_index = 0
severity_time = 0
severity_timeout = 10

channels = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
channel_index = 0

def rssi_to_dis(rssi):
    if rssi <= -60:
        return "very far away"
    elif rssi <= -50:
        return "far away"
    elif rssi <= -40:
        return 'nearby'
    elif rssi <= -30:
        return 'closely'
    elif rssi <= 0:
        return 'extremely closely'
def rssi_to_severity(rssi):
    if rssi >= -70 and rssi <= -50:
        return 1
    elif rssi >= -50:
        return 2

def display_severity():
    global severity_index
    match severity_index:
        case 2:
            green.off()
            yellow.off()
            red.on()
        case 1:
            green.off()
            yellow.on() #Keep red on if already in case of decay
        case 0:
            red.off()
            yellow.off()
            green.on()

def handle_severity(stop_event):
    global severity_time, severity_timeout, severity_index
    try:
        while not stop_event.is_set():
            if severity_time+severity_timeout < time.time():
                if severity_index > 0 :
                    severity_index -= 1
                    severity_time = time.time()
            display_severity()
            time.sleep(0.1)
    except KeyboardInterrupt:
                print("Quitting handle.")
                quit()
def hop_channels(stop_event):
    global channels, channel_index
    time.sleep(2)
    while not stop_event.is_set():
        time.sleep(1)
        status = system(f"sudo iw dev {interface} set channel {str(channels[channel_index])}")
        if status != 0:
            print("Hopping error...")
        channel_index = (channel_index+1) % len(channels)
    print("Hop quitting!")

def pk_handle(packet):
    global devices, severity_index, severity_time
    if packet.haslayer(Dot11ProbeReq):
        mac_address = packet.addr2
        rssi = -999

        if packet.haslayer(RadioTap):
            if hasattr(packet[RadioTap], 'dBm_AntSignal'):
                rssi = packet[RadioTap].dBm_AntSignal
            elif hasattr(packet[RadioTap], 'dBm_antsignal'):
                rssi = packet[RadioTap].dbm_antsignal
        if rssi >= det_treshold:
            c_time = time.time()
            if mac_address not in devices or (c_time - devices[mac_address] > mac_timeout):
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Device {mac_address} detected {rssi_to_dis(rssi)} @ RSSI {rssi} dBm.")
                match rssi_to_severity(rssi):
                    case 1:
                        if severity_index < 2:
                            severity_index = 1
                            severity_time = c_time
                            buzzer.beep(on_time=0.5, off_time=0.5, n=2, background=True)
                    case 2:
                        severity_index = 2
                        severity_time = c_time
                        buzzer.beep(on_time=1, off_time=1, n=5, background=True)
                devices[mac_address] = c_time
if __name__ == "__main__":
    print(f"Setting {interface} to monitor mode...")
    system(f"""systemctl stop NetworkManager
ip link set {interface} down
iw dev {interface} set type monitor
ip link set {interface} up""")
    print("Done!")
    print(f"Starting detector on {interface}...")
    stop_event = threading.Event()
    threading.Thread(target=handle_severity, args=(stop_event,)).start()
    threading.Thread(target=hop_channels, args=(stop_event,)).start()
    try:
        sniff(iface=interface, prn=pk_handle, store=False)
    except KeyboardInterrupt:
        print("Quitting.")
        stop_event.set()
        green.off()
        yellow.off()
        red.off()
        buzzer.off()
        system(f"""sudo ip link set {interface} down
sudo iw dev {interface} set type managed
sudo ip link set {interface} up
sudo systemctl restart NetworkManager""")
    except Exception as e:
        print(f'Failed because of {e}')
    finally:
        stop_event.set()
        system(f"""sudo ip link set {interface} down
sudo iw dev {interface} set type managed
sudo ip link set {interface} up
sudo systemctl restart NetworkManager""")