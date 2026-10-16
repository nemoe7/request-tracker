# Deploy PwedePa

Two containers run the site. `pwedepa-app` serves the app, and `pwedepa-tailscale` is the Tailscale node in front of it. `compose.yml` runs the published image, so a deploy needs no source checkout. SQLite lives on the named volume, so a restart keeps the data.

## Run it

1. Copy `.env.example` to `.env` and fill it in. Set the public name first, because passkeys bind to it and a later change strands enrolled passkeys.

   ```sh
   cp .env.example .env
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

   Put that secret in `PWEDEPA_SECRET_KEY`. Compose stops with an error when the value is missing, so no deploy signs cookies with the sample secret.

   `PWEDEPA_ORIGIN` also names the passkey. Set `PWEDEPA_RP_ID` only when that ID must differ from the origin host.

2. Pull the image and start the service.

   ```sh
   docker compose up -d
   ```

3. Create the first admin, then mint an enrollment token.

   ```sh
   docker compose exec pwedepa python -m pwedepa.auth create-admin \
     --database /data/pwedepa.db --username admin --display-name "Admin"
   ```

The app listens on `127.0.0.1:5000` on the host, and the sidecar reaches it at `http://pwedepa:5000` on the compose network.

## Local build

To run this checkout in a container, build it locally. This path starts the app alone, on the same port, on its own volume.

```sh
docker compose -f compose.dev.yml up -d --build
```

The dev file supplies a sample session secret, so a local build needs no `.env` file.

## Tailscale Funnel

The `tailscale` service joins your tailnet and serves the public HTTPS name with Funnel. It mounts `tailscale-funnel.json` at `/config` and reads that file as `TS_SERVE_CONFIG`. The config proxies the public name to `http://pwedepa:5000`.

1. Mint a reusable, untagged auth key in the Tailscale admin console, then put it in `.env` as `TS_AUTHKEY`. Compose stops with an error when the value is missing. The node then carries no tags, so your tailnet treats it as one of your own devices. The sidecar calls its node `pwedepa`, so the public name is `pwedepa.your-tailnet.ts.net`. Read your own tailnet name from `docker compose logs tailscale` after the first start, then set `PWEDEPA_ORIGIN` to that name.

2. Start both services, then read the Funnel status.

   ```sh
   docker compose up -d
   docker compose exec tailscale tailscale funnel status
   ```

3. Turn on HTTPS and Funnel for the node in the admin console when it asks.

If Tailscale runs on the host instead, the same config works. Change the Proxy value to `http://127.0.0.1:5000`, then run `tailscale serve --config tailscale-funnel.json`.

## Demo site

The `pages.yml` workflow publishes a frozen demo to GitHub Pages. It seeds a throwaway database from `scripts/demo_seed.py`, renders each page once with `scripts/build_pages_demo.py`, and deploys the static result. It runs on pushes to `main` that touch the web app or the seed, and on demand from the Actions tab.

Pages serves files only, so forms and passkey buttons stay inert in the frozen copy. The deployed site needs one repository setting: Settings, Pages, source **GitHub Actions**.

To run the preview demo on your own machine, ask for demo mode in code:

```sh
.venv/bin/python -c "from pwedepa.web import create_app; create_app({'DEMO_MODE': True, 'SESSION_COOKIE_SECURE': False}).run()"
```

## Notes

- The app image builds as `pwedepa`. The sidecar uses the upstream `tailscale/tailscale` image.
- Back up the `pwedepa-data` volume. It holds the only database copy.
- The `tailscale-state` volume holds the node identity, so a rebuild keeps the device. Restart the sidecar after you edit `tailscale-funnel.json`, because it reads the file at startup.
- The starter Domains come from `domains.json`. Keep it at the project root. The image copies it to `/app/domains.json`, and a missing file fails the demo seed with a clear error.
- Demo mode stays off in deployment. Code asks for it, and no environment variable sets it.
- The container workflow scans each image build for high and critical findings.
