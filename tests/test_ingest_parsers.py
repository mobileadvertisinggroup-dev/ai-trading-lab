"""Tests for the pure ingestion parsers (network paths run only on Actions)."""
import numpy as np
import pytest

from lab.data import ingest as I


def test_parse_kline_csv_with_and_without_header():
    row = "1609459200000,29000.1,29100.2,28900.3,29050.4,120.5,1609460099999,3500000.0,1500,60.2,1750000.0,0"
    hdr = ("open_time,open,high,low,close,volume,close_time,quote_volume,"
           "count,taker_buy_volume,taker_buy_quote_volume,ignore")
    for raw in (row.encode(), (hdr + "\n" + row).encode()):
        df = I.parse_kline_csv(raw)
        assert len(df) == 1
        assert df.open_time[0] == 1609459200000
        assert df.quote_volume[0] == 3500000.0
        assert list(df.columns) == ["open_time", "open", "high", "low",
                                    "close", "volume", "quote_volume"]


def test_parse_kline_csv_normalizes_microseconds():
    row = "1609459200000000,1,2,0.5,1.5,10,1609460099999999,15,5,4,6,0"
    df = I.parse_kline_csv(row.encode())
    assert df.open_time[0] == 1609459200000


def test_parse_kline_csv_rejects_misaligned_and_malformed():
    with pytest.raises(ValueError):
        I.parse_kline_csv(b"1609459200001,1,2,0.5,1.5,10,1,15,5,4,6,0")  # off-grid
    with pytest.raises(ValueError):
        I.parse_kline_csv(b"1,2,3")  # wrong column count


def test_parse_funding_csv_known_layout():
    raw = (b"calc_time,funding_interval_hours,last_funding_rate\n"
           b"1609459200000,8,0.0001\n1609488000000,8,-0.0002\n")
    df = I.parse_funding_csv(raw)
    assert list(df.funding_time) == [1609459200000, 1609488000000]
    assert df.funding_rate[1] == -0.0002


def test_parse_funding_csv_rejects_unknown_layout():
    with pytest.raises(ValueError):
        I.parse_funding_csv(b"a,b,c\n1,2,3\n")


def test_parse_s3_listing_prefixes_and_pagination():
    xml = b"""<?xml version="1.0"?>
    <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
      <IsTruncated>true</IsTruncated>
      <CommonPrefixes><Prefix>data/futures/um/monthly/klines/BTCUSDT/</Prefix></CommonPrefixes>
      <CommonPrefixes><Prefix>data/futures/um/monthly/klines/ETHUSDT/</Prefix></CommonPrefixes>
      <Contents><Key>data/futures/um/monthly/klines/x.zip</Key></Contents>
    </ListBucketResult>"""
    prefixes, keys, truncated, marker = I.parse_s3_listing(xml)
    assert len(prefixes) == 2 and "BTCUSDT" in prefixes[0]
    assert truncated and marker == keys[-1]


def test_months_between():
    import datetime as dt
    assert I.months_between(dt.date(2023, 11, 5), dt.date(2024, 2, 1)) == \
        ["2023-11", "2023-12", "2024-01", "2024-02"]


def test_exclusion_registry_classification():
    from lab.data.ingest import classify_symbol, load_exclusion_registry
    reg = load_exclusion_registry("data/manifests/exclusion_registry_v1.json")
    assert reg["registry_version"] == "exclusions-v1"
    # stablecoin bases excluded, incl. the reviewer's named newer assets
    for s in ("USDCUSDT", "USDEUSDT", "USDSUSDT", "FDUSDUSDT", "EURUSDT"):
        rec = classify_symbol(s, reg)
        assert not rec["included"] and rec["category"] == "stablecoin_base"
    # leveraged/inverse tokens excluded by pattern
    for s in ("BTCUPUSDT", "ETHDOWNUSDT", "ADABULLUSDT", "XRPBEARUSDT"):
        assert not classify_symbol(s, reg)["included"]
    # ordinary assets included with a full classification record
    rec = classify_symbol("BTCUSDT", reg)
    assert rec == {"symbol": "BTCUSDT", "included": True, "category": None,
                   "rule": None}
    assert classify_symbol("SOLUSDT", reg)["included"]
    # near-miss names are NOT over-excluded
    assert classify_symbol("SUPERUSDT", reg)["included"]   # ends 'ER' not 'UP'
    assert classify_symbol("PUNDIXUSDT", reg)["included"]
