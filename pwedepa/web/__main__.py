"""Run the web shell: python -m pwedepa.web."""

import os

from . import check_secret, create_app

if __name__ == "__main__":
  # A public host must not sign cookies with the sample secret.
  check_secret(
    os.environ.get("PWEDEPA_SECRET_KEY", "pwedepa-dev-secret"),
    os.environ.get("PWEDEPA_ORIGIN", "http://localhost:5000"),
  )
  create_app().run(
    host=os.environ.get("PWEDEPA_HOST", "127.0.0.1"),
    port=int(os.environ.get("PWEDEPA_PORT", "5000")),
  )
