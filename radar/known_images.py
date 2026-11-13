"""Curated fallback mapping from common self-hosted container images to GitHub repositories.

Used only when an inventory container has no repository label. The mapping is static and
versioned: it is never fetched from the network and never overrides an explicit user choice.
"""
from __future__ import annotations

KNOWN_IMAGES_VERSION = 1

# Keys are normalised image names (see normalise_image_name). LinuxServer.io images map to the
# upstream application because the application release is what needs tracking.
KNOWN_IMAGES: dict[str, str] = {
    "adguard/adguardhome": "AdguardTeam/AdGuardHome",
    "advplyr/audiobookshelf": "advplyr/audiobookshelf",
    "amir20/dozzle": "amir20/dozzle",
    "authelia/authelia": "authelia/authelia",
    "b4bz/homer": "bastienwirtz/homer",
    "binwiederhier/ntfy": "binwiederhier/ntfy",
    "caddy": "caddyserver/caddy",
    "cloudflare/cloudflared": "cloudflare/cloudflared",
    "containrrr/watchtower": "containrrr/watchtower",
    "crazymax/diun": "crazy-max/diun",
    "esphome/esphome": "esphome/esphome",
    "fallenbagel/jellyseerr": "Fallenbagel/jellyseerr",
    "filebrowser/filebrowser": "filebrowser/filebrowser",
    "fireflyiii/core": "firefly-iii/firefly-iii",
    "frooodle/s-pdf": "Stirling-Tools/Stirling-PDF",
    "getmeili/meilisearch": "meilisearch/meilisearch",
    "ghcr.io/actualbudget/actual-server": "actualbudget/actual",
    "ghcr.io/advplyr/audiobookshelf": "advplyr/audiobookshelf",
    "ghcr.io/authelia/authelia": "authelia/authelia",
    "ghcr.io/dani-garcia/vaultwarden": "dani-garcia/vaultwarden",
    "ghcr.io/fallenbagel/jellyseerr": "Fallenbagel/jellyseerr",
    "ghcr.io/gethomepage/homepage": "gethomepage/homepage",
    "ghcr.io/glanceapp/glance": "glanceapp/glance",
    "ghcr.io/goauthentik/server": "goauthentik/authentik",
    "ghcr.io/henrygd/beszel": "henrygd/beszel",
    "ghcr.io/home-assistant/home-assistant": "home-assistant/core",
    "ghcr.io/immich-app/immich-machine-learning": "immich-app/immich",
    "ghcr.io/immich-app/immich-server": "immich-app/immich",
    "ghcr.io/jellyfin/jellyfin": "jellyfin/jellyfin",
    "ghcr.io/koenkk/zigbee2mqtt": "Koenkk/zigbee2mqtt",
    "ghcr.io/linkwarden/linkwarden": "linkwarden/linkwarden",
    "ghcr.io/mealie-recipes/mealie": "mealie-recipes/mealie",
    "ghcr.io/open-webui/open-webui": "open-webui/open-webui",
    "ghcr.io/paperless-ngx/paperless-ngx": "paperless-ngx/paperless-ngx",
    "ghcr.io/qdm12/gluetun": "qdm12/gluetun",
    "ghcr.io/stirling-tools/stirling-pdf": "Stirling-Tools/Stirling-PDF",
    "ghcr.io/umami-software/umami": "umami-software/umami",
    "ghcr.io/wg-easy/wg-easy": "wg-easy/wg-easy",
    "gitea/gitea": "go-gitea/gitea",
    "gotify/server": "gotify/server",
    "grafana/alloy": "grafana/alloy",
    "grafana/grafana": "grafana/grafana",
    "grafana/grafana-oss": "grafana/grafana",
    "grafana/loki": "grafana/loki",
    "grafana/promtail": "grafana/loki",
    "henrygd/beszel": "henrygd/beszel",
    "homeassistant/home-assistant": "home-assistant/core",
    "jc21/nginx-proxy-manager": "NginxProxyManager/nginx-proxy-manager",
    "jellyfin/jellyfin": "jellyfin/jellyfin",
    "koenkk/zigbee2mqtt": "Koenkk/zigbee2mqtt",
    "lissy93/dashy": "Lissy93/dashy",
    "louislam/uptime-kuma": "louislam/uptime-kuma",
    "minio/minio": "minio/minio",
    "miniflux/miniflux": "miniflux/v2",
    "nextcloud": "nextcloud/server",
    "nginx": "nginx/nginx",
    "nodered/node-red": "node-red/node-red",
    "ollama/ollama": "ollama/ollama",
    "photoprism/photoprism": "photoprism/photoprism",
    "pihole/pihole": "pi-hole/docker-pi-hole",
    "portainer/portainer": "portainer/portainer",
    "portainer/portainer-ce": "portainer/portainer",
    "portainer/portainer-ee": "portainer/portainer",
    "prom/alertmanager": "prometheus/alertmanager",
    "prom/node-exporter": "prometheus/node_exporter",
    "prom/prometheus": "prometheus/prometheus",
    "qmcgaw/gluetun": "qdm12/gluetun",
    "redis": "redis/redis",
    "sctx/overseerr": "sct/overseerr",
    "syncthing/syncthing": "syncthing/syncthing",
    "tailscale/tailscale": "tailscale/tailscale",
    "traefik": "traefik/traefik",
    "vabene1111/recipes": "TandoorRecipes/recipes",
    "vaultwarden/server": "dani-garcia/vaultwarden",
    "vikunja/vikunja": "go-vikunja/vikunja",
    "linuxserver/bazarr": "morpheus65535/bazarr",
    "linuxserver/bookstack": "BookStackApp/BookStack",
    "linuxserver/calibre-web": "janeczku/calibre-web",
    "linuxserver/code-server": "coder/code-server",
    "linuxserver/duplicati": "duplicati/duplicati",
    "linuxserver/freshrss": "FreshRSS/FreshRSS",
    "linuxserver/grocy": "grocy/grocy",
    "linuxserver/heimdall": "linuxserver/Heimdall",
    "linuxserver/jellyfin": "jellyfin/jellyfin",
    "linuxserver/lidarr": "Lidarr/Lidarr",
    "linuxserver/librespeed": "librespeed/speedtest",
    "linuxserver/nextcloud": "nextcloud/server",
    "linuxserver/nzbget": "nzbgetcom/nzbget",
    "linuxserver/overseerr": "sct/overseerr",
    "linuxserver/prowlarr": "Prowlarr/Prowlarr",
    "linuxserver/qbittorrent": "qbittorrent/qBittorrent",
    "linuxserver/radarr": "Radarr/Radarr",
    "linuxserver/readarr": "Readarr/Readarr",
    "linuxserver/sabnzbd": "sabnzbd/sabnzbd",
    "linuxserver/sonarr": "Sonarr/Sonarr",
    "linuxserver/syncthing": "syncthing/syncthing",
    "linuxserver/tautulli": "Tautulli/Tautulli",
    "linuxserver/transmission": "transmission/transmission",
}

_DOCKER_HUB_HOSTS = ("docker.io/", "index.docker.io/", "registry-1.docker.io/")
_LINUXSERVER_HOSTS = ("lscr.io/linuxserver/", "ghcr.io/linuxserver/", "docker.io/linuxserver/")


def normalise_image_name(image: str | None) -> str:
    """Return a lower-case image name without registry defaults, tag or digest."""
    name = (image or "").strip().lower()
    name = name.split("@", 1)[0]
    last_slash = name.rfind("/")
    if ":" in name[last_slash + 1:]:
        name = name[: name.rfind(":")]
    for host in _LINUXSERVER_HOSTS:
        if name.startswith(host):
            return "linuxserver/" + name[len(host):]
    for host in _DOCKER_HUB_HOSTS:
        if name.startswith(host):
            name = name[len(host):]
            break
    return name.removeprefix("library/")


def known_repository(image: str | None) -> str | None:
    return KNOWN_IMAGES.get(normalise_image_name(image))


def suggest_repository(image: str | None, detected_repository: str | None) -> tuple[str, str] | None:
    """Return (repository, source) where source is 'image label' or 'known image'.

    A label pointing at a LinuxServer.io packaging repository is replaced by the known upstream
    application repository when one is curated, because that is where application releases live.
    """
    known = known_repository(image)
    label = (detected_repository or "").strip()
    if label and not (known and label.lower().startswith("linuxserver/docker-")):
        return label, "image label"
    if known:
        return known, "known image"
    return None
