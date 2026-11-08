# Deployment plan: The CSCL Bot on Azure Container Apps

**Status: deployed on 5 Nov 2026** at https://csclbot.bravemeadow-0908f7d2.eastus.azurecontainerapps.io (subscription "Azure subscription 1", resource group `rg-csclbot`, region eastus, scale to zero, one replica at most). Registry `acrcsclbotgs7k2`, storage account `stcsclbotgs7k2` (file share `state`), environment `cae-csclbot`, app `csclbot`. The image is built in the cloud and the country in the log comes from the bundled GeoLite2 database. The public address is **https://csclbot.gerrystahl.net** (bound 5 Nov 2026; free Azure-managed certificate, issued by DigiCert/GeoTrust, valid to May 2027 and renewed automatically as long as the DNS records stay). DNS at DreamHost:

| Type | Name | Value |
|---|---|---|
| CNAME | `csclbot` | `csclbot.bravemeadow-0908f7d2.eastus.azurecontainerapps.io` |
| TXT | `asuid.csclbot` | `F4608CE6E46A699A07B740A8E15831B22433972CA49E5350003F8D0D401DBB27` |

## What will run

One container, built in Azure from the [Dockerfile](../Dockerfile), serving the Gradio page over HTTPS:

- Python 3.12, CPU-only PyTorch, the `e5-base-v2` embedding model baked into the image (no download at run time).
- The search index (83 MB: 18,239 items, with the text of Gerry's book chunks and the short article summaries) and `references.json`. No article text, no PDFs.
- `ANTHROPIC_API_KEY` and the visitor-hash salt as Azure secrets, never in the image or the repo.
- A persistent Azure Files share mounted at `/mnt/state` for the usage log (`logs/usage.csv`) and the daily spend counter (`usage.json`), so they survive restarts and new versions.
- Exactly one replica at most: rate limits are kept in memory per process, and one writer keeps the CSV intact.

## Azure resources that would be created (one resource group, `rg-csclbot`)

| Resource | Purpose |
|---|---|
| Container Registry (Basic) | stores the built image; `az acr build` builds it in the cloud |
| Log Analytics workspace | platform and console logs |
| Container Apps environment + the container app | runs the page; public HTTPS address `https://csclbot.<random>.<region>.azurecontainerapps.io` |
| Storage account + file share `state` | usage log and spend counter |

Deleting everything later is one command: `az group delete -n rg-csclbot`.

## Decisions made (5 Nov 2026)

- Region **eastus**; **scale to zero** (`MIN_REPLICAS=0`); country from **MaxMind GeoLite2** (Gerry registers a free account and saves the database as `data/GeoLite2-Country.mmdb`).
- Still open: subscription, custom web address, and the backstop spending limit at Anthropic (items 1, 4 and 5 below).

## Decisions needed from Gerry

1. **Subscription and region.** I cannot see your Azure account. Install the Azure CLI (`brew install azure-cli`), run `az login`, and tell me which subscription to use. The draft assumes `eastus`.
2. **Scale to zero or always on.** Scale to zero costs almost nothing when nobody is using it, but the first visitor after an idle period waits about a minute while the model loads. Always on (`MIN_REPLICAS=1`) answers immediately but is billed all month.
3. **Country in the log.** Azure Container Apps does **not** add the visitor's country. Options: (a) a free MaxMind GeoLite2 Country database, which needs a free MaxMind account (recommended; the app already reads it from `data/GeoLite2-Country.mmdb`); (b) put Cloudflare or Azure Front Door in front, which can supply the country but adds cost and setup; (c) skip it, and the log says `unknown`.
4. **Web address.** The default Azure address is long. A custom address such as `csclbot.gerrystahl.net` is possible if you can add a DNS record for gerrystahl.net; Azure can issue the certificate. This can be added after the first deployment.
5. **Backstop spending limit at Anthropic.** In the Anthropic console, set a monthly spend limit on the key. The app's own $5/day cap is the first line of defence; this is the second.

## Where the usage log will be

The cloud app writes the Excel-readable log inside Azure, **not** into your project folder. `deploy/fetch_logs.sh` downloads `usage.csv` into `data/logs/` on your machine; then `src/usage_report.py` (or Excel) works as it does locally. You can run it whenever you want a fresh copy.

## Steps (after the decisions)

1. Install the Azure CLI and log in.
2. Optionally save the MaxMind database as `data/GeoLite2-Country.mmdb` (git-ignored; the image is private, as the MaxMind license requires).
3. Review `deploy/deploy.sh` and `deploy/containerapp.yaml` together with me.
4. Run `deploy/deploy.sh` with `SUBSCRIPTION`, `SUFFIX` and `ANTHROPIC_API_KEY` set. I run it step by step so any error can be fixed as it occurs.
5. Test the live address (a question, a blocked question, the notice, the log file), then put the URL into the paper.

## Rebuilding the index before an update

After changing the index (`src/build_index.py`, `src/build_keyword_index.py`), rebuild the image so that `data/index/` is copied in, then update the app as below.

## Updating, stopping, deleting

- **New version:** `az acr build -r <acr> -t csclbot:<tag> .`, then `az containerapp update -g rg-csclbot -n csclbot --image <acr>.azurecr.io/csclbot:<tag>`.
- **Emergency stop:** `az containerapp update -g rg-csclbot -n csclbot --min-replicas 0 --max-replicas 0` (or delete the key at Anthropic).
- **Delete everything:** `az group delete -n rg-csclbot`.

## Safeguards

- HTTPS only; secrets stored as Azure secrets; the container runs as a non-root user.
- Per visitor: 8 questions per hour and 30 per day; over-long questions refused.
- Daily spend cap ($5 by default, `CSCLBOT_DAILY_SPEND_CAP_USD`), kept on the persistent share so a restart does not reset it.
- The visitor's address is taken from the entry the Azure proxy appended to `X-Forwarded-For` (`CSCLBOT_PROXY_HOPS=1`), so a visitor cannot dodge the limit by forging the header. The address is stored only as a salted hash.

## Cost (to check, not a quote)

Container Apps bills per second of CPU and memory with monthly free allowances, and a container that is scaled to zero costs almost nothing. An always-on 1 vCPU / 2 GiB container will cost more, on the order of tens of dollars a month. The registry (Basic), the storage account and log ingestion add a few dollars a month at this scale. Please check the Azure pricing calculator for your region before deciding on always-on. The Anthropic cost is separate: about a cent per question at Haiku's rates.

## Verified on first deployment

- The cloud build works (3.5 minutes), including the optional MaxMind copy line. A live question was answered in about 6 seconds; the usage log and spend counter persist on the Azure share; the country was recorded.
- `deploy.sh` needed fixes on the first run: register the Container Registry and Storage providers, name the resource group when creating the share. `fetch_logs.sh` needed the storage key instead of OAuth.

## Not yet verified

- The Docker build itself (including the optional MaxMind copy line) and the `az` commands. They are written from memory and will be corrected on the first run.
- That the Azure Files mount options let the non-root user append to the CSV. If not, the container can run as root, or the mount options will be adjusted.
- Scale-to-zero resets the in-memory per-visitor counters (the spend counter persists).
- Cold-start time with the model baked in; a `minReplicas: 1` fallback is available.
