import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.letterhead.schemas import LetterheadConfig, LetterheadHeaderSource


class TestLetterheadConfig:
    def test_defaults_to_auto_header_source(self) -> None:
        config = LetterheadConfig()
        assert config.header_source == LetterheadHeaderSource.AUTO
        assert config.physical_top_margin_mm == 40.0
        assert config.physical_bottom_margin_mm == 20.0

    def test_custom_asset_requires_a_header_image(self) -> None:
        with pytest.raises(ValidationError):
            LetterheadConfig(header_source=LetterheadHeaderSource.CUSTOM_ASSET)

    def test_custom_asset_with_header_image_is_valid(self) -> None:
        config = LetterheadConfig(header_source=LetterheadHeaderSource.CUSTOM_ASSET, header_image_url="https://cdn.example.com/header.png")
        assert config.header_image_url == "https://cdn.example.com/header.png"

    @pytest.mark.parametrize("margin", [-1, 201])
    def test_rejects_out_of_range_margins(self, margin: float) -> None:
        with pytest.raises(ValidationError):
            LetterheadConfig(physical_top_margin_mm=margin)
