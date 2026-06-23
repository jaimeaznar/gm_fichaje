"""Verificación de residencia UE (REQ-23)."""

from __future__ import annotations

import pytest

from app.core.config import RegionNotEUError, Settings, assert_eu_region, is_eu_region


@pytest.mark.parametrize(
    "region",
    ["eu-west-1", "eu-central-1", "europe-west1", "Frankfurt", "EU_WEST_3"],
)
def test_eu_regions_accepted(region):
    assert is_eu_region(region)


@pytest.mark.parametrize(
    "region",
    ["us-east-1", "ap-south-1", "sa-east-1", "", None, "europa-imaginaria"],
)
def test_non_eu_regions_rejected(region):
    assert not is_eu_region(region)


def test_assert_eu_region_passes_for_eu():
    s = Settings(deploy_region="eu-west-1", supabase_region="eu-central-1")
    assert_eu_region(s)  # no lanza


def test_assert_eu_region_fails_for_non_eu():
    s = Settings(deploy_region="us-east-1", supabase_region="eu-central-1")
    with pytest.raises(RegionNotEUError):
        assert_eu_region(s)
