"""«Problem melden»: building, sending and the e-mail fallback – without network."""

import base64
import io
import json
import zipfile

import pytest

from verbalis import feedback
from test_service import make_service


class Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_config_from_environment_or_bundled_file(tmp_path, monkeypatch):
    monkeypatch.delenv("VERBALIS_FEEDBACK_URL", raising=False)
    monkeypatch.setattr(feedback, "_bundle_folders", lambda: [tmp_path])
    assert feedback.config() is None                                         # e-mail only
    (tmp_path / "feedback.json").write_text(json.dumps({"url": "https://script.google.com/x/exec", "token": "t"}))
    assert feedback.config() == {"url": "https://script.google.com/x/exec", "token": "t"}
    monkeypatch.setenv("VERBALIS_FEEDBACK_URL", "https://script.google.com/dev/exec")
    assert feedback.config()["url"] == "https://script.google.com/dev/exec"


def test_report_needs_a_text_and_leaves_out_device_names():
    with pytest.raises(ValueError):
        feedback.build("  ")
    report = feedback.build("Aufnahme bricht ab", diagnosis="Mikrofon: AirPods von Andrea", redact=["AirPods von Andrea"])
    assert "AirPods" not in report["diagnosis"] and report["message"] == "Aufnahme bricht ab"
    assert "log_zip" not in report


def test_too_large_log_is_not_sent(monkeypatch):
    monkeypatch.setattr(feedback, "MAX_LOG_BYTES", 10)
    report = feedback.build("x", log_zip=b"0" * 11)
    assert "log_zip" not in report and "zu gross" in report["log_note"]


def test_send_posts_json_with_token_and_checks_the_answer():
    sent = []

    def opener(request, timeout):
        sent.append(request)
        return Answer(b"ok")

    feedback.send({"message": "x"}, {"url": "https://script.google.com/x/exec", "token": "geheim"}, opener=opener)
    body = json.loads(sent[0].data)
    assert body == {"message": "x", "token": "geheim"} and sent[0].get_method() == "POST"
    with pytest.raises(RuntimeError, match="nicht angenommen"):
        feedback.send({}, {"url": "https://x"}, opener=lambda r, timeout: Answer(b"forbidden"))

    def offline(request, timeout):
        raise OSError("no network")
    with pytest.raises(RuntimeError, match="Internet"):
        feedback.send({}, {"url": "https://x"}, opener=offline)



def test_refused_report_does_not_blame_the_internet():
    """Bug (0.7.29 test): an HTTP 403 from Google (web app not open to «Anyone») was shown as
    «Ist das Internet verfügbar?» – the internet worked, the address refused."""
    import urllib.error

    def refused(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)
    with pytest.raises(RuntimeError, match=r"abgelehnt \(HTTP 403\)") as error:
        feedback.send({}, {"url": "https://x"}, opener=refused)
    assert "Internet" not in str(error.value)

def test_mail_link_goes_to_the_developer():
    link = feedback.mail_link("Ton fehlt")
    assert link.startswith("mailto:andrea@frehner.tech?") and "Ton%20fehlt" in link


def test_service_sends_log_and_diagnosis_without_names(monkeypatch):
    s = make_service()
    s.save_settings({"name": "Andrea Frehner"})
    sent = []
    monkeypatch.setattr(feedback, "config", lambda: {"url": "https://script.google.com/x/exec", "token": "t"})
    monkeypatch.setattr(feedback, "send", lambda report, target: sent.append(report))
    monkeypatch.setattr(s, "diagnose_report", lambda: "Name: Andrea Frehner\nVersion: 1")
    assert s.report_problem("Absturz beim Stoppen", "a@b.ch") == {"sent": True}
    report = sent[0]
    assert "Andrea Frehner" not in report["diagnosis"] and report["contact"] == "a@b.ch"
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(report["log_zip"]))) as z:
        assert "info.json" in z.namelist()
    s.report_problem("ohne alles", with_log=False, with_diagnosis=False)
    assert "log_zip" not in sent[1] and sent[1]["diagnosis"] == ""


def test_service_without_address_offers_mail_only(monkeypatch):
    s = make_service()
    monkeypatch.setattr(feedback, "config", lambda: None)
    assert s.report_info()["can_send"] is False
    with pytest.raises(RuntimeError, match="E-Mail"):
        s.report_problem("x")
