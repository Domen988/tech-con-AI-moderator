from app.services.avatar import avatar
import traceback

print('Attempting fetch_azure_relay_token()...')
try:
    data = avatar.fetch_azure_relay_token()
    print('SUCCESS:', data)
except Exception as e:
    print('EXCEPTION RAISED:')
    traceback.print_exc()
