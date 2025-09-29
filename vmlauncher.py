import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkVnc', '2.0')
gi.require_version('SpiceClientGLib', '2.0')
gi.require_version('SpiceClientGtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GtkVnc, SpiceClientGLib, SpiceClientGtk, Pango

import libvirt
import os
import sys
import subprocess
import xml.etree.ElementTree as ET
import time
import configparser
import gettext
import locale

# i18n
APP_NAME = "vmlauncher"
if os.path.exists('/usr/share/locale'):
    LOCALE_DIR = '/usr/share/locale'
else:
    LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'locale')

locale.setlocale(locale.LC_ALL, '')
try:
    trans = gettext.translation(APP_NAME, localedir=LOCALE_DIR, fallback=True)
except FileNotFoundError:
    trans = gettext.NullTranslations()
_ = trans.gettext



# --- Configuration ---
REFRESH_INTERVAL_SECONDS = 3
CONFIG_DIR = os.path.expanduser('~/.config/vmlauncher')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'settings.ini')
IMAGE_DIR = '/usr/share/vmlauncher/images' if os.path.exists('/usr/share/vmlauncher/images') else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images')

IMAGE_MAPPINGS = {
    'win7': 'win7.png', 'win10': 'win10.png', 'win11': 'win11.png',
    'ubuntu': 'ubuntu.png', 'centos': 'centos.png', 'fedora': 'fedora.png',
    'linux': 'linux.png',
}
PLACEHOLDER_IMAGE = 'placeholder.png'
# --- End Configuration ---


class VMViewerWindow(Gtk.Window):
    def __init__(self, vm_name, graphics):
        super().__init__(title=_("Viewer for {}").format(vm_name))
        self.set_default_size(1024, 768)
        self.vm_name = vm_name
        self.is_fullscreen = True
        self.fullscreen()
        self.connect("key-press-event", self._on_key_press)

        self.display_widget = None
        self.graphics_type = graphics.get('type')
        
        if self.graphics_type == 'spice':
            session = SpiceClientGLib.Session()
            session.set_property('host', graphics.get('listen', '127.0.0.1'))
            port = graphics.get('port')
            if port: session.set_property('port', port)
            tls_port = graphics.get('tlsPort')
            if tls_port: session.set_property('tls-port', tls_port)
            self.display_widget = SpiceClientGtk.Display(session=session)
            session.connect()
        elif self.graphics_type == 'vnc':
            self.display_widget = GtkVnc.Display()
            self.display_widget.open_host(graphics.get('listen', '127.0.0.1'), graphics.get('port'))
        
        if self.display_widget:
            self.add(self.display_widget)
            self.display_widget.show()
        else:
            label = Gtk.Label(label=_("Unsupported graphics type: {}").format(self.graphics_type))
            self.add(label)
            label.show()

    def _on_key_press(self, widget, event):
        ctrl_pressed = (event.state & Gdk.ModifierType.CONTROL_MASK) != 0
        alt_pressed = (event.state & Gdk.ModifierType.MOD1_MASK) != 0
        if ctrl_pressed and alt_pressed and event.keyval == Gdk.KEY_Return:
            self._toggle_fullscreen()

    def _toggle_fullscreen(self):
        if self.is_fullscreen:
            self.unfullscreen()
        else:
            self.fullscreen()
        self.is_fullscreen = not self.is_fullscreen


class VMLauncher(Gtk.Window):
    def __init__(self):
        super().__init__(title=_("VM Launcher"))
        self.connect("destroy", Gtk.main_quit)
        self.fullscreen()
        
        # State Management
        self.vm_domains = []
        self.current_vm_index = -1
        self.open_viewers = {}
        self.last_vm_name_to_restore = None
        self.settings = configparser.ConfigParser()
        self.vms_in_view_mode = set()
        self.embedded_display_widget = None
        self.active_embedded_vm_name = None
        self.restore_embedded_view_after_fullscreen = None
        self.is_first_load = True

        try:
            self.conn = libvirt.open('qemu:///system')
        except libvirt.libvirtError as e:
            print(f"Failed to open connection: {e}", file=sys.stderr)
            sys.exit(1)

        self._build_ui()
        self.apply_css()
        self._load_settings()
        self._refresh_vm_list()
        GLib.timeout_add_seconds(REFRESH_INTERVAL_SECONDS, self._refresh_vm_list)

    def _build_ui(self):
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        main_vbox.set_border_width(20)
        self.add(main_vbox)

        self.vm_name_label = Gtk.Label(label=_("No VMs Found"))
        self.vm_name_label.set_use_markup(True)
        self.vm_name_label.get_style_context().add_class("header")
        main_vbox.pack_start(self.vm_name_label, False, False, 0)
        
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        main_vbox.pack_start(nav_box, False, False, 10)

        search_label = Gtk.Label(label=_("Quick search for VMs:"))
        search_label.get_style_context().add_class("nav-label")
        nav_box.pack_start(search_label, False, False, 0)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Enter keyword..."))
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_entry.connect("key-press-event", self._on_search_key_press)
        nav_box.pack_start(self.search_entry, True, True, 0)

        combo_label = Gtk.Label(label=_("All VMs:"))
        combo_label.get_style_context().add_class("nav-label")
        nav_box.pack_start(combo_label, False, False, 10)

        self.vm_combo_box = Gtk.ComboBoxText()
        self.combo_box_handler_id = self.vm_combo_box.connect("changed", self._on_combo_box_changed)
        nav_box.pack_start(self.vm_combo_box, True, True, 0)

        self.vm_counter_label = Gtk.Label(label="")
        self.vm_counter_label.get_style_context().add_class("counter")
        nav_box.pack_start(self.vm_counter_label, False, False, 0)

        # Search results popup
        self.search_results_window = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.search_results_listbox = Gtk.ListBox()
        self.search_results_listbox.connect("row-activated", self._on_search_result_selected)
        scrolled_win = Gtk.ScrolledWindow()
        scrolled_win.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_win.add(self.search_results_listbox)
        self.search_results_window.add(scrolled_win)
        self.search_results_window.set_size_request(400, 200)

        carousel_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        carousel_box.set_valign(Gtk.Align.FILL)
        main_vbox.pack_start(carousel_box, True, True, 0)

        self.prev_button = Gtk.Button.new_from_icon_name("go-previous-symbolic", Gtk.IconSize.DIALOG)
        self.prev_button.set_valign(Gtk.Align.CENTER)
        self.prev_button.connect("clicked", self._on_prev_vm_clicked)
        carousel_box.pack_start(self.prev_button, False, False, 20)

        self.main_stack = Gtk.Stack()
        self.main_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        carousel_box.pack_start(self.main_stack, True, True, 0)

        event_box = Gtk.EventBox()
        self.vm_image = Gtk.Image()
        event_box.add(self.vm_image)
        event_box.connect("button-press-event", self._on_image_clicked)
        event_box.connect("realize", self._on_event_box_realize)
        self.main_stack.add_named(event_box, "image")

        self.viewer_container = Gtk.Box()
        self.main_stack.add_named(self.viewer_container, "viewer")

        self.next_button = Gtk.Button.new_from_icon_name("go-next-symbolic", Gtk.IconSize.DIALOG)
        self.next_button.set_valign(Gtk.Align.CENTER)
        self.next_button.connect("clicked", self._on_next_vm_clicked)
        carousel_box.pack_end(self.next_button, False, False, 20)

        control_panel_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        main_vbox.pack_end(control_panel_vbox, False, False, 10)

        self.vm_control_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.vm_control_box.set_halign(Gtk.Align.CENTER)
        control_panel_vbox.pack_start(self.vm_control_box, False, False, 0)

        self.start_button = Gtk.Button.new_with_label(_("Start"))
        self.shutdown_button = Gtk.Button.new_with_label(_("Shutdown"))
        self.reboot_button = Gtk.Button.new_with_label(_("Reboot"))
        self.destroy_button = Gtk.Button.new_with_label(_("Destroy"))
        self.view_button = Gtk.Button.new_with_label(_("Fullscreen View"))
        self.close_view_button = Gtk.Button.new_with_label(_("Close View"))

        self.start_button.connect("clicked", self._on_vm_action, "start")
        self.shutdown_button.connect("clicked", self._on_vm_action, "shutdown")
        self.reboot_button.connect("clicked", self._on_vm_action, "reboot")
        self.destroy_button.connect("clicked", self._on_vm_action, "destroy")
        self.view_button.connect("clicked", self._on_vm_view)
        self.close_view_button.connect("clicked", self._on_close_view_clicked)
        self.destroy_button.get_style_context().add_class("destructive-action")

        for btn in [self.start_button, self.shutdown_button, self.reboot_button, self.destroy_button, self.view_button, self.close_view_button]:
            self.vm_control_box.pack_start(btn, True, True, 0)

        host_system_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        control_panel_vbox.pack_start(host_system_box, False, False, 0)

        volume_label = Gtk.Label(label=_("Volume Control:"))
        host_system_box.pack_start(volume_label, False, False, 0)
        self.volume_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.volume_scale.set_size_request(300, -1)
        self.volume_scale.set_hexpand(False)
        self.volume_scale.connect("value-changed", self.on_volume_changed)
        host_system_box.pack_start(self.volume_scale, False, False, 0)
        self.update_volume_slider()

        spacer = Gtk.Box(hexpand=True)
        host_system_box.pack_start(spacer, True, True, 0)

        self.silent_mode_checkbox = Gtk.CheckButton(label=_("Silent host shutdown/reboot"))
        self.silent_mode_checkbox.connect("toggled", self.on_silent_toggle)
        host_system_box.pack_start(self.silent_mode_checkbox, False, False, 0)

        reboot_button = Gtk.Button.new_from_icon_name("system-reboot-symbolic", Gtk.IconSize.BUTTON)
        reboot_button.set_tooltip_text(_("Reboot Host"))
        reboot_button.connect("clicked", self.on_host_reboot)
        host_system_box.pack_start(reboot_button, False, False, 0)

        shutdown_button = Gtk.Button.new_from_icon_name("system-shutdown-symbolic", Gtk.IconSize.BUTTON)
        shutdown_button.set_tooltip_text(_("Shutdown Host"))
        shutdown_button.get_style_context().add_class("destructive-action")
        shutdown_button.connect("clicked", self.on_host_shutdown)
        host_system_box.pack_start(shutdown_button, False, False, 0)

    def _on_search_key_press(self, widget, event):
        keyval = event.keyval
        popup_visible = self.search_results_window.get_visible()

        if keyval == Gdk.KEY_Escape:
            self.search_results_window.hide()
            return True

        # If the popup isn't visible, only the Down key should do something (which is to open it)
        if not popup_visible and keyval != Gdk.KEY_Down:
            return False

        if keyval == Gdk.KEY_Down or keyval == Gdk.KEY_Up:
            rows = self.search_results_listbox.get_children()
            if not rows: return True

            selected_row = self.search_results_listbox.get_selected_row()
            current_index = -1
            if selected_row:
                current_index = selected_row.get_index()

            if keyval == Gdk.KEY_Down:
                next_index = min(current_index + 1, len(rows) - 1)
            else: # Up
                # If nothing is selected, pressing Up should select the last item
                if current_index <= 0:
                    next_index = len(rows) - 1
                else:
                    next_index = current_index - 1
            
            if next_index != current_index:
                next_row = self.search_results_listbox.get_row_at_index(next_index)
                self.search_results_listbox.select_row(next_row)
            
            return True # Stop the event from propagating to the text entry

        elif keyval == Gdk.KEY_Return or keyval == Gdk.KEY_KP_Enter:
            selected_row = self.search_results_listbox.get_selected_row()
            if selected_row:
                self._on_search_result_selected(self.search_results_listbox, selected_row)
            return True # Stop the event

        return False # Allow other keys (like text input) to be processed normally

    def _on_search_changed(self, search_entry):
        search_text = search_entry.get_text().lower()
        if not search_text:
            self.search_results_window.hide()
            return

        matching_domains = [d for d in self.vm_domains if search_text in d.name().lower()]

        for child in self.search_results_listbox.get_children():
            child.destroy()
        
        if not matching_domains:
            self.search_results_window.hide()
            return

        for domain in matching_domains:
            row = Gtk.ListBoxRow()
            row.add(Gtk.Label(label=domain.name(), xalign=0))
            self.search_results_listbox.add(row)

        x, y = self.search_entry.get_allocation().x, self.search_entry.get_allocation().y
        w, h = self.search_entry.get_allocated_width(), self.search_entry.get_allocated_height()
        win_x, win_y = self.get_position()
        self.search_results_window.move(win_x + x, win_y + y + h)
        self.search_results_window.show_all()

    def _on_search_result_selected(self, listbox, row):
        if not row: return
        selected_name = row.get_child().get_text()
        for i, domain in enumerate(self.vm_domains):
            if domain.name() == selected_name:
                self.current_vm_index = i
                self._update_display()
                break
        self.search_results_window.hide()
        self.search_entry.set_text("")

    def _on_combo_box_changed(self, combo):
        if self.is_programmatic_combo_change: return
        new_index = combo.get_active()
        if new_index != -1 and new_index != self.current_vm_index:
            self.current_vm_index = new_index
            self._update_display()

    def _refresh_vm_list(self):
        for vm_name in list(self.open_viewers.keys()):
            try:
                domain = self.conn.lookupByName(vm_name)
                if not domain.isActive(): GLib.idle_add(self.open_viewers[vm_name].close)
            except libvirt.libvirtError:
                GLib.idle_add(self.open_viewers[vm_name].close)
        for vm_name in list(self.vms_in_view_mode):
            try:
                domain = self.conn.lookupByName(vm_name)
                if not domain.isActive(): self.vms_in_view_mode.discard(vm_name)
            except libvirt.libvirtError:
                self.vms_in_view_mode.discard(vm_name)
        try:
            self.vm_domains = self.conn.listAllDomains(0)
            self.is_programmatic_combo_change = True
            self.vm_combo_box.remove_all()
            for domain in self.vm_domains:
                self.vm_combo_box.append_text(domain.name())
            self.is_programmatic_combo_change = False
            if self.last_vm_name_to_restore and self.vm_domains:
                names = [d.name() for d in self.vm_domains]
                if self.last_vm_name_to_restore in names: self.current_vm_index = names.index(self.last_vm_name_to_restore)
                self.last_vm_name_to_restore = None
            if not self.vm_domains: self.current_vm_index = -1
            elif self.current_vm_index == -1: self.current_vm_index = 0
            if self.current_vm_index >= len(self.vm_domains): self.current_vm_index = len(self.vm_domains) - 1 if self.vm_domains else -1
            if self.is_first_load and self.vm_domains:
                self.is_first_load = False
                for domain in self.vm_domains:
                    vm_type, _ = self.get_vm_type(domain.XMLDesc(0))
                    if domain.isActive() and vm_type == 'virtual': self.vms_in_view_mode.add(domain.name())
        except libvirt.libvirtError as e:
            print(f"Error refreshing VM list: {e}", file=sys.stderr); self.vm_domains = []; self.current_vm_index = -1
        self._update_display(); return True

    def _update_display(self):
        has_vms = bool(self.vm_domains)
        for w in [self.prev_button, self.next_button, self.vm_control_box, self.search_entry, self.vm_combo_box]: w.set_sensitive(has_vms)
        if not has_vms:
            self.vm_name_label.set_text(_("No VMs Found")); self.vm_counter_label.set_text(""); self.vm_image.set_from_file(os.path.join(IMAGE_DIR, PLACEHOLDER_IMAGE)); return
        
        domain = self.vm_domains[self.current_vm_index]; vm_name = domain.name(); is_active = domain.isActive()
        xml_desc = domain.XMLDesc(0); vm_type, graphics = self.get_vm_type(xml_desc); is_passthrough = (vm_type == 'passthrough')
        
        escaped_name = GLib.markup_escape_text(vm_name)
        if is_passthrough: self.vm_name_label.set_markup(f"<span foreground='#FFA500' weight='bold'>{_('[GPU Passthrough]')} </span>{escaped_name}")
        else: self.vm_name_label.set_markup(escaped_name)
        total_vms = len(self.vm_domains); self.vm_counter_label.set_text(f"({self.current_vm_index + 1} / {total_vms})")
        
        self.is_programmatic_combo_change = True
        self.vm_combo_box.set_active(self.current_vm_index)
        self.is_programmatic_combo_change = False

        should_show_embedded = vm_name in self.vms_in_view_mode and is_active and not is_passthrough
        if should_show_embedded:
            if self.main_stack.get_visible_child_name() == "image" or self.active_embedded_vm_name != vm_name: self._create_embedded_viewer(domain, graphics); self.active_embedded_vm_name = vm_name
            self.main_stack.set_visible_child_name("viewer")
        else:
            self.main_stack.set_visible_child_name("image"); self.vm_image.set_from_file(self._get_image_for_vm(vm_name))
        
        self.close_view_button.set_visible(should_show_embedded); self.start_button.set_visible(not should_show_embedded)
        self.shutdown_button.set_visible(not is_passthrough); self.reboot_button.set_visible(not is_passthrough); self.destroy_button.set_visible(not is_passthrough); self.view_button.set_visible(not is_passthrough)
        if is_passthrough: self.start_button.set_label(_("Start (Passthrough)"))
        else: self.start_button.set_label(_("Start"))
        self.start_button.set_sensitive(not is_active); self.shutdown_button.set_sensitive(is_active); self.reboot_button.set_sensitive(is_active); self.destroy_button.set_sensitive(is_active)
        self.view_button.set_sensitive(is_active and not is_passthrough and graphics is not None)

    def _on_vm_view(self, widget):
        if self.current_vm_index == -1: return
        domain = self.vm_domains[self.current_vm_index]; vm_name = domain.name()
        if vm_name in self.vms_in_view_mode: self.restore_embedded_view_after_fullscreen = vm_name; self._on_close_view_clicked(None)
        if vm_name in self.open_viewers: self.open_viewers[vm_name].present(); return
        if not domain.isActive(): self.show_error_dialog(_("VM {} is not running.").format(vm_name)); return
        xml_desc = domain.XMLDesc(0); vm_type, graphics = self.get_vm_type(xml_desc)
        if vm_type == 'virtual' and graphics: viewer = VMViewerWindow(vm_name, graphics); self.open_viewers[vm_name] = viewer; viewer.connect("destroy", self._on_viewer_destroyed, vm_name); viewer.show_all()
        else: self.show_error_dialog(_("VM {} has no graphical display to view.").format(vm_name))

    def _on_viewer_destroyed(self, widget, vm_name):
        if vm_name in self.open_viewers: del self.open_viewers[vm_name]
        if vm_name == self.restore_embedded_view_after_fullscreen: self.restore_embedded_view_after_fullscreen = None; self.vms_in_view_mode.add(vm_name); self._update_display()

    def _on_close_view_clicked(self, widget):
        if self.current_vm_index == -1: return
        vm_name = self.vm_domains[self.current_vm_index].name()
        self.vms_in_view_mode.discard(vm_name)
        if self.active_embedded_vm_name == vm_name: self._destroy_embedded_viewer()
        self._update_display()

    def _destroy_embedded_viewer(self):
        if self.embedded_display_widget: self.embedded_display_widget.destroy()
        self.embedded_display_widget = None; self.active_embedded_vm_name = None

    def _create_embedded_viewer(self, domain, graphics):
        if self.embedded_display_widget: self.embedded_display_widget.destroy()
        if graphics.get('type') == 'spice':
            session = SpiceClientGLib.Session(); session.set_property('host', graphics.get('listen', '127.0.0.1'))
            port = graphics.get('port');
            if port: session.set_property('port', port)
            tls_port = graphics.get('tlsPort');
            if tls_port: session.set_property('tls-port', tls_port)
            self.embedded_display_widget = SpiceClientGtk.Display(session=session); session.connect()
        elif graphics.get('type') == 'vnc':
            self.embedded_display_widget = GtkVnc.Display(); self.embedded_display_widget.open_host(graphics.get('listen', '127.0.0.1'), graphics.get('port'))
        if self.embedded_display_widget:
            for child in self.viewer_container.get_children(): child.destroy()
            self.viewer_container.pack_start(self.embedded_display_widget, True, True, 0); self.embedded_display_widget.show()

    def _on_image_clicked(self, widget, event):
        if self.current_vm_index == -1: return
        domain = self.vm_domains[self.current_vm_index]
        vm_name = domain.name(); xml_desc = domain.XMLDesc(0); vm_type, _ = self.get_vm_type(xml_desc)
        if vm_type == 'passthrough': self._on_vm_action(widget, "start"); return
        if domain.isActive(): self.vms_in_view_mode.add(vm_name)
        else: self.vms_in_view_mode.add(vm_name); self._on_vm_action(widget, "start")
        self._update_display()

    def _get_image_for_vm(self, vm_name):
        vm_name_lower = vm_name.lower()
        for keyword, filename in IMAGE_MAPPINGS.items():
            if keyword in vm_name_lower:
                path = os.path.join(IMAGE_DIR, filename)
                if os.path.exists(path): return path
        return os.path.join(IMAGE_DIR, PLACEHOLDER_IMAGE)

    def _on_next_vm_clicked(self, widget):
        if not self.vm_domains: return
        self.current_vm_index = (self.current_vm_index + 1) % len(self.vm_domains); self._update_display()

    def _on_prev_vm_clicked(self, widget):
        if not self.vm_domains: return
        self.current_vm_index = (self.current_vm_index - 1 + len(self.vm_domains)) % len(self.vm_domains); self._update_display()

    def _on_event_box_realize(self, widget):
        cursor = Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.HAND2); widget.get_window().set_cursor(cursor)

    def _on_vm_action(self, widget, action):
        if self.current_vm_index == -1: return
        domain = self.vm_domains[self.current_vm_index]; xml_desc = domain.XMLDesc(0); vm_type, _ = self.get_vm_type(xml_desc)
        if action == "start" and vm_type == "passthrough": self._start_passthrough_vm(domain); return
        try:
            if action == "start": domain.create()
            elif action == "shutdown": domain.shutdown()
            elif action == "reboot": domain.reboot()
            elif action == "destroy": domain.destroy()
        except libvirt.libvirtError as e: self.show_error_dialog(_("Error on action '{}' for {}: {}").format(action, domain.name(), e))
        GLib.timeout_add(500, self._refresh_vm_list)

    def _start_passthrough_vm(self, domain):
        self._save_settings()
        try:
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'revival_script.py')
            subprocess.Popen([sys.executable, script_path, domain.name()], preexec_fn=os.setpgrp); time.sleep(1); domain.create()
        except (libvirt.libvirtError, FileNotFoundError) as e: self.show_error_dialog(_("Error starting passthrough VM {}: {}").format(domain.name(), e))

    def get_vm_type(self, xml_desc):
        root = ET.fromstring(xml_desc); devices = root.find('devices')
        for hostdev in devices.findall('hostdev'):
            if hostdev.get('type') == 'pci':
                source = hostdev.find('source')
                if source is not None and source.find('address') is not None: return 'passthrough', None
        graphics = devices.find('graphics');
        if graphics is not None: return 'virtual', graphics.attrib
        return 'headless', None

    def apply_css(self):
        css_provider = Gtk.CssProvider(); css = b".nav-label { font-weight: bold; font-size: 16px; } .header { font-size: 32px; font-weight: bold; } .counter { font-size: 18px; font-style: italic; color: #888; } .destructive-action { background-color: #dc3545; color: white; }"; css_provider.load_from_data(css); Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _save_settings(self):
        try:
            if 'VMLauncher' not in self.settings: self.settings['VMLauncher'] = {}
            self.settings['VMLauncher']['silent_mode'] = str(self.silent_mode_checkbox.get_active())
            if self.current_vm_index != -1 and len(self.vm_domains) > self.current_vm_index: self.settings['VMLauncher']['last_vm_name'] = self.vm_domains[self.current_vm_index].name()
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(CONFIG_FILE, 'w') as configfile: self.settings.write(configfile)
        except Exception as e: print(f"Error saving settings: {e}", file=sys.stderr)

    def _load_settings(self):
        try:
            if not os.path.exists(CONFIG_FILE): return
            self.settings.read(CONFIG_FILE)
            if 'VMLauncher' in self.settings:
                s = self.settings['VMLauncher']; self.silent_mode_checkbox.set_active(s.getboolean('silent_mode', False)); self.last_vm_name_to_restore = s.get('last_vm_name', None)
        except Exception as e: print(f"Error loading settings: {e}", file=sys.stderr)

    def on_silent_toggle(self, widget): self._save_settings()

    def on_volume_changed(self, scale):
        value = int(scale.get_value())
        try:
            # First, get the name of the default sink for robustness
            my_env = os.environ.copy()
            my_env["LANG"] = "C"
            result = subprocess.run(["pactl", "info"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, env=my_env)
            if result.returncode == 0:
                default_sink_name = ""
                for line in result.stdout.splitlines():
                    if line.startswith("Default Sink: "):
                        default_sink_name = line.split("Default Sink: ")[1]
                        break
                if default_sink_name:
                    # Now, set the volume for that specific sink
                    subprocess.run(["pactl", "set-sink-volume", default_sink_name, f"{value}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            print("pactl command not found. Please ensure pulseaudio-utils is installed.", file=sys.stderr)
        except Exception as e:
            print(f"Error changing volume with pactl: {e}", file=sys.stderr)

    def update_volume_slider(self):
        try:
            # Get the default sink name
            my_env = os.environ.copy()
            my_env["LANG"] = "C"
            result = subprocess.run(["pactl", "info"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, env=my_env)
            if result.returncode != 0:
                self.volume_scale.set_sensitive(False)
                return

            default_sink_name = ""
            for line in result.stdout.splitlines():
                if line.startswith("Default Sink: "):
                    default_sink_name = line.split("Default Sink: ")[1]
                    break

            if not default_sink_name:
                self.volume_scale.set_sensitive(False)
                return

            # Get the volume for the default sink
            result = subprocess.run(["pactl", "list", "sinks"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, env=my_env)
            if result.returncode != 0:
                self.volume_scale.set_sensitive(False)
                return

            output = result.stdout
            sinks = output.split('Sink #')
            for sink in sinks:
                if default_sink_name in sink:
                    for line in sink.split('\n'):
                        if 'Volume:' in line and '%' in line:
                            percent_str = line.split('%')[0].split('/')[-1].strip()
                            if percent_str.isdigit():
                                self.volume_scale.set_value(int(percent_str))
                                return # Found it, exit
            # If we reach here, we didn't find the volume for the default sink
            self.volume_scale.set_sensitive(False)

        except Exception as e:
            print(f"Could not get initial volume with pactl: {e}", file=sys.stderr)
            self.volume_scale.set_sensitive(False)

    def on_host_shutdown(self, widget):
        if self.silent_mode_checkbox.get_active(): os.system("systemctl poweroff"); return
        dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK_CANCEL, text=_("Confirm Host Shutdown")); dialog.format_secondary_text(_("Are you sure you want to shut down the physical machine?"));
        if dialog.run() == Gtk.ResponseType.OK: os.system("systemctl poweroff")
        dialog.destroy()

    def on_host_reboot(self, widget):
        if self.silent_mode_checkbox.get_active(): os.system("systemctl reboot"); return
        dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK_CANCEL, text=_("Confirm Host Reboot")); dialog.format_secondary_text(_("Are you sure you want to reboot the physical machine?"));
        if dialog.run() == Gtk.ResponseType.OK: os.system("systemctl reboot")
        dialog.destroy()

    def show_error_dialog(self, message):
        dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.CANCEL, text=_("An Error Occurred")); dialog.format_secondary_text(message); dialog.run(); dialog.destroy()

if __name__ == "__main__":
    if os.geteuid() != 0 and 'libvirt' not in os.popen('groups').read():
         print(_("Error: This program must be run as root or by a user in the 'libvirt' group."), file=sys.stderr); sys.exit(1)
    win = VMLauncher()
    win.show_all()
    Gtk.main()