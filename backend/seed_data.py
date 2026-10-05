"""Seed the database with test data including the primary test user."""
from app.database import engine, SessionLocal, Base
from app.models import User, Policy, Coverage, ClaimsOfficer
from app.security import hash_password

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
        password_hash=hash_password("shield@123"),
        role="senior",
        department="SIU",
    )
    db.add(officer)

    # ── 5 SIU officers for quorum voting ──────────────────────────────────
    test_officers = [
        ClaimsOfficer(name="Sarayu Vishlawath", email="sarayu.vishlawath@syntheticshield.demo", password_hash=hash_password("demo123"), role="siu_officer", department="SIU"),
        ClaimsOfficer(name="Abhishek Konnur", email="abhishek.konnur@syntheticshield.demo", password_hash=hash_password("demo123"), role="siu_officer", department="SIU"),
        ClaimsOfficer(name="Felina Menezes", email="felina.menezes@syntheticshield.demo", password_hash=hash_password("demo123"), role="siu_officer", department="SIU"),
        ClaimsOfficer(name="Arjun Premanathan", email="arjun.premanathan@syntheticshield.demo", password_hash=hash_password("demo123"), role="siu_officer", department="SIU"),
        ClaimsOfficer(name="Priya Jha", email="priya.jha@syntheticshield.demo", password_hash=hash_password("demo123"), role="moderator", department="Claims"),
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
