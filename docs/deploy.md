# Deploy PwedePa

One container serves the app. SQLite lives on the named volume in `compose.yml`, so a rebuild keeps the data.

## Run it

1. Set the public origin before the first start. Passkeys bind to it, and a later change strands enrolled passkeys.

   ```sh
   export PWEDEPA_RP_ID=your-host.example
   export PWEDEPA_ORIGIN=https://your-host.example
   ```

2. Build and start the service.

   ```sh
   docker compose up -d --build
   ```

3. Create the first admin, then mint an enrollment token.

   ```sh
   docker compose exec pwedepa python -m pwedepa.auth create-admin \
     --database /data/pwedepa.db --username admin --display-name "Admin"
   ```

The app listens on `127.0.0.1:5000` on the host. A reverse proxy or Tailscale Funnel terminates TLS in front of it.

## Tailscale Funnel

`tailscale-funnel.json` is a serve config template. It proxies the public HTTPS name to the app on port 5000.

1. Replace `${TS_CERT_DOMAIN}` with the device DNS name from `tailscale status`.
2. Set the config, then turn Funnel on.

   ```sh
   tailscale serve --config tailscale-funnel.json
   tailscale funnel status
   ```

3. Point `PWEDEPA_RP_ID` and `PWEDEPA_ORIGIN` at the same public name, then restart the service.

## Demo site

The `pages.yml` workflow publishes a frozen demo to GitHub Pages. It seeds a throwaway database from `scripts/demo_seed.py`, renders each page once with `scripts/build_pages_demo.py`, and deploys the static result. It runs on pushes to `main` that touch the web app or the seed, and on demand from the Actions tab.

Pages serves files only, so forms and passkey buttons stay inert in the frozen copy. The deployed site needs one repository setting: Settings, Pages, source **GitHub Actions**.

## Notes

- Back up the `pwedepa-data` volume. It holds the only database copy.
- The starter Domains come from `domains.json`. Keep it at the project root. The image copies it to `/app/domains.json`, and a missing file fails the demo seed with a clear error.
- Demo mode stays off in deployment. Code asks for it, and no environment variable sets it.
- The container workflow scans each image build for high and critical findings.
