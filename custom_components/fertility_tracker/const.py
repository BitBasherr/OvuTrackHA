from __future__ import annotations

DOMAIN = "fertility_tracker"

PLATFORMS = ["sensor", "binary_sensor", "calendar"]

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "fertility_tracker_"

CONF_NAME = "name"
CONF_LUTEAL_DAYS = "luteal_days"
CONF_RECENT_WEIGHT = "recent_weight"
CONF_LONG_WEIGHT = "long_weight"
CONF_RECENT_WINDOW = "recent_window"
CONF_NOTIFY_SERVICES = "notify_services"
CONF_TRIGGER_ENTITIES = "trigger_entities"
CONF_DAILY_REMINDER_TIME = "daily_reminder_time"
CONF_QUIET_HOURS_START = "quiet_hours_start"
CONF_QUIET_HOURS_END = "quiet_hours_end"

DEFAULT_LUTEAL_DAYS = 14
DEFAULT_RECENT_WEIGHT = 0.7
DEFAULT_LONG_WEIGHT = 0.3
DEFAULT_RECENT_WINDOW = 3
DEFAULT_DAILY_REMINDER_TIME = "09:00:00"  # local time; “ask if period happened”
DEFAULT_QUIET_HOURS_START = "22:00:00"
DEFAULT_QUIET_HOURS_END = "07:00:00"

ATTR_CYCLE_DAY = "cycle_day"
ATTR_CYCLE_LEN_AVG = "cycle_length_avg"
ATTR_CYCLE_LEN_STD = "cycle_length_std"
ATTR_NEXT_PERIOD = "next_period_date"
ATTR_PRED_OVULATION = "predicted_ovulation_date"
ATTR_FERTILE_START = "fertile_window_start"
ATTR_FERTILE_END = "fertile_window_end"
ATTR_IMPLANT_START = "implantation_window_start"
ATTR_IMPLANT_END = "implantation_window_end"
ATTR_RISK_LABEL = "risk_label"
ATTR_LAST_PERIOD_START = "last_period_start"
ATTR_LAST_PERIOD_END = "last_period_end"

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
