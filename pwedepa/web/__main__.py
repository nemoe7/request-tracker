"""Run the web shell: python -m pwedepa.web."""

import os

from . import create_app

if __name__ == "__main__":
  create_app().run(
    host=os.environ.get("PWEDEPA_HOST", "127.0.0.1"),
    port=int(os.environ.get("PWEDEPA_PORT", "5000")),
  )
