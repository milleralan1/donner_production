import unittest
from unittest.mock import Mock
from uuid import uuid4

from reset_db import create_test_data


class ResetDatabaseTests(unittest.TestCase):
    def test_create_test_data_accepts_uuid_account_ids_from_cloud_sql(self):
        db = Mock()
        db.users.find_by_clerk_id.return_value = None
        db.accounts.find_by_user.return_value = []
        account_ids = [uuid4(), uuid4(), uuid4()]
        db.accounts.create_account.side_effect = account_ids
        db.positions.find_by_account.return_value = []

        create_test_data(db)

        self.assertEqual(
            [call.args[0] for call in db.positions.add_position.call_args_list],
            [str(account_ids[0])] * 5,
        )


if __name__ == "__main__":
    unittest.main()
