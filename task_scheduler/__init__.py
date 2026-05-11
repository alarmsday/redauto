"""Multi-device task scheduler module"""

import asyncio
import multiprocessing as mp
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass
import threading
import time
from datetime import datetime

from data.shared_state import (
    get_pending_tasks, assign_task_to_device, complete_task,
    get_online_devices, update_device_status, get_device_status
)
from device_manager import get_device_manager, DeviceInfo
from account_manager import get_account_pool


@dataclass
class SchedulerConfig:
    max_devices: int = 10
    heartbeat_interval: int = 5  # seconds
    offline_threshold: int = 30  # seconds
    check_interval: int = 1  # seconds


class TaskScheduler:
    """Multi-device task scheduler with round-robin allocation"""

    def __init__(self, config: SchedulerConfig = None):
        self.config = config or SchedulerConfig()
        self._running = False
        self._devices: Dict[str, mp.Process] = {}
        self._lock = threading.Lock()
        self._callbacks: List[Callable] = []

    def register_callback(self, callback: Callable):
        """Register callback for task events"""
        self._callbacks.append(callback)

    async def start(self):
        """Start the scheduler"""
        self._running = True
        await self._schedule_loop()

    async def stop(self):
        """Stop the scheduler"""
        self._running = False
        # Stop all device processes
        with self._lock:
            for device_id, process in self._devices.items():
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
            self._devices.clear()

    async def _schedule_loop(self):
        """Main scheduling loop"""
        while self._running:
            try:
                # 1. Scan devices
                device_manager = get_device_manager()
                devices = device_manager.scan_devices()
                online_devices = [d for d in devices if d.status.value == "online"]

                # 2. Update device status in DB
                for device in online_devices:
                    update_device_status(
                        device_id=device.device_id,
                        status="online",
                        device_name=device.device_name,
                        connection_type=device.connection_type.value
                    )

                # 3. Check for dead processes and cleanup
                await self._cleanup_dead_processes()

                # 4. Get pending tasks
                pending_tasks = get_pending_tasks(limit=self.config.max_devices)

                # 5. Assign tasks to available devices
                await self._assign_tasks(online_devices, pending_tasks)

                # 6. Check for offline devices and reassign tasks
                await self._reassign_tasks_from_offline_devices()

                # 7. Notify callbacks
                for callback in self._callbacks:
                    try:
                        callback(online_devices, pending_tasks)
                    except Exception as e:
                        print(f"Callback error: {e}")

            except Exception as e:
                print(f"Scheduler loop error: {e}")

            await asyncio.sleep(self.config.check_interval)

    async def _cleanup_dead_processes(self):
        """Clean up dead device processes"""
        with self._lock:
            dead_devices = [
                device_id for device_id, process in self._devices.items()
                if not process.is_alive()
            ]
            for device_id in dead_devices:
                del self._devices[device_id]
                update_device_status(device_id, "offline")

    async def _assign_tasks(self, devices: List[DeviceInfo], tasks: List[Dict]):
        """Assign tasks to available devices using round-robin"""
        if not tasks or not devices:
            return

        # Simple round-robin: assign one task per device
        # 应用黑白名单过滤
        from device_manager import get_device_manager
        device_manager = get_device_manager()
        available_devices = [
            d for d in devices
            if (d.device_id not in self._devices or not self._devices[d.device_id].is_alive())
            and device_manager.is_device_allowed(d.device_id)
        ]

        for i, task in enumerate(tasks):
            if i >= len(available_devices):
                break

            device = available_devices[i]
            device_id = device.device_id

            # Try to assign task (atomic operation)
            if assign_task_to_device(task['id'], device_id):
                # Start device process
                await self._start_device_process(device_id, task)

    async def _start_device_process(self, device_id: str, task: Dict):
        """Start a process for a device"""
        with self._lock:
            if device_id in self._devices and self._devices[device_id].is_alive():
                return

            # Create process
            process = mp.Process(
                target=_device_worker,
                args=(device_id, task)
            )
            process.start()
            self._devices[device_id] = process

            update_device_status(device_id, "running", task['id'])

    async def _reassign_tasks_from_offline_devices(self):
        """Reassign tasks from devices that went offline"""
        db = get_pending_tasks(limit=100)

        for task in db:
            if task['status'] == 'running' and task.get('device_id'):
                device_status = get_device_status(task['device_id'])
                if device_status:
                    # Check if device is truly offline
                    last_heartbeat = device_status.get('last_heartbeat')
                    if last_heartbeat:
                        if isinstance(last_heartbeat, str):
                            last_heartbeat = datetime.fromisoformat(last_heartbeat)
                        elapsed = (datetime.now() - last_heartbeat).total_seconds()
                        if elapsed > self.config.offline_threshold:
                            # Device is offline, reassign task
                            complete_task(task['id'], 'failed')
                            # Re-create task
                            from data.shared_state import create_task
                            create_task(task['target_user_id'], task['target_nickname'])

    def get_status(self) -> Dict:
        """Get scheduler status"""
        with self._lock:
            return {
                "running": self._running,
                "active_processes": len([p for p in self._devices.values() if p.is_alive()]),
                "total_devices": len(self._devices)
            }


def _device_worker(device_id: str, task: Dict):
    """Worker process for a device"""
    # Import here to avoid circular imports in child process
    import sys
    sys.path.insert(0, '.')

    from workflow import XiaohongshuWorkflow
    from device_manager import get_device_manager

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Initialize workflow
        workflow = XiaohongshuWorkflow(device_id)

        # Update status
        update_device_status(device_id, "running", task['id'])

        # Run workflow (this will block until done or error)
        loop.run_until_complete(workflow.start())

    except Exception as e:
        print(f"Device {device_id} worker error: {e}")
    finally:
        loop.close()
        complete_task(task['id'], 'completed' if 'success' in task else 'failed')


# Global scheduler instance
_scheduler: TaskScheduler = None


def get_scheduler() -> TaskScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler()
    return _scheduler
