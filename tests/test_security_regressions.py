import os
import tempfile
import threading
import unittest
from datetime import date, datetime

from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError


class RequestStub:
    base_url = "http://testserver/"


class SecurityRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        os.environ.update(
            {
                "DATABASE_PATH": f"{cls.temp_dir.name}/test.db",
                "ADMIN_USERNAME": "test-admin",
                "ADMIN_PASSWORD": "correct-horse-battery-staple",
                "APP_SECRET": "12345678901234567890123456789012",
            }
        )
        global auth, main, models, SessionLocal
        import auth
        import main
        import models
        from database import SessionLocal

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def setUp(self):
        db = SessionLocal()
        try:
            db.query(models.Booking).delete()
            db.query(models.Pass).delete()
            db.query(models.UserEmailAlias).delete()
            db.query(models.User).delete()
            db.query(models.YogaClass).delete()
            db.commit()
        finally:
            db.close()

    def create_class(self, capacity=1):
        db = SessionLocal()
        try:
            payload = main.ClassCreate(
                title="Tesztóra", start_time=datetime(2026, 12, 1, 10, 0), max_capacity=capacity
            )
            created = main.create_class(payload, db, "test-admin")
            return created["id"]
        finally:
            db.close()

    def book(self, class_id, name, email):
        db = SessionLocal()
        try:
            payload = main.BookingRequest(name=name, email=email, class_id=class_id)
            return main.create_booking(payload, RequestStub(), db)
        finally:
            db.close()

    def test_rejects_invalid_capacity_and_identity(self):
        with self.assertRaises(ValidationError):
            main.ClassCreate(title="Teszt", start_time=datetime(2026, 12, 1, 10, 0), max_capacity=0)
        with self.assertRaises(ValidationError):
            main.BookingRequest(name=" ", email="rossz-email", class_id=1)

    def test_single_capacity_creates_waitlist_not_overbooking(self):
        class_id = self.create_class(capacity=1)
        first = self.book(class_id, "Első Tanítvány", "ELSO@example.test")
        second = self.book(class_id, "Második Tanítvány", "masodik@example.test")
        self.assertEqual(first["status"], "active")
        self.assertEqual(second["status"], "waitlisted")
        self.assertIn("személyesen kell rendezned", first["payment_notice"])

        db = SessionLocal()
        try:
            self.assertEqual(
                db.query(models.Booking).filter(models.Booking.status == "active").count(), 1
            )
            self.assertEqual(
                db.query(models.User).filter_by(email="elso@example.test").count(), 1
            )
        finally:
            db.close()

    def test_parallel_bookings_do_not_exceed_capacity(self):
        class_id = self.create_class(capacity=1)
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def book_in_parallel(name, email):
            db = SessionLocal()
            try:
                barrier.wait(timeout=5)
                payload = main.BookingRequest(name=name, email=email, class_id=class_id)
                results.append(main.create_booking(payload, RequestStub(), db)["status"])
            except Exception as error:  # A szálhibákat a teszt főszála jelenti.
                errors.append(error)
            finally:
                db.close()

        threads = [
            threading.Thread(target=book_in_parallel, args=("Első Tanítvány", "elso@example.test")),
            threading.Thread(target=book_in_parallel, args=("Második Tanítvány", "masodik@example.test")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertFalse(errors)
        self.assertCountEqual(results, ["active", "waitlisted"])

    def test_cancellation_preview_has_no_side_effect_and_promotes_waitlist(self):
        class_id = self.create_class(capacity=1)
        first = self.book(class_id, "Első Tanítvány", "elso@example.test")
        self.book(class_id, "Második Tanítvány", "masodik@example.test")
        token = first["cancel_url"].split("token=", 1)[1]

        db = SessionLocal()
        try:
            preview = main.get_cancellation_details(token, db)
            self.assertTrue(preview["can_cancel"])
            self.assertEqual(
                db.query(models.Booking).filter_by(cancel_token=token).one().status, "active"
            )
        finally:
            db.close()

        db = SessionLocal()
        try:
            main.cancel_booking(token, db)
        finally:
            db.close()

        db = SessionLocal()
        try:
            statuses = [booking.status for booking in db.query(models.Booking).order_by(models.Booking.id)]
            self.assertEqual(statuses, ["cancelled", "active"])
        finally:
            db.close()

    def test_admin_token_is_bearer_token_not_basic_credentials(self):
        token, _ = auth.create_admin_token("test-admin")
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        self.assertEqual(auth.verify_admin(credentials), "test-admin")

    def test_eight_visit_pass_is_consumed_at_deadline_and_restored_on_cancellation(self):
        initial_class_id = self.create_class(capacity=2)
        self.book(initial_class_id, "Bérletes Tanítvány", "berletes@example.test")

        db = SessionLocal()
        try:
            user = db.query(models.User).filter_by(email="berletes@example.test").one()
            main.grant_pass(
                user.id,
                main.PassGrantRequest(pass_type="eight_visit"),
                db,
                "test-admin",
            )
        finally:
            db.close()

        db = SessionLocal()
        try:
            yoga_class = models.YogaClass(
                title="Közelgő tesztóra",
                start_time=main.utc_now_naive() + main.timedelta(hours=11),
                max_capacity=2,
            )
            db.add(yoga_class)
            db.commit()
            db.refresh(yoga_class)
            class_id = yoga_class.id
        finally:
            db.close()

        self.book(class_id, "Bérletes Tanítvány", "berletes@example.test")

        db = SessionLocal()
        try:
            main._begin_write_transaction(db)
            main._settle_due_pass_uses(db)
            db.commit()
            yoga_pass = db.query(models.Pass).one()
            booking = db.query(models.Booking).filter_by(class_id=class_id).one()
            self.assertEqual(yoga_pass.valid_until - yoga_pass.issued_at, main.timedelta(days=60))
            self.assertEqual(yoga_pass.remaining_uses, 7)
            self.assertTrue(booking.pass_use_consumed)

            main._begin_write_transaction(db)
            main._cancel_booking_in_transaction(db, booking, respect_deadline=False)
            db.commit()
            self.assertEqual(yoga_pass.remaining_uses, 8)
            self.assertFalse(booking.pass_use_consumed)
        finally:
            db.close()

    def test_expired_pass_is_not_active(self):
        class_id = self.create_class(capacity=2)
        self.book(class_id, "Lejárt Bérlet", "lejart@example.test")

        db = SessionLocal()
        try:
            user = db.query(models.User).filter_by(email="lejart@example.test").one()
            main.grant_pass(user.id, main.PassGrantRequest(pass_type="monthly"), db, "test-admin")
            yoga_pass = db.query(models.Pass).filter_by(user_id=user.id).one()
            yoga_pass.valid_until = main.utc_now_naive() - main.timedelta(seconds=1)
            db.commit()
            self.assertIsNone(main._pass_summary_for_user(db, user.id))
        finally:
            db.close()

    def test_admin_can_edit_pass_expiry_and_remaining_uses(self):
        class_id = self.create_class(capacity=2)
        self.book(class_id, "Szerkeszthető Bérlet", "szerkesztheto@example.test")

        db = SessionLocal()
        try:
            user = db.query(models.User).filter_by(email="szerkesztheto@example.test").one()
            created = main.grant_pass(
                user.id,
                main.PassGrantRequest(pass_type="eight_visit"),
                db,
                "test-admin",
            )
            updated = main.update_pass(
                created["id"],
                main.PassUpdateRequest(valid_until=date(2026, 12, 24), remaining_uses=5),
                db,
                "test-admin",
            )
            self.assertEqual(updated["remaining_uses"], 5)
            self.assertEqual(main.utc_to_local(updated["valid_until"]).date(), date(2026, 12, 24))
        finally:
            db.close()

    def test_only_one_active_pass_is_allowed_and_can_be_removed(self):
        class_id = self.create_class(capacity=2)
        self.book(class_id, "Egy Bérletes Vendég", "egyberlet@example.test")

        db = SessionLocal()
        try:
            user = db.query(models.User).filter_by(email="egyberlet@example.test").one()
            created = main.grant_pass(
                user.id,
                main.PassGrantRequest(pass_type="monthly"),
                db,
                "test-admin",
            )
            with self.assertRaises(main.HTTPException) as error:
                main.grant_pass(
                    user.id,
                    main.PassGrantRequest(pass_type="eight_visit"),
                    db,
                    "test-admin",
                )
            self.assertEqual(error.exception.status_code, 409)

            result = main.delete_pass(created["id"], db, "test-admin")
            self.assertIn("eltávolítva", result["message"])
            self.assertEqual(db.query(models.Pass).filter_by(user_id=user.id).count(), 0)
        finally:
            db.close()

    def test_schedule_sync_restores_instructor_zoom_and_note_from_template(self):
        import populate_db

        db = SessionLocal()
        try:
            db.add_all(
                [
                    models.YogaClass(
                        title="Iyengar jóga - diák",
                        start_time=main.to_utc_naive(datetime(2026, 12, 1, 15, 15)),
                        max_capacity=15,
                        instructor="Klára",
                        zoom_available=True,
                        note=None,
                    ),
                    models.YogaClass(
                        title="Gerincterápia",
                        start_time=main.to_utc_naive(datetime(2026, 12, 3, 10, 0)),
                        max_capacity=15,
                        instructor=None,
                        zoom_available=False,
                        note=None,
                    ),
                    models.YogaClass(
                        title="Légzés",
                        start_time=main.to_utc_naive(datetime(2026, 12, 4, 6, 20)),
                        max_capacity=15,
                        instructor="Téves oktató",
                        zoom_available=True,
                        note="Téves megjegyzés",
                    ),
                ]
            )
            db.commit()

            self.assertEqual(populate_db.sync_existing_class_metadata(db), 3)
            db.commit()

            student_class = db.query(models.YogaClass).filter_by(title="Iyengar jóga - diák").one()
            therapy_class = db.query(models.YogaClass).filter_by(title="Gerincterápia").one()
            breathing_class = db.query(models.YogaClass).filter_by(title="Légzés").one()
            self.assertFalse(student_class.zoom_available)
            self.assertEqual(student_class.note, "*")
            self.assertEqual(therapy_class.instructor, "Klára")
            self.assertTrue(therapy_class.zoom_available)
            self.assertEqual(therapy_class.note, "Szükséges otthoni kötélfal!")
            self.assertIsNone(breathing_class.instructor)
            self.assertFalse(breathing_class.zoom_available)
            self.assertIsNone(breathing_class.note)
        finally:
            db.close()

    def test_admin_can_permanently_delete_guest_and_promote_waitlist(self):
        class_id = self.create_class(capacity=1)
        self.book(class_id, "Törlendő Vendég", "torlendo@example.test")
        self.book(class_id, "Várólistás Vendég", "varolistas@example.test")

        db = SessionLocal()
        try:
            user = db.query(models.User).filter_by(email="torlendo@example.test").one()
            user_id = user.id
            db.add(models.UserEmailAlias(user_id=user_id, email="masodlagos@example.test"))
            db.commit()
            main.grant_pass(user_id, main.PassGrantRequest(pass_type="monthly"), db, "test-admin")

            result = main.delete_user(user_id, db, "test-admin")
            self.assertIn("véglegesen törölve", result["message"])
            self.assertEqual(db.query(models.User).filter_by(id=user_id).count(), 0)
            self.assertEqual(db.query(models.UserEmailAlias).filter_by(user_id=user_id).count(), 0)
            self.assertEqual(db.query(models.Pass).filter_by(user_id=user_id).count(), 0)
            self.assertEqual(db.query(models.Booking).filter_by(user_id=user_id).count(), 0)
            self.assertEqual(
                db.query(models.Booking)
                .filter_by(class_id=class_id, user_id=main._find_user_by_email(db, "varolistas@example.test").id)
                .one()
                .status,
                "active",
            )
        finally:
            db.close()

    def test_admin_can_edit_class_but_not_below_active_bookings(self):
        class_id = self.create_class(capacity=2)
        self.book(class_id, "Első Jelentkező", "elsojelentkezo@example.test")
        self.book(class_id, "Második Jelentkező", "masodikjelentkezo@example.test")

        db = SessionLocal()
        try:
            updated = main.update_class(
                class_id,
                main.ClassUpdate(
                    title="Szerkesztett jógaóra",
                    start_time=datetime(2026, 12, 2, 18, 30),
                    max_capacity=2,
                    instructor="Teszt Oktató",
                    note="Hozz magaddal matracot.",
                    zoom_available=True,
                ),
                db,
                "test-admin",
            )
            self.assertEqual(updated["title"], "Szerkesztett jógaóra")
            self.assertEqual(updated["max_capacity"], 2)
            self.assertEqual(updated["instructor"], "Teszt Oktató")
            self.assertTrue(updated["zoom_available"])

            with self.assertRaises(main.HTTPException) as error:
                main.update_class(
                    class_id,
                    main.ClassUpdate(
                        title="Túl kicsi létszám",
                        start_time=datetime(2026, 12, 2, 18, 30),
                        max_capacity=1,
                        instructor=None,
                        note=None,
                        zoom_available=False,
                    ),
                    db,
                    "test-admin",
                )
            self.assertEqual(error.exception.status_code, 409)
        finally:
            db.close()

    def test_email_merge_moves_bookings_to_one_guest(self):
        first_class_id = self.create_class(capacity=2)
        second_class_id = self.create_class(capacity=2)
        self.book(first_class_id, "Egy Vendég", "elso@example.test")
        self.book(second_class_id, "Egy Vendég", "masodik@example.test")

        db = SessionLocal()
        try:
            result = main.merge_user_emails(
                main.EmailMergeRequest(
                    primary_email="elso@example.test", secondary_email="masodik@example.test"
                ),
                db,
                "test-admin",
            )
            self.assertIn("sikeresen", result["message"])
            primary_user = main._find_user_by_email(db, "elso@example.test")
            secondary_user = main._find_user_by_email(db, "masodik@example.test")
            self.assertEqual(primary_user.id, secondary_user.id)
            self.assertEqual(db.query(models.User).count(), 1)
            self.assertEqual(
                db.query(models.Booking).filter_by(user_id=primary_user.id).count(), 2
            )

            third_class_id = self.create_class(capacity=2)
            self.book(third_class_id, "Egy Vendég", "masodik@example.test")
            self.assertEqual(db.query(models.User).count(), 1)
            self.assertEqual(
                db.query(models.Booking).filter_by(user_id=primary_user.id).count(), 3
            )
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
