DOMAIN = "football"

CONF_ENTRIES = "entries"
CONF_LEAGUE_SHORTCUT = "league_shortcut"
CONF_LEAGUE_NAME = "league_name"
CONF_TEAMS = "teams"
CONF_TEAM_ID = "team_id"
CONF_TEAM_NAME = "team_name"

BASE_URL = "https://api.sportsrc.org"

DEFAULT_SCAN_INTERVAL = 30
LIVE_SCAN_INTERVAL = 30

SENSOR_TYPES = {
    "status": {"name": "Status", "icon": "mdi:soccer"},
    "team_score": {"name": "Score", "icon": "mdi:numeric"},
    "opponent_score": {"name": "Opponent Score", "icon": "mdi:numeric"},
    "opponent": {"name": "Opponent", "icon": "mdi:account"},
    "minute": {"name": "Minute", "icon": "mdi:clock-outline"},
    "round": {"name": "Round", "icon": "mdi:tournament"},
    "league": {"name": "League", "icon": "mdi:trophy"},
}
