"""Discovery: a tag must be found whichever of its advertisements comes last."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from py_atc_ble_oepl import discovery
from py_atc_ble_oepl.protocol.constants import MANUFACTURER_ID

# A v2 advertising payload (layout as in test_protocol_atc.py): hw type 0x67, 22 °C.
PAYLOAD = bytes([2, 0x67, 0x00, 0x00, 0x01, 0, 0, 0xB8, 0x0B, 22, 0])


def _advert(address: str, name: str, *, with_data: bool, rssi: int = -60):
    device = SimpleNamespace(address=address, name=name)
    data = {MANUFACTURER_ID: PAYLOAD} if with_data else {}
    return device, SimpleNamespace(local_name=name, manufacturer_data=data, rssi=rssi)


@pytest.fixture
def adverts(monkeypatch):
    sent: list = []

    class Scanner:
        def __init__(self, detection_callback):
            self.callback = detection_callback

        async def __aenter__(self):
            for device, adv in sent:
                self.callback(device, adv)
            return self

        async def __aexit__(self, *exc):
            return None

    monkeypatch.setattr(discovery, "BleakScanner", Scanner)
    return sent


async def test_a_tag_whose_last_advert_lacks_the_data_is_still_found(adverts) -> None:
    adverts += [
        _advert("UUID-1", "ATC_05D611\x00", with_data=True, rssi=-55),
        _advert("UUID-1", "ATC_05D611\x00", with_data=False, rssi=-50),
    ]
    (found,) = await discovery.discover_atc_devices(timeout=0)
    assert (found.mac_address, found.name, found.rssi) == ("UUID-1", "ATC_05D611", -55)
    assert found.advertising_data is not None and found.advertising_data.temperature == 22


async def test_devices_without_atc_data_are_ignored(adverts) -> None:
    adverts += [_advert("UUID-2", "Some speaker", with_data=False)]
    assert await discovery.discover_atc_devices(timeout=0) == []


async def test_each_device_is_listed_once(adverts) -> None:
    adverts += [_advert("UUID-1", "ATC_05D611", with_data=True), _advert("UUID-1", "ATC_05D611", with_data=True)]
    adverts += [_advert("UUID-3", "ATC_164840", with_data=True)]
    assert sorted(d.mac_address for d in await discovery.discover_atc_devices(timeout=0)) == ["UUID-1", "UUID-3"]
