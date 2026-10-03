import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# One session for the whole process so connections to the routing and
# geocoding hosts are kept alive between requests.
session = requests.Session()
session.headers["User-Agent"] = settings.GEOCODER_USER_AGENT
session.mount(
    "https://",
    HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.3, status_forcelist=[502, 503, 504])),
)
