"""
API endpoint tests.
"""

import pytest
from app.models.schemas import OutreachRequest, FeedbackRequest


class TestOutreachRequestValidation:
    """Test input validation on OutreachRequest."""

    def test_valid_request(self):
        req = OutreachRequest(domain="stripe.com", person_name="Jane Smith")
        assert req.domain == "stripe.com"
        assert req.person_name == "Jane Smith"

    def test_domain_normalization(self):
        req = OutreachRequest(domain="HTTPS://Stripe.COM/pricing", person_name="Jane Smith")
        assert req.domain == "stripe.com"

    def test_domain_strips_protocol(self):
        req = OutreachRequest(domain="http://example.com", person_name="Jane Smith")
        assert req.domain == "example.com"

    def test_invalid_domain_rejected(self):
        with pytest.raises(ValueError):
            OutreachRequest(domain="not a domain!", person_name="Jane Smith")

    def test_single_name_rejected(self):
        with pytest.raises(ValueError, match="full name"):
            OutreachRequest(domain="stripe.com", person_name="Jane")

    def test_name_with_injection_chars_rejected(self):
        with pytest.raises(ValueError, match="invalid characters"):
            OutreachRequest(domain="stripe.com", person_name="<script>alert(1)</script> Jane")

    def test_empty_domain_rejected(self):
        with pytest.raises(ValueError):
            OutreachRequest(domain="", person_name="Jane Smith")

    def test_webhook_url_optional(self):
        req = OutreachRequest(domain="stripe.com", person_name="Jane Smith")
        assert req.webhook_url is None

    def test_webhook_url_accepted(self):
        req = OutreachRequest(
            domain="stripe.com",
            person_name="Jane Smith",
            webhook_url="https://example.com/hook",
        )
        assert req.webhook_url == "https://example.com/hook"


class TestFeedbackRequestValidation:
    """Test input validation on FeedbackRequest."""

    def test_valid_thumbs_up(self):
        req = FeedbackRequest(rating="thumbs_up")
        assert req.rating == "thumbs_up"

    def test_valid_thumbs_down(self):
        req = FeedbackRequest(rating="thumbs_down", comment="Not relevant")
        assert req.rating == "thumbs_down"

    def test_invalid_rating_rejected(self):
        with pytest.raises(ValueError):
            FeedbackRequest(rating="meh")

    def test_quality_range(self):
        req = FeedbackRequest(rating="thumbs_up", hook_quality=5, message_quality=1)
        assert req.hook_quality == 5

    def test_quality_out_of_range(self):
        with pytest.raises(ValueError):
            FeedbackRequest(rating="thumbs_up", hook_quality=6)

    def test_quality_below_range(self):
        with pytest.raises(ValueError):
            FeedbackRequest(rating="thumbs_up", hook_quality=0)
