import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

from app.modules.notifications.service import render_body


class TestRenderBody:
    def test_substitutes_a_single_placeholder(self) -> None:
        assert render_body("Hi {{patient_name}}!", {"patient_name": "Jane"}) == "Hi Jane!"

    def test_substitutes_multiple_placeholders(self) -> None:
        body = "Hi {{patient_name}}, your appointment at {{clinic_name}} is on {{appointment_time}}."
        context = {"patient_name": "Jane", "clinic_name": "Sunrise Clinic", "appointment_time": "2026-09-10T10:00:00"}
        assert render_body(body, context) == "Hi Jane, your appointment at Sunrise Clinic is on 2026-09-10T10:00:00."

    def test_repeated_placeholder_is_substituted_every_time(self) -> None:
        assert render_body("{{name}} and {{name}} again", {"name": "X"}) == "X and X again"

    def test_missing_variable_renders_as_a_bracketed_placeholder(self) -> None:
        assert render_body("Hi {{patient_name}}!", {}) == "Hi [patient_name]!"

    def test_partial_context_only_fills_in_what_it_has(self) -> None:
        body = "Hi {{patient_name}}, at {{clinic_name}}."
        assert render_body(body, {"patient_name": "Jane"}) == "Hi Jane, at [clinic_name]."

    def test_body_with_no_placeholders_is_returned_unchanged(self) -> None:
        assert render_body("No placeholders here.", {"unused": "value"}) == "No placeholders here."

    def test_never_raises_on_malformed_or_empty_input(self) -> None:
        assert render_body("", {}) == ""
        assert render_body("Just {{one} brace", {}) == "Just {{one} brace"
