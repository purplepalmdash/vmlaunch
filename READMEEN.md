# VM Launcher

This is a simple graphical launcher for `libvirt` virtual machines. It is designed to run in Kiosk mode on Ubuntu 18.04 and later, providing a large button interface to manage virtual machines.

## Features

- Starts in fullscreen mode.
- Automatically lists and refreshes all `libvirt` virtual machines and their statuses.
- Supports "Start/Shutdown/Reboot/Force Off" operations for virtual machines.
- Intelligently distinguishes between normal virtual machines and VFIO GPU passthrough virtual machines.
- Provides an embedded graphical viewer for normal virtual machines (using SPICE/VNC).
- Provides a "self-destruct and recover" startup process for GPU passthrough virtual machines.
- Provides the ability to shut down the physical host and adjust the system volume.

---

## Deployment Steps

Please strictly follow the steps below to deploy this application on your target machine.

### 1. System Dependencies

First, install all necessary packages.

```bash
sudo apt-get update
sudo apt-get install -y \
    python3 \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-3.0 \
    python3-libvirt \
    gir1.2-gtk-vnc-2.0 \
    gir1.2-spiceclientgtk-3.0 \
    software-properties-common
```

### 2. User Permissions

The user running this application needs specific permissions.

- **Libvirt Permissions:** Add your user to the `libvirt` group to allow it to manage virtual machines.

  ```bash
  # Replace <your_username> with your actual username
  sudo usermod -aG libvirt <your_username>
  ```
  After adding, you need to **re-login** for the group permissions to take effect.

  **Shutdown and Reboot Permissions (Optional):**
  If you want to use the "Shutdown Host" and "Reboot Host" buttons on the interface, you need to grant your user passwordless execution rights for `systemctl poweroff` and `systemctl reboot`.
  **Please operate with caution, as this involves system security.**

  1.  Run `sudo visudo` to safely edit the sudoers file.
  2.  Add the following lines at the end of the file, replacing `<your_username>` with your username:

      ```
      <your_username> ALL=(ALL) NOPASSWD: /bin/systemctl poweroff, /bin/systemctl reboot
      ```

### 3. Application Setup

1.  **Files:** Make sure the `vmlauncher.py`, `revival_script.py`, and `vmlauncher.desktop` files are in the same directory.

    2.  **Set Execution Permissions:** `revival_script.py` must be executable.

        ```bash
        chmod +x revival_script.py
        ```

    3.  **Configure Virtual Machine Images (New UI):**
        The new UI will display an image for each virtual machine. The image matching rules are as follows:
        -   At the top of the `vmlauncher.py` script, there is a dictionary named `IMAGE_MAPPINGS`.
        -   The program checks if the virtual machine name (case-insensitive) contains a keyword (key) from the dictionary.
        -   If it does, the program will use the corresponding image file name for that keyword and look for and display the image in the `images/` directory.
        -   **Example**: If your virtual machine is named `Test-Ubuntu-Server`, it will match the keyword `ubuntu`, and the program will try to load the `images/ubuntu.png` file.
        -   If no matching keyword is found, or if the image file does not exist, the program will display the default `images/placeholder.png` image.

        **Steps:**
        a.  Place your image files (e.g., `win10.png`, `ubuntu.png`, etc.) in the `images/` directory.
        b.  (Optional) Edit the `IMAGE_MAPPINGS` dictionary at the top of the `vmlauncher.py` file to add or modify your own keywords and image file names.
### 4. Set Autostart (Recommended Method)

This method utilizes the desktop environment's autostart feature for the best compatibility.

1.  **Create autostart directory:**

    ```bash
    mkdir -p ~/.config/autostart
    ```

2.  **Copy .desktop file:**

    ```bash
    cp vmlauncher.desktop ~/.config/autostart/
    ```

3.  **Reboot:** Reboot your computer. When you log in to the desktop, VM Launcher should automatically start in fullscreen mode.

---

## Customization

- **Display Manager in Revival Script:**
  The `revival_script.py` script attempts to restart the display manager after a passthrough virtual machine is shut down. The default is set to `gdm3`. If you use a different display manager (such as `lightdm` or `sddm`), please edit the `DISPLAY_MANAGER_SERVICE` variable in the `revival_script.py` file.

- **Path in .desktop file:**
  If you move the location of `vmlauncher.py`, be sure to update the path in the `Exec=` line of the `vmlauncher.desktop` file.

## Troubleshooting

If the application does not start or work as expected, try the following:

- **Manual Execution:** Running the main program directly in the terminal can expose most errors.

  ```bash
  python3 vmlauncher.py
  ```

- **Check Libvirt Service:** Make sure the `libvirtd` service is running.

  ```bash
  systemctl status libvirtd
  ```

## Icon Dimensions

- `vmlauncher.png`: This is the application icon. The recommended size is 256x256 pixels.
- `placeholder.png`: This is the placeholder image for VMs. A size of 256x256 pixels is recommended.