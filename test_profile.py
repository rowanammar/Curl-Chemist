import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from firestore_helpers import get_user_profile

profile = get_user_profile()
print(f"User Profile: {profile}")
