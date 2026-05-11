"""Configuration loader module"""

import yaml
import os
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class SystemConfig:
    max_devices: int = 10
    heartbeat_interval: int = 5
    offline_threshold: int = 30
    max_retries: int = 3
    retry_interval: int = 3
    operations_per_minute: int = 12
    daily_limit_per_user: int = 3
    min_interval_between_operations: int = 180
    new_account_ramp_days: int = 7
    new_account_daily_limit: int = 20


@dataclass
class AIConfig:
    enabled: bool = True
    max_llm_concurrent: int = 3
    llm_timeout: int = 5
    case_similarity_threshold: float = 0.85


@dataclass
class DashboardConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    ws_path: str = "/ws"


class ConfigLoader:
    """Configuration loader from YAML files"""

    _instance: Optional['ConfigLoader'] = None

    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "configs")
        self.config_dir = config_dir
        self._system_config: Optional[SystemConfig] = None
        self._ai_config: Optional[AIConfig] = None
        self._dashboard_config: Optional[DashboardConfig] = None

    def load_all(self):
        """Load all configuration files"""
        self._load_system_config()
        self._load_ai_config()
        self._load_dashboard_config()

    def _load_system_config(self):
        """Load system configuration"""
        path = os.path.join(self.config_dir, "system.yaml")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                sys_data = data.get('system', {})
                self._system_config = SystemConfig(
                    max_devices=sys_data.get('max_devices', 10),
                    heartbeat_interval=sys_data.get('heartbeat_interval', 5),
                    offline_threshold=sys_data.get('offline_threshold', 30),
                    max_retries=sys_data.get('max_retries', 3),
                    retry_interval=sys_data.get('retry_interval', 3),
                    operations_per_minute=sys_data.get('operations_per_minute', 12),
                    daily_limit_per_user=sys_data.get('daily_limit_per_user', 3),
                    min_interval_between_operations=sys_data.get('min_interval_between_operations', 180),
                    new_account_ramp_days=sys_data.get('new_account_ramp_days', 7),
                    new_account_daily_limit=sys_data.get('new_account_daily_limit', 20)
                )
        else:
            self._system_config = SystemConfig()

    def _load_ai_config(self):
        """Load AI Agent configuration"""
        path = os.path.join(self.config_dir, "system.yaml")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                ai_data = data.get('ai_agent', {})
                self._ai_config = AIConfig(
                    enabled=ai_data.get('enabled', True),
                    max_llm_concurrent=ai_data.get('max_llm_concurrent', 3),
                    llm_timeout=ai_data.get('llm_timeout', 5),
                    case_similarity_threshold=ai_data.get('case_similarity_threshold', 0.85)
                )
        else:
            self._ai_config = AIConfig()

    def _load_dashboard_config(self):
        """Load dashboard configuration"""
        path = os.path.join(self.config_dir, "system.yaml")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                dash_data = data.get('dashboard', {})
                self._dashboard_config = DashboardConfig(
                    host=dash_data.get('host', '0.0.0.0'),
                    port=dash_data.get('port', 8080),
                    ws_path=dash_data.get('ws_path', '/ws')
                )
        else:
            self._dashboard_config = DashboardConfig()

    @property
    def system(self) -> SystemConfig:
        if self._system_config is None:
            self._load_system_config()
        return self._system_config

    @property
    def ai(self) -> AIConfig:
        if self._ai_config is None:
            self._load_ai_config()
        return self._ai_config

    @property
    def dashboard(self) -> DashboardConfig:
        if self._dashboard_config is None:
            self._load_dashboard_config()
        return self._dashboard_config


def get_config() -> ConfigLoader:
    """Get global config loader instance"""
    if ConfigLoader._instance is None:
        ConfigLoader._instance = ConfigLoader()
    return ConfigLoader._instance
