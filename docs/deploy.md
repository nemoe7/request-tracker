# Deploy PwedePa

`compose.yml` runs two containers. `pwedepa-app` serves the app, and
`pwedepa-tailscale` is the Tailscale node in front of it. SQLite lives on the
`pwedepa-data` volume, so a restart keeps the data.

## Run it

1. Copy `.env.example` to `.env` and fill it in. Set `PWEDEPA_ORIGIN` first,
   because passkeys bind to it.

   ```sh
   cp .env.example .env
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

   Put that value in `PWEDEPA_SECRET_KEY`. Compose stops when the value is
   missing.

2. Start the service.

   ```sh
   docker compose up -d
   ```

3. Read the admin sign-up token in the log. When that line is gone, mint one.

   ```sh
   docker compose exec pwedepa python -m pwedepa.auth create-admin \
     --database /data/pwedepa.db
   ```

   The person who enrols picks their own username and display name.

The app listens on `127.0.0.1:5000` and reports health at `/health`. The sidecar
reaches the app at `http://pwedepa:5000` on the compose network.

## Local build

```sh
docker compose -f compose.dev.yml up -d --build
```

The dev compose file supplies a sample secret and a localhost origin, so it needs
no `.env`. The app reads `config.dev.yml` whole whenever that file sits beside
`config.yml`, and it seeds a demo request and a demo issue on a first start.

## Tailscale Funnel

1. Mint a reusable, untagged auth key in the admin console, then put it in
   `.env` as `TS_AUTHKEY`. The sidecar calls its node `pwedepa`, so the public
   name is `pwedepa.your-tailnet.ts.net`. Read your own name from
   `docker compose logs tailscale`, then set `PWEDEPA_ORIGIN` to it.

2. Start both services, then read the Funnel status.

   ```sh
   docker compose up -d
   docker compose exec tailscale tailscale funnel status
   ```

3. Turn on HTTPS and Funnel for the node in the admin console when it asks.

If Tailscale runs on the host instead, change the Proxy value in
`tailscale/serve.json` to `http://127.0.0.1:5000`, then run
`tailscale serve --config tailscale/serve.json`.

## Demo site

The `pages.yml` workflow freezes a demo to GitHub Pages on each push to `main`
that touches the web app, and on demand from the Actions tab. Pages serves files
only, so forms and passkey buttons stay inert there. The repository needs one
setting: Settings, Pages, source: GitHub Actions.

## Notes

- Back up the `pwedepa-data` volume. It holds the only database copy.
- The `tailscale-state` volume holds the node identity. Restart the sidecar
  after you edit `tailscale/serve.json`.
- `config.yml` at the project root is a template: every key waits, commented out.
  Uncomment the keys a deploy needs, or mount a real file read-only at
  `/app/config.yml`. A key in that file wins over the same environment variable,
  and no variable names a config file.
- The passkey library stays on 3.x. Read its changelog before a major bump.
- Demo mode stays off in deployment. Code asks for it, and no environment
  variable sets it.
