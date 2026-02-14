import os
import threading
import time
import base64
from pathlib import Path
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Button, DataTable, Log, Label, DirectoryTree, ProgressBar
from textual.containers import Horizontal, Vertical
from textual import work
import meshtastic
import meshtastic.serial_interface
from pubsub import pub 

class NoHiddenFilter(DirectoryTree):
    def filter_paths(self, paths: list[Path]) -> list[Path]:
        return [path for path in paths if not path.name.startswith(".")]

class MeshZApp(App):
    TITLE = "Z-Mesh: Meshtastic File Transfer"
    
    # Transfer State Variables
    target_node_id = None  
    selected_file_path = None
    CHUNK_SIZE = 120  # Optimized for real-world reliability
    current_chunk = 0
    total_chunks = 0
    transfer_active = False
    
    # Retry/Watchdog Logic
    last_ack_time = 0
    retry_count = 0
    MAX_RETRIES = 5
    TIMEOUT_SECONDS = 30 # Increased to prevent premature timeouts

    # Receiver State Variables
    receiving_file_name = None
    receiving_total_chunks = 0
    receive_buffer = {} 

    BINDINGS = [("q", "quit", "Quit")]

    CSS = """
    #sidebar { width: 30%; border-right: tall $primary; padding: 1; }
    #main-panel { width: 70%; padding: 1; height: 100%; }
    #file-browser-container { height: 12; border: heavy $accent; display: none; background: $panel; margin-bottom: 1; }
    #file-browser { height: 100%; }
    Log { height: 1fr; border: tall $panel; }
    .status-label { background: $accent; color: white; margin: 1 0; padding: 0 1; }
    #progress-container { margin: 1 0; height: auto; display: none; }
    #actions { dock: bottom; height: 3; background: $surface; padding: 0 1; }
    Button { margin-right: 2; }
    DirectoryTree { background: $surface; color: $text; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="file-browser-container"):
            yield Label("📁 SELECT A FILE (Double-click to pick)")
            yield NoHiddenFilter(str(Path.home()), id="file-browser")
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label(
"╔═╗   ╔╦╗╔═╗╔═╗╦ ╦\n"
"╔═╝───║║║║╣ ╚═╗╠═╣\n"
"╚═╝   ╩ ╩╚═╝╚═╝╩ ╩"
                )
                yield Label("📡 NODES ON MESH")
                yield DataTable(id="node-table")
            with Vertical(id="main-panel"):
                yield Label("🎯 TARGET: None Selected", id="target-label", classes="status-label")
                yield Label("📜 LOG")
                yield Log(id="status-log")
                yield Label("📂 FILE: No file selected", id="file-label", classes="status-label")
                
                with Vertical(id="progress-container"):
                    yield Label("📊 Transfer Progress:", id="progress-text")
                    yield ProgressBar(total=100, show_eta=False, id="transfer-bar")

                with Horizontal(id="actions"):
                    yield Button("Select File", variant="primary", id="btn-select")
                    yield Button("SEND", variant="error", id="btn-send")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#node-table", DataTable)
        table.add_columns("Name", "Node ID", "SNR")
        table.cursor_type = "row"
        self.connect_to_radio()
        self.start_watchdog()

    @work(exclusive=True, thread=True)
    def connect_to_radio(self) -> None:
        try:
            self.log_message("Scanning for radio...")
            self.interface = meshtastic.serial_interface.SerialInterface()
            pub.subscribe(self.on_packet_received, "meshtastic.receive")
            time.sleep(2)
            self.call_from_thread(self.refresh_nodes)
            self.log_message("Radio Connected & Handshake Listener Active.")
        except Exception as e:
            self.log_message(f"Connection Failed: {str(e)}")

    def start_watchdog(self):
        def watch_loop():
            while True:
                time.sleep(1)
                if self.transfer_active and self.current_chunk > 0:
                    if (time.time() - self.last_ack_time) > self.TIMEOUT_SECONDS:
                        self.handle_timeout()
        t = threading.Thread(target=watch_loop, daemon=True)
        t.start()

    def handle_timeout(self):
        if self.retry_count < self.MAX_RETRIES:
            self.retry_count += 1
            self.log_message(f"⚠️ Timeout! Retrying Chunk {self.current_chunk} ({self.retry_count}/{self.MAX_RETRIES})")
            self.send_next_chunk()
        else:
            self.log_message("❌ Transfer Failed: Max retries exceeded.")
            self.transfer_active = False
            self.call_from_thread(self.hide_progress)

    def hide_progress(self):
        self.query_one("#progress-container").display = "none"

    def update_progress(self, current, total, label_text="Transferring..."):
        bar = self.query_one("#transfer-bar", ProgressBar)
        txt = self.query_one("#progress-text", Label)
        container = self.query_one("#progress-container")
        container.display = "block"
        bar.total = total
        bar.progress = current
        txt.update(f"📊 {label_text}: {current}/{total} chunks")

    def on_packet_received(self, packet, interface):
        try:
            if 'decoded' in packet and packet['decoded']['portnum'] == 'TEXT_MESSAGE_APP':
                sender = packet.get('fromId')
                msg = packet['decoded']['payload']
                if isinstance(msg, bytes): msg = msg.decode('utf-8')
                
                if msg.startswith("MESHZ_REQ"):
                    parts = msg.split("|")
                    self.receiving_file_name = parts[1]
                    self.receiving_total_chunks = int(parts[3])
                    self.receive_buffer = {} 
                    self.log_message(f"📩 REQ from {sender}: {self.receiving_file_name}")
                    self.update_progress(0, self.receiving_total_chunks, "Receiving")
                    self.interface.sendText("MESHZ_ACK", destinationId=sender)
                
                elif msg.startswith("ZD|"):
                    parts = msg.split("|")
                    c_num = int(parts[1])
                    c_data = parts[2]
                    self.receive_buffer[c_num] = base64.b64decode(c_data)
                    self.update_progress(len(self.receive_buffer), self.receiving_total_chunks, "Receiving")
                    self.interface.sendText(f"MESHZ_GOCONT|{c_num}", destinationId=sender)
                    if len(self.receive_buffer) == self.receiving_total_chunks:
                        self.save_received_file()
                        self.call_from_thread(self.hide_progress)

                elif msg == "MESHZ_ACK":
                    if self.transfer_active and sender == self.target_node_id:
                        self.current_chunk = 1
                        self.last_ack_time = time.time()
                        self.retry_count = 0
                        self.update_progress(1, self.total_chunks, "Sending")
                        self.send_next_chunk()

                elif msg.startswith("MESHZ_GOCONT|"):
                    if self.transfer_active and sender == self.target_node_id:
                        ack_num = int(msg.split("|")[1])
                        if ack_num == self.current_chunk:
                            self.last_ack_time = time.time()
                            self.retry_count = 0 
                            self.current_chunk += 1
                            if self.current_chunk <= self.total_chunks:
                                self.update_progress(self.current_chunk, self.total_chunks, "Sending")
                                self.send_next_chunk()
                            else:
                                self.transfer_active = False
                                self.log_message("🏁 TRANSFER COMPLETE!")
                                self.call_from_thread(self.hide_progress)
        except Exception as e:
            self.log_message(f"Packet Error: {e}")

    def save_received_file(self) -> None:
        try:
            downloads_path = str(Path.home() / "Downloads")
            save_path = os.path.join(downloads_path, f"meshz_{self.receiving_file_name}")
            with open(save_path, "wb") as f:
                for i in range(1, self.receiving_total_chunks + 1):
                    f.write(self.receive_buffer[i])
            self.log_message(f"💾 FILE SAVED: {save_path}")
        except Exception as e:
            self.log_message(f"❌ Save Error: {e}")

    def handle_send_request(self) -> None:
        if not self.target_node_id or not self.selected_file_path:
            self.log_message("❌ Target or File missing!")
            return
        try:
            filename = os.path.basename(self.selected_file_path)
            filesize = os.path.getsize(self.selected_file_path)
            self.total_chunks = (filesize // self.CHUNK_SIZE) + 1
            self.current_chunk = 0
            self.transfer_active = True
            self.last_ack_time = time.time()
            self.update_progress(0, self.total_chunks, "Initiating")
            self.interface.sendText(f"MESHZ_REQ|{filename}|{filesize}|{self.total_chunks}", destinationId=self.target_node_id)
            self.log_message(f"📡 Sending: {filename}...")
        except Exception as e:
            self.log_message(f"❌ Error: {str(e)}")

    def send_next_chunk(self) -> None:
        try:
            with open(self.selected_file_path, "rb") as f:
                f.seek((self.current_chunk - 1) * self.CHUNK_SIZE)
                raw_data = f.read(self.CHUNK_SIZE)
                encoded_data = base64.b64encode(raw_data).decode('utf-8')
                self.interface.sendText(f"ZD|{self.current_chunk}|{encoded_data}", destinationId=self.target_node_id)
        except Exception as e:
            self.log_message(f"❌ Chunk Error: {e}")
            self.transfer_active = False

    def log_message(self, message: str) -> None:
        try:
            log_widget = self.query_one("#status-log")
            if self._thread_id == threading.get_ident():
                log_widget.write_line(message)
            else:
                self.call_from_thread(log_widget.write_line, message)
        except: pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-select":
            self.query_one("#file-browser-container").display = not self.query_one("#file-browser-container").display
        elif event.button.id == "btn-send":
            self.handle_send_request()

    def refresh_nodes(self) -> None:
        if not hasattr(self, 'interface') or not self.interface.nodes: return
        table = self.query_one("#node-table", DataTable)
        table.clear(columns=False) 
        for node_id, node in self.interface.nodes.items():
            user = node.get('user', {})
            table.add_row(user.get('longName', node_id), node_id, str(node.get('snr', 'N/A')))

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self.selected_file_path = event.path
        self.query_one("#file-label").update(f"📂 FILE: {os.path.basename(event.path)}")
        self.query_one("#file-browser-container").display = False

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_data = event.data_table.get_row(event.row_key)
        self.target_node_id = str(row_data[1])
        self.query_one("#target-label").update(f"🎯 TARGET: {row_data[0]} ({self.target_node_id})")

if __name__ == "__main__":
    MeshZApp().run()