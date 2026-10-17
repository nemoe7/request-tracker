"""Run the web shell: python -m pwedepa.web."""

import os

import uvicorn
from a2wsgi import WSGIMiddleware

from . import check_secret, create_app, print_first_token


def main() -> None:
  """Serve the app through uvicorn, in place of the Flask development server."""
  # A public host must not sign cookies with the sample secret.
  check_secret(
    os.environ.get("PWEDEPA_SECRET_KEY", "pwedepa-dev-secret"),
    os.environ.get("PWEDEPA_ORIGIN", "http://localhost:5000"),
  )
  app = create_app()
  # An empty database needs one admin, and the log is the one place an operator looks.
  print_first_token(app)
  # Flask answers as a WSGI app, and uvicorn speaks ASGI, so one adapter joins them.
  uvicorn.run(
    WSGIMiddleware(app),
    host=os.environ.get("PWEDEPA_HOST", "127.0.0.1"),
    port=int(os.environ.get("PWEDEPA_PORT", "5000")),
  )


if __name__ == "__main__":
  main()
