import unittest

from pg_test_support import TestDatabase
from app.services import auth_service
from app.services import memory_service, database_chat_history


class AuthTests(unittest.TestCase):
    def setUp(self):
        # Isolate each test run on its own fresh PostgreSQL database.
        self._db = TestDatabase()
        self._db.start()

    def tearDown(self):
        self._db.stop()

    # --- basic lifecycle ---------------------------------------------------
    def test_register_login_me_logout(self):
        user = auth_service.register_user("alice", "password123")
        self.assertEqual(user["username"], "alice")

        token = auth_service.authenticate("alice", "password123")
        self.assertIsNotNone(token)

        resolved = auth_service.resolve_user(token)
        self.assertEqual(resolved["username"], "alice")
        self.assertEqual(resolved["session_id"], f"user:{user['id']}")

        # Correctly rejects a wrong password.
        self.assertIsNone(auth_service.authenticate("alice", "wrongpass"))

        # Logout revokes the token.
        auth_service.revoke_token(token)
        self.assertIsNone(auth_service.resolve_user(token))

    def test_username_is_case_insensitive_and_unique(self):
        auth_service.register_user("bob", "password123")
        with self.assertRaises(ValueError):
            auth_service.register_user("BOB", "anotherpass1")

        # Login is case-insensitive on the username.
        self.assertIsNotNone(auth_service.authenticate("BoB", "password123"))

    def test_password_validation(self):
        with self.assertRaises(ValueError):
            auth_service.register_user("x", "password123")
        with self.assertRaises(ValueError):
            auth_service.register_user("username", "short")

    # --- user separation ---------------------------------------------------
    def test_two_users_cannot_see_each_other_data(self):
        alice = auth_service.register_user("alice", "password123")
        bob = auth_service.register_user("bob", "password123")
        alice_token = auth_service.authenticate("alice", "password123")
        bob_token = auth_service.authenticate("bob", "password123")
        alice_session = auth_service.resolve_user(alice_token)["session_id"]
        bob_session = auth_service.resolve_user(bob_token)["session_id"]
        self.assertNotEqual(alice_session, bob_session)

        memory_service.save_memories({"name": "Alice"}, alice_session)
        memory_service.save_memories({"name": "Bob"}, bob_session)
        database_chat_history.add_message("user", "hi alice", alice_session)
        database_chat_history.add_message("user", "hi bob", bob_session)

        # Alice sees only her own data.
        self.assertEqual(memory_service.get_all_memories(alice_session), {"name": "Alice"})
        alice_msgs = database_chat_history.get_messages(alice_session)
        self.assertEqual(len(alice_msgs), 1)
        self.assertEqual(alice_msgs[0].content, "hi alice")

        # Bob sees only his own data.
        self.assertEqual(memory_service.get_all_memories(bob_session), {"name": "Bob"})
        bob_msgs = database_chat_history.get_messages(bob_session)
        self.assertEqual(len(bob_msgs), 1)
        self.assertEqual(bob_msgs[0].content, "hi bob")

        # Clearing one user's chat does not affect the other.
        database_chat_history.clear_messages(alice_session)
        self.assertEqual(len(database_chat_history.get_messages(alice_session)), 0)
        self.assertEqual(len(database_chat_history.get_messages(bob_session)), 1)


if __name__ == "__main__":
    unittest.main()
