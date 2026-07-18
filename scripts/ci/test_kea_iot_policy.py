#!/usr/bin/env python3
"""Regression tests for Kea IoT reservations and Home Assistant LAN policy."""

from __future__ import annotations

import ipaddress
import json
import re
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
RESERVATIONS_PATH = REPO_ROOT / "apps" / "kea" / "iot-reservations.json"
KEA_CONFIG_PATH = REPO_ROOT / "apps" / "kea" / "kea-dhcp4.conf"
KEA_KUSTOMIZATION_PATH = REPO_ROOT / "apps" / "kea" / "kustomization.yaml"
HOME_ASSISTANT_POLICY_PATH = (
    REPO_ROOT / "apps" / "home-assistant" / "networkpolicy.yaml"
)
IOT_POOL = ipaddress.ip_network("192.168.1.0/24")
MAC_ADDRESS = re.compile(r"^[0-9a-f]{2}(?::[0-9a-f]{2}){5}$")


class KeaIotReservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reservations = json.loads(RESERVATIONS_PATH.read_text())

    def test_reservations_are_unique_valid_and_sorted(self) -> None:
        self.assertIsInstance(self.reservations, list)
        self.assertGreater(len(self.reservations), 0)

        addresses: list[ipaddress.IPv4Address] = []
        mac_addresses: list[str] = []
        hostnames: list[str] = []
        for reservation in self.reservations:
            self.assertEqual(
                set(reservation),
                {"hw-address", "ip-address", "hostname"},
            )
            self.assertRegex(reservation["hw-address"], MAC_ADDRESS)
            address = ipaddress.ip_address(reservation["ip-address"])
            self.assertIn(address, IOT_POOL)
            self.assertGreaterEqual(int(address), int(IOT_POOL.network_address) + 10)
            self.assertLessEqual(int(address), int(IOT_POOL.network_address) + 239)
            self.assertRegex(
                reservation["hostname"],
                r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$",
            )
            addresses.append(address)
            mac_addresses.append(reservation["hw-address"])
            hostnames.append(reservation["hostname"])

        self.assertEqual(len(addresses), len(set(addresses)))
        self.assertEqual(len(mac_addresses), len(set(mac_addresses)))
        self.assertEqual(len(hostnames), len(set(hostnames)))
        self.assertEqual(addresses, sorted(addresses))

    def test_reservation_inventory_is_mounted_and_included(self) -> None:
        kea_config = KEA_CONFIG_PATH.read_text()
        self.assertIn(
            '"reservations": <?include "/etc/kea/iot-reservations.json"?>',
            kea_config,
        )
        kustomization = yaml.safe_load(KEA_KUSTOMIZATION_PATH.read_text())
        files = kustomization["configMapGenerator"][0]["files"]
        self.assertIn("iot-reservations.json", files)


class HomeAssistantIotPolicyTests(unittest.TestCase):
    def test_tplink_lan_rule_is_protocol_scoped(self) -> None:
        policy = yaml.safe_load(HOME_ASSISTANT_POLICY_PATH.read_text())
        matching_rules = [
            rule
            for rule in policy["spec"]["egress"]
            if any(
                destination.get("ipBlock", {}).get("cidr") == "192.168.1.0/24"
                for destination in rule.get("to", [])
            )
        ]
        self.assertEqual(len(matching_rules), 1)
        ports = {
            (entry["protocol"], entry["port"])
            for entry in matching_rules[0].get("ports", [])
        }
        self.assertEqual(
            ports,
            {
                ("UDP", 9999),
                ("UDP", 20002),
                ("TCP", 80),
                ("TCP", 9999),
            },
        )


if __name__ == "__main__":
    unittest.main()
