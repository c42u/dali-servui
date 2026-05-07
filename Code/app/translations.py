# =============================================================================
# DALI ServUI – Übersetzungen (Deutsch/Englisch)
# Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
# Version: 1.0.0 | Deploy: 2026-05-07
# =============================================================================

TRANSLATIONS = {
    'de': {
        # Navigation
        'app_name': 'DALI ServUI',
        'nav_dashboard': 'Dashboard',
        'nav_devices': 'Geräte',
        'nav_groups': 'Gruppen',
        'nav_scenes': 'Szenen',
        'nav_discovery': 'Erkennung',
        'nav_settings': 'Einstellungen',
        'nav_help': 'Hilfe',
        'nav_log': 'Protokoll',

        # Hilfe
        'help_title': 'Hilfe',

        # Dashboard
        'dashboard_title': 'Dashboard',
        'status_connected': 'Verbunden',
        'status_disconnected': 'Nicht verbunden',
        'status_dryrun': 'Testmodus',
        'firmware': 'Firmware',
        'devices_found': 'Geräte gefunden',
        'queue_size': 'Warteschlange',

        # Geräte
        'devices_title': 'Geräte',
        'device_address': 'Adresse',
        'device_level': 'Helligkeit',
        'device_type': 'Typ',
        'device_groups': 'Gruppen',
        'device_status': 'Status',
        'device_on': 'Ein',
        'device_off': 'Aus',
        'device_present': 'Aktiv',
        'device_absent': 'Nicht erreichbar',

        # Gruppen
        'groups_title': 'Gruppensteuerung',
        'group': 'Gruppe',
        'group_all_on': 'Alle ein',
        'group_all_off': 'Alle aus',

        # Discovery
        'discovery_title': 'Geräte-Erkennung',
        'scan_bus': 'Bus scannen',
        'scan_running': 'Scan läuft...',
        'scan_complete': 'Scan abgeschlossen',
        'commission_bus': 'Adressen zuweisen',
        'commission_broadcast': 'Alle neu adressieren',
        'commission_new_only': 'Nur neue Geräte',
        'commission_running': 'Adresszuweisung läuft...',
        'commission_complete': 'Adresszuweisung abgeschlossen',

        # Steuerung
        'brightness': 'Helligkeit',
        'broadcast': 'Broadcast (alle)',
        'apply': 'Anwenden',

        # Status
        'success': 'Erfolgreich',
        'error': 'Fehler',
        'timeout': 'Zeitüberschreitung',
        'no_device': 'Kein Gerät gefunden',

        # Einstellungen
        'settings_title': 'Einstellungen',
        'language': 'Sprache',
        'lang_de': 'Deutsch',
        'lang_en': 'English',
        'dryrun_mode': 'Testmodus (ohne Hardware)',
        'api_token': 'API-Token',
        'save': 'Speichern',

        # Allgemein
        'loading': 'Laden...',
        'confirm': 'Bestätigen',
        'cancel': 'Abbrechen',
        'refresh': 'Aktualisieren',
        'actions': 'Aktionen',
    },

    'en': {
        # Navigation
        'app_name': 'DALI ServUI',
        'nav_dashboard': 'Dashboard',
        'nav_devices': 'Devices',
        'nav_groups': 'Groups',
        'nav_scenes': 'Scenes',
        'nav_discovery': 'Discovery',
        'nav_settings': 'Settings',
        'nav_help': 'Help',
        'nav_log': 'Log',

        # Help
        'help_title': 'Help',

        # Dashboard
        'dashboard_title': 'Dashboard',
        'status_connected': 'Connected',
        'status_disconnected': 'Disconnected',
        'status_dryrun': 'Dry Run Mode',
        'firmware': 'Firmware',
        'devices_found': 'Devices found',
        'queue_size': 'Queue',

        # Devices
        'devices_title': 'Devices',
        'device_address': 'Address',
        'device_level': 'Brightness',
        'device_type': 'Type',
        'device_groups': 'Groups',
        'device_status': 'Status',
        'device_on': 'On',
        'device_off': 'Off',
        'device_present': 'Active',
        'device_absent': 'Unreachable',

        # Groups
        'groups_title': 'Group Control',
        'group': 'Group',
        'group_all_on': 'All on',
        'group_all_off': 'All off',

        # Discovery
        'discovery_title': 'Device Discovery',
        'scan_bus': 'Scan bus',
        'scan_running': 'Scanning...',
        'scan_complete': 'Scan complete',
        'commission_bus': 'Assign addresses',
        'commission_broadcast': 'Re-address all',
        'commission_new_only': 'New devices only',
        'commission_running': 'Commissioning...',
        'commission_complete': 'Commissioning complete',

        # Controls
        'brightness': 'Brightness',
        'broadcast': 'Broadcast (all)',
        'apply': 'Apply',

        # Status
        'success': 'Success',
        'error': 'Error',
        'timeout': 'Timeout',
        'no_device': 'No device found',

        # Settings
        'settings_title': 'Settings',
        'language': 'Language',
        'lang_de': 'Deutsch',
        'lang_en': 'English',
        'dryrun_mode': 'Dry run mode (no hardware)',
        'api_token': 'API Token',
        'save': 'Save',

        # General
        'loading': 'Loading...',
        'confirm': 'Confirm',
        'cancel': 'Cancel',
        'refresh': 'Refresh',
        'actions': 'Actions',
    }
}


def get_translation(lang: str) -> dict:
    """Hole die Übersetzungen für die angegebene Sprache.

    Args:
        lang: Sprachcode ('de' oder 'en')

    Returns:
        Dict mit allen Übersetzungen, Fallback auf Deutsch
    """
    return TRANSLATIONS.get(lang, TRANSLATIONS['de'])
