"""SIU majority voting: a strict majority of the panel decides, as soon as it's reached."""
import pytest

from app.models import ClaimAssignment, ClaimsOfficer, Payout
from app.routers import siu


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def siu_panel(db, test_claim, monkeypatch):
    """5-officer panel assigned to test_claim, claim in siu_investigation."""
    async def _no_notify(*args, **kwargs):
        return None
    monkeypatch.setattr(siu, "notify_claim_status", _no_notify)

    officers = []
    for i in range(5):
        o = ClaimsOfficer(name=f"SIU {i}", email=f"siu{i}@test.com", password_hash="x", role="siu_officer")
        db.add(o)
        officers.append(o)
    db.commit()
    for o in officers:
        db.add(ClaimAssignment(claim_id=test_claim.id, officer_id=o.id,
                               assignment_type="siu_vote", status="pending"))
    test_claim.status = "siu_investigation"
    db.commit()
    return officers


def _vote(client, token, claim_id, officer, vote):
    return client.post(f"/claims/{claim_id}/siu-vote", headers=_auth_headers(token),
                       json={"officer_id": officer.id, "vote": vote, "notes": ""})


def test_three_of_five_fraud_confirms_fraud(client, db, test_claim, siu_panel, officer_token):
    for o, v in zip(siu_panel, ["confirm_fraud", "clear", "confirm_fraud", "confirm_fraud"]):
        resp = _vote(client, officer_token, test_claim.id, o, v)
        assert resp.status_code == 200
    body = resp.json()
    assert body["finalized"] is True and body["outcome"] == "confirmed_fraud"
    db.refresh(test_claim)
    assert test_claim.status == "siu_confirmed_fraud"
    # the panel member who never voted is taken off their open workload
    statuses = {a.officer_id: a.status for a in db.query(ClaimAssignment).filter_by(claim_id=test_claim.id)}
    assert statuses[siu_panel[4].id] == "closed"
    # further votes are rejected — the case is decided
    assert _vote(client, officer_token, test_claim.id, siu_panel[4], "clear").status_code == 400


def test_three_of_five_clear_clears_and_pays(client, db, test_claim, siu_panel, officer_token):
    for o, v in zip(siu_panel, ["clear", "confirm_fraud", "clear", "clear"]):
        resp = _vote(client, officer_token, test_claim.id, o, v)
    assert resp.json()["outcome"] == "cleared"
    db.refresh(test_claim)
    assert test_claim.status == "siu_cleared"
    assert db.query(Payout).filter_by(claim_id=test_claim.id).count() == 1


def test_no_decision_before_majority(client, db, test_claim, siu_panel, officer_token):
    for o, v in zip(siu_panel, ["confirm_fraud", "confirm_fraud", "clear", "clear"]):
        resp = _vote(client, officer_token, test_claim.id, o, v)
        assert resp.json()["finalized"] is False
    db.refresh(test_claim)
    assert test_claim.status == "siu_investigation"
    status = client.get(f"/claims/{test_claim.id}/siu-status", headers=_auth_headers(officer_token)).json()
    assert status["majority_needed"] == 3 and status["fraud_votes"] == 2 and status["clear_votes"] == 2


def test_reported_case_3_fraud_then_2_clear_is_fraud(client, db, test_claim, siu_panel, officer_token):
    """The CLM-2026-00030 sequence: decided as fraud at the 3rd vote; later votes rejected."""
    for o in siu_panel[:3]:
        resp = _vote(client, officer_token, test_claim.id, o, "confirm_fraud")
    assert resp.json()["outcome"] == "confirmed_fraud"
    assert _vote(client, officer_token, test_claim.id, siu_panel[3], "clear").status_code == 400
    db.refresh(test_claim)
    assert test_claim.status == "siu_confirmed_fraud"
    assert db.query(Payout).filter_by(claim_id=test_claim.id).count() == 0


def test_cleared_payout_is_claimed_amount_capped_at_coverage(client, db, test_claim, siu_panel, officer_token):
    test_claim.claim_amount_cents = 4_200_00            # $4,200 claimed, coverage limit $5,000
    db.commit()
    for o in siu_panel[:3]:
        _vote(client, officer_token, test_claim.id, o, "clear")
    db.refresh(test_claim)
    assert test_claim.payout_amount_cents == 4_200_00
    assert db.query(Payout).filter_by(claim_id=test_claim.id).one().amount_cents == 4_200_00


def test_double_vote_for_same_officer_is_rejected(client, db, test_claim, siu_panel, officer_token):
    assert _vote(client, officer_token, test_claim.id, siu_panel[0], "confirm_fraud").status_code == 200
    assert _vote(client, officer_token, test_claim.id, siu_panel[0], "confirm_fraud").status_code == 400


def test_siu_panel_never_includes_moderators(db, test_claim, test_officer):
    from app.agents.assignment_agent import assign_siu_officers
    siu = ClaimsOfficer(name="Only SIU", email="only@test.com", password_hash="x", role="siu_officer")
    db.add(siu)
    db.commit()
    assert assign_siu_officers(test_claim.id, db) == [siu.id]   # moderator test_officer excluded


def test_majority_sizes():
    assert [siu._majority(n) for n in (1, 2, 3, 4, 5, 6)] == [1, 2, 2, 3, 3, 4]
