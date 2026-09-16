"""Fixtures communes des tests."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Active le chargement des intégrations custom dans chaque test."""
    return
