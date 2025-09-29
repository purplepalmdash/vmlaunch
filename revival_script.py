
import sys
import os
import time
import libvirt

# --- Configuration ---
# IMPORTANT: Change this to your display manager if you are not using GDM
# Common options: gdm3, lightdm, sddm
DISPLAY_MANAGER_SERVICE = "gdm3"
POLL_INTERVAL_SECONDS = 5
# --- End Configuration ---

def main():
    if len(sys.argv) < 2:
        print("Usage: revival_script.py <vm_name>", file=sys.stderr)
        sys.exit(1)

    vm_name = sys.argv[1]
    print(f"Revival script started for VM: {vm_name}")

    conn = None
    try:
        conn = libvirt.open('qemu:///system')
    except libvirt.libvirtError as e:
        print(f"Revival script failed to connect to libvirt: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        domain = conn.lookupByName(vm_name)
    except libvirt.libvirtError:
        print(f"Revival script could not find VM: {vm_name}", file=sys.stderr)
        conn.close()
        sys.exit(1)

    # First, wait for the VM to actually start running
    while not domain.isActive():
        print("Revival script: Waiting for VM to become active...")
        time.sleep(POLL_INTERVAL_SECONDS)

    print(f"Revival script: VM {vm_name} is active. Monitoring for shutdown.")

    # Now, monitor until the VM is no longer active
    while domain.isActive():
        time.sleep(POLL_INTERVAL_SECONDS)

    print(f"Revival script: VM {vm_name} has shut down.")
    conn.close()

    # Time to bring the host GUI back to life
    print(f"Revival script: Restarting display manager '{DISPLAY_MANAGER_SERVICE}'...")
    # This command requires root privileges
    os.system(f"systemctl start {DISPLAY_MANAGER_SERVICE}")

    sys.exit(0)

if __name__ == "__main__":
    # Ensure the script is run with root privileges
    if os.geteuid() != 0:
        print("Error: This script must be run as root.", file=sys.stderr)
        sys.exit(1)
    main()
