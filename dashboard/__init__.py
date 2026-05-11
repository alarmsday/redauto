"""Monitoring dashboard module - Flask backend"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

from data.shared_state import (
    get_db, get_online_devices, get_pending_tasks,
    get_device_status, update_device_status
)
from ai_agent import get_pending_alerts, resolve_alert
from data.websocket_server import get_status_server


app = Flask(__name__, template_folder='templates')
CORS(app)


def get_task_statistics() -> Dict[str, Any]:
    """Get task statistics"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) as running,
                SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed
            FROM task_queue
        """)
        row = cursor.fetchone()
        return dict(row) if row else {}


def get_device_statistics() -> Dict[str, Any]:
    """Get device statistics"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as total FROM device_status")
        total = cursor.fetchone()[0]

    online = get_online_devices()
    return {
        "total": total,
        "online": len(online),
        "offline": total - len(online)
    }


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')


@app.route('/api/stats')
def stats():
    """Get overall statistics"""
    task_stats = get_task_statistics()
    device_stats = get_device_statistics()
    pending_alerts = get_pending_alerts()

    return jsonify({
        "tasks": task_stats,
        "devices": device_stats,
        "pending_alerts": len(pending_alerts),
        "timestamp": datetime.now().isoformat()
    })


@app.route('/api/devices')
def devices():
    """Get all devices"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute("SELECT * FROM device_status ORDER BY last_heartbeat DESC")
        devices = [dict(row) for row in cursor.fetchall()]

    return jsonify({"devices": devices})


@app.route('/api/devices/<device_id>')
def device_detail(device_id: str):
    """Get device detail"""
    status = get_device_status(device_id)
    if not status:
        return jsonify({"error": "Device not found"}), 404
    return jsonify(status)


@app.route('/api/tasks')
def tasks():
    """Get task list"""
    status_filter = request.args.get('status')
    limit = int(request.args.get('limit', 100))

    db = get_db()
    with db.get_cursor() as cursor:
        if status_filter:
            cursor.execute(
                "SELECT * FROM task_queue WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status_filter, limit)
            )
        else:
            cursor.execute(
                "SELECT * FROM task_queue ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
        tasks = [dict(row) for row in cursor.fetchall()]

    return jsonify({"tasks": tasks})


@app.route('/api/alerts')
def alerts():
    """Get pending alerts"""
    return jsonify({"alerts": get_pending_alerts()})


@app.route('/api/alerts/<device_id>/resolve', methods=['POST'])
def resolve_device_alert(device_id: str):
    """Resolve alert for device"""
    resolve_alert(device_id)
    return jsonify({"success": True})


@app.route('/api/reports')
def reports():
    """Get historical reports"""
    # TODO: List reports from storage
    return jsonify({"reports": []})


@app.route('/api/health')
def health():
    """Health check"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


async def run_websocket_server():
    """Run WebSocket server in background"""
    server = get_status_server()
    await server.start()
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await server.stop()


def start_dashboard(host: str = "0.0.0.0", port: int = 8080):
    """Start the dashboard server"""
    # Start WebSocket server in background thread
    from threading import Thread

    def run_ws():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_websocket_server())

    ws_thread = Thread(target=run_ws, daemon=True)
    ws_thread.start()

    # Run Flask app
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    start_dashboard()
