# Process manager for hosted bots
import os
import sys
import time
import subprocess
import logging
import asyncio
from typing import Dict
from core.database import (
    get_project, update_project_status, get_all_projects
)
from core.utils import load_config

logger = logging.getLogger(__name__)

class ProcessManager:
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.restart_history: Dict[str, list] = {}

    def get_log_path(self, bot_id: str) -> str:
        config = load_config()
        return os.path.join(config["storage_root"], "logs", f"{bot_id}.log")

    def is_running(self, bot_id: str) -> bool:
        proc = self.processes.get(bot_id)
        if proc and proc.poll() is None:
            return True
        return False

    def start_bot(self, bot_id: str) -> (bool, str):
        project = get_project(bot_id)
        if not project:
            return False, "Project not found in database."

        if self.is_running(bot_id):
            return False, "Bot is already running."

        project_dir = project["project_dir"]
        main_file = project["main_file"]
        exec_path = os.path.join(project_dir, main_file)

        if not os.path.isfile(exec_path):
            return False, f"Entry file '{main_file}' does not exist in project directory."

        log_path = self.get_log_path(bot_id)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        # Truncate log if too large
        config = load_config()
        if os.path.exists(log_path) and os.path.getsize(log_path) > config["max_log_bytes"]:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"--- Log rotated at {time.ctime()} ---\n")

        try:
            log_file = open(log_path, "a", encoding="utf-8", buffering=1)
            log_file.write(f"\n[HOST] === Starting bot at {time.ctime()} ===\n")
            
            # Start process without shell=True to avoid injection
            proc = subprocess.Popen(
                [sys.executable, "-u", main_file],
                cwd=project_dir,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=os.environ.copy()
            )
            self.processes[bot_id] = proc
            update_project_status(
                bot_id=bot_id,
                status="RUNNING",
                pid=proc.pid,
                uptime_start=time.time(),
                exit_code=0,
                last_error=""
            )
            return True, f"Started successfully with PID {proc.pid}."
        except Exception as e:
            err = str(e)
            update_project_status(bot_id=bot_id, status="CRASHED", pid=0, exit_code=-1, last_error=err)
            return False, f"Execution failed: {err}"

    def stop_bot(self, bot_id: str) -> (bool, str):
        proc = self.processes.get(bot_id)
        if not proc or proc.poll() is not None:
            self.processes.pop(bot_id, None)
            update_project_status(bot_id=bot_id, status="STOPPED", pid=0)
            return True, "Bot is already stopped."

        try:
            proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
            
            self.processes.pop(bot_id, None)
            update_project_status(bot_id=bot_id, status="STOPPED", pid=0)
            return True, "Bot stopped successfully."
        except Exception as e:
            return False, f"Failed to stop: {str(e)}"

    def restart_bot(self, bot_id: str) -> (bool, str):
        self.stop_bot(bot_id)
        time.sleep(1)
        return self.start_bot(bot_id)

    async def supervisor_loop(self):
        """
        Runs continuously in the background. Detects unexpected exits and applies
        crash-loop protection.
        """
        config = load_config()
        max_restarts = config["max_restarts"]
        window_sec = config["restart_window_seconds"]

        while True:
            try:
                projects = get_all_projects()
                now = time.time()

                for proj in projects:
                    bot_id = proj["bot_id"]
                    expected_status = proj["status"]

                    if expected_status == "RUNNING":
                        proc = self.processes.get(bot_id)
                        
                        # Process died
                        if not proc or proc.poll() is not None:
                            exit_code = proc.poll() if proc else -1
                            self.processes.pop(bot_id, None)
                            
                            # Check restart loop history
                            history = self.restart_history.setdefault(bot_id, [])
                            history = [t for t in history if now - t < window_sec]
                            history.append(now)
                            self.restart_history[bot_id] = history

                            if len(history) > max_restarts:
                                # Crash loop triggered!
                                msg = f"Crash loop detected! Exited with code {exit_code}. Auto-restart paused."
                                update_project_status(
                                    bot_id=bot_id,
                                    status="CRASHED",
                                    pid=0,
                                    exit_code=exit_code,
                                    last_error=msg
                                )
                                logger.error(f"Bot {bot_id} entered crash loop.")
                            else:
                                # Attempt auto-restart
                                logger.warning(f"Bot {bot_id} crashed (Code: {exit_code}). Auto-restarting...")
                                ok, _ = self.start_bot(bot_id)
                                if not ok:
                                    update_project_status(
                                        bot_id=bot_id,
                                        status="CRASHED",
                                        pid=0,
                                        exit_code=exit_code,
                                        last_error="Auto-restart failed to launch."
                                    )
            except Exception as e:
                logger.error(f"Error in process supervisor: {e}")

            await asyncio.sleep(5)

# Singleton manager
pm = ProcessManager()