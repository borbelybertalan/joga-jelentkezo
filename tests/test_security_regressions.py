import os
import tempfile
import threading
import unittest
from datetime import datetime

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


if __name__ == "__main__":
    unittest.main()
