"""Seed the database with test data including the primary test user."""
from app.database import engine, SessionLocal, Base
from app.models import User, Policy, Coverage, ClaimsOfficer

Base.metadata.create_all(bind=engine)


def seed():
    db = SessionLocal()

    # Skip if already seeded
    if db.query(User).first():
        print("Database already seeded. Skipping.")
        db.close()
        return

    # ── Test user (mobile app login) ───────────────────────────────────────
    user = User(
        full_name="Krishna Anurag",
        dob="2000-01-16",
        email="krishnaanurag16@gmail.com",
        phone="6202234696",
    )
    db.add(user)
    db.flush()

    # ── Policy ─────────────────────────────────────────────────────────────
    policy = Policy(
        user_id=user.id,
        policy_number="POL-2026-AU-087234",
        status="active",
        issued_date="2025-03-15",
        renewal_date="2027-03-15",
    )
    db.add(policy)
    db.flush()

    # ── Coverages ──────────────────────────────────────────────────────────
    coverages = [
        Coverage(
            policy_id=policy.id,
            coverage_type="own_damage",
            coverage_label="Own Damage",
            coverage_limit_cents=5000000,
            status="active",
        ),
        Coverage(
            policy_id=policy.id,
            coverage_type="third_party_liability",
            coverage_label="Third-Party Liability",
            coverage_limit_cents=10000000,
            status="active",
        ),
        Coverage(
            policy_id=policy.id,
            coverage_type="add_on",
            coverage_label="Roadside Assistance Add-On",
            coverage_limit_cents=50000,
            status="active",
        ),
    ]
    db.add_all(coverages)

    # ── Dashboard officer (Claims Officer Lead) ─────────────────────────────
    officer = ClaimsOfficer(
        name="Krishna Anurag",
        email="krishnaanurag16@gmail.com",
        password_hash="shield@123",
        role="senior",
        department="SIU",
    )
    db.add(officer)

    # ── 5 SIU officers for quorum voting ──────────────────────────────────
    test_officers = [
        ClaimsOfficer(name="D. Torres", email="d.torres@syntheticshield.demo", password_hash="demo123", role="siu_officer", department="SIU"),
        ClaimsOfficer(name="R. Park", email="r.park@syntheticshield.demo", password_hash="demo123", role="siu_officer", department="SIU"),
        ClaimsOfficer(name="S. Okonkwo", email="s.okonkwo@syntheticshield.demo", password_hash="demo123", role="siu_officer", department="SIU"),
        ClaimsOfficer(name="M. Reyes", email="m.reyes@syntheticshield.demo", password_hash="demo123", role="siu_officer", department="SIU"),
        ClaimsOfficer(name="J. Chen", email="j.chen@syntheticshield.demo", password_hash="demo123", role="moderator", department="Claims"),
    ]
    db.add_all(test_officers)

    db.commit()
    db.close()
    print("Database seeded successfully!")
    print()
    print("═══ Test Credentials ═══")
    print("Mobile App (OTP login):")
    print("  Phone: 6202234696")
    print("  Email: krishnaanurag16@gmail.com")
    print("  (OTP will be printed in console since OTP_PROVIDER=console)")
    print()
    print("SIU Dashboard:")
    print("  Email: krishnaanurag16@gmail.com")
    print("  Password: shield@123")


if __name__ == "__main__":
    seed()
