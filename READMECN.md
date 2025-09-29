# VM Launcher

这是一个为 `libvirt` 虚拟机设计的简易图形启动器。它被设计为在 Ubuntu 18.04 及以上版本中以 Kiosk 模式运行，提供一个大按钮界面来管理虚拟机。

## 功能

- 以全屏模式启动。
- 自动列出并刷新所有 `libvirt` 虚拟机及其状态。
- 支持对虚拟机的“启动/关闭/重启/强制关闭”操作。
- 智能区分普通虚拟机和 VFIO 显卡直通虚拟机。
- 为普通虚拟机（使用 SPICE/VNC）提供内嵌的图形查看器。
- 为显卡直通虚拟机提供“自毁并恢复”的启动流程。
- 提供关闭物理主机和调节系统音量的功能。

---

## 部署步骤

请严格遵循以下步骤在您的目标机器上部署此应用。

### 1. 系统依赖

首先，安装所有必需的软件包。

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

### 2. 用户权限

运行此应用的用户需要特定的权限。

- **Libvirt 权限:** 将您的用户添加到 `libvirt` 组，以允许其管理虚拟机。

  ```bash
  # 将 <your_username> 替换为您的实际用户名
  sudo usermod -aG libvirt <your_username>
  ```
  添加后，您需要**重新登录**才能使组权限生效。

  **关机和重启权限 (可选):**
  如果您想使用界面上的“关闭主机”和“重启主机”按钮，需要为您的用户授予无密码执行 `systemctl poweroff` 和 `systemctl reboot` 的权限。
  **请谨慎操作，这涉及系统安全。**

  1.  运行 `sudo visudo` 来安全地编辑 sudoers 文件。
  2.  在文件的末尾添加以下行，将 `<your_username>` 替换为您的用户名：

      ```
      <your_username> ALL=(ALL) NOPASSWD: /bin/systemctl poweroff, /bin/systemctl reboot
      ```

### 3. 应用程序设置

1.  **文件:** 确保 `vmlauncher.py`, `revival_script.py`, 和 `vmlauncher.desktop` 这三个文件位于同一目录中。

    2.  **设置执行权限:** `revival_script.py` 必须是可执行的。

        ```bash
        chmod +x revival_script.py
        ```

    3.  **配置虚拟机图片 (新UI):**
        新版UI会为每个虚拟机展示一张图片。图片匹配规则如下:
        -   在 `vmlauncher.py` 脚本的顶部，有一个名为 `IMAGE_MAPPINGS` 的字典。
        -   程序会检查虚拟机的名称（不区分大小写）是否包含字典中的某个关键字（key）。
        -   如果包含，程序将使用该关键字对应的图片文件名，在 `images/` 目录中查找并显示该图片。
        -   **示例**: 如果您的虚拟机名为 `Test-Ubuntu-Server`，它会匹配到关键字 `ubuntu`，程序将尝试加载 `images/ubuntu.png` 文件。
        -   如果没有找到任何匹配的关键字，或者图片文件不存在，程序将显示默认的 `images/placeholder.png` 图片。

        **操作步骤:**
        a.  将您的图片文件 (例如 `win10.png`, `ubuntu.png` 等) 放入 `images/` 目录。
        b.  (可选) 编辑 `vmlauncher.py` 文件顶部的 `IMAGE_MAPPINGS` 字典，添加或修改您自己的关键字和图片文件名。
### 4. 设置自动启动 (推荐方法)

此方法利用桌面环境的自动启动功能，兼容性最好。

1.  **创建 autostart 目录:**

    ```bash
    mkdir -p ~/.config/autostart
    ```

2.  **复制 .desktop 文件:**

    ```bash
    cp vmlauncher.desktop ~/.config/autostart/
    ```

3.  **重启:** 重启您的计算机。当您登录到桌面时，VM Launcher 应该会自动以全屏模式启动。

---

## 自定义配置

- **恢复脚本中的显示管理器:**
  `revival_script.py` 脚本在直通虚拟机关闭后会尝试重启显示管理器。默认设置为 `gdm3`。如果您使用不同的显示管理器（如 `lightdm` 或 `sddm`），请编辑 `revival_script.py` 文件中的 `DISPLAY_MANAGER_SERVICE` 变量。

- **.desktop 文件中的路径:**
  如果您移动了 `vmlauncher.py` 的位置，请务必更新 `vmlauncher.desktop` 文件中 `Exec=` 行的路径。

## 故障排查

如果应用没有按预期启动或工作，请尝试以下操作：

- **手动运行:** 直接在终端中运行主程序，可以暴露大部分错误。

  ```bash
  python3 vmlauncher.py
  ```

- **检查 Libvirt 服务:** 确保 `libvirtd` 服务正在运行。

  ```bash
  systemctl status libvirtd
  ```

## 图标尺寸

- `vmlauncher.png`: 这是应用程序图标。推荐尺寸为 256x256 像素。
- `placeholder.png`: 这是虚拟机的占位符图像。推荐尺寸为 256x256 像素。
