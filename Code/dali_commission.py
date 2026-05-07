#!/usr/bin/env python3
# =============================================================================
# DALI ServUI – Commissioning CLI-Skript
# Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
# Version: 1.0.0 | Deploy: 2026-05-07
#
# Adressiert alle DALI-Geraete auf dem Bus ueber den Hasseb USB Master.
# Nutzt python-dali (stabil, getestet mit 21 EVGs).
#
# Verwendung:
#   sudo /opt/dali-servui/venv/bin/python3 dali_commission.py
#   sudo /opt/dali-servui/venv/bin/python3 dali_commission.py --reset-only
#   sudo /opt/dali-servui/venv/bin/python3 dali_commission.py --scan-only
#
# Voraussetzungen:
#   pip install python-dali pyusb hidapi
#   Service muss gestoppt sein: sudo systemctl stop dali-servui
# =============================================================================

import argparse
import sys
import time


def get_driver():
    """Hasseb-Treiber oeffnen."""
    from dali.driver.hasseb import SyncHassebDALIUSBDriver
    return SyncHassebDALIUSBDriver()


def factory_reset(drv):
    """Alle Kurzadressen loeschen und Factory Reset."""
    from dali.gear.general import Reset, DTR0
    from dali.address import Broadcast
    from dali.sequences import Initialise, Terminate, SetShortAddress

    print("Alle Kurzadressen loeschen...")
    drv.send(Terminate())
    time.sleep(0.1)
    drv.send(Initialise(broadcast=True))
    time.sleep(0.1)
    drv.send(Initialise(broadcast=True))
    time.sleep(0.3)
    drv.send(DTR0(255))
    time.sleep(0.05)
    drv.send(SetShortAddress(Broadcast()))
    time.sleep(0.1)
    drv.send(SetShortAddress(Broadcast()))
    time.sleep(0.1)
    drv.send(Terminate())
    time.sleep(0.5)
    print("  Kurzadressen geloescht.")

    print("Factory Reset (Broadcast)...")
    drv.send(Reset(Broadcast()))
    time.sleep(0.1)
    drv.send(Reset(Broadcast()))
    time.sleep(3.0)
    print("  Reset gesendet. EVGs initialisieren sich...")


def commission(drv):
    """Commissioning: Alle Geraete adressieren."""
    from dali.sequences import Commissioning

    print("Commissioning laeuft (kann 2-5 Minuten dauern)...")
    print()

    def on_progress(p):
        msg = str(p)
        if 'found' in msg.lower() or 'address' in msg.lower() or 'complete' in msg.lower():
            print(f"  {msg}")

    drv.run_sequence(Commissioning(), progress_cb=on_progress)
    print()


def scan(drv):
    """Bus-Scan: Alle Adressen 0-63 abfragen."""
    from dali.gear.general import (
        QueryControlGearPresent, QueryActualLevel, QueryDeviceType
    )
    from dali.address import Short

    print("Bus-Scan (Adressen 0-63)...")
    found = []
    for addr in range(64):
        resp = drv.send(QueryControlGearPresent(Short(addr)))
        if resp and resp.raw_value is not None:
            # Level und Typ abfragen
            level_resp = drv.send(QueryActualLevel(Short(addr)))
            level = level_resp.raw_value.as_integer if level_resp and level_resp.raw_value else '?'
            type_resp = drv.send(QueryDeviceType(Short(addr)))
            dtype = type_resp.raw_value.as_integer if type_resp and type_resp.raw_value else '?'
            found.append(addr)
            print(f"  Addr {addr:2d}: Level={level}, Typ={dtype}")

    print(f"\n{len(found)} Geraete gefunden: {found}")
    return found


def main():
    parser = argparse.ArgumentParser(
        description='DALI ServUI – Commissioning CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Beispiele:\n'
               '  %(prog)s              Factory Reset + Commissioning + Scan\n'
               '  %(prog)s --reset-only Nur Factory Reset\n'
               '  %(prog)s --scan-only  Nur Bus-Scan (keine Aenderungen)\n'
               '  %(prog)s --no-reset   Commissioning ohne Reset\n'
    )
    parser.add_argument('--reset-only', action='store_true',
                        help='Nur Factory Reset, kein Commissioning')
    parser.add_argument('--scan-only', action='store_true',
                        help='Nur Bus-Scan, keine Aenderungen')
    parser.add_argument('--no-reset', action='store_true',
                        help='Commissioning ohne vorherigen Reset')
    args = parser.parse_args()

    print("=" * 60)
    print("DALI ServUI – Commissioning CLI")
    print("=" * 60)
    print()

    try:
        drv = get_driver()
        print("Hasseb USB DALI Master geoeffnet")
        print()
    except Exception as e:
        print(f"FEHLER: Hasseb konnte nicht geoeffnet werden: {e}")
        print("Ist der Service gestoppt? sudo systemctl stop dali-servui")
        sys.exit(1)

    try:
        if args.scan_only:
            scan(drv)
        elif args.reset_only:
            factory_reset(drv)
        else:
            if not args.no_reset:
                factory_reset(drv)
            commission(drv)
            print()
            scan(drv)
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
    except Exception as e:
        print(f"\nFEHLER: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            drv.close()
        except Exception:
            pass

    print()
    print("Fertig. Service wieder starten:")
    print("  sudo systemctl start dali-servui")


if __name__ == '__main__':
    main()
